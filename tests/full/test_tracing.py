import pytest

from system.dungeon import Dungeon
from system.logs.tracing import begin_trace_frame, logger, reset_trace_calls


@pytest.fixture
def trace_log(caplog, monkeypatch):
    reset_trace_calls()
    logger.addHandler(caplog.handler)
    monkeypatch.setattr(logger, "detail", 1)
    try:
        yield caplog
    finally:
        logger.removeHandler(caplog.handler)


def test_arguments_return_and_nested_calls(dungeon, trace_log, monkeypatch):
    monkeypatch.setattr(logger, "detail", 2)
    result = dungeon.move_player(dx=1, dy=0)
    assert "CALL Dungeon.move_player(dx=1, dy=0)" in trace_log.text
    assert "CALL Dungeon.move_actor(" in trace_log.text
    assert "RETURN Dungeon.move_player -> MoveResult(moved=True" in trace_log.text
    assert result.moved
    assert dungeon.player_position == (1, 0)


def test_exception_is_logged_and_reraised(trace_log, monkeypatch):
    monkeypatch.setattr(logger, "detail", 2)
    dungeon = Dungeon(3, 3)
    with pytest.raises(ValueError):
        dungeon.move_player(1, 0)
    assert "RAISE Dungeon.move_player" in trace_log.text


def test_queries_are_only_in_detail_three(dungeon, trace_log, monkeypatch):
    monkeypatch.setattr(logger, "detail", 3)
    dungeon.in_bounds(1, 2)
    assert "RETURN Dungeon.in_bounds -> True" in trace_log.text
    trace_log.clear()
    monkeypatch.setattr(logger, "detail", 2)
    dungeon.in_bounds(1, 2)
    assert not trace_log.records


def test_default_shows_method_at_entry_without_arguments(trace_log):
    dungeon = Dungeon(3, 3)
    assert [r.getMessage() for r in trace_log.records] == ["CALL Dungeon.__init__"]
    trace_log.clear()
    dungeon.in_bounds(1, 1)
    logger.info3("現在座標: (1, 1)")
    assert not trace_log.records


@pytest.mark.parametrize("detail", [1, 2, 3])
def test_all_severities_obey_detail_setting(detail, trace_log, monkeypatch):
    monkeypatch.setattr(logger, "detail", detail)
    for severity in ("info", "warn", "error"):
        for number in (1, 2, 3):
            getattr(logger, f"{severity}{number}")("sample")
    labels = [r.label for r in trace_log.records]
    assert labels == [f"{severity}{number}"
                      for severity in ("INFO", "WARN", "ERROR")
                      for number in range(1, detail + 1)]


def test_continuous_calls_are_logged_once_then_logged_after_pause(dungeon, trace_log, monkeypatch):
    monkeypatch.setattr(logger, "detail", 2)
    begin_trace_frame()
    dungeon.move_player(1, 0)
    dungeon.move_player(1, 0)
    begin_trace_frame()
    dungeon.move_player(-1, 0)
    messages = [r.getMessage() for r in trace_log.records]
    assert messages.count("CALL Dungeon.move_player") == 1
    assert sum(m.startswith("RETURN Dungeon.move_player") for m in messages) == 1
    begin_trace_frame()  # このフレームは呼ばない
    begin_trace_frame()
    dungeon.move_player(1, 0)
    messages = [r.getMessage() for r in trace_log.records]
    assert messages.count("CALL Dungeon.move_player") == 2
