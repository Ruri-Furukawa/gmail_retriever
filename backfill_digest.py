#!/usr/bin/env python3
"""複数日分の対象メールをまとめて抽出し、バックフィル要約用JSONを出力する読み取り専用スクリプト。

定期実行スクリプト(fetch_target_mail.py / daily_digest.sh)とは独立した一回限りの
バックフィル用スクリプト。対象アドレスの判定ロジックは fetch_target_mail.py の
load_target_addresses() をそのまま再利用する。
"""

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from fetch_target_mail import load_target_addresses
from fetch_unread_emails import extract_body, get_credentials, get_header

BASE_DIR = Path(__file__).resolve().parent
MAIL_DATA_DIR = BASE_DIR / "mail_data"
MANIFEST_PATH = MAIL_DATA_DIR / "_manifest.json"

JST = timezone(timedelta(hours=9))


def fetch_range(service, start_date: date, end_date: date) -> list[dict]:
    after_date = (start_date - timedelta(days=1)).strftime("%Y/%m/%d")
    before_date = (end_date + timedelta(days=1)).strftime("%Y/%m/%d")

    results = []
    page_token = None
    while True:
        resp = (
            service.users()
            .messages()
            .list(
                userId="me",
                q=f"after:{after_date} before:{before_date}",
                maxResults=500,
                pageToken=page_token,
            )
            .execute()
        )
        messages = resp.get("messages", [])
        for m in messages:
            msg = service.users().messages().get(userId="me", id=m["id"], format="full").execute()
            headers = msg["payload"].get("headers", [])
            results.append(
                {
                    "id": msg["id"],
                    "from": get_header(headers, "From"),
                    "subject": get_header(headers, "Subject"),
                    "date": get_header(headers, "Date"),
                    "body": extract_body(msg["payload"]),
                }
            )
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return results


def main():
    parser = argparse.ArgumentParser(
        description="複数日分の対象メールをまとめてJSON出力する(バックフィル用・定期実行スクリプトとは別)"
    )
    parser.add_argument("--start", type=str, required=True, help="開始日 YYYY-MM-DD (JST)")
    parser.add_argument(
        "--end", type=str, default=None, help="終了日 YYYY-MM-DD (JST)。省略時は実行時点のJSTでの今日"
    )
    args = parser.parse_args()

    start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
    end_date = (
        datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else datetime.now(JST).date()
    )

    targets = load_target_addresses()
    if not targets:
        sys.exit("unread_by_sender.xlsx に【就活】/【企業】対象アドレスが見つかりません。")

    creds = get_credentials()
    service = build("gmail", "v1", credentials=creds)

    try:
        candidates = fetch_range(service, start_date, end_date)
    except HttpError as error:
        sys.exit(f"Gmail API呼び出し中にエラーが発生しました: {error}")

    by_date: dict[str, list[dict]] = {}
    for c in candidates:
        _, addr = parseaddr(c["from"])
        addr = addr.lower()
        if addr not in targets:
            continue

        try:
            dt = parsedate_to_datetime(c["date"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        dt_jst = dt.astimezone(JST)
        d = dt_jst.date()
        if d < start_date or d > end_date:
            continue

        rule = targets[addr]
        by_date.setdefault(d.isoformat(), []).append(
            {
                "id": c["id"],
                "from_address": addr,
                "from_name": rule["name"] or c["from"],
                "subject": c["subject"],
                "date_jst": dt_jst.isoformat(),
                "body": c["body"],
                "rule_type": rule["type"],
                "rule_comment": rule["comment"],
                "base_tag": rule["base_tag"],
            }
        )

    MAIL_DATA_DIR.mkdir(exist_ok=True)
    generated_at = datetime.now(JST).isoformat()
    written_files = []

    d = start_date
    while d <= end_date:
        day_key = d.isoformat()
        emails = by_date.get(day_key, [])
        day_output = {
            "target_date": day_key,
            "generated_at": generated_at,
            "count": len(emails),
            "emails": emails,
        }
        day_path = MAIL_DATA_DIR / f"{day_key}.json"
        day_path.write_text(json.dumps(day_output, ensure_ascii=False, indent=2), encoding="utf-8")
        written_files.append(str(day_path))
        d += timedelta(days=1)

    manifest = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "generated_at": generated_at,
        "files": written_files,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    total = sum(len(v) for v in by_date.values())
    print(
        f"{start_date}〜{end_date} の対象メール {total} 件({len(written_files)}日分)を "
        f"{MAIL_DATA_DIR} 配下に日付別ファイルとして保存しました。"
    )


if __name__ == "__main__":
    main()
