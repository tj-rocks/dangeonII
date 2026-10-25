import pytest

from system import configuration


def test_yaml_comments_and_nested_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(configuration, "SETTINGS_DIR", tmp_path)
    (tmp_path / "test.yml").write_text(
        "# キー設定\nbindings:\n  move_up: w\n", encoding="utf-8")
    assert configuration.load_settings("test.yml") == {"bindings": {"move_up": "w"}}


@pytest.mark.parametrize("text", ["", "- up\n- down\n", "plain text"])
def test_non_mapping_yaml_is_rejected(tmp_path, monkeypatch, text):
    monkeypatch.setattr(configuration, "SETTINGS_DIR", tmp_path)
    (tmp_path / "test.yml").write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="マッピング"):
        configuration.load_settings("test.yml")
