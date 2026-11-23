from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional
import httpx

import config
from collector.base import EnrichedJob

TOKEN_URL = "https://kauth.kakao.com/oauth/token"
SEND_ME_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"


def _load_tokens() -> Optional[dict]:
    if not config.KAKAO_TOKEN_PATH.exists():
        return None
    try:
        return json.loads(config.KAKAO_TOKEN_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_tokens(tokens: dict) -> None:
    config.KAKAO_TOKEN_PATH.write_text(
        json.dumps(tokens, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def refresh_access_token(tokens: dict) -> Optional[dict]:
    """refresh_token으로 access_token 자동 갱신 (카카오가 새 refresh_token 주면 자동 교체 저장)."""
    rest_key = config.KAKAO_REST_API_KEY or tokens.get("rest_api_key", "")
    refresh_tok = tokens.get("refresh_token", "")
    if not rest_key or not refresh_tok:
        return None

    data = {
        "grant_type": "refresh_token",
        "client_id": rest_key,
        "refresh_token": refresh_tok,
    }
    secret = config.KAKAO_CLIENT_SECRET or tokens.get("client_secret", "")
    if secret:
        data["client_secret"] = secret

    try:
        r = httpx.post(TOKEN_URL, data=data, timeout=15.0)
        if r.status_code != 200:
            return None
        res = r.json()
        updated = dict(tokens)
        updated["access_token"] = res["access_token"]
        if res.get("refresh_token"):
            updated["refresh_token"] = res["refresh_token"]
        updated["updated_at"] = datetime.now().isoformat()
        _save_tokens(updated)
        return updated
    except Exception:
        return None


def _is_closed_job(job: EnrichedJob) -> bool:
    import re
    from datetime import date
    if job.is_closed_in_text:
        return True
    dl = (job.deadline or "").strip()
    m = re.match(r"^(20\d{2})-(\d{2})-(\d{2})$", dl)
    if not m:
        return False
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3))) < date.today()
    except ValueError:
        return False


def build_briefing_text(jobs: List[EnrichedJob], new_count: int, briefing: Optional[dict] = None) -> str:
    today_str = datetime.now().strftime("%Y-%m-%d")
    active_jobs = [j for j in jobs if not _is_closed_job(j)]
    goyang = [j for j in active_jobs if j.distance_zone == "고양시 관내"]
    nearby = [j for j in active_jobs if j.distance_zone == "인접 출퇴근"]
    remote = [j for j in active_jobs if j.is_remote]

    lines = [
        f"[장애인 채용 브리핑 · {today_str}]",
        f"접수중 {len(active_jobs)}건 (신규 {new_count}건)",
        f"고양 {len(goyang)}건 / 인접 {len(nearby)}건 / 재택 {len(remote)}건",
        "",
    ]

    # 접수중 + 전일제 + 경증 지원 가능 + 공공/지자체/대기업 우선 선별 (마감 공고 제외!)
    eligible = [
        j for j in active_jobs
        if not j.is_part_time
        and j.disability_severity != "중증만 가능"
        and j.employment_type != "공공일자리"
    ]
    highlights = [j for j in eligible if j.is_new and j.distance_rank <= 3][:4]
    if len(highlights) < 4:
        for j in eligible:
            if j not in highlights and j.org_type in ("공공기관", "지자체", "대기업", "외국계"):
                highlights.append(j)
            if len(highlights) >= 4:
                break
    if not highlights:
        highlights = active_jobs[:4]

    if highlights:
        lines.append("★ 주요 접수중 공고")
        for j in highlights[:4]:
            z = "고양" if j.distance_zone == "고양시 관내" else ("재택" if j.is_remote else "인접" if j.distance_zone == "인접 출퇴근" else "수도권")
            lines.append(f"• [{z}/{j.org_type}] {j.company}")
            lines.append(f"  {j.title[:26]} (마감 {j.deadline})")

    text = "\n".join(lines)
    return text[:480]


def send_kakao_briefing(jobs: List[EnrichedJob], new_count: int, briefing: Optional[dict] = None) -> tuple[bool, str]:
    tokens = _load_tokens()
    if not tokens:
        return False, "카카오 토큰 미설정 (scripts/setup_kakao.py 미실행)"

    refreshed = refresh_access_token(tokens)
    if refreshed:
        tokens = refreshed

    access_token = tokens.get("access_token")
    if not access_token:
        return False, "카카오 access_token 없음"

    site_url = config.SITE_PUBLIC_URL or "http://localhost:8080"
    template_obj = {
        "object_type": "text",
        "text": build_briefing_text(jobs, new_count, briefing=briefing),
        "link": {
            "web_url": site_url,
            "mobile_web_url": site_url,
        },
        "button_title": "전체 공고 보러가기",
    }

    try:
        r = httpx.post(
            SEND_ME_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            data={"template_object": json.dumps(template_obj, ensure_ascii=False)},
            timeout=15.0,
        )
        if r.status_code == 200:
            return True, "카카오톡 나에게 보내기 전송 성공"
        return False, f"카카오 API 응답 오류 ({r.status_code}): {r.text[:150]}"
    except Exception as e:
        return False, f"카카오 전송 예외: {e}"
