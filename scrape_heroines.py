import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup


# =========================================
# HEROINES LIVE
# HEROINES公式サイト イベント情報取得
# =========================================

BASE_URL = "https://heroines.jp"
OUTPUT_FILE = Path("events_heroines.json")

START_DATE = date.today()
END_DATE = date(2027, 1, 31)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

ARTISTS = [
    "iLiFE!",
    "夜光性アミューズ",
    "のんふぃく！",
    "iON!",
    "MEGAFON",
    "TENRIN",
    "ガガピエロ",
    "CUTIE STREET",
    "HEROINES",
]

AREA_KEYWORDS = {
    "北海道・札幌": [
        "札幌",
        "北海道",
        "PENNY LANE24",
        "Zepp Sapporo",
        "SPiCE",
        "cube garden",
        "Sound Lab mole",
    ],
    "北海道・小樽": [
        "小樽",
    ],
    "東京": [
        "東京",
        "渋谷",
        "新宿",
        "池袋",
        "秋葉原",
        "六本木",
        "品川",
        "恵比寿",
        "代官山",
        "下北沢",
        "吉祥寺",
        "中野",
        "原宿",
        "お台場",
        "Zepp DiverCity",
        "Zepp Shinjuku",
        "Zepp Haneda",
        "Spotify O-EAST",
        "Spotify O-WEST",
        "Spotify O-nest",
        "LIQUIDROOM",
        "KANDA SQUARE HALL",
        "EX THEATER ROPPONGI",
    ],
}


# =========================================
# HTTP
# =========================================

session = requests.Session()
session.headers.update(HEADERS)


def get_html(url):
    try:
        response = session.get(
            url,
            timeout=(15, 45),
        )

        response.raise_for_status()

        response.encoding = response.apparent_encoding or "utf-8"

        print(f"取得成功: {url}")
        print(f"HTTP: {response.status_code}")
        print(f"LENGTH: {len(response.text)}")

        return response.text

    except Exception as e:
        print(f"取得失敗: {url}")
        print(f"ERROR: {e}")
        return ""


# =========================================
# Yahoo検索
# =========================================

def search_yahoo(query):
    """
    Yahoo検索からHEROINES公式NEWSの記事URLを取得する
    """

    search_url = (
        "https://search.yahoo.co.jp/search?"
        f"p={quote(query)}"
    )

    html = get_html(search_url)

    if not html:
        return []

    urls = set()

    # HTML内からHEROINES公式NEWSの記事URLを直接抽出
    pattern = r"https://heroines\.jp/news/public/_/[a-zA-Z0-9]+\.html"

    for match in re.findall(pattern, html):
        urls.add(match)

    print(f"検索結果: {len(urls)}件")

    return sorted(urls)


# =========================================
# 公式NEWS記事URLを集める
# =========================================

def collect_article_urls():
    urls = set()

    months = [
        "2026年9月",
        "2026年10月",
        "2026年11月",
        "2026年12月",
        "2027年1月",
    ]

    for artist in ARTISTS:
        for month in months:

            query = (
                f'site:heroines.jp/news/public/_/ '
                f'"{artist}" "{month}"'
            )

            print()
            print("========================================")
            print("検索:", query)
            print("========================================")

            found = search_yahoo(query)

            for url in found:
                urls.add(url)

    # 公式サイトのトップページからも記事URLを探す
    print()
    print("公式サイトトップページを確認")

    home_html = get_html(BASE_URL + "/")

    if home_html:
        pattern = r"https://heroines\.jp/news/public/_/[a-zA-Z0-9]+\.html"

        for url in re.findall(pattern, home_html):
            urls.add(url)

    print()
    print("========================================")
    print(f"記事URL合計: {len(urls)}件")
    print("========================================")

    return sorted(urls)


# =========================================
# 日付
# =========================================

DATE_PATTERNS = [
    r"(?P<y>20\d{2})年(?P<m>\d{1,2})月(?P<d>\d{1,2})日",
    r"(?P<y>20\d{2})[./-](?P<m>\d{1,2})[./-](?P<d>\d{1,2})",
]


def extract_dates(text):
    results = []

    for pattern in DATE_PATTERNS:

        for match in re.finditer(pattern, text):

            try:
                y = int(match.group("y"))
                m = int(match.group("m"))
                d = int(match.group("d"))

                value = date(y, m, d)

                if START_DATE <= value <= END_DATE:
                    results.append(
                        {
                            "date": value,
                            "position": match.start(),
                        }
                    )

            except ValueError:
                pass

    # 重複除去
    unique = {}

    for item in results:
        key = (
            item["date"].isoformat(),
            item["position"],
        )

        unique[key] = item

    return list(unique.values())


# =========================================
# エリア判定
# =========================================

def detect_area(text):
    scores = {}

    for area, keywords in AREA_KEYWORDS.items():

        score = 0

        for keyword in keywords:

            if keyword in text:
                score += 1

        if score:
            scores[area] = score

    if not scores:
        return ""

    return max(
        scores,
        key=scores.get,
    )


# =========================================
# グループ判定
# =========================================

def detect_group(title, text):

    candidates = []

    for artist in ARTISTS:

        if artist in title:
            candidates.append(artist)

    if candidates:
        return candidates[0]

    for artist in ARTISTS:

        if artist in text:
            candidates.append(artist)

    if candidates:
        return candidates[0]

    return "HEROINES"


# =========================================
# 会場判定
# =========================================

VENUE_KEYWORDS = [
    "Zepp",
    "PENNY LANE24",
    "PENNY LANE",
    "cube garden",
    "SPiCE",
    "Sound Lab mole",
    "KANDA SQUARE HALL",
    "Spotify O-EAST",
    "Spotify O-WEST",
    "Spotify O-nest",
    "LIQUIDROOM",
    "EX THEATER",
    "BIGCAT",
    "なんばHatch",
    "Zepp Namba",
    "Zepp DiverCity",
    "Zepp Shinjuku",
    "Zepp Haneda",
    "Kanadevia Hall",
    "Hall",
    "HALL",
    "ホール",
    "ライブハウス",
]


def detect_venue(text):

    # 「会場：○○」形式
    patterns = [
        r"会場\s*[:：]\s*([^\n\r|]{2,80})",
        r"会場\s*[：:]\s*([^\n\r]{2,80})",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE,
        )

        if match:
            venue = match.group(1).strip()

            venue = re.sub(
                r"\s+",
                " ",
                venue,
            )

            return venue[:100]

    # 会場名キーワード
    for keyword in VENUE_KEYWORDS:

        if keyword in text:
            return keyword

    return ""


# =========================================
# ステータス
# =========================================

def detect_status(text):

    if "SOLD OUT" in text.upper():
        return "SOLD OUT"

    if "完売" in text:
        return "SOLD OUT"

    if "受付終了" in text:
        return "受付終了"

    if "販売中" in text:
        return "販売中"

    if "受付中" in text:
        return "受付中"

    if "一般発売" in text:
        return "一般発売"

    return ""


# =========================================
# 記事タイトル
# =========================================

def get_title(soup):

    h1 = soup.find("h1")

    if h1:
        title = h1.get_text(
            " ",
            strip=True,
        )

        if title:
            return title

    if soup.title:

        title = soup.title.get_text(
            " ",
            strip=True,
        )

        title = re.sub(
            r"\s*\|.*$",
            "",
            title,
        )

        return title.strip()

    return "HEROINES EVENT"


# =========================================
# 記事解析
# =========================================

def parse_article(url):

    print()
    print("----------------------------------------")
    print("記事解析:")
    print(url)
    print("----------------------------------------")

    html = get_html(url)

    if not html:
        return []

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    title = get_title(soup)

    # 不要なscript/styleを除去
    for tag in soup(
        ["script", "style", "noscript"]
    ):
        tag.decompose()

    text = soup.get_text(
        "\n",
        strip=True,
    )

    text = re.sub(
        r"\n+",
        "\n",
        text,
    )

    if not text:
        return []

    dates = extract_dates(text)

    if not dates:
        print("イベント日が見つかりません")
        return []

    events = []

    # 記事の先頭にある掲載日を避けるため、
    # 最初の数百文字を少し低く評価する
    for date_info in dates:

        event_date = date_info["date"]
        position = date_info["position"]

        # 日付周辺の文章
        start = max(
            0,
            position - 250,
        )

        end = min(
            len(text),
            position + 350,
        )

        context = text[start:end]

        area = detect_area(context)

        # Hokkaido / Tokyo以外は今回は対象外
        if not area:

            # 記事全体でも確認
            area = detect_area(text)

        if not area:
            continue

        # 日付周辺から会場を探す
        venue = detect_venue(context)

        if not venue:
            venue = detect_venue(text)

        group = detect_group(
            title,
            text,
        )

        status = detect_status(text)

        event = {
            "date": event_date.isoformat(),
            "group": group,
            "title": title,
            "venue": venue,
            "area": area,
            "status": status,
            "source": "HEROINES公式サイト",
            "url": url,
        }

        events.append(event)

    return events


# =========================================
# 重複除去
# =========================================

def remove_duplicates(events):

    unique = {}

    for event in events:

        key = (
            event.get("date", ""),
            event.get("group", ""),
            event.get("title", ""),
            event.get("venue", ""),
            event.get("area", ""),
        )

        unique[key] = event

    return list(unique.values())


# =========================================
# 保存
# =========================================

def save_events(events):

    events = remove_duplicates(events)

    events.sort(
        key=lambda x: (
            x.get("date", ""),
            x.get("group", ""),
            x.get("title", ""),
        )
    )

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            events,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print()
    print("========================================")
    print("保存完了")
    print("========================================")
    print(f"ファイル: {OUTPUT_FILE}")
    print(f"イベント数: {len(events)}")


# =========================================
# メイン
# =========================================

def main():

    print()
    print("========================================")
    print("HEROINES公式サイト イベント取得開始")
    print("========================================")

    article_urls = collect_article_urls()

    if not article_urls:
        raise RuntimeError(
            "HEROINES公式NEWSの記事URLを取得できませんでした"
        )

    all_events = []

    for url in article_urls:

        try:

            events = parse_article(url)

            print(
                f"検出イベント: {len(events)}件"
            )

            all_events.extend(events)

        except Exception as e:

            print(
                f"記事解析エラー: {url}"
            )

            print(
                f"ERROR: {e}"
            )

    all_events = remove_duplicates(
        all_events
    )

    if not all_events:

        raise RuntimeError(
            "イベントを1件も取得できませんでした。"
            "既存データを空にしないため保存を中止します。"
        )

    save_events(all_events)

    print()
    print("HEROINES公式サイトの取得完了！")
    print(
        f"最終イベント数: {len(all_events)}"
    )


if __name__ == "__main__":
    main()
