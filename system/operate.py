"""Pygameのキー入力をダンジョンの移動に変換する。"""

import pygame

from system.dungeon import Dungeon, MoveResult
from system.logs.tracing import logger, trace_class
from dataclasses import dataclass
from system.configuration import load_settings


@dataclass(frozen=True)
class OperateSettings:
    move_up: int
    move_down: int
    move_left: int
    move_right: int
    quit: int

    @classmethod
    def load(cls):
        return cls.from_dict(load_settings("operate.yml"))

    @classmethod
    def from_dict(cls, data):
        actions = ("move_up", "move_down", "move_left", "move_right", "quit")
        try:
            bindings = data["bindings"]
            codes = {}
            for action in actions:
                name = bindings[action]
                if not isinstance(name, str) or not name:
                    raise ValueError(f"{action}: キー名は文字列で指定してください")
                codes[action] = pygame.key.key_code(name)
            if len(set(codes.values())) != len(actions):
                raise ValueError("キー割り当てが重複しています")
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"operate.ymlの設定が不正です: {error}") from error
        return cls(**codes)


@trace_class(info_methods=("__init__", "handle_event", "track_event", "move_held", "is_quit_event"))
class Operate:
    def __init__(self, dungeon: Dungeon, settings: OperateSettings | None = None):
        self.dungeon = dungeon
        self.settings = settings if settings is not None else OperateSettings.load()
        self.directions = {
            self.settings.move_up: (0, -1),
            self.settings.move_down: (0, 1),
            self.settings.move_left: (-1, 0),
            self.settings.move_right: (1, 0),
        }
        self._held_keys = []

    def track_event(self, event: pygame.event.Event) -> None:
        """移動中もキーの押下・解放を記録。最後に押した方向を優先する。"""
        if event.type == pygame.WINDOWFOCUSLOST:
            self._held_keys.clear()
        elif event.type == pygame.KEYDOWN and event.key in self.directions:
            if event.key not in self._held_keys:
                self._held_keys.append(event.key)
        elif event.type == pygame.KEYUP and event.key in self._held_keys:
            self._held_keys.remove(event.key)

    def move_held(self) -> MoveResult | None:
        if not self._held_keys:
            return None
        return self.handle_event(pygame.event.Event(pygame.KEYDOWN, key=self._held_keys[-1]))

    def is_quit_event(self, event: pygame.event.Event) -> bool:
        return event.type == pygame.QUIT or (
            event.type == pygame.KEYDOWN and event.key == self.settings.quit
        )

    def handle_event(self, event: pygame.event.Event) -> MoveResult | None:
        """矢印キーのKEYDOWNを処理する。長押しの繰り返し入力も受け付ける。"""
        if event.type != pygame.KEYDOWN:
            return None
        direction = self.directions.get(event.key)
        if direction is None:
            return None

        result = self.dungeon.move_player(*direction)
        logger.info3("現在座標: %s 移動: %s (%s)",
                    self.dungeon.player_position, result.moved, result.reason)
        if result.item is not None:
            logger.info2("アイテム取得: %s", result.item.name)
        return result
