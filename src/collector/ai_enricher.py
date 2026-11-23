from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import config
from collector.base import (
    EnrichedJob,
    RawJob,
    classify_distance_zone,
    clean_text,
    normalize_deadline,
    parse_monthly_salary_krw,
    stable_hash,
)

ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _load_cache() -> Dict[str, dict]:
    if config.AI_CACHE_PATH.exists():
        try:
            return json.loads(config.AI_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(cache: Dict[str, dict]) -> None:
    try:
        config.AI_CACHE_PATH.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def _infer_org_type(company: str, title: str, text: str, source_id: str) -> str:
    combined = f"{company} {title} {text[:800]}"
    if source_id == "alio" or any(
        k in combined for k in ("공사", "공단", "연구원", "진흥원", "공공기관", "재단법인", "산하기관", "국립", "한국철도", "한국전력")
    ):
        return "공공기관"
    if any(k in combined for k in ("시청", "구청", "군청", "도청", "행정복지센터", "고양특례시", "서울특별시", "경기도청", "교육청", "공무직", "자치구")):
        return "지자체"
    if any(k in combined for k in ("자회사형", "표준사업장")):
        return "표준사업장"
    if any(k in combined for k in ("외국계", "글로벌", "Amcor", "코리아", "Korea", "유한회사")):
        return "외국계"
    if any(
        k in combined
        for k in ("삼성", "LG", "SK", "현대", "롯데", "신세계", "CJ", "씨제이", "카카오", "네이버", "쿠팡", "한화", "포스코", "KT", "KB", "신한", "하나은행", "우리은행", "증권", "대기업")
    ):
        return "대기업"
    if any(k in combined for k in ("복지관", "복지센터", "사회복지", "사단법인", "(사)", "장애인협회", "비영리", "어린이집", "요양원")):
        return "복지·비영리"
    return "민간기업"


def _infer_work_hours(text: str) -> Tuple[str, bool]:
    t = text[:2000]
    # 구체적 시간 패턴 추출
    m_time = re.search(r"(\d{1,2}:\d{2}\s*[~\-]\s*\d{1,2}:\d{2})", t)
    m_day = re.search(r"(주\s*[1-6]일)", t)
    m_hr = re.search(r"(?:일|1일|하루)\s*(\d(?:\.\d)?)\s*시간", t)
    m_whr = re.search(r"주\s*(\d{1,2})\s*시간", t)

    parts = []
    if m_day:
        parts.append(m_day.group(1).replace(" ", ""))
    if m_hr:
        parts.append(f"일 {m_hr.group(1)}시간")
    elif m_whr:
        parts.append(f"주 {m_whr.group(1)}시간")
    if m_time:
        parts.append(m_time.group(1).replace(" ", ""))

    is_part = False
    if m_hr and float(m_hr.group(1)) <= 6.5:
        is_part = True
    elif m_whr and int(m_whr.group(1)) <= 32:
        is_part = True
    elif any(k in t for k in ("단시간", "시간제", "파트타임", "일 4시간", "일4시간", "일 5시간", "오전근무", "오후근무")):
        is_part = True

    if parts:
        label = " · ".join(parts)
        if is_part and "단시간" not in label:
            label += " (단시간)"
        return label, is_part
    if is_part:
        return "단시간/시간제 (상세 참고)", True
    return "상세공고 참고", False


def _infer_employment_type(emp_raw: str, title: str, text: str) -> str:
    combined = f"{emp_raw} {title} {text[:1000]}"
    if any(k in combined for k in ("장애인일자리사업", "복지일자리", "행정도우미", "공공일자리")):
        return "공공일자리"
    if "정규직" in combined and "비정규직" not in combined:
        return "정규직"
    if "무기계약" in combined or "공무직" in combined:
        return "무기계약직"
    if "인턴" in combined:
        return "인턴"
    if any(k in combined for k in ("시간제", "단시간", "아르바이트", "파트")):
        return "시간제"
    if any(k in combined for k in ("계약직", "기간제", "비정규직", "대체인력")):
        return "계약직"
    return emp_raw[:15] if emp_raw else "상세 참고"


def _infer_residency_restriction(title: str, text: str) -> str:
    combined = f"{title}\n{text[:1800]}"
    # 서울시/자치구 거주자 한정 등 감지
    m = re.search(r"(서울(?:특별시|시)?|[가-힣]{2,4}(?:구|시))\s*(?:주민등록\s*)?(?:거주자|주민)\s*(?:한정|만|대상|필수)", combined)
    if m:
        region = m.group(1)
        if "고양" not in region and "경기" not in region:
            return f"{region} 거주자 제한 가능 (원문 확인)"
    if "서울시 거주" in combined or "서울특별시 거주" in combined:
        return "서울시 거주자 제한 가능 (원문 확인)"
    return ""


def _infer_disability_type(title: str, emp_raw: str, text: str, source_id: str) -> str:
    combined = f"{title} {emp_raw} {text[:1000]}"
    if "제한경쟁" in combined:
        return "공공 제한경쟁"
    if "장애인만 채용" in combined or "장애인 전형" in combined or "장애인전형" in combined or "장애인 전용" in combined:
        return "장애인만 채용"
    if "병행채용" in combined:
        return "병행채용"
    if "우대" in combined:
        return "장애인 우대"
    if source_id in ("kead", "jobcnt", "modoojob"):
        return "장애인 채용"
    return "장애인 채용"


def _infer_disability_severity(title: str, text: str) -> str:
    combined = f"{title} {text[:1800]}"
    if any(k in combined for k in ("중증장애인만", "중증 장애인만", "중증만", "장애의 정도가 심한 장애인만", "장애 정도가 심한 장애인 대상", "심한 장애인 한정", "중증장애인 전용", "중증장애인 채용")):
        return "중증만 가능"
    if any(k in combined for k in ("경증장애인만", "경증만", "장애의 정도가 심하지 않은 장애인만", "경증 한정")):
        return "경증만 가능"
    if any(k in combined for k in ("중증 우대", "중증장애인 우대", "심한 장애인 우대")):
        return "중증 우대"
    if any(k in combined for k in ("경증·중증 무관", "중증·경증 무관", "장애정도 무관", "장애 정도 무관", "경중 무관", "중증/경증 무관", "등록장애인", "장애인복지카드")):
        return "중증·경증 무관"
    return "상세 확인"


def _infer_contract_period(emp_type: str, title: str, text: str) -> Tuple[str, str]:
    combined = f"{emp_type} {title} {text[:1800]}"
    if any(k in combined for k in ("기간의 정함이 없는", "정규직", "무기계약")) and not re.search(r"계약기간\s*[:：]?\s*\d+\s*개월", combined):
        return "정규직 (기간 제한 없음)", "정규·무기계약"
    m_mon = re.search(r"(?:계약기간|근무기간|임용기간|기간제)[^\n]{0,18}?(\d{1,2})\s*개월", combined)
    if m_mon:
        months = int(m_mon.group(1))
        extra = " (정규직 전환 검토)" if "전환" in combined else ""
        cat = "1년 이상" if months >= 12 else ("6개월~1년" if months >= 6 else "6개월 미만")
        return f"{months}개월{extra}", cat
    m_yr = re.search(r"(?:계약기간|근무기간|임용기간)[^\n]{0,18}?(\d)\s*년", combined)
    if m_yr:
        yrs = int(m_yr.group(1))
        return f"{yrs}년 계약", "1년 이상"
    if "장애인일자리사업" in combined or "공공일자리" in combined:
        return "1년 단위 사업 (1~12월)", "1년 이상"
    if emp_type in ("정규직", "무기계약직"):
        return f"{emp_type} (기간 제한 없음)", "정규·무기계약"
    return "상세 참고", "상세 참고"


def _infer_application_start(text: str) -> str:
    m = re.search(
        r"(?:접수기간|모집기간|지원기간|신청기간)[^\n]{0,20}?(20\d{2}[.\-/]\d{1,2}[.\-/]\d{1,2})\s*[~\-]",
        text[:1600],
    )
    if m:
        return normalize_deadline(m.group(1))
    return ""


def _infer_is_closed(deadline_raw: str, text: str) -> bool:
    if any(k in (deadline_raw or "") for k in ("마감됨", "접수마감", "채용마감", "종료")):
        return True
    if any(k in text[:500] for k in ("마감된 공고", "접수가 마감", "채용이 마감")):
        return True
    return False


def rule_based_enrich(raw: RawJob, collected_at: str) -> EnrichedJob:
    """OpenCode AI 실패/미사용 시에도 깔끔하게 동작하는 안전 폴백 정제기."""
    text = raw.raw_text or ""
    company = raw.company.strip() or "기관/기업 (원문 확인)"
    title = raw.title.strip() or "제목 없음"

    location = raw.location_raw.strip()
    if not location:
        m = re.search(r"(?:경기도|서울특별시|서울|경기)\s+[가-힣]+(?:시|구|군)", text[:1200])
        location = m.group(0) if m else "상세 참고"

    zone, rank, is_remote = classify_distance_zone(location, f"{title} {text}")
    org_type = _infer_org_type(company, title, text, raw.source_id)

    salary_text = raw.salary_raw.strip()
    if not salary_text:
        m_sal = re.search(
            r"(?:월급|시급|연봉|일급|보수)\s*[:：]?\s*[\d,\.~]+\s*(?:만원|원)(?:\s*~\s*[\d,\.]+\s*(?:만원|원))?",
            text[:1800],
        )
        salary_text = m_sal.group(0) if m_sal else "회사내규 / 상세 참고"

    salary_monthly = parse_monthly_salary_krw(salary_text)
    work_hours, is_part_time = _infer_work_hours(f"{title} {text}")
    emp_type = _infer_employment_type(raw.employment_raw, title, text)
    contract_period, contract_category = _infer_contract_period(emp_type, title, text)
    disability_type = _infer_disability_type(title, raw.employment_raw, text, raw.source_id)
    disability_severity = _infer_disability_severity(title, text)
    residency = _infer_residency_restriction(title, text)
    app_start = _infer_application_start(text)
    is_closed = _infer_is_closed(raw.deadline_raw, text)
    deadline = normalize_deadline(raw.deadline_raw)
    if deadline == "채용시까지":
        m_dl = re.search(r"(?:마감일|접수기간|모집기간)[^\n]{0,35}?(?:~\s*)?(20\d{2}[.\-/]\d{1,2}[.\-/]\d{1,2})", text[:1500])
        if m_dl:
            deadline = normalize_deadline(m_dl.group(1))

    tags: List[str] = []
    if zone == "고양시 관내":
        tags.append("#고양시")
    if is_remote:
        tags.append("#재택가능")
    if is_part_time:
        tags.append("#단시간")
    if org_type in ("공공기관", "지자체"):
        tags.append(f"#{org_type}")
    elif org_type in ("대기업", "외국계", "표준사업장"):
        tags.append(f"#{org_type}")
    if disability_type in ("장애인만 채용", "공공 제한경쟁"):
        tags.append(f"#{disability_type.replace(' ', '')}")
    if any(k in f"{title} {text[:1200]}" for k in ("경력무관", "신입", "초보")):
        tags.append("#초보가능")
    if residency:
        tags.append("#거주지제한확인")

    summary = [
        f"[{org_type}] {company}에서 '{title[:45]}' 채용을 진행합니다.",
        f"근무지: {location} ({zone}) / 근무시간: {work_hours}",
        f"급여: {salary_text} / 계약: {contract_period} / 마감: {deadline}",
    ]

    job_id = raw.wanted_auth_no or f"{raw.source_id}_{stable_hash(raw.external_id or raw.url)}"
    return EnrichedJob(
        id=job_id,
        sources=[raw.source_name],
        source_ids=[raw.source_id],
        url=raw.url,
        title=title,
        company=company,
        org_type=org_type,
        location=location,
        distance_zone=zone,
        distance_rank=rank,
        salary_text=salary_text,
        salary_monthly_krw=salary_monthly,
        work_hours=work_hours,
        is_part_time=is_part_time,
        is_remote=is_remote,
        employment_type=emp_type,
        contract_period=contract_period,
        contract_category=contract_category,
        disability_type=disability_type,
        disability_severity=disability_severity,
        residency_restriction=residency,
        duties=clean_text(text[:280]) if text else title,
        qualifications="상세 원문 참고",
        apply_method="원문 공고 링크에서 지원",
        easy_summary=summary,
        tags=list(dict.fromkeys(tags))[:6],
        application_start=app_start,
        deadline=deadline,
        is_closed_in_text=is_closed,
        posted_date=raw.posted_raw,
        collected_at=collected_at,
        ai_processed=False,
        attachments=raw.attachments,
        attachment_read=raw.attachment_read,
        raw_excerpt=clean_text(text)[:2600],
    )


def _find_opencode_bin() -> Optional[str]:
    # Windows에서 opencode.cmd는 cmd.exe 인자 이스케이프/줄바꿈 문제를 일으키므로 네이티브 opencode.exe를 최우선 사용
    native_exe = Path.home() / "AppData" / "Roaming" / "npm" / "node_modules" / "opencode-ai" / "bin" / "opencode.exe"
    if native_exe.exists():
        return str(native_exe)
    for cand in ("opencode.exe", "opencode", "opencode.cmd"):
        found = shutil.which(cand)
        if found:
            return found
    return None


def _extract_json_array(stdout: str) -> Optional[list]:
    cleaned = ANSI_RE.sub("", stdout or "").strip()
    # Try fenced json block first
    m = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", cleaned)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # Find outermost [ ... ]
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start != -1 and end > start:
        candidate = cleaned[start : end + 1]
        try:
            return json.loads(candidate)
        except Exception:
            pass
    return None


def _call_opencode_batch(batch: List[RawJob]) -> Optional[List[dict]]:
    opencode_bin = _find_opencode_bin()
    if not opencode_bin:
        return None

    payload = []
    for idx, r in enumerate(batch):
        payload.append(
            {
                "idx": idx,
                "source": r.source_name,
                "title_hint": r.title,
                "company_hint": r.company,
                "location_hint": r.location_raw,
                "salary_hint": r.salary_raw,
                "deadline_hint": r.deadline_raw,
                "text": (r.raw_text or "")[: (3800 if r.attachment_read else 2400)],
            }
        )

    instructions = (
        "너는 한국 장애인 채용공고 전문 에디터다. 아래 입력 JSON의 채용공고 원문들을 읽고 "
        "각 항목을 아래 스키마의 순수 JSON 배열(Array)로만 출력하라. 설명 문장이나 마크다운 코드블록 없이 JSON 배열만 출력할 것.\n"
        "각 원소 필드:\n"
        "- idx: 정수 (입력 idx 그대로)\n"
        "- is_for_disabled: boolean (장애인 구직자가 지원하는 공고면 true, 비장애인 복지사/활동지원사 등 일반직원 채용이면 false)\n"
        "- company: 문자열 (정확한 기업/기관명)\n"
        "- title: 문자열 (깔끔하게 정리한 공고 제목)\n"
        "- org_type: 다음 중 하나 선택 [\"공공기관\", \"지자체\", \"대기업\", \"외국계\", \"표준사업장\", \"민간기업\", \"복지·비영리\"]\n"
        "- location: 문자열 (예: \"경기도 고양시 덕양구 삼송동\", \"서울 영등포구\", \"재택근무\")\n"
        "- salary_text: 문자열 (예: \"월급 235만원\", \"시급 10,320원\", \"연봉 3,200만원\", \"회사내규\")\n"
        "- salary_monthly_krw: 정수 또는 null (월급 환산 만원 단위 정수. 예: 월 235만원 -> 235, 일4시간 시급10320원 -> 108, 모르면 null)\n"
        "- work_hours: 문자열 (예: \"주 5일, 일 4시간 (단시간)\", \"주 5일 09:00~18:00 (전일제)\")\n"
        "- is_part_time: boolean (일 6시간 이하 단시간/시간제 여부)\n"
        "- is_remote: boolean (재택근무/원격근무 가능 여부)\n"
        "- employment_type: 다음 중 하나 [\"정규직\", \"계약직\", \"무기계약직\", \"인턴\", \"공공일자리\", \"시간제\", \"상세 참고\"]\n"
        "- contract_period: 문자열 (구체적 계약기간. 예: \"정규직 (기간 제한 없음)\", \"12개월 (2027.01~2027.12)\", \"3개월 (정규직 전환 검토)\", \"상세 참고\")\n"
        "- contract_category: 다음 중 하나 [\"정규·무기계약\", \"1년 이상\", \"6개월~1년\", \"6개월 미만\", \"상세 참고\"]\n"
        "- disability_type: 다음 중 하나 [\"장애인만 채용\", \"공공 제한경쟁\", \"병행채용\", \"장애인 우대\", \"장애인 채용\"]\n"
        "- disability_severity: 다음 중 하나 [\"중증·경증 무관\", \"중증만 가능\", \"경증만 가능\", \"중증 우대\", \"상세 확인\"] (본문에 중증만/심한장애인만 제한이 있으면 \"중증만 가능\", 경증만 가능이면 \"경증만 가능\", 중증 우대면 \"중증 우대\", 등록장애인 전반/제한없음이면 \"중증·경증 무관\")\n"
        "- disability_detail: 문자열 (우대 장애유형·세부조건 등, 없으면 빈 문자열)\n"
        "- residency_restriction: 문자열 (예: \"서울시 거주자 한정\" 처럼 특정 지자체 거주 제한이 있으면 명시, 없으면 빈 문자열)\n"
        "- duties: 문자열 (담당 직무 1~2문장 요약)\n"
        "- qualifications: 문자열 (필수 자격/경력/학력 요약)\n"
        "- apply_method: 문자열 (지원 방법 요약)\n"
        "- application_start: 문자열 (접수 시작일이 명시된 경우 YYYY-MM-DD, 없으면 빈 문자열)\n"
        "- deadline: 문자열 (접수 마감일 YYYY-MM-DD 형식 또는 \"채용시까지\")\n"
        "- is_closed: boolean (본문에 이미 마감/종료되었다고 명시된 경우 true, 아니면 false)\n"
        "- easy_summary: 문자열 배열 정확히 3개 (누구나 쉽게 이해하는 3줄 핵심 요약: ①무슨 일 ②어디서·몇 시간 ③급여·계약·장애조건)\n"
        "- tags: 문자열 배열 3~6개 (예: \"#고양시\", \"#재택가능\", \"#단시간\", \"#공공기관\", \"#초보가능\", \"#사무보조\")\n\n"
        "=== 입력 공고 JSON ===\n"
        + json.dumps(payload, ensure_ascii=False)
    )

    try:
        cmd = [
            opencode_bin,
            "run",
            "-m",
            config.OPENCODE_MODEL,
            "--pure",
            "위 지시사항과 입력 공고 JSON을 처리해서 순수 JSON 배열만 출력하라.",
        ]
        env = os.environ.copy()
        env["NO_COLOR"] = "1"
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run(
            cmd,
            input=instructions,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            env=env,
            cwd=str(config.ROOT_DIR),
            creationflags=creation_flags,
        )
        if proc.returncode != 0:
            return None
        parsed = _extract_json_array(proc.stdout)
        if isinstance(parsed, list):
            return parsed
        return None
    except Exception:
        return None


def _merge_ai_result(raw: RawJob, fallback: EnrichedJob, ai: dict) -> Optional[EnrichedJob]:
    # 키워드 검색 기반 출처에서 비장애인 직원 채용으로 판정되면 자동 제외
    if ai.get("is_for_disabled") is False and raw.source_id in ("saramin", "alio", "jobaba"):
        return None

    loc = clean_text(str(ai.get("location") or fallback.location))
    zone, rank, inferred_remote = classify_distance_zone(loc, f"{raw.title} {raw.raw_text}")
    is_remote = bool(ai.get("is_remote")) or inferred_remote
    if is_remote and rank >= 6:
        zone, rank = "재택근무", 3

    sal_text = clean_text(str(ai.get("salary_text") or fallback.salary_text))
    sal_monthly = ai.get("salary_monthly_krw")
    if isinstance(sal_monthly, (int, float)) and 20 <= sal_monthly <= 2000:
        sal_monthly = int(round(sal_monthly))
    else:
        sal_monthly = parse_monthly_salary_krw(sal_text) or fallback.salary_monthly_krw

    easy = ai.get("easy_summary")
    if not isinstance(easy, list) or not easy:
        easy = fallback.easy_summary
    else:
        easy = [clean_text(str(x)) for x in easy[:3] if str(x).strip()]

    tags = ai.get("tags")
    if not isinstance(tags, list) or not tags:
        tags = fallback.tags
    else:
        tags = [
            (str(t).strip() if str(t).strip().startswith("#") else f"#{str(t).strip()}")
            for t in tags[:6]
            if str(t).strip()
        ]

    residency = clean_text(str(ai.get("residency_restriction") or fallback.residency_restriction))
    if residency and not any("거주" in t for t in tags):
        tags.append("#거주지제한")

    valid_orgs = {"공공기관", "지자체", "대기업", "외국계", "표준사업장", "민간기업", "복지·비영리"}
    org_type = str(ai.get("org_type") or fallback.org_type).strip()
    if org_type not in valid_orgs:
        org_type = fallback.org_type

    valid_sev = {"중증·경증 무관", "중증만 가능", "경증만 가능", "중증 우대", "상세 확인"}
    severity = clean_text(str(ai.get("disability_severity") or fallback.disability_severity))
    if severity not in valid_sev:
        severity = fallback.disability_severity

    valid_contract_cat = {"정규·무기계약", "1년 이상", "6개월~1년", "6개월 미만", "상세 참고"}
    contract_cat = clean_text(str(ai.get("contract_category") or fallback.contract_category))
    if contract_cat not in valid_contract_cat:
        contract_cat = fallback.contract_category

    app_start_raw = clean_text(str(ai.get("application_start") or fallback.application_start))
    app_start = normalize_deadline(app_start_raw) if app_start_raw else ""
    if app_start == "채용시까지":
        app_start = ""

    return EnrichedJob(
        id=fallback.id,
        sources=fallback.sources,
        source_ids=fallback.source_ids,
        url=fallback.url,
        title=clean_text(str(ai.get("title") or fallback.title)),
        company=clean_text(str(ai.get("company") or fallback.company)),
        org_type=org_type,
        location=loc,
        distance_zone=zone,
        distance_rank=rank,
        salary_text=sal_text,
        salary_monthly_krw=sal_monthly,
        work_hours=clean_text(str(ai.get("work_hours") or fallback.work_hours)),
        is_part_time=bool(ai.get("is_part_time")) if ai.get("is_part_time") is not None else fallback.is_part_time,
        is_remote=is_remote,
        employment_type=clean_text(str(ai.get("employment_type") or fallback.employment_type)),
        contract_period=clean_text(str(ai.get("contract_period") or fallback.contract_period)),
        contract_category=contract_cat,
        disability_type=clean_text(str(ai.get("disability_type") or fallback.disability_type)),
        disability_severity=severity,
        disability_detail=clean_text(str(ai.get("disability_detail") or "")),
        residency_restriction=residency,
        duties=clean_text(str(ai.get("duties") or fallback.duties)),
        qualifications=clean_text(str(ai.get("qualifications") or fallback.qualifications)),
        apply_method=clean_text(str(ai.get("apply_method") or fallback.apply_method)),
        easy_summary=easy,
        tags=list(dict.fromkeys(tags))[:7],
        application_start=app_start,
        deadline=normalize_deadline(str(ai.get("deadline") or fallback.deadline)),
        is_closed_in_text=bool(ai.get("is_closed")) or fallback.is_closed_in_text,
        posted_date=fallback.posted_date,
        collected_at=fallback.collected_at,
        ai_processed=True,
        attachments=fallback.attachments,
        attachment_read=fallback.attachment_read,
        raw_excerpt=fallback.raw_excerpt,
    )


def enrich_jobs(
    raw_jobs: List[RawJob],
    use_ai: bool = True,
    batch_size: int = 5,
    log_fn=print,
) -> Tuple[List[EnrichedJob], dict]:
    collected_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    cache = _load_cache()
    enriched: List[EnrichedJob] = []
    pending: List[Tuple[RawJob, str, EnrichedJob]] = []

    stats = {"cached": 0, "ai_success": 0, "ai_filtered_out": 0, "fallback": 0}

    for raw in raw_jobs:
        fallback = rule_based_enrich(raw, collected_at)
        att_tag = "att" if raw.attachment_read else "web"
        cache_key = f"v2:{att_tag}:{raw.source_id}:{raw.external_id}:{stable_hash(raw.raw_text[:2500])}"
        if use_ai and cache_key in cache:
            cached_ai = cache[cache_key]
            merged = _merge_ai_result(raw, fallback, cached_ai)
            if merged is None:
                stats["ai_filtered_out"] += 1
            else:
                enriched.append(merged)
                stats["cached"] += 1
        elif use_ai:
            pending.append((raw, cache_key, fallback))
        else:
            enriched.append(fallback)
            stats["fallback"] += 1

    if use_ai and pending:
        chunks = [pending[i : i + batch_size] for i in range(0, len(pending), batch_size)]
        log_fn(
            f"[AI] OpenCode ({config.OPENCODE_MODEL})로 신규 {len(pending)}건 정제 시작 "
            f"(배치 {len(chunks)}개 · 동시 3워커)..."
        )
        done_count = 0

        def _process_chunk(chunk):
            return chunk, _call_opencode_batch([item[0] for item in chunk])

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(_process_chunk, ch) for ch in chunks]
            for fut in as_completed(futures):
                chunk, ai_list = fut.result()
                by_idx: Dict[int, dict] = {}
                if ai_list:
                    for entry in ai_list:
                        if isinstance(entry, dict) and isinstance(entry.get("idx"), int):
                            by_idx[entry["idx"]] = entry

                for local_idx, (raw, cache_key, fallback) in enumerate(chunk):
                    ai_item = by_idx.get(local_idx)
                    if ai_item:
                        cache[cache_key] = ai_item
                        merged = _merge_ai_result(raw, fallback, ai_item)
                        if merged is None:
                            stats["ai_filtered_out"] += 1
                        else:
                            enriched.append(merged)
                            stats["ai_success"] += 1
                    else:
                        enriched.append(fallback)
                        stats["fallback"] += 1

                done_count += len(chunk)
                _save_cache(cache)
                log_fn(
                    f"  진행 {done_count}/{len(pending)} "
                    f"(AI성공: {stats['ai_success']}, 폴백: {stats['fallback']}, 노이즈제외: {stats['ai_filtered_out']})"
                )

    return enriched, stats
