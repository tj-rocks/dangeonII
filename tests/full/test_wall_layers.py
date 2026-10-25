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


def test_wall_endpoints_follow_stair_slope_without_extra_height(renderer):
    dungeon = Dungeon(9, 7)
    for x in range(1, 8):
        dungeon.set_tile(x, 1, Tile.WALL)
    dungeon.set_elevation(2, 2, 2)
    dungeon.set_stair_block(3, 2, 1, (1, 0))
    dungeon.set_stair_block(4, 2, 2, (1, 0))
    dungeon.set_elevation(5, 2, 6)
    before = dungeon.elevations
    profiles = renderer._wall_profiles(dungeon.terrain, dungeon.elevations, dungeon.stair_blocks)
    assert profiles[2, 2, 'north'] == (1, 1)
    assert profiles[3, 2, 'north'] == (1, 2)
    assert profiles[4, 2, 'north'] == (2, 3)
    assert profiles[5, 2, 'north'] == (3, 3)
    assert dungeon.elevations == before
    assert renderer._wall_profiles(dungeon.terrain, dungeon.elevations, dungeon.stair_blocks) is profiles
    dungeon.set_elevation(5, 2, 8)
    changed = renderer._wall_profiles(dungeon.terrain, dungeon.elevations, dungeon.stair_blocks)
    assert changed[5, 2, 'north'] == (4, 4)
    assert changed[3, 2, 'north'] == (1, 2)


def test_sloping_wall_layers_stay_two_tiles_tall(renderer, monkeypatch):
    polygons = []
    original = pygame.draw.polygon
    def capture(surface, color, points, *args):
        polygons.append(points)
        return original(surface, color, points, *args)
    monkeypatch.setattr(pygame.draw, 'polygon', capture)
    renderer._draw_wall_face(200, 300, 'north', 0, -1, (1, 2))
    assert len(polygons) == 3  # 2層と天端。底上げ用の余分な壁はない。
    for points in polygons[:2]:
        assert points[0][0] == points[3][0]
        assert points[1][0] == points[2][0]
        assert points[0][1]-points[3][1] == renderer.tile_height
        assert points[1][1]-points[2][1] == renderer.tile_height
    assert polygons[0][3] == polygons[1][0]
    assert polygons[0][2] == polygons[1][1]


def test_player_silhouette_only_appears_on_hidden_body(renderer):
    player = Player()
    renderer.screen.fill((20, 20, 20))
    renderer._draw_actor(player, 200, 250)
    snapshot = renderer._player_visibility_snapshot(200, 250)
    before = renderer.screen.copy()
    renderer._draw_occluded_player(snapshot)
    assert pygame.image.tobytes(renderer.screen, 'RGB') == pygame.image.tobytes(before, 'RGB')
    rect, _, shape = snapshot
    covered = pygame.Rect(rect.centerx, rect.top, rect.width, rect.height).clip(rect)
    pygame.draw.rect(renderer.screen, (50, 50, 50), covered)
    hidden = renderer.screen.copy()
    renderer._draw_occluded_player(snapshot)
    changed = 0
    for y in range(rect.height):
        for x in range(rect.width):
            point = (rect.x+x, rect.y+y)
            if renderer.screen.get_at(point) != hidden.get_at(point):
                assert covered.collidepoint(point)
                assert shape.get_at((x, y)).a
                changed += 1
    assert changed > 0
    renderer.config['player_occlusion']['enabled'] = False
    renderer.screen.blit(hidden, (0, 0))
    renderer._draw_occluded_player(snapshot)
    assert pygame.image.tobytes(renderer.screen, 'RGB') == pygame.image.tobytes(hidden, 'RGB')


@pytest.mark.parametrize('direction', [(1,0), (-1,0), (0,1), (0,-1)])
def test_stair_wall_endpoints_match_lower_and_upper_floor(renderer, direction):
    dungeon = Dungeon(9, 9)
    dx, dy = direction
    # 進行方向に対して左側へ壁を置く。
    wx, wy = -dy, dx
    names = {(1,0): 'east', (-1,0): 'west', (0,1): 'south', (0,-1): 'north'}
    name = names[wx, wy]
    for step in (-1, 0, 1):
        x, y = 4+dx*step, 4+dy*step
        dungeon.set_tile(x+wx, y+wy, Tile.WALL)
        dungeon.set_elevation(x, y, 2 if step < 1 else 4)
    dungeon.set_stair_block(4, 4, 1, direction)
    profiles = renderer._wall_profiles(dungeon.terrain, dungeon.elevations, dungeon.stair_blocks)
    assert sorted(profiles[4, 4, name]) == [1, 2]
    assert profiles[4-dx, 4-dy, name] == (1, 1)
    assert profiles[4+dx, 4+dy, name] == (2, 2)


@pytest.mark.parametrize('face,offset,up', [
    ('east', (1,0), (0,1)), ('east', (1,0), (0,-1)),
    ('south', (0,1), (1,0)), ('south', (0,1), (-1,0)),
])
def test_floor_beside_stairs_does_not_draw_cliff_to_zero(renderer, monkeypatch, face, offset, up):
    dungeon = Dungeon(10, 10)
    dungeon.set_elevation(4, 4, 8)
    nx, ny = 4+offset[0], 4+offset[1]
    dungeon.set_stair_block(nx, ny, 2, up)
    dungeon.place(Player(), 4, 4)
    assert dungeon.edge_height(nx, ny, -offset[0], -offset[1]) is None
    before = dungeon.elevations
    faces = []
    original = renderer._draw_riser
    def record(cx, cy, direction, drop):
        faces.append((cx, cy, direction, drop))
        original(cx, cy, direction, drop)
    monkeypatch.setattr(renderer, '_draw_riser', record)
    renderer.draw(dungeon, 0)
    cx, cy = renderer.map_to_screen(4, 4, dungeon, 4)
    assert (cx, cy, face, renderer.tile_height) in faces
    assert (cx, cy, face, renderer.tile_height*4) not in faces
    assert dungeon.elevations == before
    assert not dungeon.can_step(4, 4, nx, ny)


def test_terrain_order_does_not_switch_when_camera_leaves_exact_floor_height(renderer, monkeypatch):
    dungeon = Dungeon(18,18)
    for y in range(18):
        for x in range(18):
            dungeon.set_tile(x,y,Tile.WALL)
    # 奥の低い壁が、高い床に投影上重なる配置。
    dungeon.set_tile(7,7,Tile.FLOOR)
    dungeon.set_elevation(7,7,2)
    for y in range(8,13):
        for x in range(8,13):
            dungeon.set_tile(x,y,Tile.FLOOR)
            dungeon.set_elevation(x,y,6)
    dungeon.place(Player(),10,10)
    monkeypatch.setattr(dungeon,'surface_height',lambda x,y: 3)
    renderer.draw(dungeon,0,show_hud=False)
    exact = pygame.image.tobytes(renderer.screen,'RGB')
    # 投影先は丸めで同じ画素のまま。標高一致だけで地形の前後が変わってはいけない。
    monkeypatch.setattr(dungeon,'surface_height',lambda x,y: 2.999)
    renderer.draw(dungeon,0,show_hud=False)
    assert pygame.image.tobytes(renderer.screen,'RGB') == exact


def test_floor_brightness_increases_with_height_and_clamps(renderer):
    low = renderer._floor_color(True,0,1)
    high = renderer._floor_color(True,0,2)
    assert all(h > l for h,l in zip(high,low))
    assert renderer._floor_color(True,0,4) == renderer._floor_color(True,0,99)
    renderer.screen.fill((0,0,0))
    renderer._draw_floor(200,200,True,0,elevation=2)
    assert renderer.screen.get_at((200,200))[:3] == high


def test_cliff_edges_mark_all_directions_but_not_walls_or_stair_entrances(renderer):
    dungeon = Dungeon(7,7)
    for y in range(7):
        for x in range(7):
            dungeon.set_elevation(x,y,2)
    dungeon.set_elevation(3,3,4)
    edges = renderer._cliff_edges(dungeon.terrain,dungeon.elevations,dungeon.stair_blocks,3,3)
    assert set(edges) == {'north','west','south','east'}
    dungeon.set_stair_block(3,4,1,(0,-1))
    dungeon.set_tile(3,2,Tile.WALL)
    dungeon.set_elevation(2,3,4)
    assert renderer._cliff_edges(dungeon.terrain,dungeon.elevations,dungeon.stair_blocks,3,3) == ('east',)
    renderer.screen.fill((0,0,0))
    renderer._draw_floor(200,200,True,0,elevation=2,cliff_edges=('north',))
    assert renderer.config['elevation_style']['edge_width'] > renderer.config['grid_line_width']
    assert renderer.screen.get_at((216,192))[:3] == tuple(renderer.config['elevation_style']['edge_color'])


@pytest.mark.parametrize('vertex,names,offsets',[
    (0,('north','west'),((0,-1),(-1,0))),
    (1,('north','east'),((0,-1),(1,0))),
    (2,('south','east'),((0,1),(1,0))),
    (3,('south','west'),((0,1),(-1,0))),
])
def test_wall_corners_fill_top_gap_without_changing_terrain(renderer,vertex,names,offsets):
    renderer.config['wall_corner_post']['enabled'] = False  # 柱の下にある天面接続そのものを確認。
    dungeon = Dungeon(7,7)
    for dx,dy in offsets:
        dungeon.set_tile(3+dx,3+dy,Tile.WALL)
    dx,dy = offsets[0][0]+offsets[1][0],offsets[0][1]+offsets[1][1]
    assert renderer.wall_corners(dungeon.terrain,3,3) == [(vertex,*names)]  # 角は天端を必ずつなぐ。
    dungeon.set_tile(3+dx,3+dy,Tile.WALL)
    before = dungeon.terrain
    assert renderer.wall_corners(before,3,3) == [(vertex,*names)]
    renderer.screen.fill((0,0,0))
    renderer._draw_wall_corner(300,300,vertex,*names,2)
    cx,cy = renderer._diamond(300,300)[vertex]
    cap = renderer.config['wall_cap_width_tiles']
    point = (round(cx-(dx-dy)*renderer.tile_width/4*cap),
             round(cy-2*renderer.tile_height-renderer.wall_height-(dx+dy)*renderer.tile_height/4*cap))
    assert renderer.screen.get_at(point)[:3] == tuple(renderer.config['wall_layers'][-1]['colors']['top'])
    assert dungeon.terrain == before


def test_open_corridor_does_not_get_corner_wall(renderer):
    dungeon = Dungeon(7,7)
    dungeon.set_tile(3,2,Tile.WALL)
    assert renderer.wall_corners(dungeon.terrain,3,3) == []
    assert ('west',-1,0) not in renderer.wall_faces(dungeon.terrain,3,3)


@pytest.mark.parametrize('vertex,names',[(1,('north','east')),(2,('south','east')),(3,('south','west'))])
def test_corner_post_stays_on_shared_vertex_and_uses_vertical_wall_colors(renderer,vertex,names):
    renderer.config['wall_corner_post']['enabled'] = True
    renderer.screen.fill((0,0,0))
    renderer._draw_wall_corner(300,300,vertex,*names,2)
    cx,cy = renderer._diamond(300,300)[vertex]
    base = cy-2*renderer.tile_height
    post = renderer.config['wall_corner_post']
    side = 'right' if vertex == 3 else post['color_side']
    for index,offset in ((0,16),(1,48)):
        assert renderer.screen.get_at((cx,base-offset))[:3] == tuple(
            renderer.config['wall_layers'][index]['colors'][side])
    for px in range(cx-post['width_pixels']//2,cx-post['width_pixels']//2+post['width_pixels']):
        for py in range(base-renderer.wall_height-post['height_offset_pixels'],base-renderer.wall_height-post['height_offset_pixels']+2):
            assert renderer.screen.get_at((px,py))[:3] == tuple(renderer.config['wall_layers'][-1]['colors']['top'])
    # 外側へずれた柱を増やさず、共有頂点の細い幅だけに描く。
    for x in range(250,350):
        if abs(x-cx) > post['width_pixels']:
            assert renderer.screen.get_at((x,base-16))[:3] == (0,0,0)


def test_wall_ends_only_close_exposed_tips_not_straight_joins_or_corners(renderer):
    profiles = {(3,3,'north'):(1,1),(4,3,'north'):(1,1),(3,3,'west'):(1,1)}
    ends = renderer._wall_ends(profiles)
    assert ends[3,3,'north'] == ()
    assert ends[4,3,'north'] == (1,)
    assert renderer._wall_ends(profiles) is ends
    changed = dict(profiles)
    changed[4,3,'north'] = (2,2)
    assert renderer._wall_ends(changed)[3,3,'north'] == (1,)


def test_connected_straight_wall_caps_are_not_cut_at_tile_seams(renderer):
    profiles = {(3,3,'north'):(1,1),(4,3,'north'):(1,1),(3,3,'west'):(1,1)}
    caps = renderer._wall_cap_ends(profiles)
    assert 1 not in caps[3,3,'north']
    assert 0 not in caps[4,3,'north']
    assert renderer._wall_cap_ends(profiles) is caps


def test_exposed_wall_tip_has_same_thickness_and_two_layer_colors(renderer):
    renderer.screen.fill((0,0,0))
    renderer._draw_wall_face(160,200,'east',1,0)
    assert renderer.screen.get_at((158,196))[:3] == (0,0,0)
    renderer._draw_wall_face(160,200,'east',1,0,exposed_ends=(0,))
    assert renderer.screen.get_at((158,196))[:3] == tuple(renderer.config['wall_layers'][0]['colors']['left'])
    assert renderer.screen.get_at((158,164))[:3] == tuple(renderer.config['wall_layers'][1]['colors']['left'])
    assert renderer.screen.get_at((150,196))[:3] == (0,0,0)


def test_elevated_wall_and_cut_end_are_supported_to_ground(renderer):
    renderer.screen.fill((0,0,0))
    renderer._draw_wall_face(160,250,'north',0,-1,(2,2),exposed_ends=(1,))
    assert renderer.screen.get_at((176,210))[:3] == (0,0,0)
    renderer._draw_wall_face(160,250,'north',0,-1,(2,2),exposed_ends=(1,),support_depths=(2,2))
    color = tuple(renderer.config['wall_layers'][0]['colors']['right'])
    assert renderer.screen.get_at((176,210))[:3] == color
    assert renderer.screen.get_at((190,210))[:3] == color
    assert renderer.wall_height == renderer.tile_height*2


def test_rendered_wall_support_depth_matches_its_raised_base(renderer,monkeypatch):
    dungeon = Dungeon(7,7)
    dungeon.set_elevation(3,3,4)
    dungeon.set_tile(3,2,Tile.WALL)
    dungeon.place(Player(),3,3)
    captured = []
    original = renderer._draw_wall_face
    def record(*args):
        captured.append(args)
        original(*args)
    monkeypatch.setattr(renderer,'_draw_wall_face',record)
    renderer.draw(dungeon,0,show_hud=False)
    assert any(args[5] == (2,2) and args[7] == (2,2) for args in captured)
    assert all(args[5] == args[7] for args in captured)


@pytest.mark.parametrize('vertex,names',[(1,('north','east')),(3,('south','west'))])
def test_left_and_right_corner_caps_do_not_form_outward_spikes(renderer,vertex,names):
    renderer.config['wall_corner_post']['enabled'] = False
    renderer.screen.fill((0,0,0))
    renderer._draw_wall_corner(300,300,vertex,*names,1)
    cx,cy = renderer._diamond(300,300)[vertex]
    reach = round(renderer.tile_width/2*renderer.config['wall_cap_width_tiles'])
    top = cy-renderer.tile_height-renderer.wall_height
    painted = [(x,y) for y in range(top-10,top+10) for x in range(cx-15,cx+16)
               if renderer.screen.get_at((x,y))[:3] != (0,0,0)]
    assert painted
    assert all(abs(x-cx) <= reach for x,y in painted)


def test_whole_room_wall_caps_stay_inside_vertical_wall_silhouette(renderer):
    renderer.config['wall_corner_post']['enabled'] = False  # 柱を除いた天面そのものの輪郭。
    dungeon = Dungeon(15,15)
    for y in range(15):
        for x in range(15):
            dungeon.set_tile(x,y,Tile.WALL)
    for y in range(5,10):
        for x in range(5,10):
            dungeon.set_tile(x,y,Tile.FLOOR)
            dungeon.set_elevation(x,y,6)
    dungeon.place(Player(),7,7)
    renderer.config['wall_occlusion']['enabled'] = False
    renderer.draw(dungeon,0,show_hud=False)
    # 左右の壁の縦線はx=160,480。天端だけ外へ飛び出してはいけない。
    for rect in (pygame.Rect(0,0,160,600),pygame.Rect(481,0,159,600)):
        actual = pygame.image.tobytes(renderer.screen.subsurface(rect),'RGB')
        assert actual == bytes(rect.width*rect.height*3)
    assert renderer.screen.get_at((160,260))[:3] != (0,0,0)
    assert renderer.screen.get_at((480,260))[:3] != (0,0,0)


@pytest.mark.parametrize('name,dx,dy,end,boundary,side',[
    ('north',0,-1,0,160,'left'),('west',-1,0,1,160,'right'),
])
@pytest.mark.parametrize('heights',[(0,0),(2,3)])
def test_open_back_wall_end_has_no_unsupported_cap_overhang(renderer,name,dx,dy,end,boundary,side,heights):
    renderer.screen.fill((0,0,0))
    renderer._draw_wall_face(160,300,name,dx,dy,heights,exposed_ends=(end,))
    rect = pygame.Rect(0,0,boundary,600) if side == 'left' else pygame.Rect(boundary+1,0,640-boundary-1,600)
    pixels = pygame.image.tobytes(renderer.screen.subsurface(rect),'RGB')
    assert pixels == bytes(rect.width*rect.height*3)


@pytest.mark.parametrize('side', ['left', 'right'])
def test_room_with_wall_island_has_no_cap_overhang_at_corridor_corners(renderer, side):
    renderer.config['wall_corner_post']['enabled'] = False
    dungeon = Dungeon(16,16)
    for y in range(16):
        for x in range(16):
            floor = 3 <= x < 13 and 3 <= y < 13 and not (5 <= x < 8 and 5 <= y < 8)
            dungeon.set_tile(x,y,Tile.FLOOR if floor else Tile.WALL)
            if floor:
                dungeon.set_elevation(x,y,2)
    dungeon.place(Player(),8,8)
    renderer.config['wall_occlusion']['enabled'] = False
    renderer.draw(dungeon,0,show_hud=False)
    vertex = (4.5,7.5) if side == 'left' else (7.5,4.5)
    x,y = renderer.map_to_screen(*vertex,dungeon,elevation=1)
    y -= renderer.wall_height
    top_color = tuple(renderer.config['wall_layers'][-1]['colors']['top'])
    # 壁の島の左右の角。隣接する別々の床の壁が接する位置を、描画全体で確認する。
    outside = range(x-6,x) if side == 'left' else range(x+1,x+7)
    assert all(renderer.screen.get_at((px,py))[:3] != top_color
               for px in outside for py in range(y-4,y+5))
    assert renderer.screen.get_at((x,y))[:3] == top_color


@pytest.mark.parametrize('side', ['left', 'right'])
@pytest.mark.parametrize('sloped', [False, True])
def test_joined_wall_tips_share_vertical_outline_even_on_slopes(renderer,side,sloped):
    dungeon = Dungeon(9,9)
    dungeon.set_tile(4,4,Tile.WALL)
    if side == 'right':
        faces = [(4,3,'south',0,1),(5,4,'west',-1,0)]
        vertex = (4.5,3.5)
        stairs = [(4,3,1,(1,0)),(5,4,2,(0,1))]
    else:
        faces = [(3,4,'east',1,0),(4,5,'north',0,-1)]
        vertex = (3.5,4.5)
        stairs = [(3,4,1,(0,1)),(4,5,2,(1,0))]
    for x,y,*_ in faces:
        dungeon.set_elevation(x,y,4)
    if sloped:
        for x,y,base,up in stairs:
            dungeon.set_stair_block(x,y,base,up)
    profiles = renderer._wall_profiles(dungeon.terrain,dungeon.elevations,dungeon.stair_blocks)
    ends, caps = renderer._wall_ends(profiles), renderer._wall_cap_ends(profiles)
    renderer.screen.fill((0,0,0))
    for x,y,name,dx,dy in faces:
        key = (x,y,name)
        renderer._draw_wall_face(*renderer.map_to_screen(x,y,dungeon),name,dx,dy,
                                 profiles[key],ends[key],profiles[key],caps[key])
    boundary,_ = renderer.map_to_screen(*vertex,dungeon)
    rect = (pygame.Rect(0,0,boundary,600) if side == 'left'
            else pygame.Rect(boundary+1,0,639-boundary,600))
    pixels = pygame.image.tobytes(renderer.screen.subsurface(rect),'RGB')
    assert pixels == bytes(rect.width*rect.height*3)
    # 端そのものまで削ってしまわず、2段の壁面が縦につながっている。
    x,y = renderer.map_to_screen(*vertex,dungeon,elevation=2)
    assert renderer.screen.get_at((x,y-16))[:3] != (0,0,0)
    assert renderer.screen.get_at((x,y-48))[:3] != (0,0,0)


def test_wall_island_posts_cover_all_four_shared_corners(renderer):
    dungeon = Dungeon(16,16)
    for y in range(16):
        for x in range(16):
            dungeon.set_elevation(x,y,2)
    for y in range(5,8):
        for x in range(5,9):
            dungeon.set_tile(x,y,Tile.WALL)
    dungeon.place(Player(),10,10)
    renderer.config['wall_occlusion']['enabled'] = False
    before = (dungeon.terrain,dungeon.elevations)
    renderer.draw(dungeon,0,show_hud=False)
    profiles = renderer._wall_profiles(dungeon.terrain,dungeon.elevations,dungeon.stair_blocks)
    posts = renderer._wall_join_posts(profiles)
    corners = {(4.5,4.5),(8.5,4.5),(8.5,7.5),(4.5,7.5)}
    assert {(x,y) for x,y,*_ in posts} == corners
    post = renderer.config['wall_corner_post']
    for x,y in corners:
        side = 'right' if (x,y) == (4.5,7.5) else post['color_side']
        cx,cy = renderer.map_to_screen(x,y,dungeon,1)
        for px in range(cx-post['width_pixels']//2,cx-post['width_pixels']//2+post['width_pixels']):
            for py in range(cy-renderer.wall_height-post['height_offset_pixels'],cy-renderer.wall_height-post['height_offset_pixels']+2):
                assert renderer.screen.get_at((px,py))[:3] == tuple(renderer.config['wall_layers'][-1]['colors']['top'])
        for layer,offset in ((0,16),(1,48)):
            assert renderer.screen.get_at((cx,cy-offset))[:3] == tuple(
                renderer.config['wall_layers'][layer]['colors'][side])
    assert (dungeon.terrain,dungeon.elevations) == before
    assert renderer._wall_join_posts(profiles) is posts


def test_corner_post_respects_transparency_and_enabled_setting(renderer):
    renderer.camera = (0,0)
    renderer._fade_mask.fill((255,255,255,65))
    renderer.screen.fill((0,0,0))
    renderer._draw_wall_join_post(200,200,2,False)
    opaque = renderer.screen.get_at((200,184))[:3]
    renderer.screen.fill((0,0,0))
    renderer._draw_wall_join_post(200,200,2,True)
    faded = renderer.screen.get_at((200,184))[:3]
    assert all(0 < f < o for f,o in zip(faded,opaque))
    renderer.config['wall_corner_post']['enabled'] = False
    renderer.screen.fill((0,0,0))
    renderer._draw_wall_join_post(200,200,2,False)
    assert pygame.image.tobytes(renderer.screen,'RGB') == bytes(640*600*3)
