import json
from pathlib import Path


TICKETDIVE_FILE = Path("events.json")
LAWSON_FILE = Path("events_lawson.json")
OUTPUT_FILE = Path("events.json")


def load_json(path):
    if not path.exists():
        return []

    try:
        data = json.loads(
            path.read_text(encoding="utf-8")
        )

        if isinstance(data, list):
            return data

    except Exception as e:
        print(f"読み込みエラー: {path} / {e}")

    return []


def event_key(event):
    """
    同じライブかどうかを判断するためのキー
    """

    return (
        event.get("date", ""),
        event.get("group", ""),
        event.get("title", ""),
        event.get("venue", ""),
    )


def merge_sources(existing_sources, new_sources):
    """
    同じイベントに複数の情報源がある場合、
    sourcesを1つにまとめる。
    """

    sources = []

    for source in existing_sources + new_sources:

        if not isinstance(source, dict):
            continue

        name = source.get("name", "")
        url = source.get("url", "")

        if not name or not url:
            continue

        if not any(
            s.get("url") == url
            for s in sources
        ):
            sources.append(
                {
                    "name": name,
                    "url": url,
                }
            )

    return sources


def normalize_event(event):
    """
    古い形式の
    source / url

    を新しい
    sources
    形式に変換する。
    """

    event = dict(event)

    sources = []

    # 新形式
    if isinstance(event.get("sources"), list):
        sources.extend(event["sources"])

    # 旧形式
    if event.get("source") and event.get("url"):
        sources.append(
            {
                "name": event["source"],
                "url": event["url"],
            }
        )

    event["sources"] = merge_sources([], sources)

    # 古い項目は残しても問題ないが、
    # サイト表示ではsourcesを優先する
    return event


def merge_events():

    ticketdive_events = load_json(TICKETDIVE_FILE)
    lawson_events = load_json(LAWSON_FILE)

    print(f"TicketDive: {len(ticketdive_events)}件")
    print(f"ローチケ: {len(lawson_events)}件")

    merged = {}

    # TicketDive
    for event in ticketdive_events:

        event = normalize_event(event)

        key = event_key(event)

        if key not in merged:
            merged[key] = event
        else:
            merged[key]["sources"] = merge_sources(
                merged[key].get("sources", []),
                event.get("sources", []),
            )

    # ローチケ
    for event in lawson_events:

        event = normalize_event(event)

        key = event_key(event)

        if key not in merged:
            merged[key] = event
        else:
            merged[key]["sources"] = merge_sources(
                merged[key].get("sources", []),
                event.get("sources", []),
            )

    result = list(merged.values())

    result.sort(
        key=lambda event: (
            event.get("date", ""),
            event.get("group", ""),
            event.get("title", ""),
        )
    )

    OUTPUT_FILE.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("==============================")
    print("イベント統合完了")
    print(f"統合後: {len(result)}件")
    print("==============================")


if __name__ == "__main__":
    merge_events()
