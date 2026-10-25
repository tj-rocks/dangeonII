"""実際の描画順で、階段の踏み面が地形に隠れる割合を計測する。"""

from collections import Counter, deque

import pygame

from system.configuration import load_settings
from system.renderer import DungeonRenderer


def pixel_counts(surface):
    """32bit描画面の色ごとの画素数。NumPyなどの追加依存は不要。"""
    return Counter(memoryview(surface.get_buffer()).cast('I'))


class StairVisibilityInspector(DungeonRenderer):
    """踏み面だけ固有色、それ以外は黒で同じ描画処理を実行する。"""

    def __init__(self, dungeon):
        config = load_settings('renderer.yml')
        # マップ全体を切らずに描く。元のタイル寸法を使用する。
        width = (dungeon.width+dungeon.height)*config['tile_width']//2 + config['tile_width']*2
        highest = max(max(row) for row in dungeon.elevations)/2
        wall_height = sum(layer['height_tiles'] for layer in config['wall_layers'])
        extra = round((highest+wall_height)*config['tile_height'])
        height = ((dungeon.width+dungeon.height)*config['tile_height']//2
                  + extra + config['origin_y'] + config['tile_height']*2)
        super().__init__(pygame.Surface((width, height), depth=32))
        self.config['origin_y'] += extra
        self.config['wall_occlusion']['enabled'] = False
        self.config['player_occlusion']['enabled'] = False
        self.config['surface_debug']['enabled'] = False
        self.colors['background'] = [0, 0, 0]
        self.colors['wall_ground'] = [0, 0, 0]
        self.colors['grid'] = [0, 0, 0]
        self._ids = {}
        self._expected = {}
        self._current_color = (0, 0, 0)

    def _draw_texture(self, target, kind, index, points):
        # 可視率の識別色はテクスチャで上書きしない。
        pass

    def _surface_color(self, kind, normal):
        return self._current_color if kind == 'stair_top' else (0, 0, 0)

    def _draw_actor(self, actor, cx, cy):
        # ゲーム開始前の地形だけを評価する。
        pass

    def _draw_stair_block(self, x, y, block, dungeon):
        identifier = len(self._ids)+1
        color = (identifier & 255, (identifier >> 8) & 255, (identifier >> 16) & 255)
        self._current_color = color
        self._ids[x, y] = self.screen.map_rgb(color)
        super()._draw_stair_block(x, y, block, dungeon)
        # 描画直後の踏み面を分母とする。後の地形による上書きを分子に反映する。
        cx, cy = self.map_to_screen(x, y, dungeon)
        rect = pygame.Rect(cx-self.tile_width, cy-round((block.base_height+1)*self.tile_height)-self.tile_height,
                           self.tile_width*2, round((block.base_height+1)*self.tile_height)+self.tile_height*2)
        rect = rect.clip(self.screen.get_rect())
        crop = self.screen.subsurface(rect).copy()
        self._expected[x, y] = pixel_counts(crop)[self._ids[x, y]]

    def inspect(self, dungeon, threshold):
        """地形のみのコピーを評価し、ブロック単位と連続階段単位の結果を返す。"""
        if not 0 <= threshold <= 1:
            raise ValueError('可視率の閾値は0〜1にしてください')
        from system.dungeon import Dungeon, Tile
        geometry = Dungeon(dungeon.width, dungeon.height)
        elevations = dungeon.elevations
        for y, row in enumerate(dungeon.terrain):
            for x, tile in enumerate(row):
                geometry.set_tile(x, y, tile)
                if tile == Tile.FLOOR:
                    geometry.set_elevation(x, y, elevations[y][x])
        blocks = dungeon.stair_blocks
        for y, row in enumerate(blocks):
            for x, block in enumerate(row):
                if block:
                    geometry.set_stair_block(x, y, block.base_height, block.up_direction)
        self._ids.clear()
        self._expected.clear()
        self.draw(geometry, 0, show_hud=False)
        counts = pixel_counts(self.screen)
        results = {}
        for point, identifier in self._ids.items():
            expected, visible = self._expected[point], counts[identifier]
            ratio = visible/expected if expected else 0
            block = blocks[point[1]][point[0]]
            results[point] = dict(x=point[0], y=point[1], base_height=block.base_height,
                                  up_direction=list(block.up_direction), total_pixels=expected,
                                  visible_pixels=visible, visible_ratio=round(ratio, 4),
                                  status='hidden' if not visible else 'partial' if ratio < threshold else 'visible')
        flights = self._flights(results, blocks, threshold)
        return geometry, dict(blocks=list(results.values()), flights=flights)

    def _flights(self, results, blocks, threshold):
        remaining = set(results)
        flights = []
        while remaining:
            point = min(remaining)
            remaining.remove(point)
            group, queue = [point], deque([point])
            while queue:
                x, y = queue.popleft()
                block = blocks[y][x]
                dx, dy = block.up_direction
                for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    neighbor = x+ox, y+oy
                    if neighbor not in remaining:
                        continue
                    other = blocks[neighbor[1]][neighbor[0]]
                    if (other.up_direction == block.up_direction
                            and other.base_height == block.base_height+dx*ox+dy*oy):
                        remaining.remove(neighbor)
                        group.append(neighbor)
                        queue.append(neighbor)
            expected = sum(results[p]['total_pixels'] for p in group)
            visible = sum(results[p]['visible_pixels'] for p in group)
            ratio = visible/expected if expected else 0
            flights.append(dict(id=len(flights)+1, coordinates=[list(p) for p in sorted(group)],
                                up_direction=results[point]['up_direction'], total_pixels=expected,
                                visible_pixels=visible, visible_ratio=round(ratio, 4),
                                status='hidden' if not visible else 'partial' if ratio < threshold else 'visible'))
        return flights

    def save_overview(self, geometry, report, path, settings):
        """通常の地形画像に階段番号と判定色を重ねて保存する。"""
        renderer = DungeonRenderer(pygame.Surface(self.screen.get_size(), depth=32))
        renderer.config['origin_y'] = self.config['origin_y']
        renderer.config['wall_occlusion']['enabled'] = False
        renderer.config['surface_debug']['enabled'] = False
        renderer.draw(geometry, 0, show_hud=False)
        font = pygame.font.Font(None, settings['label_font_size'])
        blocks = geometry.stair_blocks
        marked = []
        for flight in report['flights']:
            color = settings['marker_colors'][flight['status']]
            # 隠れた階段でも、投影される位置に印を描く。
            x, y = flight['coordinates'][len(flight['coordinates'])//2]
            center = renderer.map_to_screen(x, y, geometry, blocks[y][x].base_height+.5)
            pygame.draw.circle(renderer.screen, color, center, settings['marker_radius'], 2)
            label = font.render(f"{flight['id']}:{flight['visible_ratio']:.0%}", True, color)
            renderer.screen.blit(label, (center[0]+settings['marker_radius'], center[1]))
            marked.append((flight, center))
        pygame.image.save(renderer.screen, str(path))
        from pathlib import Path
        path = Path(path)
        for flight, center in marked:
            if flight['status'] == 'visible':
                continue
            rect = pygame.Rect((0, 0), settings['crop_size'])
            rect.center = center
            rect = rect.clip(renderer.screen.get_rect())
            pygame.image.save(renderer.screen.subsurface(rect),
                              str(path.with_name(f"{path.stem}_stair_{flight['id']}.png")))
