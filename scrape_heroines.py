import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://heroines.jp"
SEARCH_URL = "https://search.yahoo.co.jp/search"

START_DATE = date.today()
END_DATE = date(2027, 1, 31)

ARTISTS = [
    "iLiFE!",
    "のんふぃく！",
    "夜光性アミューズ",
    "iON!",
    "MEGAFON",
    "HEROINES"
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    )
}


def fetch(url, timeout=30):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=timeout
    )
    response.raise_for_status()
    return response.text


def clean(text):
    return re.sub(r"\s+", " ", text).strip()


def parse_date_string(y, m, d):
    try:
        return date(int(y), int(m), int(d))
    except ValueError:
        return None


def find_dates(text):
    patterns = [
        r"(20\d{2})[./年-](\d{1,2})[./月-](\d{1,2})",
        r"(20\d{2})年(\d{1,2})月(\d{1,2})日",
    ]

    found = []

    for pattern in patterns:
        for match in re.finditer(pattern, text):
            d = parse_date_string(
                match.group(1),
                match.group(2),
                match.group(3)
            )

            if d and START_DATE <= d <= END_DATE:
                if d not in found:
                    found.append(d)

    return sorted(found)


def classify_area(text):
    if "札幌" in text or "北海道" in text:
        return "北海道・札幌"

    if "小樽" in text:
        return "北海道・小樽"

    if "東京" in text or "渋谷" in text or "新宿" in text:
        return "東京"

    return ""


def guess_venue(text):
    venue_patterns = [
        r"@\s*([^\n]+)",
        r"会場\s*[:：]\s*([^\n]+)",
        r"会場\s+([^\n]+)",
    ]

    for pattern in venue_patterns:
        match = re.search(pattern, text)

        if match:
            venue = clean(match.group(1))

            venue = re.split(
                r"\b(?:OPEN|START|開場|開演)\b",
                venue
            )[0]

            venue = venue.strip(" 　@")

            if len(venue) <= 100:
                return venue

    known_venues = [
        "Zepp Sapporo",
        "PENNY LANE24",
        "小樽GOLD STONE",
        "Zepp Haneda",
        "Zepp DiverCity",
        "KT Zepp Yokohama",
        "Ebisu Garden Hall",
        "Kanadevia Hall",
        "幕張メッセ",
    ]

    for venue in known_venues:
        if venue in text:
            return venue

    return ""


def guess_group(title, text):
    combined = title + " " + text

    for artist in ARTISTS:
        if artist in combined:
            return artist

    return "HEROINES"


def search_yahoo(query):
    params = {
        "p": query
    }

    response = requests.get(
        SEARCH_URL,
        params=params,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    urls = []

    for a in soup.find_all("a", href=True):
        href = a["href"]

        if "heroines.jp/news/public/" not in href:
            continue

        if href.startswith("/"):
            href = urljoin(
                "https://search.yahoo.co.jp",
                href
            )

        parsed = urlparse(href)

        if parsed.netloc == "search.yahoo.co.jp":
            qs = parse_qs(parsed.query)

            if "url" in qs:
                href = qs["url"][0]

        if href.startswith(BASE_URL):
            if href not in urls:
                urls.append(href)

    return urls


def get_title(soup):
    h1 = soup.find("h1")

    if h1:
        title = clean(
            h1.get_text(" ", strip=True)
        )

        if title and title != "NEWS":
            return title

    title_tag = soup.find("title")

    if title_tag:
        title = clean(
            title_tag.get_text(" ", strip=True)
        )

        title = re.sub(
            r"\s*\|\s*HEROINES.*$",
            "",
            title
        )

        return title

    return "HEROINES EVENT"


def main():
    print("HEROINES公式NEWSを検索中...")

        
article_urls = []
queries = []

months = [
        "2026年9月",
        "2026年10月",
        "2026年11月",
        "2026年12月",
        "2027年1月",
    ]

for artist in ARTISTS:
        for month in months:
            queries.append(
                f'site:heroines.jp/news/public/_/ "{artist}" "{month}"'
            )

        queries.append(
            f'site:heroines.jp/news/public/_/ "{artist}" "札幌"'
        )

        queries.append(
            f'site:heroines.jp/news/public/_/ "{artist}" "北海道"'
        )

        queries.append(
            f'site:heroines.jp/news/public/_/ "{artist}" "東京"'
        )

    queries.append(
        'site:heroines.jp/news/public/_/ "2026年9月" "札幌"'
    )

    queries.append(
        'site:heroines.jp/news/public/_/ "2026年10月" "札幌"'
    )

    queries.append(
        'site:heroines.jp/news/public/_/ "2026年11月" "札幌"'
    )

    queries.append(
        'site:heroines.jp/news/public/_/ "2026年12月" "札幌"'
    )

    queries.append(
        'site:heroines.jp/news/public/_/ "2027年1月" "札幌"'
    )

    for query in queries:
        try:
            print()
            print("検索:", query)

            urls = search_yahoo(query)

            print("記事:", len(urls))

            for url in urls:
                if url not in article_urls:
                    article_urls.append(url)

        except Exception as e:
            print("検索失敗:", e)

    print()
    print("公式NEWS記事候補:", len(article_urls))

    events = []

    for url in article_urls[:80]:
        try:
            print()
            print("取得:", url)

            html = fetch(url)

            soup = BeautifulSoup(
                html,
                "html.parser"
            )

            title = get_title(soup)

            text = soup.get_text(
                "\n",
                strip=True
            )

            text = re.sub(
                r"[ \t]+",
                " ",
                text
            )

            dates = find_dates(text)

            if not dates:
                print("未来の公演日なし")
                continue

            group = guess_group(
                title,
                text
            )

            area = classify_area(text)

            venue = guess_venue(text)

            for event_date in dates:
                events.append({
                    "date": event_date.isoformat(),
                    "group": group,
                    "title": title,
                    "venue": venue,
                    "area": area,
                    "status": "",
                    "source": "HEROINES公式サイト",
                    "url": url
                })

                print(
                    "イベント:",
                    event_date.isoformat(),
                    group,
                    title,
                    venue,
                    area
                )

        except Exception as e:
            print(
                "記事取得失敗:",
                url,
                e
            )

    unique = {}

    for event in events:
        key = (
            event["date"],
            event["group"],
            event["title"],
            event["venue"]
        )

        unique[key] = event

    events = list(unique.values())

    events.sort(
        key=lambda x: (
            x["date"],
            x["group"],
            x["title"]
        )
    )

    output = Path(
        "events_heroines.json"
    )

    with output.open(
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            events,
            f,
            ensure_ascii=False,
            indent=2
        )

    print()
    print(
        "HEROINES公式イベント:",
        len(events),
        "件"
    )

    print(
        "保存:",
        output
    )


if __name__ == "__main__":
    main()
