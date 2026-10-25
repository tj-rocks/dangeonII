from collections import deque

import pytest

from system.configuration import load_settings
from system.dungeon import Dungeon, DungeonGenerator, Player, Tile
from system.renderer import MoveAnimation


def test_stairs_allow_round_trip_but_cliffs_do_not():
    dungeon = Dungeon(8, 5)
    # 地上0 → 標高0〜1を接続する階段ブロック → 高台1。横入りは禁止。
    dungeon.set_stair_block(2, 2, 0, (1, 0))
    dungeon.set_elevation(3, 2, 2)
    dungeon.set_elevation(4, 2, 2)
    dungeon.place(Player(), 1, 2)
    assert dungeon.move_player(1, 0).moved
    assert dungeon.floor_height(*dungeon.player_position) == 0.5
    before = dungeon.actors
    assert dungeon.move_player(0, -1).reason == "height_blocked"
    assert dungeon.actors == before
    assert dungeon.move_player(1, 0).moved
    assert dungeon.floor_height(*dungeon.player_position) == 1
    assert dungeon.move_player(0, 1).reason == "height_blocked"
    assert dungeon.move_player(-1, 0).moved
    assert dungeon.move_player(-1, 0).moved
    assert dungeon.player_position == (1, 2)


def test_half_height_without_stairs_is_not_climbable():
    dungeon = Dungeon(4, 4)
    dungeon.set_elevation(2, 1, 1)
    dungeon.place(Player(), 1, 1)
    assert dungeon.move_player(1, 0).reason == "height_blocked"


def test_height_arrays_are_copies_and_invalid_changes_are_rejected():
    dungeon = Dungeon(4, 4)
    dungeon.set_elevation(1, 1, 2)
    dungeon.elevations[1][1] = 99
    assert dungeon.floor_height(1, 1) == 1
    dungeon.set_tile(1, 1, Tile.WALL)
    assert dungeon.elevations[1][1] == 0
    with pytest.raises(ValueError):
        dungeon.set_elevation(1, 1, 2)
    with pytest.raises(ValueError):
        dungeon.set_elevation(2, 2, -1)


@pytest.mark.parametrize("seed", [0, 1, 42, 100, 999])
@pytest.mark.parametrize("corridor_level", [1, 2])
def test_generated_elevation_sections_keep_all_floors_reachable(seed, corridor_level):
    world = load_settings("setting.yml")["dungeon"]
    generator = DungeonGenerator(world["width"], world["height"],
                                 **dict(world["generation"], seed=seed, corridor_elevation=corridor_level))
    dungeon = generator.generate()
    terrain, elevations = dungeon.terrain, dungeon.elevations
    assert any(value in (2, 4) for row in elevations for value in row)
    assert all(value in range(2 * max(generator.section_elevations + [corridor_level]) + 1) for row in elevations for value in row)
    start = generator.rooms[0].center
    seen, queue = {start}, deque([start])
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if (nx, ny) not in seen and dungeon.can_step(x, y, nx, ny):
                seen.add((nx, ny))
                queue.append((nx, ny))
    assert len(seen) == sum(value == Tile.FLOOR for row in terrain for value in row)
    generator.populate(dungeon, "Player", ["薬"], ["敵"])
    assert dungeon.floor_height(*dungeon.player_position) == generator.rooms[0].elevation
    assert all(dungeon.stair_axes[y][x] is None for y, row in enumerate(dungeon.actors)
               for x, actor in enumerate(row) if actor is not None)


def test_seed_reproduces_heights_and_stair_directions():
    world = load_settings("setting.yml")["dungeon"]
    generator = DungeonGenerator(world["width"], world["height"],
                                 **dict(world["generation"], seed=42))
    a, b = generator.generate(), generator.generate()
    assert a.elevations == b.elevations
    assert a.stair_axes == b.stair_axes


def test_vertical_animation_is_continuous():
    animation = MoveAnimation(100)
    animation.start((1, 1), (2, 1), 0, 0, 0.5)
    assert animation.height(0) == 0
    assert animation.height(50) == 0.25
    assert animation.height(100) == 0.5
    animation.start((2, 1), (1, 1), 100, 0.5, 0)
    assert animation.height(150) == 0.25
    assert animation.height(200) == 0


@pytest.mark.parametrize('height,axis', [(height, axis) for height in (1, 2, 3, 4) for axis in ('x', 'y')])
def test_each_height_and_stair_axis_can_be_walked_up_and_down(height, axis):
    dungeon = Dungeon(10, 10)
    dx, dy = (1, 0) if axis == 'x' else (0, 1)
    for step in range(height):
        dungeon.set_stair_block(2 + dx * (step + 1), 2 + dy * (step + 1), step, (dx, dy))
    dungeon.set_elevation(2 + dx * (height + 1), 2 + dy * (height + 1), height * 2)
    dungeon.place(Player(), 2, 2)
    for step in range(height + 1):
        assert dungeon.move_player(dx, dy).moved
    assert dungeon.floor_height(*dungeon.player_position) == height
    for step in range(height + 1):
        assert dungeon.move_player(-dx, -dy).moved
    assert dungeon.player_position == (2, 2)


@pytest.mark.parametrize('level', [1, 2, 3, 4])
def test_flat_sections_need_no_stairs_when_corridor_level_matches(level):
    world = load_settings('setting.yml')['dungeon']
    settings = dict(world['generation'], seed=42, section_elevations=[level], corridor_elevation=level)
    dungeon = DungeonGenerator(world['width'], world['height'], **settings).generate()
    assert all(value == level * 2 for y, row in enumerate(dungeon.elevations)
               for x, value in enumerate(row) if dungeon.terrain[y][x] == Tile.FLOOR)
    assert all(block is None for row in dungeon.stair_blocks for block in row)


@pytest.mark.parametrize('direction', [(1, 0), (-1, 0), (0, 1), (0, -1)])
def test_stair_block_connects_edges_and_has_continuous_surface(direction):
    dungeon = Dungeon(8, 8)
    dungeon.set_stair_block(3, 3, 1, direction)
    dx, dy = direction
    assert dungeon.edge_height(3, 3, dx, dy) == 2
    assert dungeon.edge_height(3, 3, -dx, -dy) == 1
    assert dungeon.edge_height(3, 3, -dy, dx) is None
    for t in (0.01, 0.25, 0.5, 0.75, 0.99):
        assert dungeon.surface_height(3 + dx * (t - 0.5), 3 + dy * (t - 0.5)) == pytest.approx(1 + t)
    copied = dungeon.stair_blocks
    copied[3][3] = None
    assert dungeon.stair_blocks[3][3] is not None


def test_sections_keep_assigned_elevation_except_stair_entrances():
    world = load_settings('setting.yml')['dungeon']
    generator = DungeonGenerator(world['width'], world['height'],
                                 **dict(world['generation'], seed=42))
    dungeon = generator.generate()
    elevations, blocks = dungeon.elevations, dungeon.stair_blocks
    for room in generator.rooms:
        for y in range(room.y, room.y + room.height):
            for x in range(room.x, room.x + room.width):
                if blocks[y][x] is None:
                    if elevations[y][x] != room.elevation * 2:
                        # 上端の1マス踊り場だけは、隣接する高い床と同じ標高になる。
                        assert elevations[y][x] > room.elevation * 2
                        assert any(dungeon.in_bounds(x-dx, y-dy)
                                   and (block := blocks[y-dy][x-dx]) is not None
                                   and block.up_direction == (dx, dy)
                                   and (block.base_height+1)*2 == elevations[y][x]
                                   for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)))
                else:
                    assert room.elevation <= blocks[y][x].base_height
                    assert blocks[y][x].base_height < max(generator.section_elevations)
    assert {room.elevation for room in generator.rooms} == {1, 2, 3, 4}


def test_stair_block_renders_treads_without_changing_map(monkeypatch):
    import pygame
    from system.renderer import DungeonRenderer
    monkeypatch.setenv('SDL_VIDEODRIVER', 'dummy')
    monkeypatch.setenv('SDL_AUDIODRIVER', 'dummy')
    pygame.init()
    try:
        dungeon = Dungeon(12, 12)
        screen = pygame.Surface((640, 600))
        renderer = DungeonRenderer(screen)
        assert renderer.config["stairs"]["treads_per_block"] == 2
        for direction in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            dungeon.set_stair_block(4, 5, 0, direction)
            before = dungeon.elevations
            screen.fill((0, 0, 0))
            renderer._draw_stair_block(4, 5, dungeon.stair_blocks[5][4], dungeon)
            # 踏み面と蹴上げの両方が実際の画素に描かれる。
            colors = {screen.get_at((x, y))[:3] for y in range(200, 330) for x in range(240, 370)}
            assert tuple(renderer.colors['platform_odd']) in colors
            assert tuple(renderer.colors['platform_side_left']) in colors
            assert dungeon.elevations == before
    finally:
        pygame.quit()


@pytest.mark.parametrize("direction", [(1, 0), (-1, 0), (0, 1), (0, -1)])
def test_generated_three_block_stair_chain_connects_height_one_to_four(direction):
    from system.dungeon.dungeon import Room
    world = load_settings('setting.yml')['dungeon']
    generator = DungeonGenerator(world['width'], world['height'], **dict(world['generation'], stair_sides=['north', 'west', 'south', 'east'], cliff_sides=['north', 'west', 'south', 'east']))
    dungeon = Dungeon(12, 12)
    for y in range(12):
        for x in range(12):
            dungeon.set_tile(x, y, Tile.WALL)
    dx, dy = direction
    start = (5 - 3*dx, 5 - 3*dy)
    for step in range(5):
        x, y = start[0] + dx*step, start[1] + dy*step
        dungeon.set_tile(x, y, Tile.FLOOR)
        dungeon.set_elevation(x, y, 8 if step == 4 else 2)
    generator.rooms = (Room(*start, 1, 1, 1),)
    generator._connect_elevations(dungeon)
    assert len(dungeon.reachable_from(start)) == 5
    assert [dungeon.stair_blocks[start[1]+dy*i][start[0]+dx*i].base_height
            for i in range(1, 4)] == [1, 2, 3]
    dungeon.place(Player(), *start)
    for _ in range(4):
        assert dungeon.move_player(dx, dy).moved
    assert dungeon.floor_height(*dungeon.player_position) == 4
    for _ in range(4):
        assert dungeon.move_player(-dx, -dy).moved


@pytest.mark.parametrize('direction', [(1, 0), (-1, 0), (0, 1), (0, -1)])
def test_corridor_stairs_cover_all_three_lanes(direction):
    from system.dungeon.dungeon import Room
    world = load_settings('setting.yml')['dungeon']
    generator = DungeonGenerator(world['width'], world['height'], **dict(world['generation'], stair_sides=['north', 'west', 'south', 'east'], cliff_sides=['north', 'west', 'south', 'east']))
    dungeon = Dungeon(14, 14)
    for y in range(14):
        for x in range(14):
            dungeon.set_tile(x, y, Tile.WALL)
    dx, dy = direction
    px, py = -dy, dx
    start = (6-3*dx, 6-3*dy)
    for lane in (-1, 0, 1):
        for step in range(5):
            x, y = start[0]+dx*step+px*lane, start[1]+dy*step+py*lane
            dungeon.set_tile(x, y, Tile.FLOOR)
            dungeon.set_elevation(x, y, 8 if step == 4 else 2)
    generator.rooms = (Room(*start, 1, 1, 1),)
    generator._connect_elevations(dungeon)
    for lane in (-1, 0, 1):
        for step in (1, 2, 3):
            block = dungeon.stair_blocks[start[1]+dy*step+py*lane][start[0]+dx*step+px*lane]
            assert block is not None
            assert block.base_height == step
            assert block.up_direction == direction
    assert len(dungeon.reachable_from(start)) == 15


@pytest.mark.parametrize('boundary', [(1, 0), (-1, 0), (0, 1), (0, -1)])
@pytest.mark.parametrize('high', [2, 3, 4])
def test_room_stairs_run_parallel_to_cliff_and_turn_at_one_tile_landing(boundary, high):
    from system.dungeon.dungeon import Room
    world = load_settings('setting.yml')['dungeon']
    generator = DungeonGenerator(world['width'], world['height'], **dict(world['generation'], seed=42, stair_sides=['north', 'west', 'south', 'east'], cliff_sides=['north', 'west', 'south', 'east']))
    dungeon = Dungeon(24, 24)
    for y in range(24):
        for x in range(24):
            dungeon.set_tile(x, y, Tile.WALL)
    dx, dy = boundary
    low_room = Room(8, 8, 7, 7, 1)
    high_room = Room(8+dx*7, 8+dy*7, 7, 7, high)
    generator.rooms = (low_room, high_room)
    for room in generator.rooms:
        for y in range(room.y, room.y+room.height):
            for x in range(room.x, room.x+room.width):
                dungeon.set_tile(x, y, Tile.FLOOR)
                dungeon.set_elevation(x, y, room.elevation*2)
    generator._connect_elevations(dungeon)
    blocks = [(x, y, block) for y, row in enumerate(dungeon.stair_blocks)
              for x, block in enumerate(row) if block is not None]
    assert len(blocks) == high-1
    assert all(block.up_direction[0]*dx + block.up_direction[1]*dy == 0
               for x, y, block in blocks)
    x, y, top = next(value for value in blocks if value[2].base_height == high-1)
    sx, sy = top.up_direction
    landing = (x+sx, y+sy)
    assert dungeon.stair_blocks[landing[1]][landing[0]] is None
    assert dungeon.floor_height(*landing) == high
    assert dungeon.can_step(x, y, *landing)
    assert dungeon.can_step(*landing, landing[0]+dx, landing[1]+dy)
    # 踊り場は1マスだけ。高い床へ曲がり、往復できる。
    changed_flats = [(x,y) for y in range(8,15) for x in range(8,15)
                     if dungeon.stair_blocks[y][x] is None and dungeon.floor_height(x,y) != 1]
    assert changed_flats == [landing]
    assert len(dungeon.reachable_from(low_room.center)) == 98
    dungeon.place(Player(), x, y)
    assert dungeon.move_player(sx, sy).moved
    assert dungeon.move_player(dx, dy).moved
    assert dungeon.move_player(-dx, -dy).moved
    assert dungeon.move_player(-sx, -sy).moved
