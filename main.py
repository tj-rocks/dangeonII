"""実行: python main.py。ウィンドウを選択して矢印キーで操作。"""

import argparse
from random import Random
import pygame

from system.dungeon import DescentDungeonGenerator, DungeonGenerator
from system.operate import Operate
from system.renderer import DungeonRenderer
from system.logs.tracing import begin_trace_frame, configure_logging, logger
from system.configuration import load_settings
from system.savedata import SaveData


def main(log_detail: int | None = None, debug_surfaces: bool = False) -> None:
    settings = load_settings("setting.yml")
    configure_logging(settings["logging"]["detail"] if log_detail is None else log_detail)
    pygame.init()
    try:
        window = settings["window"]
        screen = pygame.display.set_mode((window["width"], window["height"]))
        pygame.display.set_caption(window["title"])
        clock = pygame.time.Clock()

        world = settings["dungeon"]
        mode = world["generation_mode"]
        if mode not in ("classic", "descent", "mixed"):
            raise ValueError("generation_modeはclassic・descent・mixedから指定してください")
        if mode == "mixed":
            mode = Random(world["generation"]["seed"]).choice(("classic", "descent"))
        generator = (DungeonGenerator(world["width"], world["height"], **world["generation"])
                     if mode == "classic" else
                     DescentDungeonGenerator(world["width"], world["height"], **world["descent_generation"]))
        logger.info1("ダンジョン生成方式: %s", mode)
        if isinstance(generator, DescentDungeonGenerator):
            logger.info1("下降マップ: 希望 %sx%s 標高%s → 採用 %sx%s 標高%s",
                         generator.requested_width, generator.requested_height,
                         generator.requested_elevation, generator.width,
                         generator.height, generator.start_elevation)
        dungeon = generator.generate()
        generator.populate(dungeon, world["player"]["name"],
                           [item["name"] for item in world["items"]],
                           [enemy["name"] for enemy in world["enemies"]])
        SaveData().enter_dungeon()
        operate = Operate(dungeon)
        pygame.key.set_repeat()  # OSのキーリピートではなく押下状態で連続移動する
        renderer = DungeonRenderer(screen, operate.settings)
        if debug_surfaces:
            renderer.config["surface_debug"]["enabled"] = True
        logger.info3("現在座標: %s", dungeon.player_position)

        running = True
        while running:
            begin_trace_frame()
            now_ms = pygame.time.get_ticks()
            for event in pygame.event.get():
                if operate.is_quit_event(event):
                    running = False
                    break
                operate.track_event(event)
            if not running:
                break
            if not renderer.move_animation.is_active(now_ms):
                before = dungeon.player_position
                before_height = dungeon.floor_height(*before)
                result = operate.move_held()
                if result is not None and result.moved:
                    renderer.move_animation.start(before, dungeon.player_position, now_ms,
                                                  before_height, dungeon.floor_height(*dungeon.player_position))
                    if result.level_stair is not None:
                        logger.info1("階層移動階段に到達: %s", dungeon.player_position)
            renderer.draw(dungeon, now_ms)
            pygame.display.flip()
            clock.tick(window["fps"])
    finally:
        pygame.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-detail", type=int, choices=(1, 2, 3), default=None,
                        help="ログの詳細度。通常1、メソッド2、座標・描画3")
    parser.add_argument("--debug", action="store_true", help="--log-detail 3と同じ")
    parser.add_argument("--debug-surfaces", action="store_true", help="壁・床側面・階段を色分けして診断表示")
    args = parser.parse_args()
    main(log_detail=3 if args.debug else args.log_detail, debug_surfaces=args.debug_surfaces)
