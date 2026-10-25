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
    assert len(generator.rooms) == generator.section_count
    for index, room in enumerate(generator.rooms):
        assert [room.width, room.height] in generator.section_sizes
        assert room.elevation in generator.section_elevations
        assert all(not room.overlaps(other, 0) for other in generator.rooms[:index])
        assert all(not room.overlaps(other, generator.wall_thickness)
                   or room.adjoins(other, generator.corridor_width) for other in generator.rooms[:index])
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
        make_generator(section_count=10000, max_attempts=20).generate()


def test_invalid_room_sizes_fail():
    with pytest.raises(ValueError):
        make_generator(section_sizes=[[4, 4]])


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


def test_adjacent_sections_are_generated_and_connected_by_real_movement():
    generator = make_generator(adjacent_probability=1)
    dungeon = generator.generate()
    assert all(any(room.adjoins(other, generator.corridor_width) for other in generator.rooms[:index])
               for index, room in enumerate(generator.rooms) if index > 0)
    assert any(room.elevation != other.elevation and room.adjoins(other, generator.corridor_width)
               for room in generator.rooms for other in generator.rooms if room is not other)
    total = sum(tile == Tile.FLOOR for row in dungeon.terrain for tile in row)
    assert len(dungeon.reachable_from(generator.rooms[0].center)) == total


def test_non_adjacent_sections_keep_wall_spacing():
    generator = make_generator(adjacent_probability=0)
    generator.generate()
    assert all(not room.overlaps(other, generator.wall_thickness)
               for index, room in enumerate(generator.rooms) for other in generator.rooms[:index])


def test_impossible_height_connection_is_not_returned_as_playable_map():
    from system.dungeon import Dungeon, Room
    generator = make_generator()
    dungeon = Dungeon(6, 6)
    for y in range(6):
        for x in range(6):
            dungeon.set_tile(x, y, Tile.WALL)
    dungeon.set_tile(2, 2, Tile.FLOOR)
    dungeon.set_tile(3, 2, Tile.FLOOR)
    dungeon.set_elevation(2, 2, 2)
    dungeon.set_elevation(3, 2, 4)
    generator.rooms = (Room(2, 2, 1, 1),)
    with pytest.raises(ValueError, match='階段の設置場所'):
        generator._connect_elevations(dungeon)


@pytest.mark.parametrize('boundary,allowed', [((1,0),False), ((0,1),False), ((-1,0),True), ((0,-1),True)])
def test_stairs_only_connect_to_right_or_bottom_of_high_floor_and_cliffs_stay(boundary, allowed):
    from system.dungeon import Dungeon, Room
    from system.dungeon.dungeon import StairPlacementError
    generator = make_generator()
    dungeon = Dungeon(24, 24)
    for y in range(24):
        for x in range(24):
            dungeon.set_tile(x, y, Tile.WALL)
    dx, dy = boundary
    low = Room(8, 8, 7, 7, 1)
    high = Room(8+dx*7, 8+dy*7, 7, 7, 3)
    generator.rooms = (low, high)
    for room in generator.rooms:
        for y in range(room.y, room.y+room.height):
            for x in range(room.x, room.x+room.width):
                dungeon.set_tile(x,y,Tile.FLOOR)
                dungeon.set_elevation(x,y,room.elevation*2)
    before = dungeon.elevations
    if allowed:
        generator._connect_elevations(dungeon)
        assert len(dungeon.reachable_from(low.center)) == 98
        assert any(block for row in dungeon.stair_blocks for block in row)
    else:
        with pytest.raises(StairPlacementError):
            generator._connect_elevations(dungeon)
        assert dungeon.elevations == before  # 禁止側の崖を平坦化しない。
        assert all(block is None for row in dungeon.stair_blocks for block in row)


@pytest.mark.parametrize('seed', [0, 1, 42, 100, 999])
def test_generated_stair_connections_follow_allowed_sides_and_all_floors_remain_reachable(seed, monkeypatch):
    generator = make_generator(seed)
    room_layout = generator._room_stair_layouts
    corridor_layout = generator._stair_layout
    calls = []
    def room_check(x,y,direction,*args):
        assert direction in ((-1,0),(0,-1))
        calls.append(direction)
        return room_layout(x,y,direction,*args)
    def corridor_check(chain,*args):
        assert chain[0][3] in ((-1,0),(0,-1))
        calls.append(chain[0][3])
        return corridor_layout(chain,*args)
    monkeypatch.setattr(generator,'_room_stair_layouts',room_check)
    monkeypatch.setattr(generator,'_stair_layout',corridor_check)
    dungeon = generator.generate()
    assert calls
    assert len({r.elevation for r in generator.rooms}) > 1
    assert len(dungeon.reachable_from(generator.rooms[0].center)) == sum(
        tile == Tile.FLOOR for row in dungeon.terrain for tile in row)


@pytest.mark.parametrize('sides', [[], ['up'], [None], 'east'])
def test_invalid_stair_sides_are_rejected(sides):
    with pytest.raises(ValueError, match='stair_sides'):
        make_generator(stair_sides=sides)


@pytest.mark.parametrize('seed', [0,1,42,100,999])
def test_corridor_stairs_and_landing_stay_clear_of_other_corridor_branches(seed):
    generator = make_generator(seed)
    dungeon = generator.generate()
    blocks, terrain = dungeon.stair_blocks, dungeon.terrain
    corridor_blocks = []
    for y,row in enumerate(blocks):
        for x,block in enumerate(row):
            if block is None or any(r.x <= x < r.x+r.width and r.y <= y < r.y+r.height for r in generator.rooms):
                continue
            corridor_blocks.append((x,y))
            dx,dy = block.up_direction
            for ox,oy in ((-dy,dx),(dy,-dx)):
                nx,ny = x+ox,y+oy
                if terrain[ny][nx] == Tile.FLOOR:
                    other = blocks[ny][nx]
                    assert other is not None  # 階段の横から通常通路が合流しない。
                    assert other.base_height == block.base_height
                    assert other.up_direction == block.up_direction
            if block.base_height == generator.corridor_elevation:
                nx,ny = x-dx,y-dy
                assert blocks[ny][nx] is None
                assert dungeon.floor_height(nx,ny) == generator.corridor_elevation
                # 下端の平らな踊り場にも、通路幅の外から分岐が食い込まない。
                for sign in (-1,1):
                    ox,oy = -dy*sign,dx*sign
                    sx,sy = nx,ny
                    width = 0
                    while dungeon.in_bounds(sx,sy) and terrain[sy][sx] == Tile.FLOOR:
                        width += 1
                        sx,sy = sx+ox,sy+oy
                    assert width <= generator.corridor_width
    assert corridor_blocks


def test_room_height_determines_required_space_before_room_is_accepted():
    from system.dungeon import Room
    generator = make_generator(stair_sides=['east'])
    neighbor = Room(17,4,6,6,1)
    low = Room(4,4,6,6,1)
    high = Room(4,4,6,6,4)
    assert generator._plan_entrance(low,[neighbor],[]) is not None
    assert generator._plan_entrance(high,[neighbor],[]) is None
    plan = generator._plan_entrance(high,[],[])
    assert plan is not None
    assert len(plan.run)-1 >= high.elevation-generator.corridor_elevation+generator.stair_landing_length
    # 次の部屋も、先に決まった階段の場所へ入れない。
    assert generator._plan_entrance(neighbor,[high],[plan]) is None


def test_all_rooms_have_height_based_entrance_plan_before_routing(monkeypatch):
    generator = make_generator()
    route = generator._route_corridors
    seen = []
    def check_plans(dungeon,rooms):
        assert len(generator.entrance_plans) == len(rooms)
        assert [p.room for p in generator.entrance_plans] == rooms
        for plan in generator.entrance_plans:
            assert plan.stair_area <= plan.area
            for room in rooms:
                if room is plan.room:
                    continue
                assert not any(room.x <= x < room.x+room.width and room.y <= y < room.y+room.height
                               for x,y in plan.area | plan.protected)
        seen.append(True)
        route(dungeon,rooms)
    monkeypatch.setattr(generator,'_route_corridors',check_plans)
    dungeon = generator.generate()
    assert seen
    assert len(dungeon.reachable_from(generator.rooms[0].center)) == sum(
        tile == Tile.FLOOR for row in dungeon.terrain for tile in row)


@pytest.mark.parametrize('landing', [0,-1,True])
def test_stair_landing_requires_positive_integer(landing):
    with pytest.raises(ValueError):
        make_generator(stair_landing_length=landing)


@pytest.mark.parametrize('seed',[0,1,42,100,999])
def test_generated_flat_cliffs_only_face_right_or_bottom(seed):
    generator = make_generator(seed)
    dungeon = generator.generate()
    terrain,elevations,blocks = dungeon.terrain,dungeon.elevations,dungeon.stair_blocks
    for y,row in enumerate(terrain):
        for x,tile in enumerate(row):
            if tile != Tile.FLOOR or blocks[y][x] is not None:
                continue
            for dx,dy in ((-1,0),(0,-1)):
                nx,ny = x+dx,y+dy
                if (dungeon.in_bounds(nx,ny) and terrain[ny][nx] == Tile.FLOOR
                        and blocks[ny][nx] is None):
                    assert elevations[y][x] <= elevations[ny][nx], (seed,(x,y),(nx,ny))
    assert len({room.elevation for room in generator.rooms}) > 1
    assert len(dungeon.reachable_from(generator.rooms[0].center)) == sum(
        tile == Tile.FLOOR for row in terrain for tile in row)


@pytest.mark.parametrize('direction,allowed', [((1,0),False),((0,1),False),((-1,0),True),((0,-1),True)])
def test_room_adjacency_rejects_hidden_cliff_before_placement(direction,allowed):
    from system.dungeon import Room
    generator = make_generator()
    dx,dy = direction
    low = Room(12,12,6,6,1)
    high = Room(12+dx*6,12+dy*6,6,6,2)
    assert generator._room_cliff_allowed(low,high) is allowed
    assert generator._room_cliff_allowed(high,low) is allowed


@pytest.mark.parametrize('sides',[[],['up'],[None],'east'])
def test_invalid_cliff_sides_are_rejected(sides):
    with pytest.raises(ValueError,match='cliff_sides'):
        make_generator(cliff_sides=sides)


@pytest.mark.parametrize('seed',[0,42])
def test_stair_clearance_reserves_space_without_extra_rooms_or_corridors(seed):
    generator = make_generator(seed)
    dungeon = generator.generate()
    terrain = dungeon.terrain
    for plan in generator.entrance_plans:
        for x,y in plan.protected-plan.area:
            if not dungeon.in_bounds(x,y):
                continue
            room = plan.room
            if room.x <= x < room.x+room.width and room.y <= y < room.y+room.height:
                continue
            assert terrain[y][x] == Tile.WALL
    assert generator.stair_clearance == 2
