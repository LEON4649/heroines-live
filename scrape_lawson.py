import json
import re
import time
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup


# =========================
# 設定
# =========================

OUTPUT = Path("events_lawson.json")

START = date.today()
END = date(2027, 1, 31)

# 最初はHEROINES主要グループを対象にします
ARTISTS = [
    "iLiFE!",
    "夜光性アミューズ",
    "のんふぃく！",
    "iON!",
    "MEGAFON",
]

BASE_URL = "https://l-tike.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
}


# =========================
# 共通処理
# =========================

def clean_text(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def parse_date(text):
    """
    ローチケの
    2026/10/10(土)
    2026/10/10(土)・2026/10/11(日)
    などから最初の日付を取得
    """
    if not text:
        return None

    match = re.search(r"(20\d{2})[年/.-](\d{1,2})[月/.-](\d{1,2})", text)

    if not match:
        return None

    try:
        return date(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
        )
    except ValueError:
        return None


def classify_area(text):
    text = clean_text(text)

    if "北海道" in text:
        if any(word in text for word in ["札幌", "Zepp Sapporo", "ペニーレーン"]):
            return "北海道・札幌"
        return "北海道"

    if "東京都" in text or "東京" in text:
        return "東京"

    return ""


def is_target_area(text):
    return bool(classify_area(text))


def get_status(text):
    text = clean_text(text)

    if "受付終了" in text:
        return "受付終了"

    if "予定枚数終了" in text:
        return "予定枚数終了"

    if "発売中" in text:
        return "販売中"

    if "本日発売" in text:
        return "販売中"

    if "発売前" in text:
        return "発売前"

    if "受付中" in text:
        return "販売中"

    return "販売情報あり"


def make_event_id(group, event_date, title, venue):
    raw = f"{group}-{event_date}-{title}-{venue}"
    return re.sub(r"[^a-zA-Z0-9_-]", "-", raw).strip("-").lower()


# =========================
# ローチケ検索
# =========================

def search_lawson(artist):

    url = f"{BASE_URL}/search/?keyword={quote(artist)}"

    print(f"検索中: {artist}")
    print(url)

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30,
        )
        response.raise_for_status()
    except Exception as e:
        print(f"取得失敗: {artist} / {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    events = []

    # ローチケ内のリンクを確認
    links = soup.find_all("a", href=True)

    seen_urls = set()

    for link in links:

        href = link.get("href", "")
        text = clean_text(link.get_text(" ", strip=True))

        if not href:
            continue

        # ローチケのイベント詳細らしきページ
        if "/event/" not in href and "/l-tike/" not in href:
            continue

        full_url = urljoin(BASE_URL, href)

        if full_url in seen_urls:
            continue

        seen_urls.add(full_url)

        # 周辺の情報を取得
        parent = link

        for _ in range(5):
            if parent.parent:
                parent = parent.parent

        block_text = clean_text(parent.get_text(" ", strip=True))

        if len(block_text) < 20:
            continue

        event_date = parse_date(block_text)

        if not event_date:
            continue

        if event_date < START or event_date > END:
            continue

        if not is_target_area(block_text):
            continue

        area = classify_area(block_text)

        # タイトル候補
        title = text

        if len(title) < 3:
            continue

        # 明らかな検索ページ内の不要リンクを除外
        bad_words = [
            "詳細はこちら",
            "お申し込みはこちら",
            "お気に入り",
            "ログイン",
            "会員登録",
        ]

        if title in bad_words:
            continue

        # 会場
        venue = ""

        prefectures = [
            "北海道",
            "東京都",
        ]

        lines = [
            clean_text(x)
            for x in parent.stripped_strings
        ]

        for line in lines:
            if any(pref in line for pref in prefectures):
                venue = line
                break

        status = get_status(block_text)

        event = {
            "id": make_event_id(
                artist,
                event_date.isoformat(),
                title,
                venue,
            ),
            "date": event_date.isoformat(),
            "group": artist,
            "title": title,
            "venue": venue,
            "area": area,
            "status": status,
            "sources": [
                {
                    "name": "ローチケ",
                    "url": full_url,
                }
            ],
        }

        events.append(event)

    return events


# =========================
# 重複除去
# =========================

def remove_duplicates(events):

    result = []
    seen = set()

    for event in events:

        key = (
            event.get("group", ""),
            event.get("date", ""),
            event.get("title", ""),
            event.get("venue", ""),
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(event)

    return result


# =========================
# メイン処理
# =========================

def main():

    all_events = []

    for artist in ARTISTS:

        try:
            events = search_lawson(artist)

            print(
                f"{artist}: {len(events)}件"
            )

            all_events.extend(events)

        except Exception as e:
            print(
                f"{artist}でエラー: {e}"
            )

        # ローチケへのアクセス間隔
        time.sleep(2)

    all_events = remove_duplicates(all_events)

    all_events.sort(
        key=lambda x: (
            x.get("date", ""),
            x.get("group", ""),
            x.get("title", ""),
        )
    )

    OUTPUT.write_text(
        json.dumps(
            all_events,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("==========================")
    print("ローチケ取得完了")
    print(f"取得件数: {len(all_events)}")
    print(f"保存先: {OUTPUT}")
    print("==========================")


if __name__ == "__main__":
    main()
