#!/usr/bin/env python3
"""
메가박스 진행중 이벤트 키워드 감시 → 텔레그램(또는 슬랙) 알림

동작 방식
---------
메가박스 이벤트 목록은 페이지 HTML이 아니라 아래 AJAX 호출로 내려온다.

    POST https://www.megabox.co.kr/on/oh/ohe/Event/eventMngDiv.do
    Content-Type: application/json;charset=UTF-8
    {
      "currentPage": "1", "recordCountPerPage": "1000",
      "eventStatCd": "ONG",        # ONG=진행중, END=지난
      "eventTitle": "디지몬",       # 제목 검색어 (서버에서 필터링)
      "eventDivCd": "",            # ''=전체, CED01 영화, CED02 극장,
                                   # CED03 메가Pick, CED04 시사회/무대인사, CED05 제휴/할인
      "eventTyCd": "", "orderReqCd": "ONGlist"
    }

응답은 JSON이 아니라 목록 <li> HTML 조각이다. 이 스크립트는 조각을 파싱해
(eventNo, 제목)을 뽑고, 이전 실행에서 본 적 없는 항목만 알림을 보낸다.

사용법
------
1) 의존성
     uv pip install requests beautifulsoup4     # 또는 pip install ...

2) 파싱 검증 (알림 전송 없음)
     python megabox_watch.py --debug            # 수집 결과 출력
     python megabox_watch.py --dump             # 원본 HTML 조각을 fragment.html로 저장

3) 실행
     export TELEGRAM_BOT_TOKEN="123456:ABC..."
     export TELEGRAM_CHAT_ID="123456789"
     python megabox_watch.py

4) 스케줄 (30분마다)
     */30 * * * * cd /path/to/dir && /usr/bin/python3 megabox_watch.py >> watch.log 2>&1

환경변수
--------
  DISCORD_WEBHOOK_URL                     (선택) 디스코드 웹후크
  TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID   (선택) 텔레그램 알림용
  SLACK_WEBHOOK_URL                       (선택) 슬랙 Incoming Webhook
  KEYWORDS        (선택) 쉼표 구분. 기본 "디지몬,디지타마"
  EVENT_STAT_CD   (선택) ONG(기본) 또는 END
  STATE_FILE      (선택) 기본 seen_events.json
  FIRST_RUN_NOTIFY (선택) "1"이면 최초 실행에도 기존 항목 전부 알림
                   (기본: 최초엔 기준선만 저장하고 조용히 종료)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://www.megabox.co.kr"
API_URL = f"{BASE}/on/oh/ohe/Event/eventMngDiv.do"
DETAIL_URL = f"{BASE}/event/detail?eventNo={{no}}"
TIMEOUT = 15

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Content-Type": "application/json;charset=UTF-8",
    "Accept": "text/html, */*; q=0.01",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"{BASE}/event",
    "Origin": BASE,
}

KEYWORDS = [k.strip() for k in os.getenv("KEYWORDS", "디지몬,디지타마").split(",") if k.strip()]
EVENT_STAT_CD = os.getenv("EVENT_STAT_CD", "ONG")
STATE_FILE = Path(os.getenv("STATE_FILE", "seen_events.json"))


# --------------------------------------------------------------------------
# 수집
# --------------------------------------------------------------------------
def fetch_fragment(keyword: str) -> str:
    payload = {
        "currentPage": "1",
        "recordCountPerPage": "1000",
        "eventStatCd": EVENT_STAT_CD,
        "eventTitle": keyword,
        "eventDivCd": "",
        "eventTyCd": "",
        "orderReqCd": "ONGlist" if EVENT_STAT_CD == "ONG" else "ENDlist",
    }
    res = requests.post(
        API_URL,
        headers=HEADERS,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        timeout=TIMEOUT,
    )
    res.raise_for_status()
    res.encoding = res.encoding or "utf-8"
    return res.text


EVENT_NO_PATTERNS = (
    # eventNo=13984 / name="eventNo" value="13984" / "eventNo":"13984"
    r"eventNo\D{0,30}?(\d{3,})",
    # data-no="13984", data-event-no="13984"
    r"data-(?:event-?no|no)\s*=\s*[\"'](\d{3,})[\"']",
    # fn_moveEventDtl('13984'), fn_eventDetail(13984)
    r"fn_[A-Za-z_]*(?:[Ee]vent|Dtl)[A-Za-z_]*\(\s*[\"']?(\d{3,})",
)


def extract_event_no(block, raw: str) -> str:
    for pat in EVENT_NO_PATTERNS:
        m = re.search(pat, raw, re.I)
        if m:
            return m.group(1)
    # 마지막 수단: 링크 계열 속성값 안의 긴 숫자
    for attr in ("href", "onclick", "data-target", "id"):
        el = block if block.has_attr(attr) else block.find(attrs={attr: True})
        if el:
            m = re.search(r"(\d{4,})", el.get(attr) or "")
            if m:
                return m.group(1)
    return ""


def parse_fragment(html: str) -> list[dict]:
    """목록 HTML 조각에서 {no, title, url} 추출."""
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    seen: set[str] = set()

    blocks = soup.select("li") or soup.select("a")
    for block in blocks:
        raw = str(block)

        no = extract_event_no(block, raw)

        # 제목 추출: .tit 계열 → img alt → 링크 텍스트 순
        title = ""
        for sel in (".tit", "p.tit", ".txt", "strong", "a"):
            el = block.select_one(sel)
            if el:
                title = " ".join(el.get_text(" ", strip=True).split())
                if title:
                    break
        if not title:
            img = block.find("img")
            if img and img.get("alt"):
                title = img["alt"].strip()
        if not title:
            continue

        key = no or hashlib.md5(title.encode("utf-8")).hexdigest()[:12]
        if key in seen:
            continue
        seen.add(key)

        items.append(
            {
                "no": no,
                "title": title,
                "url": DETAIL_URL.format(no=no) if no else f"{BASE}/event",
            }
        )
    return items


def collect() -> list[dict]:
    merged: dict[str, dict] = {}
    for kw in KEYWORDS:
        try:
            for item in parse_fragment(fetch_fragment(kw)):
                merged.setdefault(item["no"] or item["title"], item)
        except requests.RequestException as e:
            print(f"[error] '{kw}' 조회 실패: {e}", file=sys.stderr)
    return list(merged.values())


# --------------------------------------------------------------------------
# 상태 저장
# --------------------------------------------------------------------------
def load_seen() -> set[str]:
    if not STATE_FILE.exists():
        return set()
    try:
        return set(json.loads(STATE_FILE.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return set()


def save_seen(seen: set[str]) -> None:
    STATE_FILE.write_text(
        json.dumps(sorted(seen), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def key_of(item: dict) -> str:
    return item["no"] or hashlib.md5(item["title"].encode("utf-8")).hexdigest()[:12]


# --------------------------------------------------------------------------
# 알림
# --------------------------------------------------------------------------
def notify(text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    webhook = os.getenv("SLACK_WEBHOOK_URL")
    discord = os.getenv("DISCORD_WEBHOOK_URL")

    if not (token and chat_id) and not webhook and not discord:
        print("[warn] 알림 채널 미설정 — 콘솔 출력만 합니다.", file=sys.stderr)
        print(text)
        return

    if discord:
        # 디스코드는 2000자 제한. 넉넉히 잘라서 보낸다.
        r = requests.post(
            discord,
            json={"content": text[:1900], "flags": 0},
            timeout=TIMEOUT,
        )
        if not r.ok:
            print(f"[error] discord {r.status_code}: {r.text}", file=sys.stderr)

    if token and chat_id:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=TIMEOUT,
        )
        if not r.ok:
            print(f"[error] telegram {r.status_code}: {r.text}", file=sys.stderr)

    if webhook:
        r = requests.post(webhook, json={"text": text}, timeout=TIMEOUT)
        if not r.ok:
            print(f"[error] slack {r.status_code}: {r.text}", file=sys.stderr)


# --------------------------------------------------------------------------
def main() -> int:
    if "--dump" in sys.argv:
        html = fetch_fragment(KEYWORDS[0])
        Path("fragment.html").write_text(html, encoding="utf-8")
        print(f"fragment.html 저장 완료 ({len(html)} bytes) — 키워드: {KEYWORDS[0]}")
        return 0

    items = collect()

    if "--debug" in sys.argv:
        print(f"키워드 {KEYWORDS} / 상태 {EVENT_STAT_CD} → {len(items)}건")
        for i in items:
            print(f"  - [{i['no'] or '-'}] {i['title']}")
            print(f"    {i['url']}")
        if not items:
            print("\n0건입니다. 실제로 없는 것일 수도 있고 파싱 실패일 수도 있으니")
            print("--dump 으로 fragment.html 을 받아 구조를 확인해 보세요.")
        return 0

    seen = load_seen()
    first_run = not STATE_FILE.exists()
    new = [i for i in items if key_of(i) not in seen]

    if first_run and os.getenv("FIRST_RUN_NOTIFY") != "1":
        save_seen({key_of(i) for i in items})
        print(f"최초 실행: 기존 {len(items)}건을 기준선으로 저장했습니다.")
        return 0

    if not new:
        print(f"신규 없음 (매칭 {len(items)}건)")
        return 0

    lines = [f"🎬 메가박스 신규 이벤트 — {', '.join(KEYWORDS)}", ""]
    for i in new:
        lines.append(f"• {i['title']}\n  {i['url']}")
    notify("\n".join(lines))

    seen.update(key_of(i) for i in new)
    save_seen(seen)
    print(f"신규 {len(new)}건 알림 전송")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
