"""マップ座標を画面座標に変換して描画する。ゲーム状態は変更しない。"""

import pygame
from collections import OrderedDict
from pathlib import Path

from system.dungeon import Dungeon, Player, Tile
from system.logs.tracing import trace_class
from system.configuration import load_settings
from system.operate import OperateSettings


class TexturePalette:
    """画像配列の選択・面への投影・投影結果の再利用。"""

    KINDS = ("wall_upper", "wall_lower", "floor", "corridor", "stairs")

    def __init__(self, settings, root, cache_size):
        if type(cache_size) is not int or cache_size < 1:
            raise ValueError("texture_cache_sizeは正の整数にしてください")
        self.cache_size = cache_size
        self.images = {}
        self.cache = OrderedDict()
        for kind in self.KINDS:
            paths = settings[kind]
            if not isinstance(paths, list) or any(not isinstance(p, str) or not p.strip() for p in paths):
                raise ValueError(f"textures.{kind}は画像パスの配列にしてください")
            self.images[kind] = []
            for path in paths:
                filename = Path(root) / path
                try:
                    self.images[kind].append(pygame.image.load(str(filename)))
                except (OSError, pygame.error) as error:
                    raise ValueError(f"textures.{kind}: 画像を読み込めません: {filename}") from error

    def draw(self, target, kind, index, points):
        images = self.images[kind]
        if not images:
            return
        points = tuple((round(x), round(y)) for x,y in points)
        left,top = min(x for x,y in points),min(y for x,y in points)
        shape = tuple((x-left,y-top) for x,y in points)
        variant = index % len(images)
        key = kind,variant,shape
        if key not in self.cache:
            source = images[variant]
            width,height = max(x for x,y in shape)+1,max(y for x,y in shape)+1
            projected = pygame.Surface((width,height),pygame.SRCALPHA)
            ax,ay = shape[0]
            ux,uy = shape[1][0]-ax,shape[1][1]-ay
            vx,vy = shape[3][0]-ax,shape[3][1]-ay
            determinant = ux*vy-uy*vx
            if not determinant:
                return
            for y in range(height):
                for x in range(width):
                    u = ((x-ax)*vy-(y-ay)*vx)/determinant
                    v = (ux*(y-ay)-uy*(x-ax))/determinant
                    if 0 <= u <= 1 and 0 <= v <= 1:
                        sx = min(source.get_width()-1,int(u*source.get_width()))
                        sy = min(source.get_height()-1,int(v*source.get_height()))
                        projected.set_at((x,y),source.get_at((sx,sy)))
            self.cache[key] = projected
            if len(self.cache) > self.cache_size:
                self.cache.popitem(last=False)
        self.cache.move_to_end(key)
        target.blit(self.cache[key],(left,top))


@trace_class(info_methods=("__init__", "start"))
class MoveAnimation:
    def __init__(self, duration_ms: int):
        if type(duration_ms) is not int or duration_ms <= 0:
            raise ValueError("duration_msは正の整数にしてください")
        self.duration_ms = duration_ms
        self._start = None
        self._end = None
        self._started_ms = 0
        self._start_height = self._end_height = 0.0

    def start(self, start: tuple[int, int], end: tuple[int, int], now_ms: int,
              start_height: float = 0, end_height: float = 0) -> None:
        self._start = start
        self._end = end
        self._started_ms = now_ms
        self._start_height, self._end_height = start_height, end_height

    def is_active(self, now_ms: int) -> bool:
        return self._end is not None and now_ms - self._started_ms < self.duration_ms

    def position(self, now_ms: int) -> tuple[float, float] | None:
        if self._end is None:
            return None
        if not self.is_active(now_ms):
            return self._end
        elapsed = max(0, now_ms - self._started_ms)
        progress = elapsed / self.duration_ms
        sx, sy = self._start
        ex, ey = self._end
        return sx + (ex - sx) * progress, sy + (ey - sy) * progress

    def height(self, now_ms: int) -> float | None:
        if self._end is None:
            return None
        progress = min(1, max(0, (now_ms - self._started_ms) / self.duration_ms))
        return self._start_height + (self._end_height - self._start_height) * progress


@trace_class(info_methods=("__init__", "draw"))
class DungeonRenderer:
    def __init__(self, screen: pygame.Surface, operate_settings: OperateSettings | None = None):
        self.screen = screen
        self.config = load_settings("renderer.yml")
        self.textures = TexturePalette(self.config["textures"],Path(__file__).resolve().parent.parent,
                                       self.config["texture_cache_size"])
        animation = self.config["move_animation"]
        self.move_animation = MoveAnimation(animation["duration_ms"])
        self.colors = self.config["colors"]
        self.operate_settings = operate_settings if operate_settings is not None else OperateSettings.load()
        self.tile_width = self.config["tile_width"]
        self.tile_height = self.config["tile_height"]
        self.font = pygame.font.Font(None, self.config["font_size"])
        self.small_font = pygame.font.Font(None, self.config["small_font_size"])
        self.camera = None
        self.camera_height = 0.0
        self._wall_profile_source = None
        self._wall_profile_cache = None
        self._wall_end_source = None
        self._wall_end_cache = None
        self._wall_cap_end_cache = None
        self._wall_join_post_cache = ()
        self._fade_mask = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        self._fade_circle = self._make_fade_circle()
        self.wall_height = sum(round(layer["height_tiles"] * self.tile_height)
                               for layer in self.config["wall_layers"])

    def _draw_texture(self, target, kind, index, points):
        if not self.config["surface_debug"]["enabled"]:
            self.textures.draw(target,kind,index,points)

    def _make_fade_circle(self):
        setting = self.config["wall_occlusion"]
        radius, softness = setting["radius_pixels"], setting["softness"]
        if type(radius) is not int or radius <= 0 or not 0 < softness <= 1:
            raise ValueError("円の半径は正の整数、softnessは0より大きく1以下にしてください")
        circle = pygame.Surface((radius * 2 + 1, radius * 2 + 1), pygame.SRCALPHA)
        circle.fill((255, 255, 255, 255))
        for r in range(radius, -1, -1):
            t = max(0, min(1, (r / radius - (1 - softness)) / softness))
            alpha = round(setting["alpha"] + (255 - setting["alpha"]) * t * t * (3 - 2 * t))
            pygame.draw.circle(circle, (255, 255, 255, alpha), (radius, radius), r)
        return circle

    def _prepare_fade_mask(self, dungeon):
        self._fade_mask.fill((255, 255, 255, 255))
        if self.camera is not None and self.config["wall_occlusion"]["enabled"]:
            center = self.map_to_screen(*self.camera, dungeon, self.camera_height)
            self._fade_mask.blit(self._fade_circle, self._fade_circle.get_rect(center=center),
                                 special_flags=pygame.BLEND_RGBA_MIN)

    def map_to_screen(self, x: float, y: float, dungeon: Dungeon, elevation: float = 0) -> tuple[int, int]:
        """マス中心の画面座標。論理座標は常に整数のまま管理する。"""
        origin_x = self.screen.get_width() // 2 - (
            dungeon.width - dungeon.height
        ) * self.tile_width // 4
        if self.camera is not None:
            x -= self.camera[0]
            y -= self.camera[1]
            return (round(self.screen.get_width() / 2 + (x - y) * self.tile_width / 2),
                    round(self.screen.get_height() / 2 + (x + y) * self.tile_height / 2
                          - (elevation - self.camera_height) * self.tile_height))
        return (
            round(origin_x + (x - y) * self.tile_width / 2),
            round(self.config["origin_y"] + (x + y) * self.tile_height / 2 - elevation * self.tile_height),
        )

    def _diamond(self, cx: int, cy: int) -> list[tuple[int, int]]:
        hw, hh = self.tile_width // 2, self.tile_height // 2
        return [(cx, cy - hh), (cx + hw, cy),
                (cx, cy + hh), (cx - hw, cy)]

    def wall_faces(self, terrain, x, y):
        if terrain[y][x] != Tile.FLOOR:
            return []
        height, width = len(terrain), len(terrain[0])
        faces = []
        for name, dx, dy in (("north", 0, -1), ("west", -1, 0),
                             ("south", 0, 1), ("east", 1, 0)):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < width and 0 <= ny < height) or terrain[ny][nx] == Tile.WALL:
                faces.append((name, dx, dy))
        return faces

    def wall_corners(self, terrain, x, y):
        """隣り合う2つの壁面がある角を必ずつなぐ。"""
        faces = {name:(dx,dy) for name,dx,dy in self.wall_faces(terrain,x,y)}
        result = []
        for vertex,first,second in ((0,"north","west"),(1,"north","east"),
                                    (2,"south","east"),(3,"south","west")):
            if first not in faces or second not in faces:
                continue
            result.append((vertex,first,second))
        return result

    def _surface_color(self, kind, normal):
        """診断表示のときだけ面の種類ごとの色を返す。"""
        debug = self.config["surface_debug"]
        return debug["colors"][kind] if debug["enabled"] else normal

    def _wall_profiles(self, terrain, elevations, stairs):
        """床標高から壁の両端を求め、階段上では連続した斜面にする。"""
        source = (terrain, elevations, stairs)
        if source == self._wall_profile_source:
            return self._wall_profile_cache
        corners = ((-.5, -.5), (.5, -.5), (.5, .5), (-.5, .5))
        edges = {"north": (0, 1), "west": (3, 0), "south": (3, 2), "east": (2, 1)}
        profiles = {}
        for y, row in enumerate(terrain):
            for x, tile in enumerate(row):
                for name, _, _ in self.wall_faces(terrain, x, y):
                    block = stairs[y][x]
                    if block is None:
                        heights = (elevations[y][x]/2,) * 2
                    else:
                        dx, dy = block.up_direction
                        heights = tuple(block.base_height + .5 + corners[i][0]*dx + corners[i][1]*dy
                                        for i in edges[name])
                    profiles[x, y, name] = heights
        self._wall_profile_source = source
        self._wall_profile_cache = profiles
        return profiles

    def _wall_ends(self, profiles):
        """共有頂点から、開放端と天面を輪郭へ切り揃える端を求める。"""
        if profiles is self._wall_end_source:
            return self._wall_end_cache
        vertices = ((-1,-1),(1,-1),(1,1),(-1,1))
        edges = {"north":(0,1),"west":(3,0),"south":(3,2),"east":(2,1)}
        joins = {}
        for (x,y,name),heights in profiles.items():
            for end,(vertex,z) in enumerate(zip(edges[name],heights)):
                ox,oy = vertices[vertex]
                other_x,other_y = vertices[edges[name][1-end]]
                screen_dx = (other_x-other_y)-(ox-oy)
                joins.setdefault((2*x+ox,2*y+oy,z),[]).append(((x,y,name),end,screen_dx))
        ends = {key:[] for key in profiles}
        cap_ends = {key:[] for key in profiles}
        posts = []
        normals = {"north":(0,-1),"west":(-1,0),"south":(0,1),"east":(1,0)}
        for (vx,vy,z),entries in joins.items():
            if len(entries) == 1:
                key,end,_ = entries[0]
                ends[key].append(end)
            elif len({dx > 0 for _,_,dx in entries}) == 1:
                # 別マスの壁が回り込む角も、共有する縦の輪郭で天面を止める。
                # 直線の継ぎ目は左右へ辺が続くため、切り欠かない。
                for key,end,_ in entries:
                    cap_ends[key].append(end)
            if len(entries) == 2:
                first,second = (entry[0] for entry in entries)
                ax,ay = normals[first[2]]
                bx,by = normals[second[2]]
                if first[:2] != second[:2] and ax*bx+ay*by == 0:
                    depth = max(x+y+sum(normals[name])/2 for x,y,name in (first,second))
                    fade = first[2] in ("south","east") or second[2] in ("south","east")
                    left_corner = all(screen_dx > 0 for _,_,screen_dx in entries)
                    posts.append((vx/2,vy/2,z,depth,fade,left_corner))
        self._wall_end_source = profiles
        self._wall_end_cache = {key:tuple(value) for key,value in ends.items()}
        self._wall_cap_end_cache = {key:tuple(value) for key,value in cap_ends.items()}
        self._wall_join_post_cache = tuple(posts)
        return self._wall_end_cache

    def _wall_join_posts(self, profiles):
        """別の床マスに属する壁が直角につながる位置を返す。"""
        self._wall_ends(profiles)
        return self._wall_join_post_cache

    def _draw_wall_join_post(self, cx, cy, elevation, fade, left_corner=False):
        """共有頂点へ細い柱を重ね、別マスの壁の継ぎ目を閉じる。"""
        post = self.config["wall_corner_post"]
        if not post["enabled"]:
            return
        top = cy-self.wall_height-post["height_offset_pixels"]
        ground = cy+round(elevation*self.tile_height)
        half_cap = max(post["width_pixels"],post["cap_width_pixels"])//2
        half_depth = post["cap_depth_pixels"]//2
        rect = pygame.Rect(cx-half_cap,top-half_depth,2*half_cap+1,ground-top+half_depth+1)
        target = pygame.Surface(rect.size,pygame.SRCALPHA)
        side = "right" if left_corner else post["color_side"]
        self._paint_wall_post(target,cx-rect.x,cy-rect.y,elevation,side)
        self._blit_wall_surface(target,rect,fade)

    def _paint_wall_post(self, target, cx, cy, elevation, side):
        """柱本体と、壁より高い丸い柱頭を同じ座標系で描く。"""
        post = self.config["wall_corner_post"]
        width = post["width_pixels"]
        extra = post["height_offset_pixels"]
        top = cy-self.wall_height-extra
        ground = cy+round(elevation*self.tile_height)
        body_x = cx-width//2
        pygame.draw.rect(target,self._surface_color("wall",self.config["wall_layers"][0]["colors"][side]),
                         (body_x,top,width,ground-top+1))
        offset = 0
        for index,layer in enumerate(self.config["wall_layers"]):
            height = round(layer["height_tiles"]*self.tile_height)
            if index == len(self.config["wall_layers"])-1:
                height += extra
            offset += height
            pygame.draw.rect(target,self._surface_color("wall",layer["colors"][side]),
                             (body_x,cy-offset,width,height))
        self._draw_post_cap(target,cx,top,side)

    def _draw_post_cap(self, target, cx, cy, side):
        """円形の柱頭を斜めから見た楕円と、その厚みを描く。"""
        post = self.config["wall_corner_post"]
        hw,hh = post["cap_width_pixels"]//2,post["cap_depth_pixels"]//2
        depth = post["cap_height_pixels"]
        roof = pygame.Rect(cx-hw,cy-hh,2*hw+1,2*hh+1)
        colors = self.config["wall_layers"][-1]["colors"]
        side_color = self._surface_color("wall",colors[side])
        pygame.draw.ellipse(target,side_color,roof.move(0,depth))
        pygame.draw.rect(target,side_color,(cx-hw,cy,roof.width,depth))
        pygame.draw.ellipse(target,self._surface_color("wall",colors["top"]),roof)

    def _wall_cap_ends(self, profiles):
        """接続する壁面が共有する左右の輪郭端を返す。"""
        self._wall_ends(profiles)
        return self._wall_cap_end_cache

    def _trim_wall_cap_end(self, points, boundary, keep_right):
        """壁の縦輪郭から天面だけが飛び出さないように切る。"""
        clipped = []
        previous = points[-1]
        previous_inside = previous[0] >= boundary if keep_right else previous[0] <= boundary
        for point in points:
            inside = point[0] >= boundary if keep_right else point[0] <= boundary
            if inside != previous_inside:
                t = (boundary-previous[0])/(point[0]-previous[0])
                clipped.append((boundary,previous[1]+t*(point[1]-previous[1])))
            if inside:
                clipped.append(point)
            previous,previous_inside = point,inside
        return clipped

    def _draw_wall_face(self, cx, cy, direction, dx, dy, endpoint_heights=(0, 0), exposed_ends=(), support_depths=(0, 0), cap_ends=(), texture_index=0):
        corners = self._diamond(cx, cy)
        edges = {"north": (0, 1), "west": (3, 0), "south": (3, 2), "east": (2, 1)}
        a, b = ((corners[i][0], corners[i][1]-round(z*self.tile_height))
                for i, z in zip(edges[direction], endpoint_heights))
        cap = self.config["wall_cap_width_tiles"]
        shift = (-(dx - dy) * self.tile_width / 2 * cap,
                 -(dx + dy) * self.tile_height / 2 * cap)
        top_a, top_b = (a[0], a[1] - self.wall_height), (b[0], b[1] - self.wall_height)
        cap_points = [top_a, top_b, (top_b[0] + shift[0], top_b[1] + shift[1]),
                      (top_a[0] + shift[0], top_a[1] + shift[1])]
        visible_end = 1 if direction in ("north","south") else 0
        trim_ends = set(cap_ends) | {end for end in exposed_ends if end != visible_end}
        for end in sorted(trim_ends):
            endpoint,other = ((a,b)[end],(a,b)[1-end])
            cap_points = self._trim_wall_cap_end(cap_points,endpoint[0],other[0]>endpoint[0])
        feet = [(p[0],p[1]+round(depth*self.tile_height)) for p,depth in zip((a,b),support_depths)]
        points = [a,b,*cap_points,*feet,
                  *[(x+shift[0],y+shift[1]) for x,y in feet]]
        left, right = int(min(p[0] for p in points)) - 1, int(max(p[0] for p in points)) + 2
        top, bottom = int(min(p[1] for p in points)) - 1, int(max(p[1] for p in points)) + 2
        rect = pygame.Rect(left, top, right - left, bottom - top)
        target = pygame.Surface(rect.size, pygame.SRCALPHA)
        local = lambda points: [(round(x - rect.x), round(y - rect.y)) for x, y in points]
        offset = 0
        side = "right" if direction in ("north", "south") else "left"
        if any(support_depths):
            pygame.draw.polygon(target,self._surface_color("wall",self.config["wall_layers"][0]["colors"][side]),
                                local([a,b,feet[1],feet[0]]))
        for layer_index,layer in enumerate(self.config["wall_layers"]):
            height = round(layer["height_tiles"] * self.tile_height)
            base = [(a[0], a[1] - offset), (b[0], b[1] - offset)]
            raised = [(px, py - height) for px, py in base]
            pygame.draw.polygon(target, self._surface_color("wall", layer["colors"][side]), local([*base, raised[1], raised[0]]))
            kind = "wall_lower" if layer_index == 0 else "wall_upper"
            self._draw_texture(target,kind,texture_index,local([raised[0],raised[1],base[1],base[0]]))
            offset += height
        # 天端と同じ内向きの厚みで、壁の切り口を閉じる。
        end_side = side
        for end in exposed_ends:
            if end != visible_end:
                continue
            px,py = (a,b)[end]
            depth = round(support_depths[end]*self.tile_height)
            if depth:
                points = [(px,py),(px+shift[0],py+shift[1]),
                          (px+shift[0],py+shift[1]+depth),(px,py+depth)]
                pygame.draw.polygon(target,self._surface_color("wall",self.config["wall_layers"][0]["colors"][end_side]),local(points))
            offset = 0
            for layer in self.config["wall_layers"]:
                height = round(layer["height_tiles"]*self.tile_height)
                inner = (px,py-offset)
                outer = (px+shift[0],py-offset+shift[1])
                points = [inner,outer,(outer[0],outer[1]-height),(inner[0],inner[1]-height)]
                pygame.draw.polygon(target,self._surface_color("wall",layer["colors"][end_side]),local(points))
                offset += height
        pygame.draw.polygon(target, self._surface_color("wall", self.config["wall_layers"][-1]["colors"]["top"]), local(cap_points))
        self._blit_wall_surface(target,rect,direction in ("south","east"))

    def _blit_wall_surface(self, target, rect, fade):
        """壁面と角を同じ円形透過マスクで合成する。"""
        if (fade and self.camera is not None
                and self.config["wall_occlusion"]["enabled"]
                and not self.config["surface_debug"]["enabled"]):
            mask = pygame.Surface(rect.size, pygame.SRCALPHA)
            mask.fill((255, 255, 255, 255))
            mask.blit(self._fade_mask, (-rect.x, -rect.y), special_flags=pygame.BLEND_RGBA_MIN)
            target.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        self.screen.blit(target, rect)

    def _draw_wall_corner(self, cx, cy, vertex, first, second, elevation):
        """既存壁面の共有頂点に天端と細い縦柱を合わせる。"""
        vectors = {"north":(0,-1),"west":(-1,0),"south":(0,1),"east":(1,0)}
        cap = self.config["wall_cap_width_tiles"]
        shifts = [(-(dx-dy)*self.tile_width/2*cap,-(dx+dy)*self.tile_height/2*cap)
                  for dx,dy in (vectors[first],vectors[second])]
        px,py = self._diamond(cx,cy)[vertex]
        py -= round(elevation*self.tile_height)
        a,b = shifts
        # 外側へ2方向分張り出す頂点を作らず、両壁の縁を面取りでつなぐ。
        base = [(px,py),(px+a[0],py+a[1]),(px+b[0],py+b[1])]
        top = [(x,y-self.wall_height) for x,y in base]
        post = self.config["wall_corner_post"]
        ground_y = py+round(elevation*self.tile_height)
        all_points = list(top)
        if post["enabled"]:
            all_points += [(px-post["width_pixels"],top[0][1]),
                           (px+post["width_pixels"],ground_y)]
            all_points += [(px-post["cap_width_pixels"]//2,top[0][1]-post["height_offset_pixels"]-post["cap_depth_pixels"]//2),
                           (px+post["cap_width_pixels"]//2,ground_y)]
        left,upper = int(min(x for x,y in all_points))-1,int(min(y for x,y in all_points))-1
        right,lower = int(max(x for x,y in all_points))+2,int(max(y for x,y in all_points))+2
        rect = pygame.Rect(left,upper,right-left,lower-upper)
        target = pygame.Surface(rect.size,pygame.SRCALPHA)
        local = lambda points: [(round(x-left),round(y-upper)) for x,y in points]
        pygame.draw.polygon(target,self._surface_color("wall",self.config["wall_layers"][-1]["colors"]["top"]),local(top))
        if post["enabled"]:
            side = "right" if vertex == 3 else post["color_side"]
            self._paint_wall_post(target,round(px-left),round(py-upper),elevation,side)
        self._blit_wall_surface(target,rect,first in ("south","east") or second in ("south","east"))

    def _draw_actor(self, actor, cx, cy):
        is_player = isinstance(actor, Player)
        color = self.colors["player"] if is_player else self.colors["enemy"]
        pygame.draw.ellipse(self.screen, self.colors["shadow"],
                            pygame.Rect(self.config["shadow_rect"]).move(cx, cy))
        pygame.draw.rect(self.screen, color,
                         pygame.Rect(self.config["body_rect"]).move(cx, cy),
                         border_radius=self.config["body_radius"])
        pygame.draw.circle(self.screen, color,
                           (cx + self.config["head_offset"][0], cy + self.config["head_offset"][1]),
                           self.config["head_radius"])
        label = self.small_font.render("P" if is_player else "E", True, self.colors["label"])
        self.screen.blit(label, label.get_rect(center=(cx, cy + self.config["label_offset_y"])))

    def _player_visibility_snapshot(self, cx, cy):
        """主人公の形と、遮蔽物が重なる前の画素を保存する。影は含めない。"""
        body = pygame.Rect(self.config["body_rect"]).move(cx, cy)
        hx, hy = cx+self.config["head_offset"][0], cy+self.config["head_offset"][1]
        radius = self.config["head_radius"]
        rect = body.union(pygame.Rect(hx-radius, hy-radius, radius*2+1, radius*2+1))
        rect = rect.clip(self.screen.get_rect())
        shape = pygame.Surface(rect.size, pygame.SRCALPHA)
        color = (*self.colors["player"], self.config["player_occlusion"]["alpha"])
        pygame.draw.rect(shape, color, body.move(-rect.x, -rect.y),
                         border_radius=self.config["body_radius"])
        pygame.draw.circle(shape, color, (hx-rect.x, hy-rect.y), radius)
        return rect, self.screen.subsurface(rect).copy(), shape

    def _draw_occluded_player(self, snapshot):
        """後から重なった地形の裏に、隠れた部分だけシルエットを描く。"""
        if snapshot is None or not self.config["player_occlusion"]["enabled"]:
            return
        rect, original, shape = snapshot
        overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
        for y in range(rect.height):
            for x in range(rect.width):
                color = shape.get_at((x, y))
                if color.a and self.screen.get_at((rect.x+x, rect.y+y)) != original.get_at((x, y)):
                    overlay.set_at((x, y), color)
        self.screen.blit(overlay, rect)

    def _restore_player_over_floor(self, snapshot, cx, cy, cliff_edges=()):
        """同じ標高の床が覆った主人公の画素だけを戻す。地形の描画順は変えない。"""
        if snapshot is None:
            return
        rect, original, shape = snapshot
        floor_rect = pygame.Rect(cx-self.tile_width//2, cy-self.tile_height//2,
                                 self.tile_width+1,self.tile_height+1)
        floor_rect.inflate_ip(self.config["elevation_style"]["edge_width"]*2,
                              self.config["elevation_style"]["edge_width"]*2)
        overlap = rect.clip(floor_rect)
        if not overlap.width or not overlap.height:
            return
        mask = pygame.Surface(floor_rect.size, pygame.SRCALPHA)
        points = [(x-floor_rect.x,y-floor_rect.y) for x,y in self._diamond(cx,cy)]
        pygame.draw.polygon(mask, (255,255,255,255), points)
        pygame.draw.polygon(mask, (255,255,255,255), points, self.config["grid_line_width"])
        vertices = {"north":(0,1),"west":(3,0),"south":(3,2),"east":(2,1)}
        for name in cliff_edges:
            a,b = (points[i] for i in vertices[name])
            pygame.draw.line(mask,(255,255,255,255),a,b,self.config["elevation_style"]["edge_width"])
        for y in range(overlap.height):
            for x in range(overlap.width):
                point = overlap.x+x,overlap.y+y
                local = point[0]-rect.x,point[1]-rect.y
                if mask.get_at((point[0]-floor_rect.x,point[1]-floor_rect.y)).a and shape.get_at(local).a:
                    self.screen.set_at(point,original.get_at(local))

    def _floor_color(self, raised, parity, elevation):
        """床と階段に共通の、標高に応じた明るさを返す。"""
        prefix = "platform" if raised else "floor"
        color = self.colors[prefix + ("_odd" if parity else "_even")]
        setting = self.config["elevation_style"]
        gain = min(setting["maximum_brightness_gain"],
                   max(0,elevation-setting["reference_height"])*setting["brightness_per_height"])
        return tuple(min(255,round(channel+gain)) for channel in color)

    def _cliff_edges(self, terrain, elevations, stairs, x, y):
        """隣の床より高い、歩いて通過できない境界だけを返す。"""
        height,width = len(terrain),len(terrain[0])
        z = elevations[y][x]/2
        edges = []
        for name,dx,dy in (("north",0,-1),("west",-1,0),("south",0,1),("east",1,0)):
            nx,ny = x+dx,y+dy
            if not (0<=nx<width and 0<=ny<height) or terrain[ny][nx] != Tile.FLOOR:
                continue
            block = stairs[ny][nx]
            neighbor = block.base_height+1 if block else elevations[ny][nx]/2
            if z > neighbor:
                edges.append(name)
        return tuple(edges)

    def _draw_floor(self, cx, cy, raised, parity, elevation=0, cliff_edges=(), texture_kind="floor", texture_index=0):
        color = self._floor_color(raised,parity,elevation)
        corners = self._diamond(cx, cy)
        pygame.draw.polygon(self.screen, self._surface_color("floor", color), corners)
        self._draw_texture(self.screen,texture_kind,texture_index,corners)
        pygame.draw.polygon(self.screen, self.colors["grid"], corners, self.config["grid_line_width"])
        edge_vertices = {"north":(0,1),"west":(3,0),"south":(3,2),"east":(2,1)}
        for name in cliff_edges:
            a,b = (corners[i] for i in edge_vertices[name])
            pygame.draw.line(self.screen,self._surface_color("floor",self.config["elevation_style"]["edge_color"]),
                             a,b,self.config["elevation_style"]["edge_width"])

    def _draw_stair_block(self, x, y, block, dungeon):
        count = self.config["stairs"]["treads_per_block"]
        if type(count) is not int or count <= 0:
            raise ValueError("treads_per_blockは正の整数にしてください")
        dx, dy = block.up_direction
        treads = []
        for index in range(count):
            low, high = index / count, (index + 1) / count
            if dx:
                left = x - 0.5 + low if dx > 0 else x + 0.5 - high
                right = x - 0.5 + high if dx > 0 else x + 0.5 - low
                back, front = y - 0.5, y + 0.5
            else:
                back = y - 0.5 + low if dy > 0 else y + 0.5 - high
                front = y - 0.5 + high if dy > 0 else y + 0.5 - low
                left, right = x - 0.5, x + 0.5
            treads.append(((left + right + back + front) / 2,
                           [(left, back), (right, back), (right, front), (left, front)],
                           block.base_height + high))
        for _, corners, height in sorted(treads, key=lambda value: value[0]):
            top = [self.map_to_screen(px, py, dungeon, height) for px, py in corners]
            base = [self.map_to_screen(px, py, dungeon, 0) for px, py in corners]
            for a, b, side in ((3, 2, "left"), (2, 1, "right")):
                pygame.draw.polygon(self.screen, self._surface_color("stair_side", self.colors["platform_side_" + side]),
                                    [top[a], top[b], base[b], base[a]])
                self._draw_texture(self.screen,"stairs",x+y,[top[a],top[b],base[b],base[a]])
            pygame.draw.polygon(self.screen, self._surface_color("stair_top", self._floor_color(True,(x+y)%2,height)), top)
            self._draw_texture(self.screen,"stairs",x+y,top)
            pygame.draw.polygon(self.screen, self.colors["grid"], top,
                                self.config["grid_line_width"])

    def _draw_riser(self, cx, cy, direction, drop_pixels):
        corners = self._diamond(cx, cy)
        a, b = (corners[i] for i in ((3, 2) if direction == "south" else (2, 1)))
        color = self.colors["platform_side_left" if direction == "south" else "platform_side_right"]
        pygame.draw.polygon(self.screen, self._surface_color("floor_side", color),
                            [a, b, (b[0], b[1] + drop_pixels), (a[0], a[1] + drop_pixels)])

    def draw(self, dungeon: Dungeon, now_ms: int | None = None, *, show_hud: bool = True) -> None:
        now_ms = pygame.time.get_ticks() if now_ms is None else now_ms
        self.camera = self.move_animation.position(now_ms) or dungeon.player_position
        self.camera_height = dungeon.surface_height(*self.camera) if self.camera is not None else 0
        self._prepare_fade_mask(dungeon)
        self.screen.fill(self.colors["background"])
        terrain, actors, items = dungeon.terrain, dungeon.actors, dungeon.items
        elevations, stairs = dungeon.elevations, dungeon.stair_blocks
        floor_kinds = dungeon.floor_kinds
        wall_profiles = self._wall_profiles(terrain, elevations, stairs)
        wall_ends = self._wall_ends(wall_profiles)
        wall_cap_ends = self._wall_cap_ends(wall_profiles)
        vertical_extent = self.wall_height + max(max(row) for row in elevations) / 2 * self.tile_height
        # 奥のマスから描くことで、手前の物体が奥の物体に重なる。
        # 画面サイズから余裕を持った探索範囲を求め、画面外を描かない。
        if self.camera is None:
            bounds = (0, dungeon.width, 0, dungeon.height)
        else:
            radius = (self.screen.get_width() / self.tile_width +
                      self.screen.get_height() / self.tile_height +
                      vertical_extent / self.tile_height)
            px, py = self.camera
            bounds = (max(0, int(px - radius)), min(dungeon.width, int(px + radius) + 1),
                      max(0, int(py - radius)), min(dungeon.height, int(py + radius) + 1))
        visible = self.screen.get_rect().inflate(self.tile_width * 2,
                                                 vertical_extent * 2)
        cells = sorted(((x, y) for y in range(bounds[2], bounds[3])
                        for x in range(bounds[0], bounds[1])
                        if visible.collidepoint(self.map_to_screen(x, y, dungeon))),
                       key=lambda p: sum(p))
        commands = []
        for x, y in cells:
            cx, cy = self.map_to_screen(x, y, dungeon)
            if terrain[y][x] == Tile.FLOOR:
                z = elevations[y][x] / 2
                cx, cy = self.map_to_screen(x, y, dungeon, z)
                if stairs[y][x] is not None:
                    commands.append((x + y, "stairs", (x, y, stairs[y][x], dungeon)))
                    continue
                edges = self._cliff_edges(terrain,elevations,stairs,x,y)
                commands.append((x+y, "floor", (cx,cy,z>0,(x+y)%2,z,edges,floor_kinds[y][x],x+y)))
                for name, dx, dy in (("south", 0, 1), ("east", 1, 0)):
                    nx, ny = x + dx, y + dy
                    neighbor = dungeon.edge_height(nx, ny, -dx, -dy) if dungeon.in_bounds(nx, ny) else 0
                    if neighbor is None:
                        # 横入り不可は移動の情報。描画では階段の上端まで地形がある。
                        neighbor = stairs[ny][nx].base_height + 1
                    if z > neighbor:
                        commands.append((x + y + 0.5, "riser", (cx, cy, name,
                                         round((z - neighbor) * self.tile_height))))
            else:
                pygame.draw.polygon(self.screen, self.colors["wall_ground"], self._diamond(cx, cy))
        for x, y in cells:
            z = elevations[y][x] / 2
            cx, cy = self.map_to_screen(x, y, dungeon, z)
            for name, dx, dy in self.wall_faces(terrain, x, y):
                wx, wy = self.map_to_screen(x, y, dungeon)
                commands.append((x + y + (dx + dy) / 2, "wall",
                                 (wx, wy, name, dx, dy, wall_profiles[x, y, name],wall_ends[x,y,name],
                                  wall_profiles[x,y,name],wall_cap_ends[x,y,name],x+y)))
            for vertex,first,second in self.wall_corners(terrain,x,y):
                # 各面の共有頂点の標高。階段の斜面でも同じ端点を使う。
                indices = {"north":(0,1),"west":(3,0),"south":(3,2),"east":(2,1)}
                elevation = wall_profiles[x,y,first][indices[first].index(vertex)]
                normal_depth = {"north":-1,"west":-1,"south":1,"east":1}
                depth = x+y+max(normal_depth[first],normal_depth[second])/2
                commands.append((depth,"wall_corner",
                                 (*self.map_to_screen(x,y,dungeon),vertex,first,second,elevation)))
            if items[y][x] is not None:
                commands.append((x + y, "item", (cx, cy)))
            actor = actors[y][x]
            if actor is not None:
                position = (x, y)
                if isinstance(actor, Player):
                    position = self.move_animation.position(now_ms) or position
                    z = self.camera_height
                commands.append((sum(position), "actor", (actor, *self.map_to_screen(*position, dungeon, z))))
        if self.config["wall_corner_post"]["enabled"]:
            for x,y,z,depth,fade,left_corner in self._wall_join_posts(wall_profiles):
                cx,cy = self.map_to_screen(x,y,dungeon,z)
                if visible.collidepoint((cx,cy)):
                    commands.append((depth,"wall_join_post",(cx,cy,z,fade,left_corner)))
        player_snapshot = None
        for _, kind, args in sorted(commands, key=lambda command: command[0]):
            if kind == "wall":
                self._draw_wall_face(*args)
            elif kind == "wall_corner":
                self._draw_wall_corner(*args)
            elif kind == "wall_join_post":
                self._draw_wall_join_post(*args)
            elif kind == "floor":
                self._draw_floor(*args[:4],elevation=args[4],cliff_edges=args[5],texture_kind=args[6],texture_index=args[7])
                if args[4] == self.camera_height:
                    self._restore_player_over_floor(player_snapshot, *args[:2],cliff_edges=args[5])
            elif kind == "riser":
                self._draw_riser(*args)
            elif kind == "stairs":
                self._draw_stair_block(*args)
            elif kind == "item":
                cx, cy = args
                pygame.draw.polygon(self.screen, self.colors["item"],
                                    [(cx + dx, cy + dy) for dx, dy in self.config["item_points"]])
            else:
                self._draw_actor(*args)
                if isinstance(args[0], Player):
                    player_snapshot = self._player_visibility_snapshot(*args[1:])
        self._draw_occluded_player(player_snapshot)

        if not show_hud:
            return
        keys = self.operate_settings
        key_name = pygame.key.name
        lines = [
            f"Player (x, y): {dungeon.player_position}  Height: {self.camera_height:.2f}",
            f"Move: {key_name(keys.move_up)}, {key_name(keys.move_down)}, "
            f"{key_name(keys.move_left)}, {key_name(keys.move_right)} / "
            f"Quit: {key_name(keys.quit)} / Hold: repeat",
            "Blue: Player    Gold: Item    Red: Enemy",
            "Up: y-1    Down: y+1    Left: x-1    Right: x+1",
        ]
        if self.config["surface_debug"]["enabled"]:
            lines.append(self.config["surface_debug"]["legend"])
        for index, line in enumerate(lines):
            font = self.font if index == 0 else self.small_font
            self.screen.blit(font.render(line, True, self.colors["hud"]),
                             (self.config["hud"]["x"], self.config["hud"]["y"] +
                              index * self.config["hud"]["line_spacing"]))
