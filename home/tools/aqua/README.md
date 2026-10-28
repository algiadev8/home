# aqua 管理 CLI

**ツールの種類（追加・削除）は Nix、バージョンは aqua が管理します。**
Nix は aqua 本体・環境変数・PATH も管理します。

## ツールの追加・削除

各 tool の `my.tools.*.enable` と `my.tools.aqua.packages` が、
aqua で利用するツールの集合を決めます。
Home Manager を反映すると、グローバル設定をパッケージ名で照合して同期します。

Nix には `"cli/cli"` のようにパッケージ名だけを指定し、バージョンは書きません。

- 新しく有効にしたツール: `aqua generate` で最新版を解決して追加します。
- 引き続き有効なツール: aqua が選んだ現在のバージョンを維持します。
  rebuild のたびに最新版へ更新することはありません。
- 無効にしたツール: aqua 設定から除外します。最後のツールを無効にした場合も同期します。
- 新規端末で有効なツールがない場合: 設定ファイルを作成しません。

グローバル設定の packages 一覧全体が Nix の管理対象です。
aqua 設定に手動で追加したツールも、Nix にない場合は次回反映で除外されます。
プロジェクト固有の aqua 設定は変更しません。

設定は `$XDG_CONFIG_HOME/aqua/aqua.yaml`（未設定時は `~/.config/aqua/aqua.yaml`）に
書き込み可能な通常ファイルとして配置します。Home Manager の symlink にはしません。
有効なツールがある場合、同期後の設定で `aqua install` を実行します。

## rebuild なしでバージョンを更新

Home Manager の初回反映後、新しいシェルで実行します。
プロジェクト内の aqua 設定と取り違えないよう、設定パスを明示します。

```sh
aqua --config "$AQUA_GLOBAL_CONFIG" update &&
  aqua --config "$AQUA_GLOBAL_CONFIG" install
```

`update` は設定内のレジストリとパッケージのバージョンを書き換え、
`install` はその設定に従って CLI をインストールします。

Codex だけを更新する場合:

```sh
aqua --config "$AQUA_GLOBAL_CONFIG" update codex &&
  aqua --config "$AQUA_GLOBAL_CONFIG" install
```

その後 Home Manager を再反映しても、有効なツールのバージョン、
パッケージごとのオプション、レジストリの ref、チェックサム設定は保持します。
ツールを無効にして反映してから再び有効にした場合は、新規追加として最新版を解決します。
新規追加のバージョン解決にはネットワーク接続が必要です。
解決に失敗した場合は、既存の設定を変更せず反映を中止します。
aqua 本体を Nix で更新する場合には rebuild が必要です。
Claude の自己更新は無効にし、aqua に更新元を統一しています。

## 移行と安全性

以前の Home Manager が生成した設定への symlink は、
次回反映の `linkGeneration` で取り除かれ、その後に通常ファイルを生成します。
初回配置のみの旧方式で作成済みの通常ファイルも、そのまま同期できます。

設定は検証後に一時ファイルから原子的に置き換えます。
変更がなければファイルを書き換えません。
チェックサムのサイドカーファイルとダウンロード済みの CLI 本体は削除しません。
CLI のキャッシュ削除と設定からの除外は別の操作です。

この同期処理は packages に名前付きの項目を直接並べる構成を対象にします。
パッケージの import、重複したパッケージ名、不正な設定、外部の symlink は、
黙って上書きせずエラーにします。

## 同期処理のテスト

`ruamel.yaml` を含む Python で、リポジトリのルートから実行します。

```sh
python -m unittest discover -s home/tools/aqua -p test_sync.py -v
```
