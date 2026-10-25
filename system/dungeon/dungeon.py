"""描画から独立したダンジョン。座標は (x, y)、配列へのアクセスは [y][x]。"""

from dataclasses import dataclass
from enum import IntEnum
from random import Random
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
    def actors(self) -> list[list[Player | Enemy | None]]:
        return [row[:] for row in self._actors]

    @property
    def items(self) -> list[list[Item | None]]:
        return [row[:] for row in self._items]

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
        if self._actors[ny][nx] is not None:
            return MoveResult(False, "occupied")
        self._actors[y][x] = None
        self._actors[ny][nx] = actor
        item = None
        if isinstance(actor, Player):
            item = self._items[ny][nx]
            self._items[ny][nx] = None
        return MoveResult(True, "moved", item)


@dataclass(frozen=True)
class Room:
    x: int
    y: int
    width: int
    height: int

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2

    def overlaps(self, other: "Room", gap: int) -> bool:
        return (self.x < other.x + other.width + gap
                and self.x + self.width + gap > other.x
                and self.y < other.y + other.height + gap
                and self.y + self.height + gap > other.y)


@trace_class(info_methods=("__init__", "generate", "populate"))
class DungeonGenerator:
    """壁で埋めた後、部屋→通路の順で掘る。全ての部屋を接続する。"""

    def __init__(self, width: int, height: int, room_count: int,
                 room_min_size: list[int], room_max_size: list[int],
                 wall_thickness: int, corridor_width: int, max_attempts: int, seed: int | None):
        sizes = [width, height, room_count, wall_thickness, corridor_width, max_attempts,
                 *room_min_size, *room_max_size]
        if any(type(value) is not int or value <= 0 for value in sizes):
            raise ValueError("広さ・部屋数・壁厚・試行回数は正の整数にしてください")
        if len(room_min_size) != 2 or len(room_max_size) != 2:
            raise ValueError("部屋サイズは[幅, 高さ]で指定してください")
        if any(lo > hi for lo, hi in zip(room_min_size, room_max_size)):
            raise ValueError("部屋の最小サイズが最大サイズを超えています")
        if corridor_width % 2 == 0 or corridor_width > min(room_min_size):
            raise ValueError("通路幅は部屋の最小辺以下の正の奇数にしてください")
        if any(hi + 2 * wall_thickness > extent
               for hi, extent in zip(room_max_size, (width, height))):
            raise ValueError("マップに最大サイズの部屋と外周壁が収まりません")
        if seed is not None and type(seed) is not int:
            raise ValueError("seedは整数またはnullにしてください")
        self.width, self.height = width, height
        self.room_count = room_count
        self.room_min_size, self.room_max_size = room_min_size, room_max_size
        self.wall_thickness, self.max_attempts = wall_thickness, max_attempts
        self.corridor_width = corridor_width
        self.seed = seed
        self.random = Random(seed)
        self.rooms: tuple[Room, ...] = ()

    def generate(self) -> Dungeon:
        self.random = Random(self.seed)
        self.rooms = ()
        rooms = []
        margin = self.wall_thickness
        for _ in range(self.max_attempts):
            width = self.random.randint(self.room_min_size[0], self.room_max_size[0])
            height = self.random.randint(self.room_min_size[1], self.room_max_size[1])
            room = Room(self.random.randint(margin, self.width - margin - width),
                        self.random.randint(margin, self.height - margin - height),
                        width, height)
            if any(room.overlaps(other, margin) for other in rooms):
                continue
            rooms.append(room)
            if len(rooms) == self.room_count:
                break
        if len(rooms) != self.room_count:
            raise ValueError(f"部屋を{self.room_count}個配置できませんでした。"
                             "マップを広げるか部屋数・サイズを減らしてください")

        dungeon = Dungeon(self.width, self.height)
        for y in range(self.height):
            for x in range(self.width):
                dungeon.set_tile(x, y, Tile.WALL)
        for room in rooms:
            for y in range(room.y, room.y + room.height):
                for x in range(room.x, room.x + room.width):
                    dungeon.set_tile(x, y, Tile.FLOOR)
        # 新しい部屋を、既に接続した部屋のうち最も近い部屋へ結ぶ。
        for index, room in enumerate(rooms[1:], 1):
            x, y = room.center
            other = min(rooms[:index], key=lambda r:
                        abs(r.center[0] - x) + abs(r.center[1] - y))
            tx, ty = other.center
            if self.random.choice((True, False)):
                self._carve(dungeon, (x, y), (tx, y))
                self._carve(dungeon, (tx, y), (tx, ty))
            else:
                self._carve(dungeon, (x, y), (x, ty))
                self._carve(dungeon, (x, ty), (tx, ty))
        self.rooms = tuple(rooms)
        return dungeon

    def _carve(self, dungeon: Dungeon, start: tuple[int, int], end: tuple[int, int]):
        # 中心線の両側を広げる。曲がり角も同じ幅でつながる。
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
                      for x, tile in enumerate(row) if tile == Tile.FLOOR and (x, y) != start]
        if len(candidates) < len(item_names) + len(enemy_names):
            raise ValueError("配置する敵・アイテムに対して床が足りません")
        self.random.shuffle(candidates)
        dungeon.place(Player(player_name), *start)
        for name in item_names:
            dungeon.place(Item(name), *candidates.pop())
        for name in enemy_names:
            dungeon.place(Enemy(name), *candidates.pop())
