# telegram-signal-csv-bot

Telegram Bot に届いたトレードシグナル本文を polling で受信し、SQLite を正本として保存し、正規化 CSV を出力する macOS 常駐前提の Python アプリです。受信した元メッセージは、設定がある場合のみ Telegram ログチャンネルへ `copyMessage` します。

CSV は DB import、目視確認、外部連携用です。データの正本は常に SQLite です。

## ワークフロー

```mermaid
flowchart TD
  A[Telegram message受信] --> B[raw_messagesへ保存]
  B --> C[ログチャンネルへcopyMessage]
  C --> D[本文パース]
  D -->|成功| E[parsed_signalsへ保存]
  E --> F[trade_signals.csvへ追記]
  D -->|失敗| G[rejected_messagesへ保存]
  G --> H[rejected_signals.csvへ追記]
```

`copyMessage` に失敗しても、SQLite 保存、パース、CSV 出力は継続します。

## セットアップ

実行場所: プロジェクトルート

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
```

`requirements.txt` はバージョン未固定です。新規の小規模常駐アプリとして、まず Python 3.12 系の最新互換版を使い、必要になった段階でロックファイルやバージョン固定へ移行しやすくするためです。

## Bot Token

1. Telegram で `@BotFather` を開きます。
2. `/newbot` を実行します。
3. Bot 名と username を入力します。
4. 発行された token を `.env` の `TELEGRAM_BOT_TOKEN` に設定します。

Bot Token は `.env` のみに保存してください。launchd plist やソースコードに直接書かないでください。

## .env

実行場所: プロジェクトルート

```bash
[ -f .env ] || cp .env.example .env
```

`.env` を編集します。

```env
TELEGRAM_BOT_TOKEN=123456:example
TELEGRAM_LOG_CHAT_ID=
SIGNAL_TIMEZONE=Asia/Tokyo
SQLITE_DB_PATH=./data/signals.sqlite3
CSV_OUTPUT_PATH=./output/trade_signals.csv
REJECTED_CSV_OUTPUT_PATH=./output/rejected_signals.csv
LOG_DIR=./logs
```

`TELEGRAM_LOG_CHAT_ID` が空の場合、`copyMessage` はスキップされます。

## ログチャンネルID

実行場所: プロジェクトルート

```bash
source .venv/bin/activate
python -m scripts.print_chat_id
```

ログにしたいチャンネルまたはチャットへ Bot を追加し、メッセージを送ると `chat_id` が表示されます。その値を `.env` の `TELEGRAM_LOG_CHAT_ID` に設定します。

## DB初期化

実行場所: プロジェクトルート

```bash
source .venv/bin/activate
python -m scripts.init_db
```

`SQLITE_DB_PATH` に SQLite DB が作成されます。既に作成済みの場合も安全に終了します。

初期実装段階のため、既存 SQLite ファイルへのマイグレーションスクリプトはまだ用意していません。`parsed_signals` のスキーマ変更後に既存DBを使う場合は、必要に応じて `data/signals.sqlite3` を退避または削除してから `python -m scripts.init_db` を実行し直してください。

## Entry仕様

`Entry` は1〜5点まで許容します。

```txt
Entry | 4533
Entry | 4563 - 4568
Entry | 4563 - 4568 - 4570 - 4575 - 4580
```

保存仕様:

- 1点: `entry_type = single`
- 2点: `entry_type = range`
- 3〜5点: `entry_type = multi`
- 6点以上: rejected として保存
- `entry_min` は最小値、`entry_max` は最大値
- `entry_raw` は `Entry |` より後ろの文字列を trim した値
- `entry1`〜`entry5` は元の順番で保存し、存在しない値はNULLまたはCSV空欄

## 手動起動

launchd 化する前に、必ず手動起動で動作確認してください。

実行場所: プロジェクトルート

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
python -m scripts.init_db
caffeinate -i python -m src.main
```

この状態で確認すること:

1. Telegram メッセージ受信
2. `data/signals.sqlite3` への保存
3. `output/trade_signals.csv` への出力
4. `TELEGRAM_LOG_CHAT_ID` 設定時のログチャンネルへの `copyMessage`
5. 不正メッセージの `rejected_messages` と `output/rejected_signals.csv` への保存

## launchd常駐化

手動起動で動作確認できた後に設定してください。

実行場所: プロジェクトルート

```bash
source .venv/bin/activate
./scripts/install_launch_agent.sh
```

このスクリプトは `launchd/com.nekoya.telegram-signal-csv-bot.plist.template` から実パス入り plist を生成し、`~/Library/LaunchAgents/com.nekoya.telegram-signal-csv-bot.plist` に配置します。

launchd 側には Bot Token を書きません。`.env` は Python アプリ側で読み込みます。

## 停止

実行場所: 任意

```bash
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.nekoya.telegram-signal-csv-bot.plist"
```

状態確認:

```bash
launchctl print "gui/$(id -u)/com.nekoya.telegram-signal-csv-bot"
```

Terminal を閉じても launchd 起動なら Bot は動きます。Mac を再起動した後も `RunAtLoad` により起動します。ただし、Mac がスリープすると polling は止まる可能性があります。電源接続中はスリープしない設定にしてください。

## ログ確認

実行場所: プロジェクトルート

```bash
tail -f logs/app.log
```

launchd 化後に動かない場合:

```bash
tail -f logs/launchd.err.log
tail -f logs/launchd.out.log
```

## CSV再生成

SQLite を正本として、CSV を全再生成できます。
raw message 保存後にアプリが停止した場合でも、再起動時の未処理 raw 再処理後に CSV は SQLite から全再生成されます。CSV 欠落や手動修復が必要な場合も、SQLite が正本なので次のコマンドで復旧できます。

実行場所: プロジェクトルート

```bash
source .venv/bin/activate
python -m scripts.export_csv
```

生成対象:

```txt
output/trade_signals.csv
output/rejected_signals.csv
```

CSV は UTF-8 BOM 付きで出力します。

`trade_signals.csv` のカラム順:

```txt
signal_id,source,telegram_chat_id,telegram_message_id,side,symbol,timeframe,entry_type,entry_min,entry_max,entry_raw,entry1,entry2,entry3,entry4,entry5,tp1,tp2,tp3,tp4,tp5,sl,signal_time,signal_time_utc,received_at,raw_text
```

## テスト

実行場所: プロジェクトルート

```bash
source .venv/bin/activate
pytest
```

## よくあるエラー

`TELEGRAM_BOT_TOKEN が設定されていません`
: `.env` の `TELEGRAM_BOT_TOKEN` を設定してください。

`TELEGRAM_LOG_CHAT_ID` 設定時に `copyMessage` が失敗する
: Bot がログチャンネルに追加されているか、投稿権限があるかを確認してください。失敗理由は `raw_messages.copy_error` と `logs/app.log` に残ります。

launchd では動かないが手動起動では動く
: `logs/launchd.err.log` を確認してください。`.venv/bin/python` と `.env` が存在するかも確認してください。

CSV が更新されない
: SQLite に保存されていれば復旧できます。`python -m scripts.export_csv` で全再生成してください。

## セキュリティ注意点

- `.env` は Git 管理しません。
- Bot Token をログ、README、launchd plist、ソースコードに直接書かないでください。
- `.env.example` にはダミー値または空値のみを置いてください。
- SQLite を正本にし、CSV だけを正本として扱わないでください。

## 主なファイル

```txt
src/main.py              # polling 起動エントリーポイント
src/parser.py            # シグナル本文パーサー
src/database.py          # SQLite 初期化と保存処理
src/csv_exporter.py      # CSV 追記と全再生成
src/telegram_bot.py      # Telegram polling と copyMessage
scripts/init_db.py       # DB 初期化
scripts/export_csv.py    # CSV 全再生成
scripts/print_chat_id.py # chat_id 確認
```
