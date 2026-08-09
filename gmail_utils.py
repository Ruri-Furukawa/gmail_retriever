#!/usr/bin/env python3
"""Gmail API(読み取り専用)の共通ヘルパー関数。

必要スコープ: https://www.googleapis.com/auth/gmail.readonly のみ。
削除・既読化・ラベル変更・送信などを行う権限は一切要求しない。
"""

import base64
import re
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

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
