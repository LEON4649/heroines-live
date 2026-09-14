import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup


ARTISTS = [
    "iLiFE!",
    "のんふぃく！",
    "夜光性アミューズ",
    "iON!",
    "MEGAFON",
]

START_DATE = date.today()
END_DATE = date(2027, 1, 31)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    )
}


def search_yahoo(query):
    url = (
        "https://search.yahoo.co.jp/search?p="
        + quote(query)
    )

    response = requests.get(
        url,
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

        if href not in urls:
            urls.append(href)

    return urls


def clean_text(text):
    return re.sub(
        r"\s+",
        " ",
        text
    ).strip()


def find_event_date(text):
    patterns = [
        r"(2026)[./年-](9|10|11|12)[./月-](\d{1,2})",
        r"(2027)[./年-](1)[./月-](\d{1,2})",
    ]

    for pattern in patterns:
        matches = re.findall(
            pattern,
            text
        )

        for match in matches:
            try:
                d = date(
                    int(match[0]),
                    int(match[1]),
                    int(match[2])
                )

                if START_DATE <= d <= END_DATE:
                    return d

            except ValueError:
                pass

    return None


def get_area(text):
    if "札幌" in text or "北海道" in text:
        return "北海道・札幌"

    if "小樽" in text:
        return "北海道・小樽"

    if "東京" in text or "渋谷" in text or "新宿" in text:
        return "東京"

    return ""


def get_venue(text):
    patterns = [
        r"会場[:：]\s*([^\s]+)",
        r"会場\s+([^\s]+)",
        r"＠\s*([^\s]+)",
        r"@\s*([^\s]+)",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            text
        )

        if match:
            return match.group(1)

    return ""


def get_title(soup):
    title = soup.find("h1")

    if title:
        return clean_text(
            title.get_text(
                " ",
                strip=True
            )
        )

    if soup.title:
        return clean_text(
            soup.title.get_text(
                " ",
                strip=True
            )
        )

    return "HEROINES EVENT"


def main():
    print("HEROINES公式NEWSを検索中...")

    article_urls = []

    for artist in ARTISTS:
        queries = [
            f'site:heroines.jp/news/public/_/ "{artist}"',
            f'site:heroines.jp/news/public/_/ "{artist}" "札幌"',
            f'site:heroines.jp/news/public/_/ "{artist}" "東京"',
        ]

        for query in queries:
            try:
                print()
                print("検索:", query)

                urls = search_yahoo(query)

                print(
                    "記事:",
                    len(urls)
                )

                for url in urls:
                    if url not in article_urls:
                        article_urls.append(url)

            except Exception as e:
                print(
                    "検索失敗:",
                    e
                )

    print()
    print(
        "公式NEWS記事候補:",
        len(article_urls)
    )

    events = []

    for url in article_urls[:80]:
        try:
            print()
            print("取得:", url)

            response = requests.get(
                url,
                headers=HEADERS,
                timeout=30
            )

            response.raise_for_status()

            soup = BeautifulSoup(
                response.text,
                "html.parser"
            )

            text = clean_text(
                soup.get_text(
                    " ",
                    strip=True
                )
            )

            event_date = find_event_date(text)

            if not event_date:
                print("未来の公演日なし")
                continue

            title = get_title(soup)
            area = get_area(text)
            venue = get_venue(text)

            event = {
                "date": event_date.isoformat(),
                "group": "HEROINES",
                "title": title,
                "venue": venue,
                "area": area,
                "status": "",
                "source": "HEROINES公式サイト",
                "url": url
            }

            duplicate = False

            for old in events:
                if (
                    old["date"] == event["date"]
                    and old["title"] == event["title"]
                    and old["url"] == event["url"]
                ):
                    duplicate = True
                    break

            if not duplicate:
                events.append(event)

        except Exception as e:
            print(
                "取得失敗:",
                e
            )

    events.sort(
        key=lambda x: x["date"]
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
