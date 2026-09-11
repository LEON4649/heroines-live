import json, re, time
from datetime import date
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

OUT = Path("events.json")
START = date.today()
END = date(2027, 1, 31)

ARTISTS = {
    "のんふぃく！": "https://ticketdive.com/artist/nonfic",
    "iON!": "https://ticketdive.com/artist/DLANELNRJncMgjnC532y",
    "MEGAFON": "https://ticketdive.com/artist/ENSGpvKOzkAKj5rblRJF",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; HEROINES-LIVE-Bot/1.0)"}

def get(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text

def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()

def classify(title):
    t = title.lower()
    types = []
    if any(k in t for k in ["生誕", "birthday", "バースデー"]): types.append("birthday")
    if any(k in t for k in ["卒業", "graduation"]): types.append("graduation")
    if any(k in t for k in ["ワンマン", "one-man", "oneman"]): types.append("oneman")
    if any(k in t for k in ["ツアー", "tour"]): types.append("tour")
    if any(k in t for k in ["fes", "festival", "フェス", "主催", "league", "silver", "summer"]): types.append("festival")
    return types or ["other"]

def parse_date(text):
    m = re.search(r"(20\d{2})/(\d{1,2})/(\d{1,2})", text)
    if not m: return None
    try:
        d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return d if START <= d <= END else None
    except ValueError:
        return None

def parse_event(url, fallback_group):
    soup = BeautifulSoup(get(url), "html.parser")
    text = clean(soup.get_text(" ", strip=True))
    d = parse_date(text)
    if not d: return None

    # TicketDive pages expose these labels in visible text.
    title = clean(soup.title.get_text() if soup.title else "") or fallback_group
    title = re.sub(r"\s*\|\s*TicketDive.*$", "", title).strip()

    venue = ""
    m = re.search(r"会場\s*([^\n]+?)(?:\s+出演|\s+TICKET INFO|$)", text)
    if m: venue = clean(m.group(1))

    status = "販売中" if "販売中" in text else ("受付終了" if "受付終了" in text else "要確認")

    # Prefer a clear artist/group name from the page source context.
    group = fallback_group

    area = "東京" if any(k in venue for k in ["東京", "渋谷", "新宿", "池袋", "六本木", "豊洲", "立川", "品川", "台場", "高輪", "中野", "恵比寿"]) else \
           "北海道・札幌" if "札幌" in venue or "Zepp Sapporo" in venue else \
           "北海道・小樽" if "小樽" in venue else \
           "北海道" if "北海道" in text else "その他"

    return {
        "date": d.isoformat(),
        "group": group,
        "title": title,
        "venue": venue,
        "area": area,
        "status": status,
        "source": "TicketDive",
        "url": url,
        "types": classify(title),
        "auto": True,
    }

def main():
    found = {}
    for group, artist_url in ARTISTS.items():
        try:
            soup = BeautifulSoup(get(artist_url), "html.parser")
            for a in soup.find_all("a", href=True):
                href = urljoin(artist_url, a["href"])
                if "/event/" not in href:
                    continue
                if href in found:
                    continue
                try:
                    ev = parse_event(href, group)
                    if ev:
                        found[href] = ev
                    time.sleep(0.3)
                except Exception:
                    continue
        except Exception as e:
            print("artist fetch failed:", group, e)

    existing = []
    if OUT.exists():
        try: existing = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception: existing = []

    # Keep hand-entered records and replace prior auto records with fresh data.
    merged = [e for e in existing if not e.get("auto")]
    by_url = {e.get("url"): e for e in merged if e.get("url")}
    for e in found.values():
        by_url[e["url"]] = e
    merged = list(by_url.values())
    merged.sort(key=lambda x: x.get("date","9999-99-99"))
    OUT.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"updated {OUT}: {len(merged)} events ({len(found)} auto-discovered)")

if __name__ == "__main__":
    main()
