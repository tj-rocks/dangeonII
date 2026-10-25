"""マップ座標を画面座標に変換して描画する。ゲーム状態は変更しない。"""

import pygame

from system.dungeon import Dungeon, Player, Tile
from system.logs.tracing import trace_class
from system.configuration import load_settings
from system.operate import OperateSettings


@trace_class(info_methods=("__init__", "start"))
class MoveAnimation:
    def __init__(self, duration_ms: int):
        if type(duration_ms) is not int or duration_ms <= 0:
            raise ValueError("duration_msは正の整数にしてください")
        self.duration_ms = duration_ms
        self._start = None
        self._end = None
        self._started_ms = 0

    def start(self, start: tuple[int, int], end: tuple[int, int], now_ms: int) -> None:
        self._start = start
        self._end = end
        self._started_ms = now_ms

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


@trace_class(info_methods=("__init__", "draw"))
class DungeonRenderer:
    def __init__(self, screen: pygame.Surface, operate_settings: OperateSettings | None = None):
        self.screen = screen
        self.config = load_settings("renderer.yml")
        animation = self.config["move_animation"]
        self.move_animation = MoveAnimation(animation["duration_ms"])
        self.colors = self.config["colors"]
        self.operate_settings = operate_settings if operate_settings is not None else OperateSettings.load()
        self.tile_width = self.config["tile_width"]
        self.tile_height = self.config["tile_height"]
        self.font = pygame.font.Font(None, self.config["font_size"])
        self.small_font = pygame.font.Font(None, self.config["small_font_size"])
        self.camera = None
        self._fade_mask = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        self._fade_circle = self._make_fade_circle()
        self.wall_height = sum(round(layer["height_tiles"] * self.tile_height)
                               for layer in self.config["wall_layers"])

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
            center = self.map_to_screen(*self.camera, dungeon)
            self._fade_mask.blit(self._fade_circle, self._fade_circle.get_rect(center=center),
                                 special_flags=pygame.BLEND_RGBA_MIN)

    def map_to_screen(self, x: float, y: float, dungeon: Dungeon) -> tuple[int, int]:
        """マス中心の画面座標。論理座標は常に整数のまま管理する。"""
        origin_x = self.screen.get_width() // 2 - (
            dungeon.width - dungeon.height
        ) * self.tile_width // 4
        if self.camera is not None:
            x -= self.camera[0]
            y -= self.camera[1]
            return (round(self.screen.get_width() / 2 + (x - y) * self.tile_width / 2),
                    round(self.screen.get_height() / 2 + (x + y) * self.tile_height / 2))
        return (
            round(origin_x + (x - y) * self.tile_width / 2),
            round(self.config["origin_y"] + (x + y) * self.tile_height / 2),
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

    def _draw_wall_face(self, cx, cy, direction, dx, dy):
        corners = self._diamond(cx, cy)
        edges = {"north": (0, 1), "west": (3, 0), "south": (3, 2), "east": (2, 1)}
        a, b = (corners[i] for i in edges[direction])
        cap = self.config["wall_cap_width_tiles"]
        shift = ((dx - dy) * self.tile_width / 2 * cap,
                 (dx + dy) * self.tile_height / 2 * cap)
        top_a, top_b = (a[0], a[1] - self.wall_height), (b[0], b[1] - self.wall_height)
        cap_points = [top_a, top_b, (top_b[0] + shift[0], top_b[1] + shift[1]),
                      (top_a[0] + shift[0], top_a[1] + shift[1])]
        points = [a, b, *cap_points]
        left, right = int(min(p[0] for p in points)) - 1, int(max(p[0] for p in points)) + 2
        top, bottom = int(min(p[1] for p in points)) - 1, int(max(p[1] for p in points)) + 2
        rect = pygame.Rect(left, top, right - left, bottom - top)
        target = pygame.Surface(rect.size, pygame.SRCALPHA)
        local = lambda points: [(round(x - rect.x), round(y - rect.y)) for x, y in points]
        offset = 0
        side = "right" if direction in ("north", "south") else "left"
        for layer in self.config["wall_layers"]:
            height = round(layer["height_tiles"] * self.tile_height)
            base = [(a[0], a[1] - offset), (b[0], b[1] - offset)]
            raised = [(px, py - height) for px, py in base]
            pygame.draw.polygon(target, layer["colors"][side], local([*base, raised[1], raised[0]]))
            offset += height
        pygame.draw.polygon(target, self.config["wall_layers"][-1]["colors"]["top"], local(cap_points))
        # 手前に立つ面だけ、従来と同じ画素単位の円形マスクを適用する。
        if (direction in ("south", "east") and self.camera is not None
                and self.config["wall_occlusion"]["enabled"]):
            mask = pygame.Surface(rect.size, pygame.SRCALPHA)
            mask.fill((255, 255, 255, 255))
            mask.blit(self._fade_mask, (-rect.x, -rect.y), special_flags=pygame.BLEND_RGBA_MIN)
            target.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        self.screen.blit(target, rect)

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

    def draw(self, dungeon: Dungeon, now_ms: int | None = None) -> None:
        now_ms = pygame.time.get_ticks() if now_ms is None else now_ms
        self.camera = self.move_animation.position(now_ms) or dungeon.player_position
        self._prepare_fade_mask(dungeon)
        self.screen.fill(self.colors["background"])
        terrain, actors, items = dungeon.terrain, dungeon.actors, dungeon.items
        # 奥のマスから描くことで、手前の物体が奥の物体に重なる。
        # 画面サイズから余裕を持った探索範囲を求め、画面外を描かない。
        if self.camera is None:
            bounds = (0, dungeon.width, 0, dungeon.height)
        else:
            radius = (self.screen.get_width() / self.tile_width +
                      self.screen.get_height() / self.tile_height +
                      self.wall_height / self.tile_height)
            px, py = self.camera
            bounds = (max(0, int(px - radius)), min(dungeon.width, int(px + radius) + 1),
                      max(0, int(py - radius)), min(dungeon.height, int(py + radius) + 1))
        visible = self.screen.get_rect().inflate(self.tile_width * 2,
                                                 self.wall_height * 2)
        cells = sorted(((x, y) for y in range(bounds[2], bounds[3])
                        for x in range(bounds[0], bounds[1])
                        if visible.collidepoint(self.map_to_screen(x, y, dungeon))),
                       key=lambda p: sum(p))
        for x, y in cells:
            cx, cy = self.map_to_screen(x, y, dungeon)
            if terrain[y][x] == Tile.FLOOR:
                color = self.colors["floor_odd"] if (x + y) % 2 else self.colors["floor_even"]
                pygame.draw.polygon(self.screen, color, self._diamond(cx, cy))
                pygame.draw.polygon(self.screen, self.colors["grid"], self._diamond(cx, cy),
                                    self.config["grid_line_width"])
            else:
                pygame.draw.polygon(self.screen, self.colors["wall_ground"], self._diamond(cx, cy))
        commands = []
        for x, y in cells:
            cx, cy = self.map_to_screen(x, y, dungeon)
            for name, dx, dy in self.wall_faces(terrain, x, y):
                commands.append((x + y + (dx + dy) / 2, "wall", (cx, cy, name, dx, dy)))
            if items[y][x] is not None:
                commands.append((x + y, "item", (cx, cy)))
            actor = actors[y][x]
            if actor is not None:
                position = (x, y)
                if isinstance(actor, Player):
                    position = self.move_animation.position(now_ms) or position
                commands.append((sum(position), "actor", (actor, *self.map_to_screen(*position, dungeon))))
        for _, kind, args in sorted(commands, key=lambda command: command[0]):
            if kind == "wall":
                self._draw_wall_face(*args)
            elif kind == "item":
                cx, cy = args
                pygame.draw.polygon(self.screen, self.colors["item"],
                                    [(cx + dx, cy + dy) for dx, dy in self.config["item_points"]])
            else:
                self._draw_actor(*args)

        keys = self.operate_settings
        key_name = pygame.key.name
        lines = [
            f"Player (x, y): {dungeon.player_position}",
            f"Move: {key_name(keys.move_up)}, {key_name(keys.move_down)}, "
            f"{key_name(keys.move_left)}, {key_name(keys.move_right)} / "
            f"Quit: {key_name(keys.quit)} / Hold: repeat",
            "Blue: Player    Gold: Item    Red: Enemy",
            "Up: y-1    Down: y+1    Left: x-1    Right: x+1",
        ]
        for index, line in enumerate(lines):
            font = self.font if index == 0 else self.small_font
            self.screen.blit(font.render(line, True, self.colors["hud"]),
                             (self.config["hud"]["x"], self.config["hud"]["y"] +
                              index * self.config["hud"]["line_spacing"]))
