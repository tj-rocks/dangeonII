"""描画から独立したダンジョン。座標は (x, y)、配列へのアクセスは [y][x]。"""

from dataclasses import dataclass
from enum import IntEnum
from random import Random
from math import floor
from collections import deque
from system.logs.tracing import trace_class


class Tile(IntEnum):
    FLOOR = 0
    WALL = 1


@dataclass(frozen=True, eq=False)
class Player:
    name: str = "Player"


@dataclass(frozen=True, eq=False)
class Enemy:
    name: str = "Enemy"


@dataclass(frozen=True, eq=False)
class Item:
    name: str = "Item"


@dataclass(frozen=True)
class MoveResult:
    moved: bool
    reason: str
    # アイテム到達イベント。呼び出し側で回復・効果音・表示などを処理する。
    item: Item | None = None
    # 階層移動階段へ到達したイベント。実際の階層切り替えはmain側で行う。
    level_stair: "LevelStair | None" = None


@dataclass(frozen=True)
class StairBlock:
    """1マスの高さを接続する専用ブロック。床の半段とは別の地形情報。"""
    base_height: int
    up_direction: tuple[int, int]


@dataclass(frozen=True)
class LevelStair:
    """階層移動用の下り階段。標高用のStairBlockとは別の地形情報。"""
    direction: tuple[int, int]
    visible_treads: int


@trace_class(info_methods=("__init__", "set_tile", "place", "move_player", "move_actor"))
class Dungeon:
    """地形・キャラクター・アイテムを同じサイズの2次元配列で管理。

    位置の正本は配列のみ。Player/Enemy/Itemには座標を重複保持しない。
    外部には配列のコピーを返し、更新はこのクラスのメソッドを通す。
    """

    def __init__(self, width: int, height: int):
        if width <= 0 or height <= 0:
            raise ValueError("マップの幅と高さは1以上にしてください")
        self._width = width
        self._height = height
        self._terrain = [[Tile.FLOOR for _ in range(width)] for _ in range(height)]
        self._actors: list[list[Player | Enemy | None]] = [
            [None for _ in range(width)] for _ in range(height)
        ]
        self._items: list[list[Item | None]] = [
            [None for _ in range(width)] for _ in range(height)
        ]
        self._player: Player | None = None
        # 1は0.5マス。整数のハーフブロック数で高さを管理する。
        self._floor_kinds = [["floor" for _ in range(width)] for _ in range(height)]
        self._elevations = [[0 for _ in range(width)] for _ in range(height)]
        self._stair_blocks: list[list[StairBlock | None]] = [[None for _ in range(width)] for _ in range(height)]
        self._level_stairs: list[list[LevelStair | None]] = [[None for _ in range(width)] for _ in range(height)]

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    @property
    def terrain(self) -> list[list[Tile]]:
        return [row[:] for row in self._terrain]

    @property
    def floor_kinds(self) -> list[list[str]]:
        return [row[:] for row in self._floor_kinds]

    def set_floor_kind(self, x: int, y: int, kind: str) -> None:
        self._check_bounds(x,y)
        if self._terrain[y][x] != Tile.FLOOR or kind not in ("floor","corridor"):
            raise ValueError("床にfloorまたはcorridorを指定してください")
        self._floor_kinds[y][x] = kind

    @property
    def actors(self) -> list[list[Player | Enemy | None]]:
        return [row[:] for row in self._actors]

    @property
    def items(self) -> list[list[Item | None]]:
        return [row[:] for row in self._items]

    @property
    def elevations(self) -> list[list[int]]:
        return [row[:] for row in self._elevations]

    @property
    def stair_axes(self) -> list[list[str | None]]:
        return [[None if block is None else "x" if block.up_direction[0] else "y"
                 for block in row] for row in self._stair_blocks]

    @property
    def stair_blocks(self) -> list[list[StairBlock | None]]:
        return [row[:] for row in self._stair_blocks]

    @property
    def level_stairs(self) -> list[list[LevelStair | None]]:
        return [row[:] for row in self._level_stairs]

    def floor_height(self, x: int, y: int) -> float:
        self._check_bounds(x, y)
        return self._elevations[y][x] / 2

    def set_elevation(self, x: int, y: int, half_steps: int) -> None:
        self._check_bounds(x, y)
        if self._terrain[y][x] != Tile.FLOOR:
            raise ValueError("高さは床に設定してください")
        if type(half_steps) is not int or half_steps < 0:
            raise ValueError("高さは0以上の整数（0.5マス単位）にしてください")
        if self._actors[y][x] is not None or self._items[y][x] is not None:
            raise ValueError("高さは配置前に設定してください")
        self._elevations[y][x], self._stair_blocks[y][x] = half_steps, None

    def set_stair_block(self, x: int, y: int, base_height: int, up_direction: tuple[int, int]) -> None:
        if type(base_height) is not int or base_height < 0 or up_direction not in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            raise ValueError("階段の下端は0以上の整数標高、上り方向は上下左右で指定してください")
        self.set_elevation(x, y, base_height * 2 + 1)
        self._stair_blocks[y][x] = StairBlock(base_height, up_direction)

    def set_level_stair(self, x: int, y: int, direction: tuple[int, int], visible_treads: int) -> None:
        """階層移動階段の開口部を床へ設定する。"""
        if direction not in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            raise ValueError("階層階段の方向は上下左右で指定してください")
        if type(visible_treads) is not int or visible_treads <= 0:
            raise ValueError("階層階段の踏み段数は正の整数にしてください")
        self._check_bounds(x, y)
        if self._terrain[y][x] != Tile.FLOOR:
            raise ValueError("階層階段は床に設定してください")
        if self._stair_blocks[y][x] is not None:
            raise ValueError("標高用階段と階層階段は同じマスに置けません")
        if self._actors[y][x] is not None or self._items[y][x] is not None:
            raise ValueError("配置物のあるマスには階層階段を置けません")
        self._level_stairs[y][x] = LevelStair(direction, visible_treads)

    def edge_height(self, x: int, y: int, dx: int, dy: int) -> float | None:
        """マスの出入口の標高。階段の横面には出入口がない。"""
        block = self._stair_blocks[y][x]
        if block is None:
            return self._elevations[y][x] / 2
        if (dx, dy) == block.up_direction:
            return block.base_height + 1
        if (-dx, -dy) == block.up_direction:
            return block.base_height
        return None

    def surface_height(self, x: float, y: float) -> float:
        """移動中の位置に対応する標高。階段内では斜面として連続する。"""
        ix, iy = floor(x + 0.5), floor(y + 0.5)
        self._check_bounds(ix, iy)
        block = self._stair_blocks[iy][ix]
        if block is None:
            return self._elevations[iy][ix] / 2
        dx, dy = block.up_direction
        progress = max(0, min(1, (x - ix) * dx + (y - iy) * dy + 0.5))
        return block.base_height + progress

    def can_step(self, x: int, y: int, nx: int, ny: int) -> bool:
        if not self.in_bounds(x, y) or not self.in_bounds(nx, ny):
            return False
        if abs(nx - x) + abs(ny - y) != 1:
            return False
        if self._terrain[y][x] != Tile.FLOOR or self._terrain[ny][nx] != Tile.FLOOR:
            return False
        dx, dy = nx - x, ny - y
        source = self.edge_height(x, y, dx, dy)
        target = self.edge_height(nx, ny, -dx, -dy)
        return source is not None and target is not None and source == target

    def reachable_from(self, start: tuple[int, int]) -> set[tuple[int, int]]:
        """配置物を除いた、階段・段差ルール上の到達範囲。"""
        if not self.in_bounds(*start) or self._terrain[start[1]][start[0]] != Tile.FLOOR:
            return set()
        seen, queue = {start}, deque([start])
        while queue:
            x, y = queue.popleft()
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if (nx, ny) not in seen and self.can_step(x, y, nx, ny):
                    seen.add((nx, ny))
                    queue.append((nx, ny))
        return seen

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def _check_bounds(self, x: int, y: int) -> None:
        if not self.in_bounds(x, y):
            raise ValueError(f"マップの範囲外です: {(x, y)}")

    def position_of(self, entity: Player | Enemy | Item) -> tuple[int, int]:
        grid = self._items if isinstance(entity, Item) else self._actors
        for y, row in enumerate(grid):
            for x, occupant in enumerate(row):
                if occupant is entity:
                    return x, y
        raise ValueError("そのオブジェクトは配置されていません")

    @property
    def player_position(self) -> tuple[int, int] | None:
        return None if self._player is None else self.position_of(self._player)

    def set_tile(self, x: int, y: int, tile: Tile) -> None:
        self._check_bounds(x, y)
        tile = Tile(tile)
        if tile == Tile.WALL and (
            self._actors[y][x] is not None or self._items[y][x] is not None
        ):
            raise ValueError("配置物のあるマスを壁にはできません")
        self._terrain[y][x] = tile
        if tile == Tile.WALL:
            self._elevations[y][x], self._stair_blocks[y][x] = 0, None

    def place(self, entity: Player | Enemy | Item, x: int, y: int) -> None:
        if not isinstance(entity, (Player, Enemy, Item)):
            raise TypeError("Player・Enemy・Itemを指定してください")
        self._check_bounds(x, y)
        if self._terrain[y][x] != Tile.FLOOR:
            raise ValueError("床の上に配置してください")
        grid = self._items if isinstance(entity, Item) else self._actors
        if any(occupant is entity for row in grid for occupant in row):
            raise ValueError("同じオブジェクトは二重配置できません")
        if grid[y][x] is not None:
            raise ValueError("そのレイヤーのマスは使用中です")
        if isinstance(entity, Player) and self._player is not None:
            raise ValueError("プレイヤーは1人だけ配置できます")
        grid[y][x] = entity
        if isinstance(entity, Player):
            self._player = entity

    def move_player(self, dx: int, dy: int) -> MoveResult:
        if self._player is None:
            raise ValueError("先にプレイヤーを配置してください")
        return self.move_actor(self._player, dx, dy)

    def move_actor(self, actor: Player | Enemy, dx: int, dy: int) -> MoveResult:
        """上下左右に1マス移動。失敗した場合は配列を変更しない。

        プレイヤーがアイテムに到達したら配列から取り除き、結果に返す。
        敵とは同じマスに入れない。戦闘処理は今後追加する。
        """
        if not isinstance(actor, (Player, Enemy)):
            raise TypeError("移動できるのはPlayer・Enemyだけです")
        if (dx, dy) not in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            raise ValueError("移動は上下左右の1マスを指定してください")
        x, y = self.position_of(actor)
        nx, ny = x + dx, y + dy
        if not self.in_bounds(nx, ny):
            return MoveResult(False, "out_of_bounds")
        if self._terrain[ny][nx] != Tile.FLOOR:
            return MoveResult(False, "wall")
        if not self.can_step(x, y, nx, ny):
            return MoveResult(False, "height_blocked")
        if self._actors[ny][nx] is not None:
            return MoveResult(False, "occupied")
        self._actors[y][x] = None
        self._actors[ny][nx] = actor
        item = None
        if isinstance(actor, Player):
            item = self._items[ny][nx]
            self._items[ny][nx] = None
        level_stair = self._level_stairs[ny][nx] if isinstance(actor, Player) else None
        return MoveResult(True, "level_stair" if level_stair is not None else "moved", item, level_stair)


@dataclass(frozen=True)
class Room:
    x: int
    y: int
    width: int
    height: int
    elevation: int = 1

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2

    def overlaps(self, other: "Room", gap: int) -> bool:
        return (self.x < other.x + other.width + gap
                and self.x + self.width + gap > other.x
                and self.y < other.y + other.height + gap
                and self.y + self.height + gap > other.y)

    def adjoins(self, other: "Room", min_overlap: int) -> bool:
        overlap_x = min(self.x + self.width, other.x + other.width) - max(self.x, other.x)
        overlap_y = min(self.y + self.height, other.y + other.height) - max(self.y, other.y)
        return ((self.x + self.width == other.x or other.x + other.width == self.x)
                and overlap_y >= min_overlap) or (
                    (self.y + self.height == other.y or other.y + other.height == self.y)
                    and overlap_x >= min_overlap)


@dataclass(frozen=True)
class EntrancePlan:
    """部屋の採用前に決める、通路への接続計画。"""
    room: Room
    run: tuple[tuple[int, int], ...]
    protected: frozenset[tuple[int, int]]
    area: frozenset[tuple[int, int]]
    stair_area: frozenset[tuple[int, int]]


class StairPlacementError(ValueError):
    """区画配置に階段用の空間が不足している。"""


@trace_class(info_methods=("__init__", "generate", "populate"))
class DungeonGenerator:
    """定型サイズ・標高を持つ床区画を配置し、通路と階段で接続する。"""

    def __init__(self, width: int, height: int, section_count: int,
                 section_sizes: list[list[int]], section_elevations: list[int],
                 adjacent_probability: float, corridor_elevation: int,
                 wall_thickness: int, corridor_width: int, max_attempts: int,
                 stair_attempts: int, seed: int | None, layout_attempts: int, stair_sides: list[str], stair_landing_length: int, cliff_sides: list[str], stair_clearance: int, level_stair: dict):
        if any(type(v) is not int or v <= 0 for v in
               (width, height, section_count, wall_thickness, corridor_width, max_attempts, stair_attempts, layout_attempts, stair_landing_length, stair_clearance)):
            raise ValueError("広さ・区画数・壁厚・通路幅・試行回数は正の整数にしてください")
        if (not section_sizes or any(len(size) != 2 or any(type(v) is not int or v < 5 for v in size)
                                     for size in section_sizes)):
            raise ValueError("床区画のサイズは5×5以上の[幅, 高さ]で指定してください")
        if (not section_elevations or any(type(v) is not int or v < 1 for v in section_elevations)
                or type(corridor_elevation) is not int or corridor_elevation < 1):
            raise ValueError("標高は正の整数で指定してください")
        if (type(adjacent_probability) not in (int, float) or not 0 <= adjacent_probability <= 1):
            raise ValueError("隣接配置の確率は0〜1で指定してください")
        if corridor_width % 2 == 0 or any(corridor_width > min(size) for size in section_sizes):
            raise ValueError("通路幅は床区画の最小辺以下の正の奇数にしてください")
        if any(size[0] + 2 * wall_thickness > width or size[1] + 2 * wall_thickness > height
               for size in section_sizes):
            raise ValueError("マップに床区画と外周壁が収まりません")
        if seed is not None and type(seed) is not int:
            raise ValueError("seedは整数またはnullにしてください")
        directions = {"north": (0, 1), "west": (1, 0), "south": (0, -1), "east": (-1, 0)}
        if (not isinstance(stair_sides, list) or not stair_sides
                or any(not isinstance(side, str) or side not in directions for side in stair_sides)):
            raise ValueError("stair_sidesはnorth・west・south・eastから指定してください")
        if (not isinstance(cliff_sides,list) or not cliff_sides
                or any(not isinstance(side,str) or side not in directions for side in cliff_sides)):
            raise ValueError("cliff_sidesはnorth・west・south・eastから指定してください")
        if (not isinstance(level_stair, dict)
                or type(level_stair.get("enabled")) is not bool
                or type(level_stair.get("visible_treads")) is not int
                or level_stair["visible_treads"] <= 0):
            raise ValueError("level_stairはenabledと正のvisible_treadsを指定してください")
        level_directions = {"north": (0, -1), "west": (-1, 0), "south": (0, 1), "east": (1, 0)}
        direction_name = level_stair.get("direction")
        if direction_name not in level_directions:
            raise ValueError("level_stair.directionはnorth・west・south・eastから指定してください")
        self.cliff_sides = frozenset(cliff_sides)
        self.stair_directions = tuple(directions[side] for side in stair_sides)
        self.width, self.height = width, height
        self.section_count, self.section_sizes = section_count, section_sizes
        self.section_elevations = section_elevations
        self.adjacent_probability, self.corridor_elevation = adjacent_probability, corridor_elevation
        self.wall_thickness, self.corridor_width = wall_thickness, corridor_width
        self.max_attempts, self.stair_attempts, self.seed = max_attempts, stair_attempts, seed
        self.stair_landing_length = stair_landing_length
        self.stair_clearance = stair_clearance
        self.level_stair_enabled = level_stair["enabled"]
        self.level_stair_visible_treads = level_stair["visible_treads"]
        self.level_stair_direction = level_directions[direction_name]
        self._corridor_stair_area = None
        self.entrance_plans: tuple[EntrancePlan, ...] = ()
        self.layout_attempts = layout_attempts
        self.random = Random(seed)
        self.rooms: tuple[Room, ...] = ()

    def _candidate_room(self, rooms: list[Room]) -> Room:
        width, height = self.random.choice(self.section_sizes)
        elevation = self.random.choice(self.section_elevations)
        margin = self.wall_thickness
        if rooms and self.random.random() < self.adjacent_probability:
            other = self.random.choice(rooms)
            side = self.random.choice(("north", "south", "west", "east"))
            overlap = self.corridor_width
            if side in ("north", "south"):
                x = self.random.randint(other.x - width + overlap, other.x + other.width - overlap)
                y = other.y - height if side == "north" else other.y + other.height
            else:
                x = other.x - width if side == "west" else other.x + other.width
                y = self.random.randint(other.y - height + overlap, other.y + other.height - overlap)
        else:
            x = self.random.randint(margin, self.width - margin - width)
            y = self.random.randint(margin, self.height - margin - height)
        return Room(x, y, width, height, elevation)

    def generate(self) -> Dungeon:
        self.random = Random(self.seed)
        last_error = None
        for _ in range(self.layout_attempts):
            try:
                return self._generate_layout()
            except StairPlacementError as error:
                last_error = error
        self.rooms = ()
        self.entrance_plans = ()
        raise StairPlacementError(f"階段の空間と全床への接続を確保できませんでした。最終原因: {last_error}")

    def _generate_layout(self) -> Dungeon:
        self.rooms = ()
        self.entrance_plans = ()
        rooms = []
        plans = []
        margin = self.wall_thickness
        for _ in range(self.max_attempts):
            room = self._candidate_room(rooms)
            if not (margin <= room.x and margin <= room.y
                    and room.x + room.width <= self.width - margin
                    and room.y + room.height <= self.height - margin):
                continue
            if any(room.overlaps(other, 0) or
                   (room.overlaps(other, self.wall_thickness) and
                    (self.adjacent_probability == 0 or not room.adjoins(other, self.corridor_width)))
                   for other in rooms):
                continue
            plan = self._plan_entrance(room, rooms, plans)
            if plan is None:
                continue
            rooms.append(room)
            plans.append(plan)
            if len(rooms) == self.section_count:
                break
        if len(rooms) != self.section_count:
            raise StairPlacementError(f"床区画を{self.section_count}個配置できませんでした。マップを広げるか区画数を減らしてください")
        self.entrance_plans = tuple(plans)
        dungeon = Dungeon(self.width, self.height)
        for y in range(self.height):
            for x in range(self.width):
                dungeon.set_tile(x, y, Tile.WALL)
        for room in rooms:
            for y in range(room.y, room.y + room.height):
                for x in range(room.x, room.x + room.width):
                    dungeon.set_tile(x, y, Tile.FLOOR)
        self._route_corridors(dungeon, rooms)
        self.rooms = tuple(rooms)
        # 通路の標高を先に設定し、区画内は区画生成時に決めた標高で揃える。
        for y, row in enumerate(dungeon.terrain):
            for x, tile in enumerate(row):
                if tile == Tile.FLOOR:
                    dungeon.set_elevation(x, y, self.corridor_elevation * 2)
        for room in rooms:
            for y in range(room.y, room.y + room.height):
                for x in range(room.x, room.x + room.width):
                    dungeon.set_elevation(x, y, room.elevation * 2)
        self._connect_elevations(dungeon)
        if self.level_stair_enabled:
            self._place_level_stair(dungeon)
        room_cells = {(x,y) for room in rooms for y in range(room.y,room.y+room.height)
                      for x in range(room.x,room.x+room.width)}
        for y,row in enumerate(dungeon.terrain):
            for x,tile in enumerate(row):
                if tile == Tile.FLOOR:
                    dungeon.set_floor_kind(x,y,"floor" if (x,y) in room_cells else "corridor")
        return dungeon

    def _place_level_stair(self, dungeon: Dungeon) -> None:
        """最後に採用した部屋の中央付近へ階層移動階段を1つ置く。"""
        room = self.rooms[-1]
        candidates = [
            (x, y) for y in range(room.y, room.y + room.height)
            for x in range(room.x, room.x + room.width)
            if dungeon.stair_blocks[y][x] is None
        ]
        if not candidates:
            raise StairPlacementError("階層移動階段を置ける床がありません")
        x, y = min(candidates, key=lambda point: abs(point[0] - room.center[0]) + abs(point[1] - room.center[1]))
        dungeon.set_level_stair(x, y, self.level_stair_direction, self.level_stair_visible_treads)

    def _room_cliff_allowed(self, first: Room, second: Room) -> bool:
        """高さの違う部屋が接するとき、高い床の見える側か調べる。"""
        if first.elevation == second.elevation or not first.adjoins(second,1):
            return True
        high,low = (first,second) if first.elevation > second.elevation else (second,first)
        if high.x+high.width == low.x:
            side = "east"
        elif low.x+low.width == high.x:
            side = "west"
        elif high.y+high.height == low.y:
            side = "south"
        else:
            side = "north"
        return side in self.cliff_sides

    def _hidden_cliff_buffer(self, room: Room) -> frozenset[tuple[int,int]]:
        """通路が接すると見えない段差になる、部屋の外側1列を返す。"""
        if room.elevation == self.corridor_elevation:
            return frozenset()
        vectors = {"north":(0,-1),"west":(-1,0),"south":(0,1),"east":(1,0)}
        opposite = {"north":"south","south":"north","east":"west","west":"east"}
        cells = set()
        for side,(dx,dy) in vectors.items():
            high_side = side if room.elevation > self.corridor_elevation else opposite[side]
            if high_side in self.cliff_sides:
                continue
            if dx:
                x = room.x-1 if dx<0 else room.x+room.width
                cells.update((x,y) for y in range(room.y,room.y+room.height))
            else:
                y = room.y-1 if dy<0 else room.y+room.height
                cells.update((x,y) for x in range(room.x,room.x+room.width))
        return frozenset(cells)

    def _plan_entrance(self, room: Room, rooms: list[Room], plans: list[EntrancePlan]) -> EntrancePlan | None:
        """部屋の高さから階段長を決め、部屋・既存の接続計画と衝突しない候補を選ぶ。"""
        radius, margin = self.corridor_width//2, self.wall_thickness
        if any(not self._room_cliff_allowed(room,other) for other in rooms):
            return None
        hidden_buffer = self._hidden_cliff_buffer(room)
        if any(hidden_buffer & plan.area for plan in plans):
            return None
        other_buffers = set().union(*(self._hidden_cliff_buffer(other) for other in rooms))
        room_area = {(x,y) for y in range(room.y,room.y+room.height)
                     for x in range(room.x,room.x+room.width)}
        if any(room_area & (plan.area | plan.protected) for plan in plans):
            return None
        def footprint(points, padding=radius):
            return frozenset((x+ox,y+oy) for x,y in points
                             for ox in range(-padding,padding+1) for oy in range(-padding,padding+1))
        approaches = (self.stair_directions if room.elevation >= self.corridor_elevation
                      else tuple((-dx,-dy) for dx,dy in self.stair_directions))
        options = []
        for dx,dy in approaches:
            x = room.x if dx>0 else room.x+room.width-1 if dx<0 else room.center[0]
            y = room.y if dy>0 else room.y+room.height-1 if dy<0 else room.center[1]
            difference = abs(room.elevation-self.corridor_elevation)
            length = max(1,difference)+self.stair_landing_length+radius+self.stair_clearance+1
            run = tuple((x-dx*i,y-dy*i) for i in range(length+1))
            if any(not (margin+radius <= cx < self.width-margin-radius
                        and margin+radius <= cy < self.height-margin-radius)
                   or any(r.x-radius <= cx < r.x+r.width+radius
                          and r.y-radius <= cy < r.y+r.height+radius for r in rooms)
                   for cx,cy in run):
                continue
            protected = footprint(run[1:difference+self.stair_landing_length+1],radius+self.stair_clearance)
            area = footprint(run)
            if area & (other_buffers | hidden_buffer):
                continue
            if any(r.x <= cx < r.x+r.width and r.y <= cy < r.y+r.height
                   for cx,cy in protected for r in rooms):
                continue
            if any(area & plan.protected or protected & plan.area for plan in plans):
                continue
            stair_area = frozenset((cx-dy*offset,cy+dx*offset)
                                   for cx,cy in run[1:difference+1]
                                   for offset in range(-radius,radius+1))
            options.append(EntrancePlan(room,run,protected,area,stair_area))
        return self.random.choice(options) if options else None

    def _route_corridors(self, dungeon: Dungeon, rooms: list[Room]) -> None:
        """部屋と一緒に確定した入口計画を、区画を横断しない通路で結ぶ。"""
        radius, margin = self.corridor_width//2, self.wall_thickness
        free = {(x,y) for y in range(margin+radius,self.height-margin-radius)
                for x in range(margin+radius,self.width-margin-radius)
                if not any(r.x-radius <= x < r.x+r.width+radius
                           and r.y-radius <= y < r.y+r.height+radius for r in rooms)}
        entrances = [plan.run for plan in self.entrance_plans]
        reserved = set().union(*(plan.protected for plan in self.entrance_plans))
        self._corridor_stair_area = set().union(*(plan.stair_area for plan in self.entrance_plans))
        def footprint(points):
            return {(x+ox,y+oy) for x,y in points
                    for ox in range(-radius,radius+1) for oy in range(-radius,radius+1)}
        if not entrances:
            raise StairPlacementError("許可された側に通路の入口を確保できません")
        # 見えない側へ低い通路が接しないよう、壁用の隙間も残す。
        reserved.update(set().union(*(self._hidden_cliff_buffer(room) for room in rooms)))
        free = {point for point in free if not footprint([point]) & reserved}
        network = set()
        for run in entrances:
            end = run[-1]
            if network:
                parents = {end: None}
                queue = deque([end])
                goal = None
                while queue:
                    point = queue.popleft()
                    if point in network:
                        goal = point
                        break
                    x, y = point
                    for neighbor in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                        if neighbor in free and neighbor not in parents:
                            parents[neighbor] = point
                            queue.append(neighbor)
                if goal is None:
                    raise StairPlacementError("区画を避けて通路を接続できません")
                while goal is not None:
                    self._carve(dungeon, goal, goal)
                    network.add(goal)
                    goal = parents[goal]
            for point in run:
                self._carve(dungeon, point, point)
                if point in free:
                    network.add(point)

    def _height_regions(self, dungeon: Dungeon):
        terrain, elevations = dungeon.terrain, dungeon.elevations
        labels = [[-1 for _ in range(dungeon.width)] for _ in range(dungeon.height)]
        count = 0
        for y, row in enumerate(terrain):
            for x, tile in enumerate(row):
                if tile != Tile.FLOOR or labels[y][x] != -1:
                    continue
                labels[y][x] = count
                queue = deque([(x, y)])
                while queue:
                    cx, cy = queue.popleft()
                    for nx, ny in ((cx-1, cy), (cx+1, cy), (cx, cy-1), (cx, cy+1)):
                        if (dungeon.in_bounds(nx, ny) and labels[ny][nx] == -1
                                and terrain[ny][nx] == Tile.FLOOR and elevations[ny][nx] == elevations[cy][cx]):
                            labels[ny][nx] = count
                            queue.append((nx, ny))
                count += 1
        return labels, count

    def _room_stair_layouts(self, x, y, direction, room, terrain, elevations, start):
        """段差に平行な階段と、高い床へ横に曲がれる1マス踊り場を作る。"""
        dx, dy = direction
        low, high = elevations[y][x] // 2, elevations[y+dy][x+dx] // 2
        length = high - low
        layouts = []
        for sx, sy in ((-dy, dx), (dy, -dx)):
            # (x, y)を上端の平らな踊り場とし、その横に階段を連ねる。
            run = [(x-sx*i, y-sy*i) for i in range(length+2)]
            if any(not (room.x <= cx < room.x+room.width and room.y <= cy < room.y+room.height)
                   or terrain[cy][cx] != Tile.FLOOR or elevations[cy][cx] != low*2
                   for cx, cy in run):
                continue
            chain = [(x-sx*i, y-sy*i, high-i, (sx, sy)) for i in range(1, length+1)]
            layout = chain + [(x, y, high, None)]
            occupied = {(cx,cy) for cx,cy,_,_ in chain}
            # 踊り場自体の裏側にも、見えない平床同士の段差を作らない。
            if any(side not in self.cliff_sides
                   and 0 <= x+ox < len(terrain[0]) and 0 <= y+oy < len(terrain)
                   and terrain[y+oy][x+ox] == Tile.FLOOR
                   and elevations[y+oy][x+ox] < high*2
                   and (x+ox,y+oy) not in occupied
                   for side,ox,oy in (("north",0,-1),("west",-1,0),("south",0,1),("east",1,0))):
                continue
            if any((cx, cy) == start for cx, cy, _, _ in layout):
                continue
            layouts.append(layout)
        return layouts

    def _stair_layout(self, chain, terrain, elevations, start):
        """通路の階段を横幅全体へ広げる。"""
        height, width = len(terrain), len(terrain[0])
        x, y, _, (dx, dy) = chain[0]
        # 区画外の低い床は通路。境界に沿った全レーンを同時に階段にする。
        lanes = list(chain)
        px, py = -dy, dx
        low = elevations[y][x]
        high = elevations[y+dy][x+dx]
        for sign in (-1, 1):
            offset = sign
            while True:
                sx, sy = x + px*offset, y + py*offset
                if not (0 <= sx < width and 0 <= sy < height):
                    break
                if terrain[sy][sx] != Tile.FLOOR or elevations[sy][sx] != low:
                    break
                if any(r.x <= sx < r.x+r.width and r.y <= sy < r.y+r.height for r in self.rooms):
                    break
                run = [(sx - dx*i, sy - dy*i) for i in range(len(chain)+1)]
                upper = sx+dx, sy+dy
                if (not (0 <= upper[0] < width and 0 <= upper[1] < height)
                        or terrain[upper[1]][upper[0]] != Tile.FLOOR
                        or elevations[upper[1]][upper[0]] != high):
                    break
                if any(not (0 <= rx < width and 0 <= ry < height)
                       or terrain[ry][rx] != Tile.FLOOR or elevations[ry][rx] != low
                       for rx, ry in run):
                    return None
                lanes.extend((cx+px*offset, cy+py*offset, base, direction)
                             for cx, cy, base, direction in chain)
                offset += sign
        if any((cx, cy) == start for cx, cy, _, _ in lanes):
            return None
        if self._corridor_stair_area is not None and any(
                (cx,cy) not in self._corridor_stair_area for cx,cy,_,_ in lanes):
            return None
        if self._corridor_stair_area is not None:
            occupied = {(cx,cy) for cx,cy,_,_ in lanes}
            for cx,cy,_,_ in lanes:
                for sign in (-1,1):
                    neighbor = cx+px*sign, cy+py*sign
                    if (0 <= neighbor[0] < width and 0 <= neighbor[1] < height
                            and terrain[neighbor[1]][neighbor[0]] == Tile.FLOOR
                            and neighbor not in occupied):
                        return None
            base = elevations[y][x]//2
            bottom = [(cx,cy) for cx,cy,z,_ in lanes if z == base]
            for distance in range(1,self.stair_landing_length+1):
                landing = {(cx-dx*distance,cy-dy*distance) for cx,cy in bottom}
                for cx,cy in landing:
                    for sign in (-1,1):
                        neighbor = cx+px*sign,cy+py*sign
                        if (0 <= neighbor[0] < width and 0 <= neighbor[1] < height
                                and terrain[neighbor[1]][neighbor[0]] == Tile.FLOOR
                                and neighbor not in landing):
                            return None
        return lanes

    def _connect_elevations(self, dungeon: Dungeon) -> None:
        labels, region_count = self._height_regions(dungeon)
        if region_count <= 1:
            return
        terrain, elevations = dungeon.terrain, dungeon.elevations
        start = self.rooms[0].center
        candidates = {}
        for y, row in enumerate(terrain):
            for x, tile in enumerate(row):
                if tile != Tile.FLOOR:
                    continue
                low = elevations[y][x] // 2
                # 高い床から見た接続側で制限する。横向き階段の上り方向とは別。
                for dx, dy in self.stair_directions:
                    nx, ny = x + dx, y + dy
                    if not dungeon.in_bounds(nx, ny) or terrain[ny][nx] != Tile.FLOOR:
                        continue
                    high = elevations[ny][nx] // 2
                    if high <= low:
                        continue
                    pair = tuple(sorted((labels[y][x], labels[ny][nx])))
                    room = next((room for room in self.rooms
                                 if room.x <= x < room.x+room.width
                                 and room.y <= y < room.y+room.height), None)
                    if room is not None:
                        candidates.setdefault(pair, []).extend(
                            self._room_stair_layouts(x, y, (dx, dy), room, terrain, elevations, start))
                        if not candidates[pair]:
                            del candidates[pair]
                        continue
                    length = high - low
                    chain = [(x - dx*i, y - dy*i, high - i - 1, (dx, dy))
                             for i in range(length)]
                    # 最下段の後ろにも、同じ標高の平らな踊り場を確保する。
                    run = [(x - dx*i, y - dy*i) for i in range(length + 1)]
                    if any(not dungeon.in_bounds(sx, sy) or terrain[sy][sx] != Tile.FLOOR
                           or elevations[sy][sx] != low * 2 for sx, sy in run):
                        continue
                    if any((sx, sy) == start for sx, sy, _, _ in chain):
                        continue
                    pair = tuple(sorted((labels[y][x], labels[ny][nx])))
                    layout = self._stair_layout(chain, terrain, elevations, start)
                    if layout is not None:
                        candidates.setdefault(pair, []).append(layout)
        # 候補の段階でも全領域を結べない場合、孤立した地形を返さない。
        connected = {0}
        while True:
            updated = connected | {v for pair in candidates if any(v in connected for v in pair) for v in pair}
            if updated == connected:
                break
            connected = updated
        if len(connected) != region_count:
            raise StairPlacementError("標高差をつなぐ階段の設置場所がありません。区画サイズや通路幅を広げてください")
        total = sum(tile == Tile.FLOOR for row in terrain for tile in row)
        previous = []
        for _ in range(self.stair_attempts):
            for x, y in previous:
                dungeon.set_elevation(x, y, elevations[y][x])
            previous = []
            pairs = list(candidates)
            self.random.shuffle(pairs)
            used = set()
            for pair in pairs:
                options = [chain for chain in candidates[pair]
                           if all((x, y) not in used for x, y, _, _ in chain)]
                if not options:
                    continue
                self.random.shuffle(options)
                def score(chain):
                    return sum(dungeon.in_bounds(x+dx, y+dy)
                               and terrain[y+dy][x+dx] == Tile.FLOOR
                               and elevations[y+dy][x+dx] == elevations[y][x]
                               for x, y, _, _ in chain
                               for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)))
                chain = max(options, key=score)
                for x, y, base, direction in chain:
                    if direction is None:
                        dungeon.set_elevation(x, y, base * 2)
                    else:
                        dungeon.set_stair_block(x, y, base, direction)
                    used.add((x, y))
                    previous.append((x, y))
            if len(dungeon.reachable_from(start)) == total:
                return
        raise StairPlacementError("全ての床へ移動できる階段配置を作れませんでした。区画配置・通路幅を調整してください")

    def _carve(self, dungeon: Dungeon, start: tuple[int, int], end: tuple[int, int]):
        radius = self.corridor_width // 2
        for y in range(min(start[1], end[1]) - radius, max(start[1], end[1]) + radius + 1):
            for x in range(min(start[0], end[0]) - radius, max(start[0], end[0]) + radius + 1):
                dungeon.set_tile(x, y, Tile.FLOOR)

    def populate(self, dungeon: Dungeon, player_name: str,
                 item_names: list[str], enemy_names: list[str]) -> None:
        if not self.rooms:
            raise ValueError("先にgenerateを呼んでください")
        start = self.rooms[0].center
        terrain = dungeon.terrain
        candidates = [(x, y) for y, row in enumerate(terrain)
                      for x, tile in enumerate(row) if tile == Tile.FLOOR and (x, y) != start
                      and dungeon._stair_blocks[y][x] is None
                      and dungeon._level_stairs[y][x] is None]
        if len(candidates) < len(item_names) + len(enemy_names):
            raise ValueError("配置する敵・アイテムに対して床が足りません")
        self.random.shuffle(candidates)
        dungeon.place(Player(player_name), *start)
        for name in item_names:
            dungeon.place(Item(name), *candidates.pop())
        for name in enemy_names:
            dungeon.place(Enemy(name), *candidates.pop())
