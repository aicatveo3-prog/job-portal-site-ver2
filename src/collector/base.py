from __future__ import annotations

import hashlib
import re
import time
from datetime import date, timedelta
from typing import List, Optional
import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

import config


class RawJob(BaseModel):
    source_id: str          # e.g. "goyang", "kead", "work24", "jobcnt", "alio", "saramin", "modoojob", "jobaba"
    source_name: str        # e.g. "고양시 일자리망", "한국장애인고용공단"
    external_id: str        # site-specific unique ID
    title: str
    company: str = ""
    location_raw: str = ""
    salary_raw: str = ""
    employment_raw: str = ""
    deadline_raw: str = ""
    posted_raw: str = ""
    url: str
    raw_text: str = ""      # Full cleaned detail page text + attachment text for DeepSeek 4.1
    wanted_auth_no: str = ""  # Work24/Goyang shared ID for exact dedupe
    attachments: List[dict] = Field(default_factory=list)  # [{"name": "...", "url": "..."}]
    attachment_read: bool = False


class EnrichedJob(BaseModel):
    id: str
    sources: List[str] = Field(default_factory=list)       # ["고용24", "고양시 일자리망"]
    source_ids: List[str] = Field(default_factory=list)    # ["work24", "goyang"]
    url: str
    alt_urls: List[str] = Field(default_factory=list)

    title: str
    company: str
    org_type: str = "민간기업"   # 공공기관 | 지자체 | 대기업 | 외국계 | 표준사업장 | 민간기업 | 복지·비영리
    location: str = "미상"
    distance_zone: str = "기타"  # 고양시 관내 | 인접 출퇴근 | 재택근무 | 서울 기타 | 경기 기타 | 전국/기타
    distance_rank: int = 9

    salary_text: str = "회사내규/협의"
    salary_monthly_krw: Optional[int] = None  # 만원 단위 환산 (정렬용, 예: 230 -> 230만원)
    work_hours: str = "상세공고 참고"
    is_part_time: bool = False
    is_remote: bool = False

    employment_type: str = "미상"         # 정규직 | 계약직 | 인턴 | 공공일자리 | 시간제 | 무기계약직
    contract_period: str = "상세 참고"     # 예: 정규직 (기간 제한 없음) | 12개월 (2027.01~2027.12) | 3개월 (전환검토)
    contract_category: str = "상세 참고"   # 정규·무기계약 | 1년 이상 | 6개월~1년 | 6개월 미만 | 상세 참고
    disability_type: str = "장애인 채용"   # 장애인만 채용 | 병행채용 | 장애인 우대 | 공공 제한경쟁 | 장애인 채용
    disability_severity: str = "상세 확인" # 중증·경증 무관 | 중증만 가능 | 경증만 가능 | 중증 우대 | 상세 확인
    disability_detail: str = ""           # 세부 장애유형/조건 등
    residency_restriction: str = ""       # 예: "서울시 거주자 한정" (비어있으면 제한 없음)

    duties: str = ""
    qualifications: str = ""
    apply_method: str = ""
    easy_summary: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)

    application_start: str = ""           # YYYY-MM-DD (접수 시작일, 없으면 빈 문자열)
    deadline: str = "채용시까지"          # YYYY-MM-DD or 채용시까지
    is_closed_in_text: bool = False       # 원문에 이미 마감 표시가 있는 경우
    posted_date: str = ""
    collected_at: str = ""
    is_new: bool = False
    ai_processed: bool = False
    attachments: List[dict] = Field(default_factory=list)  # [{"name": "...", "url": "..."}]
    attachment_read: bool = False
    raw_excerpt: str = ""                 # 원문 미리보기 (최대 2500자)


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\xa0", " ").replace("\u200b", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_readable_text(html: str, max_chars: int = 4500) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "header", "footer", "nav"]):
        tag.decompose()
    # Try main content containers first if substantial
    for sel in ("main", "#contents", "#content", ".contents", ".board_view", ".view_con", "article"):
        node = soup.select_one(sel)
        if node:
            txt = clean_text(node.get_text("\n", strip=True))
            if len(txt) >= 250:
                return txt[:max_chars]
    txt = clean_text(soup.get_text("\n", strip=True))
    return txt[:max_chars]


def make_http_client() -> httpx.Client:
    return httpx.Client(
        headers={
            "User-Agent": config.USER_AGENT,
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        },
        follow_redirects=True,
        timeout=config.HTTP_TIMEOUT,
        verify=False,
    )


def polite_sleep(sec: float = 0.45) -> None:
    time.sleep(sec)


def stable_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:12]


def classify_distance_zone(location: str, text: str = "") -> tuple[str, int, bool]:
    """고양시 거주자 기준 생활권 분류 + 정렬 우선순위 + 재택 여부."""
    loc = (location or "").strip()
    combined = f"{loc} {text[:800]}"

    is_remote = any(k in loc for k in ("재택", "원격", "리모트")) or any(
        k in combined for k in ("재택근무", "재택 가능", "재택가능", "풀재택", "완전 재택", "원격근무")
    )

    if any(k in loc for k in config.GOYANG_KEYWORDS):
        return ("고양시 관내", 1, is_remote)
    if is_remote and (not loc or any(k in loc for k in ("재택", "원격", "무관", "전국"))):
        return ("재택근무", 3, True)
    if any(k in loc for k in config.NEARBY_COMMUTE_KEYWORDS):
        return ("인접 출퇴근", 2, is_remote)
    if any(k in loc for k in config.SEOUL_KEYWORDS):
        return ("서울 기타", 4, is_remote)
    if any(k in loc for k in config.GYEONGGI_KEYWORDS):
        return ("경기 기타", 5, is_remote)
    if is_remote or any(k in loc for k in ("지역무관", "전국")):
        return ("재택근무" if is_remote else "전국/기타", 3 if is_remote else 6, is_remote)

    # fallback: check broader text if location was empty/unclear
    if not loc or loc in ("-", "미상", "기타"):
        if any(k in combined for k in config.GOYANG_KEYWORDS):
            return ("고양시 관내", 1, is_remote)
        if any(k in combined for k in config.NEARBY_COMMUTE_KEYWORDS):
            return ("인접 출퇴근", 2, is_remote)
        if any(k in combined for k in config.SEOUL_KEYWORDS):
            return ("서울 기타", 4, is_remote)
        if any(k in combined for k in config.GYEONGGI_KEYWORDS):
            return ("경기 기타", 5, is_remote)

    return ("전국/기타", 6, is_remote)


def is_in_target_area(location: str, title: str = "", text: str = "") -> bool:
    """고양시 · 서울 · 경기 · 재택근무/지역무관 권역 여부 판별."""
    zone, rank, is_remote = classify_distance_zone(location, f"{title} {text}")
    if rank <= 5 or is_remote:
        return True
    combined = f"{location} {title}"
    if any(k in combined for k in ("수도권", "전국", "지역무관", "재택", "원격")):
        return True
    # 비수도권 광역시/도 명시 시 제외
    non_target = ("부산", "대구", "광주", "대전", "울산", "세종", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주", "경상", "전라", "충청")
    if location and any(nt in location for nt in non_target):
        return False
    return not location or location in ("-", "미상")


def parse_monthly_salary_krw(salary_text: str) -> Optional[int]:
    """급여 문자열에서 대략적인 월급(만원 단위 정수) 환산."""
    if not salary_text:
        return None
    s = salary_text.replace(",", "").replace(" ", "")
    # 연봉
    m = re.search(r"연봉[^\d]*(\d+(?:\.\d+)?)만원", s)
    if m:
        return int(round(float(m.group(1)) / 12))
    m = re.search(r"연봉[^\d]*(\d{7,9})원", s)
    if m:
        return int(round(int(m.group(1)) / 120000))
    # 월급
    m = re.search(r"(?:월급|월)[^\d]*(\d{2,4}(?:\.\d+)?)만원", s)
    if m:
        val = float(m.group(1))
        if 30 <= val <= 2000:
            return int(round(val))
    m = re.search(r"(?:월급|월)[^\d]*(\d{6,8})원", s)
    if m:
        val = int(m.group(1)) / 10000
        if 30 <= val <= 2000:
            return int(round(val))
    # 시급 -> 주 40시간(209시간) 기준 대략 환산 (단시간은 AI가 보정)
    m = re.search(r"시급[^\d]*(\d{4,6})원", s)
    if m:
        hourly = int(m.group(1))
        if 8000 <= hourly <= 100000:
            return int(round((hourly * 209) / 10000))
    return None


def normalize_deadline(raw: str) -> str:
    if not raw:
        return "채용시까지"
    s = raw.strip()
    if any(k in s for k in ("채용시", "상시", "충원시")):
        return "채용시까지"
    # D-N / D-Day 상대 표기 → 정확한 YYYY-MM-DD 로 환산
    m_d = re.search(r"D\s*-\s*(\d{1,3})\b", s, re.I)
    if m_d:
        target = date.today() + timedelta(days=int(m_d.group(1)))
        return target.strftime("%Y-%m-%d")
    if re.search(r"\bD\s*-\s*Day\b", s, re.I) or "오늘마감" in s.replace(" ", ""):
        return date.today().strftime("%Y-%m-%d")
    # YYYY-MM-DD or YYYY.MM.DD
    m = re.search(r"(20\d{2})[.\-/년\s]+(\d{1,2})[.\-/월\s]+(\d{1,2})", s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # YY-MM-DD or YY.MM.DD
    m = re.search(r"(?<!\d)(\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})(?!\d)", s)
    if m:
        yr = 2000 + int(m.group(1))
        return f"{yr:04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # ~11.30 / ~12/07 / 11월 30일 형태 → 연도 추론
    m_md = re.search(r"(?:~|\b)(\d{1,2})[./월]\s*(\d{1,2})(?:일)?", s)
    if m_md:
        mo, dy = int(m_md.group(1)), int(m_md.group(2))
        if 1 <= mo <= 12 and 1 <= dy <= 31:
            today = date.today()
            yr = today.year
            if mo < today.month - 4:
                yr += 1
            try:
                return date(yr, mo, dy).strftime("%Y-%m-%d")
            except ValueError:
                pass
    return s[:20]


def is_excluded_role(title: str, duties: str = "") -> bool:
    """사용자 설정(config.EXCLUDED_ROLE_KEYWORDS)에 해당하는 직무(미화원·청소·요양보호사 등) 제외 판별."""
    hay = f"{title or ''} {duties or ''}"
    return any(kw in hay for kw in config.EXCLUDED_ROLE_KEYWORDS)


def is_likely_non_disabled_staff_job(title: str, raw_text: str = "") -> bool:
    """키워드 검색 사이트에서 '장애인복지관 직원(비장애인 사회복지사/요양보호사/활동지원사)' 노이즈 사전 필터."""
    t = title or ""
    # 명시적으로 장애인 채용 전형이면 통과
    if any(k in t for k in ("장애인 전형", "장애인전형", "장애인 채용", "장애인채용", "장애인 제한", "장애인제한", "장애인일자리", "장애인 일자리", "장애인 우대", "장애인우대", "장애인 특별", "장애인특별", "중증장애인")):
        return False
    # 복지시설 종사자/치료사/활동지원사/요양보호사 일반 채용은 대개 비장애인 구인
    staff_roles = ("활동지원사", "요양보호사", "언어재활사", "언어치료사", "작업치료사", "물리치료사", "사회복지사", "생활재활교사", "보육교사", "특수교사", "주간활동", "방과후활동")
    if any(r in t for r in staff_roles):
        # 본문에 장애인 제한경쟁/장애인만 채용 언급이 없으면 제외
        if not any(k in raw_text[:1200] for k in ("장애인만 채용", "장애인 제한경쟁", "장애인 전형", "장애인등록증", "복지카드")):
            return True
    return False
