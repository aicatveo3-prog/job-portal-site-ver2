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


def _is_welfare_public_job(job: EnrichedJob) -> bool:
    """웹사이트 기본 필터(장애인일자리 OFF)와 동일한 판정."""
    import re
    t = job.title or ""
    emp = job.employment_type or ""
    if emp == "무기계약직" and re.search(r"교육공무직", t):
        return False
    if emp == "공공일자리":
        return True
    return bool(re.search(r"장애인\s*(?:일반형|복지|특화형|맞춤형)?\s*일자리\s*(?:지원)?(?:사업)?|행정도우미|권리중심", t))


def _is_part_time_job(job: EnrichedJob) -> bool:
    """웹사이트 기본 필터(전일제 주5일↑)와 동일한 단시간 판정."""
    import re
    if job.is_part_time:
        return True
    emp = job.employment_type or ""
    wh = job.work_hours or ""
    title = job.title or ""
    if emp == "시간제":
        return True
    if re.search(r"단시간|시간제|파트타임|격일|주\s*[1-4]일", wh):
        return True
    if re.search(r"일\s*[1-6](?:\.\d)?\s*시간|하루\s*[1-6](?:\.\d)?\s*시간", f"{wh} {title}"):
        return True
    m_wk = re.search(r"주\s*(\d{1,2})\s*시간", wh)
    if m_wk and int(m_wk.group(1)) <= 34:
        return True
    return False


def _matches_default_filter(job: EnrichedJob) -> bool:
    """웹사이트 기본 셋팅 필터와 100% 동일:
    - 생활권: 전체
    - 기관 구분: 공공·지자체 (공공기관, 지자체)
    - 접수 상태: 접수중
    - 근무 형태: 전일제 (주5일↑)
    - 장애 정도: 경증도 지원 가능 (중증만 가능 제외)
    - 계약 기간: 전체
    - 장애인일자리: OFF (제외)
    """
    if _is_closed_job(job):
        return False
    if _is_welfare_public_job(job):
        return False
    if (job.org_type or "민간기업") not in ("공공기관", "지자체"):
        return False
    if _is_part_time_job(job):
        return False
    if (job.disability_severity or "상세 확인") == "중증만 가능":
        return False
    return True


def build_briefing_text(jobs: List[EnrichedJob], new_count: int, briefing: Optional[dict] = None) -> str:
    today_str = datetime.now().strftime("%Y-%m-%d")
    matched_jobs = [j for j in jobs if _matches_default_filter(j)]
    new_matched = [j for j in matched_jobs if j.is_new]

    # 거리 가까운 순 정렬 (고양 → 인접 → 재택 → 수도권)
    new_matched.sort(key=lambda j: (j.distance_rank, j.deadline or "9999"))

    if not new_matched:
        lines = [
            f"[장애인 채용 브리핑 · {today_str}]",
            f"오늘 체크 완료! 맞춤 신규 0건 (접수중 {len(matched_jobs)}건 유지)",
            "기본 필터(공공·전일제·경증가능)에 맞는 신규 공고가 없습니다.",
        ]
        return "\n".join(lines)[:480]

    lines = [
        f"[장애인 채용 브리핑 · {today_str}]",
        f"맞춤 신규 {len(new_matched)}건 (공공·전일제·경증가능 · 접수중 {len(matched_jobs)}건)",
        "",
        "★ 신규 접수 공고",
    ]
    shown = new_matched[:5]
    for j in shown:
        z = (
            "고양"
            if j.distance_zone == "고양시 관내"
            else ("재택" if j.is_remote else "인접" if j.distance_zone == "인접 출퇴근" else "수도권")
        )
        lines.append(f"• [{z}/{j.org_type}] {j.company}")
        lines.append(f"  {j.title[:28]} (마감 {j.deadline})")

    remaining = len(new_matched) - len(shown)
    if remaining > 0:
        lines.append(f"... 외 맞춤 신규 {remaining}건 (사이트에서 확인)")

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
