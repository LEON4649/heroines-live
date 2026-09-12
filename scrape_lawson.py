import json
import re
import time
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup


# ==========================================
# 設定
# ==========================================

OUTPUT = Path("events_lawson.json")

START = date.today()
END = date(2027, 1, 31)

ARTISTS = [
    "iLiFE!",
    "夜光性アミューズ",
    "のんふぃく！",
    "iON!",
    "MEGAFON",
]

BASE_URL = "https://l-tike.com"

# GitHub Actionsからのアクセスを少し安定させる
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Referer": "https://l-tike.com/",
    "Connection": "keep-alive",
}

CONNECT_TIMEOUT = 30
READ_TIMEOUT = 90

MAX_RETRIES = 3


# ==========================================
# Session
# ==========================================

session = requests.Session()
session.headers.update(HEADERS)


# ==========================================
# HTTP取得
# ==========================================

def get_page(url):
    """
    ローチケのページを取得する。
    タイムアウト・接続エラーがあった場合は自動リトライ。
    """

    for attempt in range(1, MAX_RETRIES + 1):

        try:
            print(
                f"  ページ取得 {attempt}/{MAX_RETRIES}: "
                f"{url}"
            )

            response = session.get(
                url,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                allow_redirects=True,
            )

            response.raise_for_status()

            print(
                f"  取得成功: "
                f"HTTP {response.status_code} / "
                f"{len(response.text):,} bytes"
            )

            return response

        except requests.exceptions.Timeout:
            print(
                f"  タイムアウトしました "
                f"({attempt}/{MAX_RETRIES})"
            )

        except requests.exceptions.ConnectionError as e:
            print(
                f"  接続エラー "
                f"({attempt}/{MAX_RETRIES}): {e}"
            )

        except requests.exceptions.HTTPError as e:
            print(
                f"  HTTPエラー "
                f"({attempt}/{MAX_RETRIES}): {e}"
            )

        except requests.exceptions.RequestException as e:
            print(
                f"  リクエストエラー "
                f"({attempt}/{MAX_RETRIES}): {e}"
            )

        if attempt < MAX_RETRIES:
            wait_time = attempt * 8
            print(f"  {wait_time}秒待って再試行します...")
            time.sleep(wait_time)

    print("  取得失敗: 最大リトライ回数に到達しました")
    return None


# ==========================================
# 日付
# ==========================================

def parse_date(text):
    """
    ローチケの
    2026/10/10
    2026/10/10(土)
    などから日付を取得。
    """

    match = re.search(
        r"(20\d{2})[年/\-](\d{1,2})[月/\-](\d{1,2})",
        text
    )

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


# ==========================================
# エリア判定
# ==========================================

def classify_area(text):

    text = text.replace("　", " ")

    # 北海道
    hokkaido_keywords = [
        "北海道",
        "札幌",
        "函館",
        "旭川",
        "小樽",
        "帯広",
        "苫小牧",
        "釧路",
    ]

    for keyword in hokkaido_keywords:
        if keyword in text:
            return "北海道・札幌" if "札幌" in text else "北海道"

    # 東京
    tokyo_keywords = [
        "東京都",
        "東京",
        "渋谷",
        "新宿",
        "池袋",
        "秋葉原",
        "品川",
        "台東区",
        "千代田区",
        "港区",
        "中央区",
        "新宿区",
        "渋谷区",
    ]

    for keyword in tokyo_keywords:
        if keyword in text:
            return "東京"

    return None


# ==========================================
# ステータス
# ==========================================

def get_status(text):

    if "中止" in text:
        return "中止"

    if "払戻" in text:
        return "払戻"

    if "本日発売" in text:
        return "本日発売"

    if "発売中" in text:
        return "販売中"

    if "受付中" in text:
        return "販売中"

    if "発売前" in text:
        return "発売前"

    if "受付終了" in text:
        return "受付終了"

    if "販売終了" in text:
        return "販売終了"

    return "販売情報あり"


# ==========================================
# イベントID
# ==========================================

def make_event_id(group, event_date, title, venue):

    raw = f"{group}-{event_date}-{title}-{venue}"

    return re.sub(
        r"[^a-zA-Z0-9ぁ-んァ-ヶ一-龠]+",
        "-",
        raw,
    ).strip("-").lower()


# ==========================================
# イベント解析
# ==========================================

def parse_search_page(html, artist, search_url):

    soup = BeautifulSoup(html, "html.parser")

    events = []

    # ローチケの検索結果ではイベントタイトルが
    # h3として表示されるケースが多いため、
    # h3を起点にイベント情報を探します。

    headings = soup.find_all(["h2", "h3"])

    for heading in headings:

        title = heading.get_text(
            " ",
            strip=True
        )

        if not title:
            continue

        # 検索結果のタイトルとして使えそうか確認
        if title in [
            "絞り込み検索",
            "販売方法",
            "受付期間",
            "申込/詳細",
            "販売状況",
        ]:
            continue

        # h3の親要素をイベントブロックとして扱う
        block = heading.parent

        if block is None:
            continue

        text = block.get_text(
            " ",
            strip=True
        )

        # 情報が少なすぎるものは除外
        if len(text) < 20:
            continue

        # 親だけでは情報が足りない場合、さらに上を見る
        if "公演日" not in text:

            parent = block.parent

            if parent is not None:

                parent_text = parent.get_text(
                    " ",
                    strip=True
                )

                if len(parent_text) > len(text):
                    text = parent_text
                    block = parent

        # 日付
        event_date = parse_date(text)

        if event_date is None:
            continue

        # 期間外
        if event_date < START or event_date > END:
            continue

        # エリア
        area = classify_area(text)

        if area is None:
            continue

        # 会場
        venue = ""

        venue_match = re.search(
            r"会場[:：]\s*(.+?)(?=\s+(?:販売方法|受付期間|申込/詳細)|$)",
            text,
        )

        if venue_match:
            venue = venue_match.group(1).strip()

        # 会場が取れない場合は少し広く探す
        if not venue:

            venue_match = re.search(
                r"会場[:：]\s*(.{1,100})",
                text,
            )

            if venue_match:
                venue = venue_match.group(1).strip()

        # URL
        event_url = search_url

        link = block.find(
            "a",
            href=True
        )

        if link:

            href = link.get("href", "").strip()

            if href:
                event_url = urljoin(
                    BASE_URL,
                    href
                )

        # ステータス
        status = get_status(text)

        # イベントID
        event_id = make_event_id(
            artist,
            event_date.isoformat(),
            title,
            venue,
        )

        events.append(
            {
                "id": event_id,
                "date": event_date.isoformat(),
                "group": artist,
                "title": title,
                "venue": venue,
                "area": area,
                "status": status,
                "source": "ローチケ",
                "url": event_url,
            }
        )

    return events


# ==========================================
# アーティスト検索
# ==========================================

def search_lawson(artist):

    search_url = (
        f"{BASE_URL}/search/"
        f"?keyword={quote(artist)}"
    )

    print()
    print("==============================")
    print(f"検索中: {artist}")
    print(search_url)
    print("==============================")

    response = get_page(search_url)

    if response is None:
        return None

    events = parse_search_page(
        response.text,
        artist,
        search_url,
    )

    # 重複除去
    unique = {}

    for event in events:
        unique[event["id"]] = event

    events = list(unique.values())

    print(
        f"{artist}: {len(events)}件"
    )

    return events


# ==========================================
# メイン
# ==========================================

def main():

    all_events = []

    success_count = 0
    failed_count = 0

    print()
    print("================================")
    print("ローチケ情報取得開始")
    print("================================")

    # 最初にトップページへアクセスして
    # SessionのCookie等を取得
    print()
    print("ローチケへ接続しています...")

    warmup = get_page(BASE_URL)

    if warmup is None:
        print("トップページ取得に失敗しました。")
        print("検索処理を続行します。")
    else:
        print("ローチケへの接続成功")

    for index, artist in enumerate(ARTISTS):

        events = search_lawson(artist)

        if events is None:

            failed_count += 1

        else:

            success_count += 1
            all_events.extend(events)

        # ローチケへの連続アクセスを避ける
        if index < len(ARTISTS) - 1:
            wait_time = 5
            print(
                f"{wait_time}秒待って次の検索へ..."
            )
            time.sleep(wait_time)

    # 全体の重複除去
    unique_events = {}

    for event in all_events:

        key = (
            event.get("date", ""),
            event.get("group", ""),
            event.get("title", ""),
            event.get("venue", ""),
        )

        unique_events[key] = event

    all_events = list(
        unique_events.values()
    )

    # 日付順
    all_events.sort(
        key=lambda x: (
            x.get("date", ""),
            x.get("group", ""),
            x.get("title", ""),
        )
    )

    print()
    print("================================")
    print("ローチケ取得結果")
    print("================================")
    print(
        f"検索成功: {success_count} / "
        f"{len(ARTISTS)}"
    )
    print(
        f"検索失敗: {failed_count} / "
        f"{len(ARTISTS)}"
    )
    print(
        f"取得イベント数: {len(all_events)}"
    )

    # すべての検索が失敗した場合は
    # 空ファイルで上書きしない
    if success_count == 0:

        print()
        print(
            "⚠️ ローチケから1件も取得できませんでした。"
        )
        print(
            "既存のevents_lawson.jsonは変更しません。"
        )

        raise RuntimeError(
            "ローチケへの接続に失敗しました"
        )

    # 保存
    OUTPUT.write_text(
        json.dumps(
            all_events,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("================================")
    print("ローチケ取得完了")
    print(
        f"取得件数: {len(all_events)}"
    )
    print(
        f"保存先: {OUTPUT}"
    )
    print("================================")


# ==========================================

if __name__ == "__main__":
    main()
