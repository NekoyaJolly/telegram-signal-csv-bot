#!/bin/sh
set -eu

PYTHON_BIN=""
PYTHON_MODE=""
CREATED_ENV=0

info() {
  printf '%s\n' "$1"
}

fail() {
  printf 'エラー: %s\n' "$1" >&2
  exit 1
}

check_project_root() {
  # 誤った場所で実行すると .venv や .env を別ディレクトリに作るため、最初に止める。
  if [ ! -f "requirements.txt" ] || [ ! -f "src/main.py" ] || [ ! -d "scripts" ]; then
    fail "プロジェクトルートで実行してください。例: cd /Users/jolly_app/projects/telegram-signal-csv-bot"
  fi
}

python_version() {
  if [ "$1" = "pyenv" ]; then
    pyenv exec python -c 'import sys; print(".".join(map(str, sys.version_info[:3])))'
  else
    "$2" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))'
  fi
}

is_python_312() {
  mode="$1"
  bin="$2"
  version="$(python_version "$mode" "$bin" 2>/dev/null || true)"
  case "$version" in
    3.12.*) return 0 ;;
    *) return 1 ;;
  esac
}

select_python() {
  # pyenv に 3.12.10 がある場合は、プロジェクトローカルで有効化してから使う。
  if command -v pyenv >/dev/null 2>&1 && pyenv versions --bare | grep -qx '3.12.10'; then
    info "pyenv の Python 3.12.10 を検出しました。pyenv local 3.12.10 を設定します。"
    pyenv local 3.12.10 || fail "pyenv local 3.12.10 に失敗しました。pyenv の設定を確認してください。"
    pyenv exec python -V || fail "pyenv exec python -V に失敗しました。pyenv の初期化状態を確認してください。"
    if is_python_312 "pyenv" ""; then
      PYTHON_MODE="pyenv"
      PYTHON_BIN="pyenv exec python"
      return
    fi
  fi

  if command -v python3.12 >/dev/null 2>&1 && is_python_312 "bin" "$(command -v python3.12)"; then
    PYTHON_MODE="bin"
    PYTHON_BIN="$(command -v python3.12)"
    return
  fi

  if command -v python3 >/dev/null 2>&1 && is_python_312 "bin" "$(command -v python3)"; then
    PYTHON_MODE="bin"
    PYTHON_BIN="$(command -v python3)"
    return
  fi

  if command -v python >/dev/null 2>&1 && is_python_312 "bin" "$(command -v python)"; then
    PYTHON_MODE="bin"
    PYTHON_BIN="$(command -v python)"
    return
  fi

  if command -v pyenv >/dev/null 2>&1 && is_python_312 "pyenv" ""; then
    PYTHON_MODE="pyenv"
    PYTHON_BIN="pyenv exec python"
    return
  fi

  fail "Python 3.12系が見つかりません。READMEのトラブルシュートを見て、pyenv local 3.12.10 または python3.12 を使える状態にしてください。"
}

run_selected_python() {
  if [ "$PYTHON_MODE" = "pyenv" ]; then
    pyenv exec python "$@"
  else
    "$PYTHON_BIN" "$@"
  fi
}

create_venv_if_needed() {
  if [ ! -d ".venv" ]; then
    info ".venv が無いため作成します。"
    run_selected_python -m venv .venv || fail ".venv の作成に失敗しました。Python 3.12 の venv モジュールを確認してください。"
  else
    info ".venv は既に存在します。"
  fi

  if [ ! -x ".venv/bin/python" ]; then
    fail ".venv/bin/python が見つかりません。.venv が壊れている可能性があります。必要なら .venv を削除して再実行してください。"
  fi
}

install_dependencies() {
  info "pip を更新します。"
  .venv/bin/python -m pip install --upgrade pip || fail "pip の更新に失敗しました。ネットワーク接続や pip の状態を確認してください。"
  info "requirements.txt をインストールします。"
  .venv/bin/python -m pip install -r requirements.txt || fail "requirements.txt のインストールに失敗しました。ネットワーク接続や依存ライブラリを確認してください。"
}

prepare_env_file() {
  if [ -f ".env" ]; then
    info ".env は既に存在します。上書きしません。"
    return
  fi

  if [ ! -f ".env.example" ]; then
    fail ".env.example が見つかりません。"
  fi

  cp .env.example .env
  CREATED_ENV=1
  info ".env を .env.example から作成しました。TELEGRAM_BOT_TOKEN を設定してください。"
}

init_database() {
  info "SQLite DB を初期化します。"
  .venv/bin/python -m scripts.init_db || fail "SQLite DB の初期化に失敗しました。.env と data ディレクトリの権限を確認してください。"
}

print_next_steps() {
  info ""
  info "セットアップが完了しました。"
  if [ "$CREATED_ENV" -eq 1 ]; then
    info "次に .env を開いて TELEGRAM_BOT_TOKEN を設定してください。Bot Token はログやGitに出さないでください。"
  fi
  info ""
  info "ログチャンネルIDを確認するコマンド:"
  info "source .venv/bin/activate"
  info "python -m scripts.print_chat_id"
  info ""
  info "手動起動するコマンド:"
  info "source .venv/bin/activate"
  info "caffeinate -i python -m src.main"
}

main() {
  check_project_root
  select_python
  info "使用するPython: ${PYTHON_BIN}"
  info "Python version: $(python_version "$PYTHON_MODE" "$PYTHON_BIN")"
  create_venv_if_needed
  install_dependencies
  prepare_env_file
  init_database
  print_next_steps
}

main "$@"
