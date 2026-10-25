from system.dungeon import Enemy, Tile


def test_player_cannot_move_into_wall_enemy_or_outside(dungeon):
    dungeon.set_tile(0, 1, Tile.WALL)
    dungeon.place(Enemy(), 1, 0)
    before = (dungeon.terrain, dungeon.actors, dungeon.items)

    for delta, reason in [((-1, 0), "out_of_bounds"),
                          ((0, 1), "wall"), ((1, 0), "occupied")]:
        result = dungeon.move_player(*delta)

        assert not result.moved
        assert result.reason == reason
        assert dungeon.player_position == (0, 0)
        assert (dungeon.terrain, dungeon.actors, dungeon.items) == before
