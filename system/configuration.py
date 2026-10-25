"""実行ディレクトリに依存せずプロジェクトのvaluesから読み込む。"""

import yaml
from pathlib import Path

SETTINGS_DIR = Path(__file__).resolve().parent.parent / "values"


def load_settings(filename: str) -> dict:
    path = SETTINGS_DIR / filename
    with path.open(encoding="utf-8") as stream:
        data = yaml.safe_load(stream)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: YAMLの最上位はマッピングにしてください")
    return data
