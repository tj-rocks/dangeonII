"""設定と分けて、プレイ中に変化する状態をYAMLへ保存する。"""

import os
from pathlib import Path
from tempfile import NamedTemporaryFile

import yaml

from system.configuration import SETTINGS_DIR
from system.logs.tracing import trace_class


@trace_class(info_methods=("__init__", "enter_dungeon"))
class SaveData:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else SETTINGS_DIR / "savedata.yml"

    def load(self) -> dict:
        if not self.path.exists():
            return {}
        with self.path.open(encoding="utf-8") as stream:
            data = yaml.safe_load(stream)
        if not isinstance(data, dict):
            raise ValueError(f"{self.path}: セーブデータはマッピングにしてください")
        return data

    def enter_dungeon(self) -> None:
        data = self.load()
        data["dungeon"] = True
        self._save(data)

    def _save(self, data: dict) -> None:
        # 書き込み途中の終了で元データが欠けないよう、一時ファイルから置換する。
        temporary = None
        try:
            with NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                    prefix=".savedata-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                yaml.safe_dump(data, stream, allow_unicode=True, sort_keys=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
