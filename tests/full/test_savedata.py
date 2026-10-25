from unittest.mock import patch

import pytest
import yaml

from system.savedata import SaveData


def test_enter_dungeon_creates_and_persists_flag(tmp_path):
    path = tmp_path / "savedata.yml"
    SaveData(path).enter_dungeon()
    assert SaveData(path).load() == {"dungeon": True}
    assert yaml.safe_load(path.read_text()) == {"dungeon": True}


def test_enter_dungeon_preserves_future_fields(tmp_path):
    path = tmp_path / "savedata.yml"
    path.write_text("dungeon: false\nfloor: 3\n", encoding="utf-8")
    SaveData(path).enter_dungeon()
    assert SaveData(path).load() == {"dungeon": True, "floor": 3}


def test_failed_save_keeps_existing_file_and_removes_temporary(tmp_path):
    path = tmp_path / "savedata.yml"
    original = "dungeon: false\n"
    path.write_text(original, encoding="utf-8")
    with patch("system.savedata.savedata.os.replace", side_effect=OSError("write failed")):
        with pytest.raises(OSError):
            SaveData(path).enter_dungeon()
    assert path.read_text() == original
    assert list(tmp_path.iterdir()) == [path]


def test_invalid_save_is_not_silently_overwritten(tmp_path):
    path = tmp_path / "savedata.yml"
    path.write_text("- dungeon\n", encoding="utf-8")
    with pytest.raises(ValueError):
        SaveData(path).enter_dungeon()
    assert path.read_text() == "- dungeon\n"
