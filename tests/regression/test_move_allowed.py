from system.dungeon import Dungeon, Player


def test_player_can_move_one_cell_in_each_direction():
    for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
        dungeon = Dungeon(3, 3)
        player = Player()
        dungeon.place(player, 1, 1)
        terrain_before = dungeon.terrain

        result = dungeon.move_player(dx, dy)

        assert result.moved
        assert result.reason == "moved"
        assert dungeon.player_position == (1 + dx, 1 + dy)
        assert dungeon.actors[1][1] is None
        assert dungeon.actors[1 + dy][1 + dx] is player
        assert dungeon.terrain == terrain_before
