import pytest

from system.dungeon import Enemy, Item, Player, Tile


def test_floor_generation_and_independent_rows(dungeon):
    assert dungeon.terrain == [[0] * 4 for _ in range(3)]
    dungeon.set_tile(1, 0, Tile.WALL)
    assert dungeon.terrain[1][1] == Tile.FLOOR


def test_item_is_collected_only_once(dungeon):
    item = Item("薬")
    dungeon.place(item, 1, 0)
    result = dungeon.move_player(1, 0)
    assert result.item is item
    assert dungeon.items[0][1] is None
    dungeon.move_player(-1, 0)
    assert dungeon.move_player(1, 0).item is None


def test_invalid_moves_and_duplicate_placement(dungeon):
    for delta in [(1, 1), (2, 0), (0, 0)]:
        with pytest.raises(ValueError):
            dungeon.move_player(*delta)
    player = dungeon.actors[0][0]
    for entity in [player, Player()]:
        with pytest.raises(ValueError):
            dungeon.place(entity, 2, 2)
    with pytest.raises(ValueError):
        dungeon.place(Item(), -1, 0)
    with pytest.raises(ValueError):
        dungeon.set_tile(0, 0, Tile.WALL)


def test_enemy_moves_without_collecting_item(dungeon):
    enemy, item = Enemy(), Item()
    dungeon.place(enemy, 2, 1)
    dungeon.place(item, 3, 1)
    assert dungeon.move_actor(enemy, 1, 0).moved
    assert dungeon.position_of(enemy) == (3, 1)
    assert dungeon.items[1][3] is item


def test_returned_arrays_cannot_change_internal_state(dungeon):
    dungeon.terrain[0][0] = Tile.WALL
    dungeon.actors[0][0] = None
    assert dungeon.terrain[0][0] == Tile.FLOOR
    assert dungeon.player_position == (0, 0)
