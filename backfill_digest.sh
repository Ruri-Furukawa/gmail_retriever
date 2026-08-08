#!/bin/zsh
# 過去日分の対象メールをデイリーノートにまとめて要約・追記する(一回限りのバックフィル用)。
# 使い方: ./backfill_digest.sh START_DATE [END_DATE]
#   例:   ./backfill_digest.sh 2026-08-01 2026-08-08
#   END_DATEを省略すると実行時点のJSTでの今日までを対象とする。
#
# 定期実行の daily_digest.sh / fetch_target_mail.py とは独立したスクリプトです。
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

START_DATE="${1:?使い方: backfill_digest.sh START_DATE [END_DATE]}"
END_DATE="${2:-}"

LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/backfill_$(date +%Y-%m-%d_%H%M%S).log"

{
  echo "=== backfill_digest run: $(date) (range: $START_DATE 〜 ${END_DATE:-today}) ==="

  if [ -n "$END_DATE" ]; then
    "$PYTHON" backfill_digest.py --start "$START_DATE" --end "$END_DATE"
  else
    "$PYTHON" backfill_digest.py --start "$START_DATE"
  fi

  MANIFEST="$SCRIPT_DIR/mail_data/_manifest.json"
  TOTAL=$("$PYTHON" -c "
import json
files = json.load(open('$MANIFEST'))['files']
print(sum(json.load(open(f))['count'] for f in files))
")
  echo "matched total: $TOTAL"

  if [ "$TOTAL" -eq 0 ]; then
    echo "対象メールなし。要約処理をスキップします。"
    exit 0
  fi

  FILE_LIST=$("$PYTHON" -c "
import json
files = json.load(open('$MANIFEST'))['files']
print('\n'.join(files))
")

  PROMPT_TEMPLATE=$(cat "$SCRIPT_DIR/backfill_digest_prompt.md")
  PROMPT="${PROMPT_TEMPLATE//\{\{OBSIDIAN_VAULT_DIR\}\}/$OBSIDIAN_VAULT_DIR}"

  claude -p "$PROMPT

対象ファイル一覧:
$FILE_LIST" \
    --permission-mode acceptEdits \
    --allowedTools "Read,Edit,Write,Glob" \
    --add-dir "$OBSIDIAN_VAULT_DIR" \
    --no-session-persistence

  echo "=== done: $(date) ==="
} >> "$LOG_FILE" 2>&1
