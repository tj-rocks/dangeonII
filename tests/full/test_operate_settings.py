import copy

import pygame
import pytest

from system.configuration import load_settings
from system.operate import Operate
from system.operate import OperateSettings


@pytest.fixture(autouse=True)
def pygame_runtime(monkeypatch):
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    try:
        yield
    finally:
        pygame.quit()


def test_rebinding_moves_and_quits_with_configured_keys(dungeon):
    data = load_settings("operate.yml")
    data["bindings"].update(move_right="d", quit="q")
    settings = OperateSettings.from_dict(data)
    operate = Operate(dungeon, settings)
    assert operate.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT)) is None
    result = operate.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_d))
    assert result.moved
    assert dungeon.player_position == (1, 0)
    assert operate.is_quit_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_q))
    assert not operate.is_quit_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert operate.is_quit_event(pygame.event.Event(pygame.QUIT))


@pytest.mark.parametrize("case", ["missing", "unknown", "duplicate"])
def test_invalid_configuration_is_rejected(case):
    data = copy.deepcopy(load_settings("operate.yml"))
    if case == "missing":
        del data["bindings"]["quit"]
    elif case == "unknown":
        data["bindings"]["move_up"] = "not_a_key"
    elif case == "duplicate":
        data["bindings"]["move_up"] = data["bindings"]["move_down"]
    with pytest.raises(ValueError, match="operate.yml"):
        OperateSettings.from_dict(data)


def test_loading_does_not_depend_on_working_directory(tmp_path, monkeypatch):
    expected = load_settings("operate.yml")
    monkeypatch.chdir(tmp_path)
    assert load_settings("operate.yml") == expected


def test_held_key_continues_without_repeat_events_and_stops_on_release(dungeon):
    operate = Operate(dungeon)
    operate.track_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT))
    assert operate.move_held().moved
    assert operate.move_held().moved
    assert dungeon.player_position == (2, 0)
    operate.track_event(pygame.event.Event(pygame.KEYUP, key=pygame.K_RIGHT))
    assert operate.move_held() is None
    operate.track_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT))
    operate.track_event(pygame.event.Event(pygame.WINDOWFOCUSLOST))
    assert operate.move_held() is None
