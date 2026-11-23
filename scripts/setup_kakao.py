from __future__ import annotations

import json
import sys
import urllib.parse
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config

REDIRECT_URI = "http://localhost:5050/callback"
AUTH_CODE: dict[str, str] = {}


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        if "code" in qs:
            AUTH_CODE["code"] = qs["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                "<h2>✅ 카카오 인증 완료! 이 창을 닫고 터미널로 돌아가세요.</h2>".encode("utf-8")
            )
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Missing code parameter")

    def log_message(self, format, *args):
        return


def main() -> None:
    print("============================================================")
    print(" 카카오톡 '나에게 보내기' 최초 1회 설정 도우미")
    print("============================================================")
    print("사전 준비 (developers.kakao.com):")
    print(" 1) 내 애플리케이션 추가 → 앱 키에서 [REST API 키] 복사")
    print(" 2) 카카오 로그인 활성화 ON")
    print(f" 3) Redirect URI에 {REDIRECT_URI} 추가")
    print(" 4) 동의항목 → '카카오톡 메시지 전송(talk_message)' 동의 설정")
    print("------------------------------------------------------------")

    rest_key = config.KAKAO_REST_API_KEY or input("REST API 키 입력: ").strip()
    if not rest_key:
        print("❌ REST API 키가 비어 있습니다.")
        return

    client_secret = config.KAKAO_CLIENT_SECRET or input("Client Secret (설정 안 했으면 그냥 Enter): ").strip()

    auth_url = (
        "https://kauth.kakao.com/oauth/authorize"
        f"?client_id={rest_key}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI, safe='')}"
        "&response_type=code"
        "&scope=talk_message"
    )
    print("\n브라우저로 카카오 로그인 창을 엽니다...")
    webbrowser.open(auth_url)

    server = HTTPServer(("127.0.0.1", 5050), CallbackHandler)
    print("카카오 로그인 및 동의 완료를 기다리는 중 (http://localhost:5050/callback)...")
    while "code" not in AUTH_CODE:
        server.handle_request()
    server.server_close()

    code = AUTH_CODE["code"]
    data = {
        "grant_type": "authorization_code",
        "client_id": rest_key,
        "redirect_uri": REDIRECT_URI,
        "code": code,
    }
    if client_secret:
        data["client_secret"] = client_secret

    resp = httpx.post("https://kauth.kakao.com/oauth/token", data=data, timeout=15.0)
    if resp.status_code != 200:
        print(f"❌ 토큰 발급 실패 ({resp.status_code}): {resp.text}")
        return

    tok = resp.json()
    saved = {
        "rest_api_key": rest_key,
        "client_secret": client_secret,
        "access_token": tok["access_token"],
        "refresh_token": tok.get("refresh_token", ""),
        "updated_at": datetime.now().isoformat(),
    }
    config.KAKAO_TOKEN_PATH.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 토큰 저장 완료: {config.KAKAO_TOKEN_PATH}")

    # 테스트 메시지 전송
    test_template = {
        "object_type": "text",
        "text": "✅ [고양시 장애인 채용 자동화] 카카오톡 알림 연결 성공!\n앞으로 매일 수집 완료 시 나와의 채팅으로 브리핑이 도착합니다.",
        "link": {
            "web_url": config.SITE_PUBLIC_URL or "http://localhost:8080",
            "mobile_web_url": config.SITE_PUBLIC_URL or "http://localhost:8080",
        },
        "button_title": "사이트 열기",
    }
    r2 = httpx.post(
        "https://kapi.kakao.com/v2/api/talk/memo/default/send",
        headers={"Authorization": f"Bearer {saved['access_token']}"},
        data={"template_object": json.dumps(test_template, ensure_ascii=False)},
        timeout=15.0,
    )
    if r2.status_code == 200:
        print("🎉 카카오톡 '나와의 채팅'으로 테스트 메시지가 도착했습니다!")
    else:
        print(f"⚠️ 토큰은 저장됐으나 테스트 발송 오류 ({r2.status_code}): {r2.text}")


if __name__ == "__main__":
    main()
