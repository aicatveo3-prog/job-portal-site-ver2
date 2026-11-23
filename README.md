# 고양시·수도권·재택 장애인 채용공고 자동화 사이트 (Ver2)

8개 공식·민간 채용 사이트에서 **고양시 · 서울 · 경기 · 재택근무** 장애인 채용공고를 하루 1회 자동 수집하고, **OpenCode Go (`opencode-go/deepseek-v4.1-flash`)**가 원문을 읽어 공공/민간 구분 · 급여 · 근무시간 · 거주지 제한 · 쉬운 3줄 요약으로 정리해 웹페이지로 보여주는 방치형 자동화 프로젝트입니다.

---

## 1. 수집 대상 8개 사이트

1. **고양시 일자리통합정보망** (`goyang.go.kr/jobs`) — 고양시 장애인 채용 + 공공채용
2. **한국장애인고용공단** (`kead.or.kr`) — 대기업·금융권·표준사업장·지자체 공고
3. **고용24** (`work24.go.kr`) — 구 워크투게더 통합, 경기·서울 장애인만/병행 채용
4. **서울시장애인일자리센터** (`jobcnt.or.kr`) — 서울 구인공고 및 자치구 일자리
5. **잡알리오** (`job.alio.go.kr`) — 공공기관 장애인 제한경쟁/우대 공고
6. **사람인** (`saramin.co.kr`) — 민간·외국계·IT·재택 장애인 전형/채용
7. **모두의잡** (`modoojob.com`) — 장애인 전문 구인 포털
8. **잡아바** (`job.gg.go.kr`) — 경기도 공공/기관 장애인 채용

---

## 2. 빠른 시작 (로컬 실행)

### ① 환경 설정 (선택)
`.env.example`을 복사해 `.env` 파일을 만들면 모델·카톡·자동푸시 등을 조절할 수 있습니다. (없어도 기본값으로 바로 동작합니다.)

### ② 수동 수집 실행
```powershell
# 전체 8개 사이트 수집 + OpenCode(DeepSeek 4.1) AI 정제 + 윈도우 알림
python scripts\run_daily.py --force

# AI 없이 빠르게 수집만 테스트할 때
python scripts\run_daily.py --force --no-ai --limit 5
```

### ③ 웹사이트 열어보기
`scripts\open_site.bat` 파일을 더블클릭하면 브라우저에서 `http://localhost:8080` 이 바로 열립니다.

---

## 3. 완전 방치형 자동 실행 (Windows 작업 스케줄러)

PC를 켤 때(로그인 1분 뒤) 및 매일 오전 9시에 까만 창 없이 백그라운드로 실행되며, **하루에 PC를 여러 번 켜도 `state/state.json` 가드로 하루 딱 1번만 수집**합니다. 수집 시작/완료 시 Windows 우측 하단에 토스트 알림이 뜹니다.

```powershell
# 자동 실행 등록
powershell -ExecutionPolicy Bypass -File scripts\register_scheduler.ps1

# 자동 실행 해제
powershell -ExecutionPolicy Bypass -File scripts\unregister_scheduler.ps1
```

---

## 4. 나중에 GitHub Pages(무료 인터넷 사이트)로 올리는 방법

웹사이트가 이미 `docs/` 폴더에 정적 파일로 구축되어 있어 별도 빌드 과정 없이 바로 공개됩니다.

1. GitHub에서 새 저장소 생성 후 이 폴더를 push합니다.
   ```powershell
   git init
   git add .
   git commit -m "feat: 장애인 채용공고 자동화 사이트 Ver2"
   git branch -M main
   git remote add origin https://github.com/<내아이디>/<저장소명>.git
   git push -u origin main
   ```
2. GitHub 저장소 **Settings → Pages → Build and deployment**:
   - Source: `Deploy from a branch`
   - Branch: `main` / Folder: **`/docs`** → Save
3. 1분 뒤 `https://<내아이디>.github.io/<저장소명>/` 로 폰·PC 어디서든 접속 가능!
4. `.env` 파일에 아래 두 줄을 설정하면 매일 수집 후 자동으로 GitHub에 올라갑니다.
   ```env
   SITE_PUBLIC_URL=https://<내아이디>.github.io/<저장소명>/
   AUTO_GIT_PUSH=true
   ```

---

## 5. 카카오톡 "나에게 보내기" 폰 알림 설정 (최초 1회)

1. [카카오 디벨로퍼스](https://developers.kakao.com) → 내 애플리케이션 추가 → **REST API 키** 복사
2. `카카오 로그인` 활성화 ON → Redirect URI에 `http://localhost:5050/callback` 추가
3. `동의항목` → **`카카오톡 메시지 전송(talk_message)`** 활성화
4. `.env`에 `KAKAO_REST_API_KEY=...` 입력 후 아래 명령 1회 실행:
   ```powershell
   python scripts\setup_kakao.py
   ```
5. 브라우저 로그인 후 토큰이 `state/kakao_tokens.json`에 저장되며, 이후 매일 수집 시 `refresh_token`을 자동 갱신합니다.
