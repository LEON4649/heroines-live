import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://heroines.jp"
NEWS_URL = "https://heroines.jp/news"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    )
}

START_DATE = date.today()
END_DATE = date(2027, 1, 31)


def fetch(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )
    response.raise_for_status()
    return response.text


def parse_date(text):
    patterns = [
        r"(20\d{2})[./年-](\d{1,2})[./月-](\d{1,2})",
        r"(20\d{2})年(\d{1,2})月(\d{1,2})日",
    ]

    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            try:
                return date(
                    int(m.group(1)),
                    int(m.group(2)),
                    int(m.group(3))
                )
            except ValueError:
                pass

    return None


def classify_area(text):
    if "札幌" in text or "北海道" in text:
        return "北海道・札幌"

    if "小樽" in text:
        return "北海道・小樽"

    if "東京" in text or "渋谷" in text or "新宿" in text:
        return "東京"

    return ""


def clean_text(text):
    return re.sub(r"\s+", " ", text).strip()


def main():
    print("HEROINES公式サイトを取得中...")
    print(NEWS_URL)

    html = fetch(NEWS_URL)
    soup = BeautifulSoup(html, "html.parser")

    links = []

    for a in soup.find_all("a", href=True):
        href = urljoin(BASE_URL, a["href"])
        title = clean_text(a.get_text(" ", strip=True))

        if "/news/public/" in href:
            if href not in [x["url"] for x in links]:
                links.append({
                    "url": href,
                    "title": title
                })

    print("NEWS記事候補:", len(links))

    events = []

    for item in links[:100]:
        try:
            article_html = fetch(item["url"])
            article = BeautifulSoup(article_html, "html.parser")

            text = clean_text(article.get_text(" ", strip=True))

            event_date = parse_date(text)

            if not event_date:
                continue

            if event_date < START_DATE or event_date > END_DATE:
                continue

            title = item["title"]

            if not title:
                title_tag = article.find("h1")
                if title_tag:
                    title = clean_text(
                        title_tag.get_text(" ", strip=True)
                    )

            area = classify_area(text)

            venue = ""

            venue_patterns = [
                r"@\s*([^\n@]+)",
                r"会場\s*[:：]\s*([^\n]+)",
            ]

            for pattern in venue_patterns:
                m = re.search(pattern, text)
                if m:
                    venue = clean_text(m.group(1))
                    break

            events.append({
                "date": event_date.isoformat(),
                "group": "HEROINES",
                "title": title,
                "venue": venue,
                "area": area,
                "status": "",
                "source": "HEROINES公式サイト",
                "url": item["url"]
            })

            print(
                "取得:",
                event_date.isoformat(),
                title
            )

        except Exception as e:
            print("取得失敗:", item["url"], e)

    output = Path("events_heroines.json")

    with output.open("w", encoding="utf-8") as f:
        json.dump(
            events,
            f,
            ensure_ascii=False,
            indent=2
        )

    print()
    print("HEROINES公式イベント:", len(events), "件")
    print("保存:", output)


if __name__ == "__main__":
    main()
