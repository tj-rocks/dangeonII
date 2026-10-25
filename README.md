# dangeonII

Python・Pygameで制作している、2Dクオータービューのダンジョン探索ゲームと、その制作基盤です。

## 現在の機能

- 2次元配列による地形・キャラクター・アイテムの座標管理
- 部屋と通路のランダム生成（マップ寸法・部屋数などはYAMLで設定）
- 1マス単位の移動と、長押し・滑らかな描画補間
- 薄い2段の壁面と、手前の壁への円形グラデーション透過
- YAMLによるキー割り当て・描画設定・現在地フラグの保存
- 詳細度を切り替えられるメソッド呼び出しログ

階層移動、村、高台、中二階、完成した画像素材はまだ実装していません。

## 起動

Python 3.10以上が必要です。現在はmacOS・Python 3.13で動作確認しています。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

Windowsでの仮想環境有効化は`.venv\Scripts\activate`です。
画面に表示されたキーで操作します。初期設定は矢印キーで移動、Escで終了です。

## テスト

```bash
python -m pip install -r tests/requirements-dev.txt

# 回帰用（CI対象）
python -m pytest -c tests/pytest.ini tests/regression -v

# 全数用
python -m pytest -c tests/pytest.ini tests -v
```

## 構成

```text
main.py                  起動とゲームループ
system/
  operate.py             キー設定と入力
  renderer.py            描画と移動アニメーション
  dungeon/dungeon.py     マップ・配置・移動ルール・生成
  savedata/savedata.py   現在地などの保存
  logs/tracing.py        ログ
  configuration.py      YAML読み込み
values/                  ゲーム・操作・描画の設定とセーブデータ
tests/                   回帰用・全数用テスト
docs/class_methods.md    クラス・メソッドの役割一覧
```

設定は`values/setting.yml`、`values/operate.yml`、`values/renderer.yml`で変更します。
`values/savedata.yml`は起動時にダンジョン滞在フラグを保存するため更新されます。
ログファイルは`system/logs/game.log`へ出力され、起動ごとに上書きされます。

詳しくは[役割一覧](docs/class_methods.md)、[テスト手順](tests/README.md)、[開発ルール](AGENTS.md)を参照してください。
仮想環境・キャッシュ・実行ログ・ローカルのバックアップZIPはGit管理に含めません。
