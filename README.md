# dangeonII

Python・Pygameで制作している、2Dクオータービューのダンジョン探索ゲームと、その制作基盤です。

## 現在の機能

- 2次元配列による地形・キャラクター・アイテムの座標管理
- 定型サイズの床区画と通路のランダム生成（離れた配置・隣接配置に対応）
- 1マス単位の移動と、長押し・滑らかな描画補間
- 床区画ごとのランダムな標高1〜4と、高低差に応じた連続階段（各ブロック2段・床と共通素材）での上り下り
- 高い床の右・下側だけに階段・平床間の段差を生成。上・左側には低い床を直接接触させず、許可側へ通路を回す
- 部屋の高さ・入口・階段・踊り場をセットで配置し、確定した入口同士を通路で結ぶ。階段のスペースが足りない部屋候補は配置しない
- 薄い2段の壁面と、手前の壁への円形グラデーション透過
- YAMLによるキー割り当て・描画設定・現在地フラグの保存
- 詳細度を切り替えられるメソッド呼び出しログ

階層移動、村、上下を両方歩ける中二階、完成した画像素材はまだ実装していません。
現在の高台は下に入れない構造です。

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


## 階段の見え方を判定する

```bash
python tools/check_stairs.py --seeds 0 1 42
```

生成結果は変えず、壁の透過・主人公を除いた状態で踏み面の可視率を測ります。
`artifacts/stair_visibility/`にseed別JSON、番号付き全体画像、見えにくい階段の拡大画像を出します。
赤は完全に隠れる、黄は可視率が閾値未満、緑は閾値以上です。既定の閾値は35%で、`values/stair_visibility.yml`から変更できます。
これは描画順に沿った画素の計測です。プレイヤーが階段だと認識できるかは画像で確認し、段差をなくす基準を決めます。地形の平坦化はまだ行いません。
