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
    new_active = [j for j in active_jobs if j.is_new]

    # 신규 접수중 공고 정렬: 전일제·경증가능·일반채용 우선 → 거리 가까운 순 → 공공/지자체/대기업 우선
    org_priority = {"공공기관": 0, "지자체": 0, "대기업": 1, "외국계": 1, "표준사업장": 2}
    new_active.sort(
        key=lambda j: (
            1 if j.employment_type == "공공일자리" else 0,
            1 if j.disability_severity == "중증만 가능" else 0,
            1 if j.is_part_time else 0,
            j.distance_rank,
            org_priority.get(j.org_type, 3),
        )
    )

    if not new_active:
        lines = [
            f"[장애인 채용 브리핑 · {today_str}]",
            f"오늘 체크 완료! 신규 접수 0건 (접수중 {len(active_jobs)}건 유지)",
            "새로 올라온 접수중 공고가 없습니다.",
        ]
        return "\n".join(lines)[:480]

    lines = [
        f"[장애인 채용 브리핑 · {today_str}]",
        f"신규 접수 {len(new_active)}건 (전체 접수중 {len(active_jobs)}건)",
        "",
        "★ 신규 접수 공고",
    ]
    shown = new_active[:5]
    for j in shown:
        z = (
            "고양"
            if j.distance_zone == "고양시 관내"
            else ("재택" if j.is_remote else "인접" if j.distance_zone == "인접 출퇴근" else "수도권")
        )
        lines.append(f"• [{z}/{j.org_type}] {j.company}")
        lines.append(f"  {j.title[:28]} (마감 {j.deadline})")

    remaining = len(new_active) - len(shown)
    if remaining > 0:
        lines.append(f"... 외 신규 {remaining}건 (사이트에서 확인)")

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
