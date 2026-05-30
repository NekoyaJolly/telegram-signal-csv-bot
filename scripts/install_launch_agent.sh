#!/bin/sh
set -eu

LABEL="com.nekoya.telegram-signal-csv-bot"
PLIST_TEMPLATE="launchd/${LABEL}.plist.template"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
TARGET_PLIST="${LAUNCH_AGENTS_DIR}/${LABEL}.plist"
USER_DOMAIN="gui/$(id -u)"

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_PATH="${PROJECT_ROOT}/.venv/bin/python"

cd "${PROJECT_ROOT}"

if [ ! -x "${PYTHON_PATH}" ]; then
  echo ".venv/bin/python が見つかりません。先にプロジェクトルートで仮想環境を作成してください。"
  exit 1
fi

if [ ! -f ".env" ]; then
  echo ".env が見つかりません。cp .env.example .env の後、必要な値を設定してください。"
  exit 1
fi

mkdir -p "${LAUNCH_AGENTS_DIR}" logs
sed \
  -e "s#__PROJECT_ROOT__#${PROJECT_ROOT}#g" \
  -e "s#__PYTHON_PATH__#${PYTHON_PATH}#g" \
  "${PLIST_TEMPLATE}" > "${TARGET_PLIST}"

if launchctl print "${USER_DOMAIN}/${LABEL}" >/dev/null 2>&1; then
  launchctl bootout "${USER_DOMAIN}" "${TARGET_PLIST}" || true
fi

launchctl bootstrap "${USER_DOMAIN}" "${TARGET_PLIST}"
launchctl kickstart -k "${USER_DOMAIN}/${LABEL}"

echo "LaunchAgent を登録しました: ${TARGET_PLIST}"
echo "状態確認: launchctl print ${USER_DOMAIN}/${LABEL}"
echo "停止: launchctl bootout ${USER_DOMAIN} ${TARGET_PLIST}"
