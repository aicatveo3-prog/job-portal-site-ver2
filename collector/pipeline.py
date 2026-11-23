from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import config
from collector.ai_enricher import enrich_jobs
from collector.base import EnrichedJob, RawJob, is_excluded_role
from collector.dedupe import dedupe_and_sort
from collector.sources import ALL_SOURCES
from notifier.kakao import send_kakao_briefing
from notifier.messengers import send_discord, send_telegram
from notifier.windows_toast import send_toast


def _load_state() -> dict:
    if config.STATE_JSON_PATH.exists():
        try:
            return json.loads(config.STATE_JSON_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_state(state: dict) -> None:
    config.STATE_JSON_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _load_prev_jobs() -> List[EnrichedJob]:
    if not config.JOBS_JSON_PATH.exists():
        return []
    try:
        data = json.loads(config.JOBS_JSON_PATH.read_text(encoding="utf-8"))
        out: List[EnrichedJob] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            hay = f"{item.get('duties', '')} {' '.join(item.get('easy_summary', []))}"
            if is_excluded_role(item.get("title", ""), hay):
                continue
            out.append(EnrichedJob(**item))
        return out
    except Exception:
        return []


def _wait_for_internet(max_wait_sec: int = 60, log_fn=print) -> bool:
    """PC 부팅 직후 와이파이/네트워크 지연 대비, 최대 60초까지 인터넷 연결 대기."""
    deadline = time.time() + max_wait_sec
    checked = 0
    while time.time() <= deadline:
        for host, port in (("1.1.1.1", 443), ("www.work24.go.kr", 443), ("github.com", 443)):
            try:
                with socket.create_connection((host, port), timeout=3):
                    if checked > 0:
                        log_fn(f"[네트워크] 인터넷 연결 확인됨 ({checked * 3}초 대기)")
                    return True
            except OSError:
                continue
        checked += 1
        time.sleep(3)
    log_fn("[네트워크] 60초 동안 인터넷 연결을 확인하지 못해 이번 실행을 건너뜁니다. (다음 기회에 자동 재시도)")
    return False


def _acquire_lock() -> bool:
    if config.LOCK_FILE_PATH.exists():
        try:
            age = time.time() - config.LOCK_FILE_PATH.stat().st_mtime
            if age < 3600:
                return False
        except Exception:
            pass
    try:
        config.LOCK_FILE_PATH.write_text(str(os.getpid()), encoding="utf-8")
        return True
    except Exception:
        return True


def _release_lock() -> None:
    try:
        config.LOCK_FILE_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def _auto_git_push(log_fn, total: int, new_count: int) -> bool:
    if not config.AUTO_GIT_PUSH:
        return False
    if not (config.ROOT_DIR / ".git").exists():
        log_fn("[GIT] .git 폴더가 없어 자동 푸시를 건너뜁니다.")
        return False
    try:
        cwd = str(config.ROOT_DIR)
        subprocess.run(["git", "add", "docs/data/jobs.json", "docs/data/meta.json", "docs/data/bundle.js"], cwd=cwd, check=True)
        diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=cwd)
        if diff.returncode == 0:
            log_fn("[GIT] 변경된 공고 데이터가 없어 커밋 생략")
            return True
        today = datetime.now().strftime("%Y-%m-%d")
        msg = f"data: {today} 장애인 채용공고 업데이트 (총 {total}건, 신규 {new_count}건)"
        subprocess.run(["git", "commit", "-m", msg], cwd=cwd, check=True)
        subprocess.run(["git", "push"], cwd=cwd, check=True)
        log_fn("[GIT] GitHub 자동 푸시 완료!")
        return True
    except Exception as e:
        log_fn(f"[GIT] 자동 푸시 실패: {e}")
        return False


def run_pipeline(
    force: bool = False,
    use_ai: Optional[bool] = None,
    limit_per_source: Optional[int] = None,
    only_sources: Optional[List[str]] = None,
    notify: bool = True,
) -> dict:
    today_str = datetime.now().strftime("%Y-%m-%d")
    log_path = config.LOGS_DIR / f"run_{today_str}.log"

    def log(msg: str) -> None:
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
        print(line, flush=True)
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    state = _load_state()
    if not force and state.get("last_run_date") == today_str:
        log(f"오늘({today_str}) 이미 수집을 완료하여 조용히 종료합니다. (강제 실행은 --force)")
        return {"skipped": True, "reason": "already_ran_today"}

    if not _acquire_lock():
        log("이미 다른 수집 프로세스가 실행 중이어서 종료합니다.")
        return {"skipped": True, "reason": "already_running"}

    started_at = datetime.now()
    ai_enabled = config.ENABLE_AI if use_ai is None else use_ai
    limit = limit_per_source or config.MAX_PER_SOURCE

    try:
        if not _wait_for_internet(max_wait_sec=60, log_fn=log):
            return {"skipped": True, "reason": "no_internet"}

        if notify:
            send_toast(
                "장애인 채용공고 수집 시작",
                "고양시·서울·경기·재택 공고를 백그라운드에서 수집·정리하고 있습니다.",
            )

        log(f"=== 수집 파이프라인 시작 (AI={ai_enabled}, 모델={config.OPENCODE_MODEL}, 사이트당 최대={limit}건) ===")
        all_raw: List[RawJob] = []
        source_reports: List[dict] = []

        selected = [
            s for s in ALL_SOURCES if not only_sources or s[0] in only_sources
        ]

        for source_id, source_name, fn in selected:
            t0 = time.time()
            try:
                raw_items = fn(limit=limit)
                items = [r for r in raw_items if not is_excluded_role(r.title)]
                excluded_cnt = len(raw_items) - len(items)
                elapsed = round(time.time() - t0, 1)
                all_raw.extend(items)
                source_reports.append(
                    {
                        "id": source_id,
                        "name": source_name,
                        "status": "ok",
                        "count": len(items),
                        "elapsed_sec": elapsed,
                        "error": "",
                    }
                )
                excl_note = f" (미화/요양 등 {excluded_cnt}건 제외)" if excluded_cnt else ""
                log(f"  ✅ {source_name} ({source_id}): {len(items)}건 수집{excl_note} ({elapsed}s)")
            except Exception as e:
                elapsed = round(time.time() - t0, 1)
                source_reports.append(
                    {
                        "id": source_id,
                        "name": source_name,
                        "status": "error",
                        "count": 0,
                        "elapsed_sec": elapsed,
                        "error": str(e)[:200],
                    }
                )
                log(f"  ⚠️ {source_name} ({source_id}) 오류: {e}")

        log(f"총 원본 수집: {len(all_raw)}건 → 정제 시작...")
        enriched, ai_stats = enrich_jobs(
            all_raw,
            use_ai=ai_enabled,
            batch_size=config.AI_BATCH_SIZE,
            log_fn=log,
        )

        # AI가 추출한 직무(duties)가 미화/청소/요양보호사/네일/조리사인 경우도 최종 제외
        enriched = [
            j for j in enriched
            if not is_excluded_role(j.title, f"{j.duties} {' '.join(j.easy_summary)}")
        ]

        prev_jobs = _load_prev_jobs()
        prev_ids = {j.id for j in prev_jobs}
        # 기존 수집 공고(지난 3개월 내 마감 포함)와 신규 수집 공고를 합쳐 중복 병합
        final_jobs: List[EnrichedJob] = dedupe_and_sort(enriched + prev_jobs, prev_ids)
        new_count = sum(1 for j in final_jobs if j.is_new)

        # 통계 계산 (부분 실행 시에도 8개 전체 출처 현황 유지)
        zone_counts: dict[str, int] = {}
        org_counts: dict[str, int] = {}
        final_src_counts: dict[str, int] = {}
        for j in final_jobs:
            zone_counts[j.distance_zone] = zone_counts.get(j.distance_zone, 0) + 1
            org_counts[j.org_type] = org_counts.get(j.org_type, 0) + 1
            for sid in j.source_ids:
                final_src_counts[sid] = final_src_counts.get(sid, 0) + 1

        report_by_id = {r["id"]: r for r in source_reports}
        full_source_reports: List[dict] = []
        for sid, sname, _ in ALL_SOURCES:
            if sid in report_by_id:
                rec = dict(report_by_id[sid])
                rec["count"] = final_src_counts.get(sid, rec["count"])
                full_source_reports.append(rec)
            else:
                full_source_reports.append(
                    {
                        "id": sid,
                        "name": sname,
                        "status": "ok",
                        "count": final_src_counts.get(sid, 0),
                        "elapsed_sec": 0.0,
                        "error": "",
                    }
                )

        meta = {
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "updated_date": today_str,
            "duration_sec": round((datetime.now() - started_at).total_seconds(), 1),
            "model": config.OPENCODE_MODEL if ai_enabled else "규칙기반(AI미사용)",
            "total_jobs": len(final_jobs),
            "new_jobs": new_count,
            "goyang_count": zone_counts.get("고양시 관내", 0),
            "nearby_count": zone_counts.get("인접 출퇴근", 0),
            "remote_count": sum(1 for j in final_jobs if j.is_remote),
            "attachments_read_count": sum(1 for j in final_jobs if j.attachment_read),
            "zone_counts": zone_counts,
            "org_counts": org_counts,
            "ai_stats": ai_stats,
            "sources": full_source_reports,
        }

        # Atomic-ish save to docs/data/
        jobs_payload = [j.model_dump() for j in final_jobs]
        jobs_json_str = json.dumps(jobs_payload, ensure_ascii=False, indent=2)
        meta_json_str = json.dumps(meta, ensure_ascii=False, indent=2)

        tmp_jobs = config.JOBS_JSON_PATH.with_suffix(".json.tmp")
        tmp_jobs.write_text(jobs_json_str, encoding="utf-8")
        tmp_jobs.replace(config.JOBS_JSON_PATH)

        tmp_meta = config.META_JSON_PATH.with_suffix(".json.tmp")
        tmp_meta.write_text(meta_json_str, encoding="utf-8")
        tmp_meta.replace(config.META_JSON_PATH)

        # 로컬 file:// 더블클릭 실행에서도 CORS 없이 바로 열리도록 bundle.js 동시 생성
        bundle_path = config.DATA_DIR / "bundle.js"
        tmp_bundle = bundle_path.with_suffix(".js.tmp")
        tmp_bundle.write_text(
            f"window.__JOBS_DATA__ = {jobs_json_str};\nwindow.__META_DATA__ = {meta_json_str};\n",
            encoding="utf-8",
        )
        tmp_bundle.replace(bundle_path)

        # 성공 시 오늘 날짜 기록 (하루 1회 가드)
        ok_sources = sum(1 for s in source_reports if s["status"] == "ok")
        if ok_sources > 0 and len(final_jobs) > 0:
            state["last_run_date"] = today_str
            state["last_run_at"] = meta["updated_at"]
            state["last_total"] = len(final_jobs)
            _save_state(state)

        log(
            f"=== 완료! 총 {len(final_jobs)}건 (신규 {new_count}건 | "
            f"고양시 {meta['goyang_count']} · 인접 {meta['nearby_count']} · 재택 {meta['remote_count']}) ==="
        )

        # 선택: GitHub 자동 푸시
        pushed = _auto_git_push(log, len(final_jobs), new_count)

        # 알림 전송
        if notify:
            err_sources = len(source_reports) - ok_sources
            toast_msg = (
                f"총 {len(final_jobs)}건 (신규 {new_count}건) · "
                f"고양 {meta['goyang_count']} · 인접 {meta['nearby_count']} · 재택 {meta['remote_count']}"
            )
            if pushed:
                toast_msg += " · 사이트 자동 업데이트 완료"
            if err_sources > 0:
                toast_msg += f" (일부 {err_sources}곳 오류)"
            send_toast("장애인 채용공고 수집 완료", toast_msg)

            ok_k, msg_k = send_kakao_briefing(final_jobs, new_count)
            log(f"[알림-카톡] {msg_k}")
            if send_discord(final_jobs, new_count):
                log("[알림-디스코드] 전송 완료")
            if send_telegram(final_jobs, new_count):
                log("[알림-텔레그램] 전송 완료")

        return meta
    finally:
        _release_lock()
