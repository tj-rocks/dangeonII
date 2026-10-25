import pygame
import pytest

from system.diagnostics.stair_visibility import StairVisibilityInspector
from system.dungeon import Dungeon, Player


@pytest.fixture(autouse=True)
def pygame_context(monkeypatch):
    monkeypatch.setenv('SDL_VIDEODRIVER', 'dummy')
    monkeypatch.setenv('SDL_AUDIODRIVER', 'dummy')
    pygame.init()
    yield
    pygame.quit()


def test_uncovered_and_fully_hidden_stairs_are_distinguished_without_changing_map():
    dungeon = Dungeon(12, 12)
    dungeon.set_stair_block(4, 4, 0, (1, 0))
    dungeon.place(Player(), 2, 2)
    inspector = StairVisibilityInspector(dungeon)
    _, report = inspector.inspect(dungeon, .35)
    assert report['flights'][0]['visible_ratio'] == 1
    assert report['flights'][0]['status'] == 'visible'
    for y in range(4, 9):
        for x in range(5, 9):
            dungeon.set_elevation(x, y, 12)
    before = (dungeon.terrain, dungeon.elevations, dungeon.stair_blocks, dungeon.actors)
    _, report = StairVisibilityInspector(dungeon).inspect(dungeon, .35)
    assert report['flights'][0]['visible_ratio'] == 0
    assert report['flights'][0]['status'] == 'hidden'
    assert before == (dungeon.terrain, dungeon.elevations, dungeon.stair_blocks, dungeon.actors)


def test_three_wide_two_block_stairs_are_one_flight():
    dungeon = Dungeon(12, 12)
    for x in range(4, 7):
        for y in range(4, 6):
            dungeon.set_stair_block(x, y, y-4, (0, 1))
    _, report = StairVisibilityInspector(dungeon).inspect(dungeon, .35)
    assert len(report['blocks']) == 6
    assert len(report['flights']) == 1
    flight = report['flights'][0]
    assert len(flight['coordinates']) == 6
    assert flight['visible_pixels'] == sum(b['visible_pixels'] for b in report['blocks'])
    assert flight['total_pixels'] == sum(b['total_pixels'] for b in report['blocks'])


def test_no_stairs_returns_empty_report_and_invalid_threshold_is_rejected():
    dungeon = Dungeon(4, 4)
    inspector = StairVisibilityInspector(dungeon)
    _, report = inspector.inspect(dungeon, .35)
    assert report == dict(blocks=[], flights=[])
    with pytest.raises(ValueError):
        inspector.inspect(dungeon, 2)
