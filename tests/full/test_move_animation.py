import pytest

from system.renderer import MoveAnimation


def test_continuous_interpolation_then_exact_destination():
    animation = MoveAnimation(duration_ms=90)
    animation.start((1, 1), (2, 1), now_ms=100)
    assert animation.position(100) == (1, 1)
    assert animation.position(115) == pytest.approx((1 + 1 / 6, 1))
    assert animation.position(130) == pytest.approx((1 + 1 / 3, 1))
    assert animation.position(160) == pytest.approx((1 + 2 / 3, 1))
    assert animation.is_active(189)
    assert animation.position(190) == (2, 1)
    assert not animation.is_active(190)
    assert animation.position(1000) == (2, 1)


def test_animation_does_not_change_dungeon_coordinates(dungeon):
    before = dungeon.player_position
    dungeon.move_player(1, 0)
    animation = MoveAnimation(90)
    animation.start(before, dungeon.player_position, 0)
    for now in (0, 30, 60, 90):
        animation.position(now)
        assert dungeon.player_position == (1, 0)
        assert dungeon.actors[0][0] is None
        assert dungeon.actors[0][1] is not None


def test_next_move_starts_from_previous_destination():
    animation = MoveAnimation(90)
    assert animation.position(0) is None
    assert not animation.is_active(0)
    animation.start((2, 2), (1, 2), 0)
    assert animation.position(60) == pytest.approx((2 - 2 / 3, 2))
    animation.start((1, 2), (1, 1), 90)
    assert animation.position(90) == (1, 2)
    assert animation.position(180) == (1, 1)


@pytest.mark.parametrize('duration', [0, -1])
def test_invalid_animation_settings(duration):
    with pytest.raises(ValueError):
        MoveAnimation(duration)


@pytest.mark.parametrize('direction', [(1,0),(0,1),(-1,0),(0,-1)])
@pytest.mark.parametrize('height', [0,1,4])
def test_same_height_floor_never_overwrites_player_during_move(monkeypatch, direction, height):
    import pygame
    from system.dungeon import Dungeon,Player
    from system.renderer import DungeonRenderer
    monkeypatch.setenv('SDL_VIDEODRIVER','dummy')
    monkeypatch.setenv('SDL_AUDIODRIVER','dummy')
    pygame.init()
    try:
        dungeon = Dungeon(12,12)
        for y in range(12):
            for x in range(12):
                dungeon.set_elevation(x,y,height*2)
        dungeon.place(Player(),5,5)
        dx,dy = direction
        assert dungeon.move_player(dx,dy).moved
        renderer = DungeonRenderer(pygame.Surface((640,600)))
        renderer.move_animation.start((5,5),(5+dx,5+dy),0,height,height)
        expected = None
        for now in range(0,renderer.move_animation.duration_ms+1):
            renderer.draw(dungeon,now,show_hud=False)
            rect,_,shape = renderer._player_visibility_snapshot(320,300)
            pixels = tuple(renderer.screen.get_at((rect.x+x,rect.y+y))
                           for y in range(rect.height) for x in range(rect.width)
                           if shape.get_at((x,y)).a)
            if expected is None:
                expected = pixels
            assert pixels == expected, (direction,height,now)
            assert dungeon.player_position == (5+dx,5+dy)
    finally:
        pygame.quit()
