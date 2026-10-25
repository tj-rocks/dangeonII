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
