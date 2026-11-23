from __future__ import annotations

import json
import socket
import sys
import threading
import urllib.parse
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config

REDIRECT_URI = "http://localhost:5050/callback"
AUTH_CODE: dict[str, str] = {}
AUTH_URL_HOLDER: dict[str, str] = {}
DONE_EVENT = threading.Event()


class DualStackServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class IPv6Server(ThreadingHTTPServer):
    address_family = socket.AF_INET6
    allow_reuse_address = True
    daemon_threads = True


class CallbackHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(5.0)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/", "/start"):
            self.send_response(302)
            self.send_header("Location", AUTH_URL_HOLDER.get("url", "https://kauth.kakao.com"))
            self.send_header("Connection", "close")
            self.end_headers()
            return
        qs = urllib.parse.parse_qs(parsed.query)
        if "code" in qs:
            AUTH_CODE["code"] = qs["code"][0]
            body = "<h2>⏳ 카카오 로그인 성공! 토큰 발급 및 테스트 발송을 처리 중입니다... (터미널/채팅 결과를 확인하세요)</h2>".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            DONE_EVENT.set()
        else:
            body = f"<h3>인증 대기/오류: {parsed.path} {parsed.query}</h3>".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)

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

    client_secret = config.KAKAO_CLIENT_SECRET
    if not client_secret and sys.stdin and sys.stdin.isatty():
        client_secret = input("Client Secret (설정 안 했으면 그냥 Enter): ").strip()

    auth_url = (
        "https://kauth.kakao.com/oauth/authorize"
        f"?client_id={rest_key}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI, safe='')}"
        "&response_type=code"
        "&scope=talk_message"
    )
    AUTH_URL_HOLDER["url"] = auth_url
    servers = []
    srv4 = DualStackServer(("127.0.0.1", 5050), CallbackHandler)
    servers.append(srv4)
    threading.Thread(target=srv4.serve_forever, daemon=True).start()
    try:
        srv6 = IPv6Server(("::1", 5050), CallbackHandler)
        servers.append(srv6)
        threading.Thread(target=srv6.serve_forever, daemon=True).start()
    except Exception:
        pass

    print("\n브라우저에서 http://localhost:5050/start 로 접속해 주세요...", flush=True)
    if "--open" in sys.argv:
        webbrowser.open("http://localhost:5050/start")
    print("카카오 로그인 및 동의 완료를 기다리는 중 (http://localhost:5050/callback)...", flush=True)
    DONE_EVENT.wait(timeout=600)
    for srv in servers:
        try:
            srv.shutdown()
            srv.server_close()
        except Exception:
            pass
    if "code" not in AUTH_CODE:
        print("❌ 인증 시간 초과 (10분). 다시 실행해 주세요.", flush=True)
        return

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
