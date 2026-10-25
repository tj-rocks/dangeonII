import pygame
import pytest

from system.dungeon import Dungeon, Player, Tile
from system.renderer import DungeonRenderer


@pytest.fixture
def renderer(monkeypatch):
    monkeypatch.setenv('SDL_VIDEODRIVER', 'dummy')
    monkeypatch.setenv('SDL_AUDIODRIVER', 'dummy')
    pygame.init()
    yield DungeonRenderer(pygame.Surface((640, 600)))
    pygame.quit()


def test_faces_exist_only_between_floor_and_wall(renderer):
    dungeon = Dungeon(5, 5)
    dungeon.set_tile(2, 1, Tile.WALL)
    assert renderer.wall_faces(dungeon.terrain, 2, 2) == [('north', 0, -1)]
    assert renderer.wall_faces(dungeon.terrain, 2, 1) == []


def test_wall_face_keeps_both_layers_and_has_no_wide_top(renderer):
    screen = renderer.screen
    screen.fill((0, 0, 0))
    renderer._draw_wall_face(160, 200, 'north', 0, -1)
    layers = renderer.config['wall_layers']
    assert renderer.wall_height == renderer.tile_height * 2
    assert screen.get_at((176, 176))[:3] == tuple(layers[0]['colors']['right'])
    assert screen.get_at((176, 144))[:3] == tuple(layers[1]['colors']['right'])
    assert screen.get_at((140, 120))[:3] == (0, 0, 0)


def test_only_front_faces_receive_circle_transparency(renderer):
    renderer.camera = (0, 0)
    renderer._fade_mask.fill((255, 255, 255, 65))
    for direction, dx, dy, pixel in [('north', 0, -1, (176, 176)),
                                    ('south', 0, 1, (144, 192))]:
        renderer.screen.fill((0, 0, 0))
        renderer.config['wall_occlusion']['enabled'] = False
        renderer._draw_wall_face(160, 200, direction, dx, dy)
        opaque = renderer.screen.get_at(pixel)[:3]
        renderer.screen.fill((0, 0, 0))
        renderer.config['wall_occlusion']['enabled'] = True
        renderer._draw_wall_face(160, 200, direction, dx, dy)
        result = renderer.screen.get_at(pixel)[:3]
        if direction == 'north':
            assert result == opaque
        else:
            assert all(0 < f < o for f, o in zip(result, opaque))


def test_wall_interior_has_no_floor_and_collision_is_preserved(renderer):
    dungeon = Dungeon(20, 20)
    dungeon.place(Player(), 10, 9)
    for y in range(10, 20):
        for x in range(20):
            dungeon.set_tile(x, y, Tile.WALL)
    renderer.config['wall_occlusion']['alpha'] = 0
    renderer._fade_circle = renderer._make_fade_circle()
    before = dungeon.terrain
    renderer.draw(dungeon, 0)
    cx, cy = renderer.map_to_screen(10, 11, dungeon)
    assert renderer.screen.get_at((cx, cy))[:3] == tuple(renderer.colors['wall_ground'])
    assert dungeon.terrain == before
    assert not dungeon.move_player(0, 1).moved


def test_circular_fade_has_smooth_edge_and_opaque_outside(monkeypatch):
    from system.dungeon import Dungeon, Player
    monkeypatch.setenv('SDL_VIDEODRIVER', 'dummy')
    monkeypatch.setenv('SDL_AUDIODRIVER', 'dummy')
    pygame.init()
    try:
        renderer = DungeonRenderer(pygame.Surface((640, 600)))
        d = Dungeon(20, 20)
        d.place(Player(), 10, 10)
        renderer.camera = (10, 10)
        renderer._prepare_fade_mask(d)
        mask = renderer._fade_mask
        alpha = renderer.config['wall_occlusion']['alpha']
        assert mask.get_at((320, 300)).a == alpha
        assert mask.get_at((480, 300)).a == 255
        assert mask.get_at((320, 460)).a == 255
        assert mask.get_at((440, 420)).a == 255  # 四角ではなく円形
        values = [mask.get_at((320 + r, 300)).a for r in range(160)]
        assert len(set(values)) > 30
        assert all(a <= b for a, b in zip(values, values[1:]))
        assert max(b - a for a, b in zip(values, values[1:])) < 10
    finally:
        pygame.quit()
