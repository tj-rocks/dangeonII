"""実行: python tools/check_stairs.py --seeds 0 1 42"""

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import pygame
from system.configuration import load_settings
from system.diagnostics.stair_visibility import StairVisibilityInspector
from system.dungeon import DungeonGenerator


def main():
    settings = load_settings('stair_visibility.yml')
    parser = argparse.ArgumentParser(description='階段の踏み面の可視率を地形だけで判定する。ゲームデータは変更しない。')
    parser.add_argument('--seeds', nargs='+', type=int, default=settings['seeds'])
    parser.add_argument('--output', type=Path, default=ROOT/settings['output_directory'])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    pygame.init()
    summaries = []
    try:
        world = load_settings('setting.yml')['dungeon']
        for seed in args.seeds:
            generator = DungeonGenerator(world['width'], world['height'], **dict(world['generation'], seed=seed))
            dungeon = generator.generate()
            inspector = StairVisibilityInspector(dungeon)
            geometry, report = inspector.inspect(dungeon, settings['minimum_visible_ratio'])
            report.update(seed=seed, minimum_visible_ratio=settings['minimum_visible_ratio'],
                          assumptions='Fixed isometric camera; opaque terrain; no actors, items, HUD or player fade. Ratios measure tread pixels, not path readability.')
            # 同じseedを再判定したとき、以前の警告用画像を残さない。
            for stale in args.output.glob(f'seed_{seed}_stair_*.png'):
                stale.unlink()
            inspector.save_overview(geometry, report, args.output/f'seed_{seed}.png', settings)
            (args.output/f'seed_{seed}.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            counts = Counter(f['status'] for f in report['flights'])
            summaries.append(dict(seed=seed, flights=len(report['flights']), **{k: counts[k] for k in ('hidden','partial','visible')}))
            print(f"seed={seed}: 階段{len(report['flights'])}組 / 完全に隠れる{counts['hidden']} / 見えにくい{counts['partial']} / 閾値以上{counts['visible']}", flush=True)
            for flight in report['flights']:
                if flight['status'] != 'visible':
                    print(f"  #{flight['id']} 上り{flight['up_direction']} 可視率{flight['visible_ratio']:.1%} 座標{flight['coordinates']}", flush=True)
            del inspector, geometry, dungeon
        (args.output/'summary.json').write_text(json.dumps(summaries, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print(f'判定画像・詳細JSON: {args.output}')
    finally:
        pygame.quit()


if __name__ == '__main__':
    main()
