#!/bin/zsh
# 対象アドレスからの当日分メールをデイリーノートに要約・追記する。
# 手動実行: ./daily_digest.sh
# 自動実行: cron/launchd等から定期実行することを想定。
#
# 事前準備: .env.example を .env にコピーし、OBSIDIAN_VAULT_DIR を設定してください。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f "$SCRIPT_DIR/.env" ]; then
  set -a
  source "$SCRIPT_DIR/.env"
  set +a
fi

: "${OBSIDIAN_VAULT_DIR:?OBSIDIAN_VAULT_DIR が設定されていません。.env.example を参考に .env を作成してください。}"

PYTHON="$SCRIPT_DIR/venv/bin/python3"

LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/$(date +%Y-%m-%d_%H%M%S).log"

{
  echo "=== daily_digest run: $(date) ==="

  "$PYTHON" fetch_target_mail.py

  TARGET_DATE=$(TZ=Asia/Tokyo date +%Y-%m-%d)
  JSON_PATH="$SCRIPT_DIR/mail_data/$TARGET_DATE.json"

  COUNT=$("$PYTHON" -c "import json; print(json.load(open('$JSON_PATH'))['count'])")
  echo "matched count: $COUNT"

  if [ "$COUNT" -eq 0 ]; then
    echo "対象メールなし。要約処理をスキップします。"
    exit 0
  fi

  PROMPT_TEMPLATE=$(cat "$SCRIPT_DIR/daily_digest_prompt.md")
  PROMPT="${PROMPT_TEMPLATE//\{\{OBSIDIAN_VAULT_DIR\}\}/$OBSIDIAN_VAULT_DIR}"

  claude -p "$PROMPT

対象ファイル: $JSON_PATH" \
    --permission-mode acceptEdits \
    --allowedTools "Read,Edit,Write,Glob" \
    --add-dir "$OBSIDIAN_VAULT_DIR" \
    --no-session-persistence

  echo "=== done: $(date) ==="
} >> "$LOG_FILE" 2>&1
