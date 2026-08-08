#!/usr/bin/env python3
"""Gmail APIを使って未読メールを取得し、JSONに保存する読み取り専用スクリプト。

必要スコープ: https://www.googleapis.com/auth/gmail.readonly のみ。
削除・既読化・ラベル変更・送信などを行う権限は一切要求しない。
"""

import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# 読み取り専用スコープ。書き込み・削除系の操作は行わない。
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

BASE_DIR = Path(__file__).resolve().parent
CREDENTIALS_PATH = BASE_DIR / "credentials.json"
TOKEN_PATH = BASE_DIR / "token.json"


def get_credentials() -> Credentials:
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                sys.exit(
                    f"credentials.json が見つかりません: {CREDENTIALS_PATH}\n"
                    "Google Cloud Console でOAuthクライアント(デスクトップアプリ)を作成し、"
                    "ダウンロードしたJSONをこのファイル名で配置してください。"
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH), SCOPES
            )
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json())

    return creds


def get_header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def strip_html(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def decode_part_data(data: str) -> str:
    return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="replace")


def extract_body(payload: dict) -> str:
    """text/plain を優先し、無ければ text/html をタグ除去して返す。"""
    plain_text = None
    html_text = None

    def walk(part: dict):
        nonlocal plain_text, html_text
        mime_type = part.get("mimeType", "")
        body = part.get("body", {})
        data = body.get("data")

        if mime_type == "text/plain" and data and plain_text is None:
            plain_text = decode_part_data(data)
        elif mime_type == "text/html" and data and html_text is None:
            html_text = decode_part_data(data)

        for sub_part in part.get("parts", []) or []:
            walk(sub_part)

    walk(payload)

    if plain_text is not None:
        return plain_text.strip()
    if html_text is not None:
        return strip_html(html_text)
    return ""


def fetch_unread_emails(service, max_results: int | None) -> list[dict]:
    """max_results が None の場合は未読メールを全件取得する。"""
    label_map = {
        label["id"]: label["name"]
        for label in service.users().labels().list(userId="me").execute().get("labels", [])
    }

    results = []
    page_token = None

    while max_results is None or len(results) < max_results:
        page_size = 100 if max_results is None else min(100, max_results - len(results))
        resp = (
            service.users()
            .messages()
            .list(
                userId="me",
                labelIds=["UNREAD"],
                maxResults=page_size,
                pageToken=page_token,
            )
            .execute()
        )
        messages = resp.get("messages", [])
        if not messages:
            break

        for msg_meta in messages:
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_meta["id"], format="full")
                .execute()
            )
            headers = msg.get("payload", {}).get("headers", [])
            label_ids = msg.get("labelIds", [])

            results.append(
                {
                    "id": msg["id"],
                    "from": get_header(headers, "From"),
                    "subject": get_header(headers, "Subject"),
                    "date": get_header(headers, "Date"),
                    "body": extract_body(msg.get("payload", {})),
                    "labels": [label_map.get(lid, lid) for lid in label_ids],
                }
            )

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return results


def main():
    parser = argparse.ArgumentParser(description="Gmailの未読メールを読み取り専用で取得しJSON保存する")
    parser.add_argument(
        "--max",
        type=int,
        default=50,
        help="取得する最大件数(デフォルト50)。0を指定すると全件取得。",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(BASE_DIR / "unread_emails.json"),
        help="出力先JSONファイルパス",
    )
    args = parser.parse_args()

    creds = get_credentials()
    service = build("gmail", "v1", credentials=creds)

    max_results = None if args.max <= 0 else args.max

    try:
        emails = fetch_unread_emails(service, max_results)
    except HttpError as error:
        sys.exit(f"Gmail API呼び出し中にエラーが発生しました: {error}")

    output_path = Path(args.output)
    output_path.write_text(
        json.dumps(emails, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"未読メール {len(emails)} 件を取得し、{output_path} に保存しました。")


if __name__ == "__main__":
    main()
