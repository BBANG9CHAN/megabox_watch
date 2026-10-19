# 🎬 Megabox Watch

메가박스 **진행 중 이벤트**에서 원하는 키워드(예: 디지몬)가 들어간 이벤트가 새로 올라오면
디스코드로 알려주는 작은 감시 스크립트입니다.

- 키워드 여러 개 동시 감시 (기본: `디지몬`, `디지타마`)
- 처음 실행할 때는 기존 이벤트를 조용히 저장하고, 이후 **새로 올라온 이벤트만** 알림
- 디스코드 / 텔레그램 / 슬랙 알림 지원
- 파이썬 파일 하나 + 실행용 bat 파일로 끝나는 단순한 구조

## 동작 방식

메가박스 이벤트 목록은 페이지 HTML이 아니라 아래 AJAX 호출로 내려옵니다.

```
POST https://www.megabox.co.kr/on/oh/ohe/Event/eventMngDiv.do
{ "eventStatCd": "ONG", "eventTitle": "<키워드>", ... }
```

응답으로 오는 목록 HTML 조각에서 (이벤트 번호, 제목)을 뽑아 `seen_events.json` 에 저장하고,
이전에 본 적 없는 번호만 알림을 보냅니다.

## 설치

```bat
pip install requests beautifulsoup4
```

## 설정

`.env.example` 을 `.env` 로 복사한 뒤 디스코드 웹후크 URL을 넣으세요. (`.env` 는 git 에 올라가지 않음)

```
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

디스코드 웹후크 만들기: 채널 설정(⚙) → **연동** → **웹후크** → **새 웹후크** → **웹후크 URL 복사**

## 실행

| 파일 | 용도 |
|---|---|
| `run.bat` | 한 번 실행하고 결과를 `watch.log` 에 기록 (작업 스케줄러에 등록하는 파일) |
| `test_run.bat` | 알림 테스트. 저장된 기록을 지우고 현재 매칭되는 이벤트를 전부 알림으로 보냄 |

알림 없이 수집 결과만 확인하고 싶다면:

```bat
python megabox_watch.py --debug    REM 매칭된 이벤트 목록 출력
python megabox_watch.py --dump     REM 원본 HTML 조각을 fragment.html 로 저장 (파싱 문제 확인용)
```

## 주기 실행 (Windows 작업 스케줄러)

1. **작업 스케줄러** → **작업 만들기**
2. 트리거: 매일, **30분마다 반복**
3. 동작: 프로그램 시작 → `run.bat` 선택, **시작 위치**에 이 폴더 경로 입력

> PC가 절전 모드에 들어가면 실행도 멈춥니다.

macOS / Linux 라면 cron 으로 등록하세요.

```
*/30 * * * * cd /path/to/megabox_watch && python3 megabox_watch.py >> watch.log 2>&1
```

## 환경변수

| 이름 | 설명 |
|---|---|
| `DISCORD_WEBHOOK_URL` | 디스코드 웹후크 |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | 텔레그램 알림 (선택) |
| `SLACK_WEBHOOK_URL` | 슬랙 Incoming Webhook (선택) |
| `KEYWORDS` | 감시할 키워드, 쉼표 구분. 기본 `디지몬,디지타마` |
| `EVENT_STAT_CD` | `ONG`(진행 중, 기본) 또는 `END`(지난 이벤트) |
| `STATE_FILE` | 본 이벤트 기록 파일. 기본 `seen_events.json` |
| `FIRST_RUN_NOTIFY` | `1` 이면 첫 실행에도 기존 이벤트를 전부 알림 |

`.env` 에 같이 적어두면 `run.bat` 이 읽어 들입니다.

## 파일

| 파일 | 설명 |
|---|---|
| `megabox_watch.py` | 수집 · 비교 · 알림 전체 로직 |
| `run.bat`, `test_run.bat` | Windows 실행용 |
| `.env` | 웹후크 등 비밀값 (git 제외) |
| `seen_events.json` | 이미 알린 이벤트 번호 (실행 중 생성, git 제외) |
| `watch.log` | 실행 기록 (git 제외) |

## 문제 해결

- **계속 `매칭 0건`** — 실제로 해당 키워드 이벤트가 없을 수 있습니다. `KEYWORDS=메가` 처럼 흔한 단어로 `--debug` 를 돌려 결과가 나오면 정상입니다.
- **흔한 단어에도 0건** — 메가박스 사이트 구조가 바뀐 경우입니다. `--dump` 로 받은 `fragment.html` 을 보고 `parse_fragment()` 를 고치세요.
- **알림이 안 옴** — `test_run.bat` 으로 테스트해 보고, `.env` 의 웹후크 URL을 확인하세요.
