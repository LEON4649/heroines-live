import json
import re
import time
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

OUT = Path("events.json")
START = date.today()
END = date(2027, 1, 31)

# HEROINES系の主要TicketDiveアーティストページ。
ARTISTS = {
    "iLiFE!": "https://ticketdive.com/artist/ilife",
    "のんふぃく！": "https://ticketdive.com/artist/nonfic",
    "iON!": "https://ticketdive.com/artist/DLANELNRJncMgjnC532y",
    "MEGAFON": "https://ticketdive.com/artist/ENSGpvKOzkAKj5rblRJF",
    "夜光性アミューズ": "https://ticketdive.com/artist/yoruami",
    "Ill": "https://ticketdive.com/artist/ill",
    "ドレスコード": "https://ticketdive.com/artist/hPx13jnctQ1PwOpkPrxk",
    "TENRIN": "https://ticketdive.com/artist/tenrin",
    "AdamLilith": "https://ticketdive.com/artist/adamlilith",
    "chuLa": "https://ticketdive.com/artist/chula",
    "i-COL": "https://ticketdive.com/artist/i-col",
    "ナナコロビヤオキ": "https://ticketdive.com/artist/nanakoro",
    "ラストシーン": "https://ticketdive.com/artist/SAdbWuWpsZLnWhDj8Q97",
    "テンシンランマン": "https://ticketdive.com/artist/trFw4t9dKKVglWUotkKw",
    "ヒロインズ研究生": "https://ticketdive.com/artist/heroines-kenkyusei",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; HEROINES-LIVE-Bot/2.0)"}

TOKYO_WORDS = [
    "東京", "渋谷", "新宿", "池袋", "六本木", "豊洲", "立川", "品川", "台場",
    "高輪", "中野", "恵比寿", "大塚", "表参道", "原宿", "青山", "秋葉原",
    "有明", "汐留", "銀座", "新木場", "お台場", "WOMB", "O-EAST", "O-WEST",
    "O-nest", "O-Crest", "Zepp DiverCity", "Zepp Haneda", "ステラボール",
    "東京ガーデンシアター", "豊洲PIT", "Kanadevia Hall", "Spotify O-", "Veats",
]
HOKKAIDO_WORDS = ["北海道", "札幌", "小樽", "旭川", "函館", "Zepp Sapporo", "GOLD STONE"]


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def classify(title):
    t = (title or "").lower()
    types = []
    if any(k in t for k in ["生誕", "birthday", "バースデー"]):
        types.append("birthday")
    if any(k in t for k in ["卒業", "graduation", "卒業公演"]):
        types.append("graduation")
    if any(k in t for k in ["ワンマン", "one-man", "oneman", "単独公演"]):
        types.append("oneman")
    if any(k in t for k in ["ツアー", "tour"]):
        types.append("tour")
    if any(k in t for k in ["fes", "festival", "フェス", "主催", "league", "silver", "white", "summer", "halloween"]):
        types.append("festival")
    return types or ["other"]


def parse_ymd(text):
    m = re.search(r"(20\d{2})[/.](\d{1,2})[/.](\d{1,2})", text or "")
    if not m:
        return None
    try:
        d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return d if START <= d <= END else None
    except ValueError:
        return None


def parse_md(text, default_year):
    m = re.search(r"(?<!\d)(\d{1,2})[./](\d{1,2})(?!\d)", text or "")
    if not m:
        return None
    try:
        d = date(default_year, int(m.group(1)), int(m.group(2)))
        if d < START and d.month == 1:
            d = date(default_year + 1, d.month, d.day)
        return d if START <= d <= END else None
    except ValueError:
        return None


def area_for(venue, surrounding_text=""):
    v = clean(venue)
    s = f"{v} {surrounding_text}"
    if any(k in s for k in HOKKAIDO_WORDS):
        if "小樽" in s or "GOLD STONE" in s:
            return "北海道・小樽"
        if "札幌" in s or "Zepp Sapporo" in s:
            return "北海道・札幌"
        return "北海道"
    if any(k in s for k in TOKYO_WORDS):
        return "東京"
    return None


def status_from(text):
    if "受付終了" in text or "販売終了" in text:
        return "受付終了"
    if "申込受付中" in text or "販売中" in text or "一般発売" in text or "受付中" in text:
        return "販売中"
    return "要確認"


def title_from(soup, fallback):
    title = clean(soup.title.get_text(" ", strip=True) if soup.title else "")
    title = re.sub(r"\s*\|\s*TicketDive.*$", "", title).strip()
    return title or fallback


def parse_ticket_blocks(soup, page_url, fallback_group):
    """Parse individual TicketDive ticket sections so multi-city tours can be split."""
    text = soup.get_text("\n", strip=True)
    lines = [clean(x) for x in text.splitlines() if clean(x)]
    page_title = title_from(soup, fallback_group)

    # Overall year from the event's published date range, otherwise current year.
    year_match = re.search(r"公演日時\s*(20\d{2})/", text)
    default_year = int(year_match.group(1)) if year_match else START.year

    results = []
    for i, line in enumerate(lines):
        md = re.fullmatch(r"(\d{1,2})[./](\d{1,2})(?:\s+\d{1,2}:\d{2})?", line)
        if not md:
            continue
        d = parse_md(line, default_year)
        if not d:
            continue

        window = lines[i + 1:i + 8]
        joined = " / ".join(window)
        venue = ""
        # Common TicketDive order: date/time -> status -> section name -> venue.
        for candidate in window:
            if any(k in candidate for k in ["受付中", "受付終了", "販売中", "販売終了", "一般販売", "先行"]):
                continue
            if len(candidate) > 1 and not re.search(r"^\d{1,2}[./]\d{1,2}", candidate):
                # Venue-like line. Avoid generic labels.
                if not any(k in candidate for k in ["TICKET INFO", "詳細", "選択する", "注意事項", "販売情報"]):
                    venue = candidate
                    break
        area = area_for(venue, joined)
        if not area:
            continue

        # Status should be taken from the section, not the page as a whole.
        section_status = status_from(joined)
        results.append({
            "date": d.isoformat(),
            "group": fallback_group,
            "title": page_title,
            "venue": venue,
            "area": area,
            "status": section_status,
            "source": "TicketDive",
            "url": page_url,
            "types": classify(page_title),
            "auto": True,
        })

    if results:
        return results

    # Fallback for simple one-day pages.
    overall = clean(text)
    d = parse_ymd(overall)
    if not d:
        return []
    venue = ""
    m = re.search(r"会場\s*([^\n]+)", text)
    if m:
        venue = clean(m.group(1))
    area = area_for(venue, overall)
    if not area:
        return []
    return [{
        "date": d.isoformat(),
        "group": fallback_group,
        "title": page_title,
        "venue": venue,
        "area": area,
        "status": status_from(overall),
        "source": "TicketDive",
        "url": page_url,
        "types": classify(page_title),
        "auto": True,
    }]


def event_key(e):
    return (e.get("date", ""), clean(e.get("title", "")).lower(), clean(e.get("venue", "")).lower())


def merge_events(existing, found):
    by_key = {}
    # Existing manual records first.
    for e in existing:
        if not isinstance(e, dict):
            continue
        k = event_key(e)
        if k[0]:
            by_key[k] = e

    # Fresh auto data wins over stale/manual duplicate records with same key.
    for e in found:
        k = event_key(e)
        if not k[0]:
            continue
        if k in by_key:
            old = by_key[k]
            groups = []
            for g in [old.get("group", ""), e.get("group", "")]:
                for part in re.split(r"\s*/\s*", g):
                    if part and part not in groups:
                        groups.append(part)
            e["group"] = " / ".join(groups[:6]) + (" / ほか" if len(groups) > 6 else "")
        by_key[k] = e

    out = list(by_key.values())
    out.sort(key=lambda x: (x.get("date", "9999-99-99"), x.get("venue", ""), x.get("title", "")))
    return out


def main():
    found = []
    seen_urls = set()

    for group, artist_url in ARTISTS.items():
        try:
            soup = BeautifulSoup(get(artist_url), "html.parser")
            event_urls = []
            for a in soup.find_all("a", href=True):
                href = urljoin(artist_url, a["href"])
                if "/event/" in href and href not in event_urls:
                    event_urls.append(href)

            for url in event_urls:
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                try:
                    page = BeautifulSoup(get(url), "html.parser")
                    found.extend(parse_ticket_blocks(page, url, group))
                except Exception as e:
                    print("event failed:", url, e)
                time.sleep(0.25)
        except Exception as e:
            print("artist fetch failed:", group, e)

    existing = []
    if OUT.exists():
        try:
            existing = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            existing = []

    merged = merge_events(existing, found)
    OUT.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"updated {OUT}: {len(merged)} events ({len(found)} Tokyo/Hokkaido event instances discovered)")


if __name__ == "__main__":
    main()
