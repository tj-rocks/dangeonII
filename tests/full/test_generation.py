from collections import deque

import pytest

from system.configuration import load_settings
from system.dungeon import DungeonGenerator, Tile


def make_generator(seed=42, **overrides):
    world = load_settings('setting.yml')['dungeon']
    settings = dict(world['generation'], seed=seed)
    settings.update(overrides)
    return DungeonGenerator(world['width'], world['height'], **settings)


@pytest.mark.parametrize('seed', [0, 1, 42, 100, 999])
def test_rooms_walls_and_all_floors_are_connected(seed):
    generator = make_generator(seed)
    dungeon = generator.generate()
    terrain = dungeon.terrain
    assert (dungeon.width, dungeon.height) == (100, 100)
    assert len(generator.rooms) == generator.room_count
    for index, room in enumerate(generator.rooms):
        assert generator.room_min_size[0] <= room.width <= generator.room_max_size[0]
        assert generator.room_min_size[1] <= room.height <= generator.room_max_size[1]
        assert all(not room.overlaps(other, generator.wall_thickness)
                   for other in generator.rooms[:index])
        assert all(terrain[y][x] == Tile.FLOOR
                   for y in range(room.y, room.y + room.height)
                   for x in range(room.x, room.x + room.width))
    margin = generator.wall_thickness
    assert all(terrain[y][x] == Tile.WALL
               for y in range(dungeon.height) for x in range(dungeon.width)
               if x < margin or y < margin or x >= dungeon.width - margin or y >= dungeon.height - margin)
    start = generator.rooms[0].center
    seen = {start}
    queue = deque([start])
    while queue:
        x, y = queue.popleft()
        for nx, ny in [(x-1, y), (x+1, y), (x, y-1), (x, y+1)]:
            if (nx, ny) not in seen and terrain[ny][nx] == Tile.FLOOR:
                seen.add((nx, ny))
                queue.append((nx, ny))
    assert len(seen) == sum(tile == Tile.FLOOR for row in terrain for tile in row)


def test_seed_reproduces_terrain_and_floor_spawns():
    first, second = make_generator(), make_generator()
    a, b = first.generate(), second.generate()
    assert a.terrain == b.terrain
    first.populate(a, 'Player', ['薬'], ['敵'])
    second.populate(b, 'Player', ['薬'], ['敵'])
    assert a.player_position == b.player_position == first.rooms[0].center
    assert [[type(v) for v in row] for row in a.actors] == [[type(v) for v in row] for row in b.actors]
    assert [[type(v) for v in row] for row in a.items] == [[type(v) for v in row] for row in b.items]
    assert all(a.terrain[y][x] == Tile.FLOOR
               for y, row in enumerate(a.actors) for x, actor in enumerate(row) if actor is not None)


def test_impossible_room_count_fails_instead_of_silently_reducing():
    with pytest.raises(ValueError, match='配置できません'):
        make_generator(room_count=10000, max_attempts=20).generate()


def test_invalid_room_sizes_fail():
    with pytest.raises(ValueError):
        make_generator(room_min_size=[20, 20], room_max_size=[5, 5])


def test_corridor_is_three_cells_wide_in_both_directions_and_at_corner():
    from system.dungeon import Dungeon

    generator = make_generator()
    dungeon = Dungeon(20, 20)
    for y in range(20):
        for x in range(20):
            dungeon.set_tile(x, y, Tile.WALL)
    generator._carve(dungeon, (5, 5), (10, 5))
    generator._carve(dungeon, (10, 5), (10, 12))
    terrain = dungeon.terrain
    assert all(terrain[y][x] == Tile.FLOOR for y in (4, 5, 6) for x in range(4, 12))
    assert all(terrain[y][x] == Tile.FLOOR for y in range(4, 14) for x in (9, 10, 11))
    assert terrain[3][7] == terrain[7][7] == Tile.WALL
    assert terrain[10][8] == terrain[10][12] == Tile.WALL


@pytest.mark.parametrize('width', [0, 2, 7])
def test_invalid_corridor_width_is_rejected(width):
    with pytest.raises(ValueError):
        make_generator(corridor_width=width)
