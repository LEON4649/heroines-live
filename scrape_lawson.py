import json
import re
from datetime import date, timedelta
from urllib.parse import quote

import requests


OUTPUT_FILE = "events_lawson.json"

TODAY = date.today()
END_DATE = date(2027, 1, 31)

ARTISTS = {
    "iLiFE!": "https://l-tike.com/artist/000000000915501/",
    "夜光性アミューズ": "https://l-tike.com/concert/mevent/?mid=668544",
    "のんふぃく！": "https://l-tike.com/artist/000000000941539/",
    "iON!": "https://l-tike.com/artist/000000001018590/",
    "MEGAFON": "https://l-tike.com/search/?keyword=MEGAFON",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    )
}


def jina_get(url):
    """Jina Reader経由でページを取得する"""
    jina_url = "https://r.jina.ai/" + url

    response = requests.get(
        jina_url,
        headers=HEADERS,
        timeout=(20, 60),
    )

    response.raise_for_status()

    return response.text


def normalize(text):
    text = text.replace("\u3000", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_date(text):
    """
    2026/10/10
    2026/10/10(土)
    10.10
    10.10(土)
    などを日付に変換
    """

    m = re.search(
        r"(20\d{2})[/.年-](\d{1,2})[/.月-](\d{1,2})",
        text
    )

    if m:
        try:
            return date(
                int(m.group(1)),
                int(m.group(2)),
                int(m.group(3))
            )
        except ValueError:
            return None

    m = re.search(
        r"(?<!\d)(\d{1,2})[./](\d{1,2})(?!\d)",
        text
    )

    if m:
        month = int(m.group(1))
        day = int(m.group(2))

        try:
            d = date(TODAY.year, month, day)

            if d < TODAY - timedelta(days=30):
                d = date(TODAY.year + 1, month, day)

            return d

        except ValueError:
            return None

    return None


def classify_area(text):
    """
    HEROINES LIVEでは北海道・東京を重点掲載。
    """

    if "北海道" in text:
        if "札幌" in text:
            return "北海道・札幌"
        if "小樽" in text:
            return "北海道・小樽"
        return "北海道"

    if "東京都" in text or "東京" in text:
        return "東京"

    return None


def get_status(text):
    if "受付終了" in text:
        return "受付終了"

    if "予定枚数終了" in text:
        return "予定枚数終了"

    if "発売中" in text or "受付中" in text:
        return "販売中"

    if "発売前" in text:
        return "発売前"

    if "抽選" in text:
        return "抽選"

    return "販売情報あり"


def clean_title(text):
    text = re.sub(r"^#+\s*", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return normalize(text)


def extract_events(markdown, artist, source_url):
    """
    Jina Readerが返すMarkdownから
    イベント見出し→日付→会場→販売状況
    を取得する。
    """

    lines = markdown.splitlines()

    events = []

    current_title = None
    current_lines = []

    def save_current():
        nonlocal current_title, current_lines

        if not current_title:
            return

        block = "\n".join(current_lines)
        clean_block = normalize(block)

        d = parse_date(clean_block)

        if not d:
            return

        if d < TODAY or d > END_DATE:
            return

        area = classify_area(clean_block)

        if not area:
            return

        status = get_status(clean_block)

        venue = ""

        venue_patterns = [
            r"会場[:：]\s*([^|]+)",
            r"会場\s+([^\n]+)",
        ]

        for pattern in venue_patterns:
            m = re.search(pattern, block)
            if m:
                venue = normalize(m.group(1))
                break

        # 会場が取れない場合は都道府県周辺から推測
        if not venue:
            for line in current_lines:
                line_clean = normalize(line)

                if (
                    "北海道" in line_clean
                    or "東京都" in line_clean
                ):
                    if len(line_clean) < 150:
                        venue = line_clean
                        break

        event = {
            "date": d.isoformat(),
            "group": artist,
            "title": current_title,
            "venue": venue,
            "area": area,
            "status": status,
            "source": "ローチケ",
            "url": source_url,
        }

        events.append(event)

    for line in lines:

        stripped = line.strip()

        # Markdownの見出しをイベント候補として扱う
        if stripped.startswith("### "):

            save_current()

            current_title = clean_title(stripped)
            current_lines = []

        elif current_title:

            current_lines.append(line)

            # 1イベントが長くなりすぎないようにする
            if len(current_lines) > 25:
                save_current()
                current_title = None
                current_lines = []

    save_current()

    return events


def remove_duplicates(events):
    unique = {}

    for event in events:

        key = (
            event["date"],
            event["group"],
            event["title"],
            event["venue"],
        )

        if key not in unique:
            unique[key] = event

    return list(unique.values())


def main():

    print("=" * 50)
    print("HEROINES LIVE - Lawson collector")
    print("Jina Reader + Artist Page mode")
    print("=" * 50)

    all_events = []

    for artist, url in ARTISTS.items():

        print()
        print("=" * 50)
        print("検索中:", artist)
        print("=" * 50)

        try:

            print("取得:", url)

            markdown = jina_get(url)

            print("HTTP: 200")
            print("文字数:", len(markdown))

            events = extract_events(
                markdown,
                artist,
                url
            )

            print("検出:", len(events), "件")

            all_events.extend(events)

        except Exception as e:

            print("取得失敗:", artist)
            print(type(e).__name__, str(e))

    all_events = remove_duplicates(all_events)

    all_events.sort(
        key=lambda x: (
            x["date"],
            x["group"],
            x["title"]
        )
    )

    print()
    print("=" * 50)
    print("最終結果:", len(all_events), "件")
    print("=" * 50)

    # 0件だった場合は既存データを残す
    if len(all_events) == 0:

        try:
            with open(
                OUTPUT_FILE,
                "r",
                encoding="utf-8"
            ) as f:
                old_events = json.load(f)

            print(
                "取得0件のため既存データを維持:",
                len(old_events),
                "件"
            )

            return

        except FileNotFoundError:

            print("既存データなし。空のJSONを作成します。")

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

    print("保存完了:", OUTPUT_FILE)


if __name__ == "__main__":
    main()
