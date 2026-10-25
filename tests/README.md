# テストの実行

開発用依存のインストール:

```bash
python -m pip install -r tests/requirements-dev.txt
```

回帰用・CI実行（移動できる／移動できない、2件）:

```bash
python -m pytest -c tests/pytest.ini tests/regression -v
```

全数用（回帰用と詳細な検証を含む）:

```bash
python -m pytest -c tests/pytest.ini tests -v
```

全数時のみの詳細な検証だけ実行:

```bash
python -m pytest -c tests/pytest.ini tests/full -v
```

設定ファイルはtests/pytest.iniに置き、通常の対象をtests/regressionに限定しています。
上記コマンドはプロジェクトルートから実行してください。
移動不可も仕様どおりの正常な結果として扱い、不正引数やログの検証はtests/fullに置いています。
回帰用はPygameを必要としません。全数用のキー設定テストはPygameを使用しますが、画面は開きません。
全数は登録済み自動テストの全件を指し、手動の画面確認は含みません。
