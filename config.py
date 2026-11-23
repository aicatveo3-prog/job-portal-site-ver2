from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")

DOCS_DIR = ROOT_DIR / "docs"
DATA_DIR = DOCS_DIR / "data"
STATE_DIR = ROOT_DIR / "state"
LOGS_DIR = STATE_DIR / "logs"

JOBS_JSON_PATH = DATA_DIR / "jobs.json"
META_JSON_PATH = DATA_DIR / "meta.json"
STATE_JSON_PATH = STATE_DIR / "state.json"
AI_CACHE_PATH = STATE_DIR / "ai_cache.json"
KAKAO_TOKEN_PATH = STATE_DIR / "kakao_tokens.json"
LOCK_FILE_PATH = STATE_DIR / "running.lock"

# OpenCode Go / DeepSeek 4.1
OPENCODE_MODEL = os.getenv("OPENCODE_MODEL", "opencode-go/deepseek-v4.1-flash").strip()
ENABLE_AI = os.getenv("ENABLE_AI", "true").lower() in ("1", "true", "yes", "y")
AI_BATCH_SIZE = max(1, int(os.getenv("AI_BATCH_SIZE", "6")))
MAX_PER_SOURCE = max(1, int(os.getenv("MAX_PER_SOURCE", "50")))

# Hosting / Git auto-push
SITE_PUBLIC_URL = os.getenv("SITE_PUBLIC_URL", "").strip()
AUTO_GIT_PUSH = os.getenv("AUTO_GIT_PUSH", "false").lower() in ("1", "true", "yes", "y")

# Notifications
ENABLE_WINDOWS_TOAST = os.getenv("ENABLE_WINDOWS_TOAST", "true").lower() in ("1", "true", "yes", "y")
KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "").strip()
KAKAO_CLIENT_SECRET = os.getenv("KAKAO_CLIENT_SECRET", "").strip()
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# HTTP defaults
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
HTTP_TIMEOUT = 18.0

# 고양시 중심 수집 권역 키워드
GOYANG_KEYWORDS = ["고양", "일산", "덕양", "화정", "삼송", "원흥", "행신", "백석", "주엽", "대화", "정발산", "마두", "풍동", "식사동", "향동", "덕은"]
NEARBY_COMMUTE_KEYWORDS = [
    "파주", "김포", "양주", "의정부",
    "은평", "마포", "서대문", "강서", "영등포", "종로", "중구", "용산", "양천",
    "상암", "마곡", "여의도", "광화문", "공덕", "합정", "홍대", "신촌", "연신내", "불광",
]
REMOTE_KEYWORDS = ["재택", "원격", "지역무관", "전국", "홈오피스", "리모트"]
SEOUL_KEYWORDS = [
    "서울", "강남", "서초", "송파", "강동", "광진", "성동", "동대문", "중랑",
    "성북", "강북", "도봉", "노원", "구로", "금천", "동작", "관악",
]
GYEONGGI_KEYWORDS = [
    "경기", "수원", "성남", "분당", "판교", "용인", "부천", "안산", "안양",
    "남양주", "화성", "평택", "시흥", "광명", "군포", "광주", "이천",
    "오산", "하남", "의왕", "구리", "안성", "포천", "여주", "동두천", "과천", "연천", "가평", "양평",
]

# 수집에서 아예 제외할 직무 키워드 (제목/직무에 포함 시 수집·AI정제 전 단계에서 제외)
EXCLUDED_ROLE_KEYWORDS = [
    "미화", "청소", "클리닝", "환경정비",
    "요양보호사", "재가요양", "방문요양", "요양원", "간병인",
    "네일아티스트", "네일아트", "네일케어", "네일 ", "네일(",
    "조리사", "조리원", "조리보조", "주방보조", "취사원",
    "버스운전", "버스 운전", "버스기사", "시내버스", "마을버스", "승무사원", "운전직", "운전원", "운전기사",
    "바리스타", "카페음료", "음료제조", "커피제조",
    "설거지", "식기세척", "세척원", "주방세척",
]

for d in (DATA_DIR, STATE_DIR, LOGS_DIR):
    d.mkdir(parents=True, exist_ok=True)
