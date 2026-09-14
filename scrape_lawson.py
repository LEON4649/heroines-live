import json
import re
import time
from datetime import date
from urllib.parse import quote

import requests


# ============================================================
# HEROINES LIVE - Lawson Ticket collector
# Jina Reader経由でローチケの検索ページを取得
# ============================================================

OUTPUT_FILE = "events_lawson.json"

TODAY = date.today()
END_DATE = date(2027, 1, 31)

ARTISTS = [
    "iLiFE!",
    "夜光性アミューズ",
    "のんふぃく！",
    "iON!",
    "MEGAFON",
]

JINA_BASE = "https://r.jina.ai/https://l-tike.com/search/?keyword="

HEADERS = {
    "User-Agent": "HEROINES-LIVE/1.0"
}

HOKKAIDO_WORDS = [
    "北海道",
    "札幌",
    "小樽",
    "旭川",
    "函館",
    "帯広",
    "苫小牧",
]

TOKYO_WORDS = [
    "東京都",
    "東京",
    "渋谷",
    "新宿",
    "池袋",
    "秋葉原",
    "六本木",
    "お台場",
]


def normalize(text):
    """文字列を比較しやすい形にする"""
    if not text:
        return ""

    text = text.replace("　", " ")
    text = text.replace("！", "!")
    text = text.replace("（", "(")
    text = text.replace("）", ")")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def classify_area(text):
    """北海道・東京だけを対象にする"""
    text = normalize(text)

    if any(word in text for word in HOKKAIDO_WORDS):
        if "札幌" in text:
            return "北海道・札幌"
        if "小樽" in text:
            return "北海道・小樽"
        return "北海道"

    if any(word in text for word in TOKYO_WORDS):
        return "東京"

    return None


def parse_date(text):
    """
    ローチケの
    2026/10/10(土)
    2026/10/10(土)・2026/10/11(日)
    10.30 金曜日
    などをできるだけ拾う
    """

    if not text:
        return None

    text = normalize(text)

    # YYYY/MM/DD
    m = re.search(r"(20\d{2})[/-](\d{1,2})[/-](\d{1,2})", text)

    if m:
        try:
            y = int(m.group(1))
            mo = int(m.group(2))
            d = int(m.group(3))
            return date(y, mo, d)
        except ValueError:
            pass

    # MM/DD
    m = re.search(r"(?<!\d)(\d{1,2})/(\d{1,2})(?!\d)", text)

    if m:
        mo = int(m.group(1))
        d = int(m.group(2))

        year = TODAY.year

        try:
            result = date(year, mo, d)

            if result < TODAY:
                result = date(year + 1, mo, d)

            return result
        except ValueError:
            pass

    # MM.DD
    m = re.search(r"(?<!\d)(\d{1,2})\.(\d{1,2})(?!\d)", text)

    if m:
        mo = int(m.group(1))
        d = int(m.group(2))

        year = TODAY.year

        try:
            result = date(year, mo, d)

            if result < TODAY:
                result = date(year + 1, mo, d)

            return result
        except ValueError:
            pass

    return None


def status_from_text(text):
    text = normalize(text)

    if "受付終了" in text:
        return "受付終了"

    if "予定枚数終了" in text:
        return "予定枚数終了"

    if "発売中" in text:
        return "発売中"

    if "受付中" in text:
        return "受付中"

    if "抽選" in text:
        return "抽選"

    if "先着" in text:
        return "先着"

    return ""


def fetch_with_jina(url):
    """
    Jina Readerを使って対象ページを取得
    """

    jina_url = "https://r.jina.ai/" + url

    print("")
    print("取得:")
    print(url)

    for attempt in range(1, 4):

        try:
            response = requests.get(
                jina_url,
                headers=HEADERS,
                timeout=(20, 60)
            )

            print("HTTP:", response.status_code)

            if response.status_code == 200:
                return response.text

            print("取得失敗:", response.status_code)

        except requests.RequestException as e:
            print("通信エラー:", e)

        if attempt < 3:
            time.sleep(5)

    return ""


def extract_events(markdown, artist):
    """
    Jina Readerが返したMarkdownから
    ローチケのイベント情報を抽出
    """

    if not markdown:
        return []

    lines = [
        normalize(line)
        for line in markdown.splitlines()
    ]

    lines = [line for line in lines if line]

    events = []

    current_title = ""
    current_date_text = ""
    current_venue = ""
    current_block = []

    def flush_event():
        nonlocal current_title
        nonlocal current_date_text
        nonlocal current_venue
        nonlocal current_block

        if not current_title:
            return

        block_text = " ".join(current_block)

        # 日付
        event_date = parse_date(
            current_date_text + " " + block_text
        )

        if not event_date:
            return

        if event_date < TODAY or event_date > END_DATE:
            return

        # 会場・地域
        area_text = current_venue + " " + block_text

        area = classify_area(area_text)

        if not area:
            return

        # タイトル
        title = current_title

        # Markdownの見出し記号などを除去
        title = re.sub(r"^#+\s*", "", title)
        title = title.strip()

        if not title:
            return

        # 明らかにアーティスト名一覧などの場合は除外
        if title in [
            artist,
            "検索結果",
            "チケット",
            "アーティスト",
        ]:
            return

        status = status_from_text(block_text)

        events.append(
            {
                "date": event_date.isoformat(),
                "group": artist,
                "title": title,
                "venue": current_venue,
                "area": area,
                "status": status,
                "source": "ローチケ",
                "url": current_url,
            }
        )

    # ローチケ検索ページの構造をざっくり解析
    for line in lines:

        # 見出し
        if line.startswith("# "):
            flush_event()

            current_title = line[2:].strip()
            current_date_text = ""
            current_venue = ""
            current_block = []

            continue

        # 公演日
        if "公演日：" in line or line.startswith("公演日"):
            current_date_text = line
            current_block.append(line)
            continue

        # 会場
        if "会場：" in line or line.startswith("会場"):
            current_venue = re.sub(
                r"^会場：?",
                "",
                line
            ).strip()

            current_block.append(line)
            continue

        # 販売情報など
        current_block.append(line)

    flush_event()

    return events


def deduplicate(events):
    """同一公演を重複排除"""

    result = []
    seen = set()

    for event in events:

        key = (
            event.get("date", ""),
            event.get("group", ""),
            event.get("title", ""),
            event.get("venue", ""),
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(event)

    return result


def load_existing():
    try:
        with open(
            OUTPUT_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            return json.load(f)

    except Exception:
        return []


def main():

    print("====================================")
    print("HEROINES LIVE - Lawson collector")
    print("Jina Reader mode")
    print("====================================")

    all_events = []

    global current_url

    for artist in ARTISTS:

        print("")
        print("====================================")
        print("検索中:", artist)
        print("====================================")

        keyword = quote(artist)

        current_url = (
            "https://l-tike.com/search/?keyword="
            + keyword
        )

        markdown = fetch_with_jina(current_url)

        if not markdown:
            print("取得できませんでした:", artist)
            continue

        events = extract_events(
            markdown,
            artist
        )

        print(
            "検出:",
            len(events),
            "件"
        )

        all_events.extend(events)

        # Jinaへの連続アクセスを少し空ける
        time.sleep(2)

    all_events = deduplicate(all_events)

    print("")
    print("====================================")
    print("最終結果:", len(all_events), "件")
    print("====================================")

    # 何も取得できなかった場合、
    # 既存データを消さない
    if not all_events:

        existing = load_existing()

        if existing:
            print(
                "新規取得0件のため、"
                "既存のevents_lawson.jsonを保持します。"
            )
            return

        print("イベントを取得できませんでした。")
        return

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            all_events,
            f,
            ensure_ascii=False,
            indent=2
        )

    print("")
    print("保存完了:", OUTPUT_FILE)


if __name__ == "__main__":
    main()
