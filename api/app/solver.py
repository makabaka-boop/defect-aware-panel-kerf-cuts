"""Guillotine 直切排样核心求解器。

在全部直切树（每刀沿整数网格线贯穿当前矩形）中：

1. 最大化成品件数；
2. 最小化切割次数；
3. 并列时按 H 先于 V、全局切割坐标较小优先，并递归比较
   先上后下（V 切时先左后右）的子树。

叶块只能是废料，或尺寸恰好等于目标件（允许旋转时含旋转尺寸）且不含瑕疵的成品。

实现为对子矩形的记忆化搜索。矩形用 ``(x, y, w, h)`` 表示，原点在左上角，
x 向右、y 向下。切法候选按并列规则要求的次序枚举（H 坐标升序先于 V 坐标升序），
配合严格比较（只有更优才替换当前最优），结果天然确定且与并列规则一致。
"""

from functools import lru_cache
from typing import List, Optional, Sequence, Tuple

Rect = Tuple[int, int, int, int]
# 内部节点（统一布局，便于缓存与取统计值）：
#   成品叶: ("piece", rect, pieces, cuts)
#   废料叶: ("scrap", rect, pieces, cuts)
#   切割内: ("cut",   rect, pieces, cuts, orientation, coord, first, second)
Node = Tuple

PIECES = 2
CUTS = 3


def _build_defect_prefix(width: int, height: int, defects: Sequence[Tuple[int, int]]):
    """二维前缀和，使任意矩形内瑕疵计数为 O(1)。"""
    acc = [[0] * (width + 1) for _ in range(height + 1)]
    for dx, dy in defects:
        acc[dy + 1][dx + 1] = 1
    for y in range(1, height + 1):
        row = acc[y]
        prev_row = acc[y - 1]
        for x in range(1, width + 1):
            row[x] += row[x - 1] + prev_row[x] - prev_row[x - 1]
    return acc


class Solver:
    def __init__(
        self,
        board_width: int,
        board_height: int,
        piece_width: int,
        piece_height: int,
        allow_rotation: bool,
        defects: Sequence[Tuple[int, int]],
    ):
        self.W = board_width
        self.H = board_height
        self.pw = piece_width
        self.ph = piece_height
        self.allow_rotation = allow_rotation
        # 成品可接受的 (宽, 高) 集合（正方形去重）
        self.targets = {(piece_width, piece_height)}
        if allow_rotation:
            self.targets.add((piece_height, piece_width))
        self.prefix = _build_defect_prefix(board_width, board_height, defects)

    def _defect_count(self, rect: Rect) -> int:
        x, y, w, h = rect
        p = self.prefix
        return p[y + h][x + w] - p[y][x + w] - p[y + h][x] + p[y][x]

    @lru_cache(maxsize=None)
    def _solve(self, rect: Rect) -> Node:
        """返回 rect 的最优子树。

        候选枚举顺序即并列优先顺序：
        成品叶 > 废料叶 > H 切（坐标升序，子节点先上后下）
        > V 切（坐标升序，子节点先左后右）。
        只有在 (件数, -刀数) 严格更优时才替换，因此排在前面的并列候选胜出，
        正好实现规定的打破并列规则；同一切法的子矩形因记忆化也只有唯一子树，
        故「递归比较子树」在到达该层时结果已确定。
        """
        x, y, w, h = rect

        # 叶候选：恰好等于目标件尺寸且无瑕疵 -> 成品叶（1 件 0 刀，恒优于废料叶）
        if (w, h) in self.targets and self._defect_count(rect) == 0:
            best: Node = ("piece", rect, 1, 0)
        else:
            # 其余一律可整块作为废料叶（0 件 0 刀）
            best = ("scrap", rect, 0, 0)

        # 所有整数网格线 H 切，坐标升序（上块 first，下块 second）
        for k in range(1, h):
            top = (x, y, w, k)
            bottom = (x, y + k, w, h - k)
            tn, bn = self._solve(top), self._solve(bottom)
            cand = (
                "cut",
                rect,
                tn[PIECES] + bn[PIECES],
                1 + tn[CUTS] + bn[CUTS],
                "H",
                y + k,
                tn,
                bn,
            )
            if (cand[PIECES], -cand[CUTS]) > (best[PIECES], -best[CUTS]):
                best = cand

        # 所有整数网格线 V 切，坐标升序（左块 first，右块 second）
        for k in range(1, w):
            left = (x, y, k, h)
            right = (x + k, y, w - k, h)
            ln, rn = self._solve(left), self._solve(right)
            cand = (
                "cut",
                rect,
                ln[PIECES] + rn[PIECES],
                1 + ln[CUTS] + rn[CUTS],
                "V",
                x + k,
                ln,
                rn,
            )
            if (cand[PIECES], -cand[CUTS]) > (best[PIECES], -best[CUTS]):
                best = cand

        return best

    def solve(self) -> dict:
        root_rect: Rect = (0, 0, self.W, self.H)
        root = self._solve(root_rect)

        pieces: List[dict] = []
        scraps: List[dict] = []
        cuts: List[dict] = []

        def rect_dict(rect: Rect) -> dict:
            x, y, w, h = rect
            return {"x": x, "y": y, "width": w, "height": h}

        def walk(node: Node, order: int) -> int:
            kind = node[0]
            rect = node[1]
            if kind == "piece":
                x, y, w, h = rect
                pieces.append(
                    {
                        "x": x,
                        "y": y,
                        "width": w,
                        "height": h,
                        "rotated": (w, h) != (self.pw, self.ph),
                    }
                )
                return order
            if kind == "scrap":
                scraps.append(rect_dict(rect))
                return order

            orientation, coord, first, second = node[4], node[5], node[6], node[7]
            order += 1
            cuts.append(
                {
                    "order": order,
                    "orientation": orientation,
                    "coord": coord,
                    "rect": rect_dict(rect),
                }
            )
            # 前序遍历：先切当前块，再依次切上/下（或左/右）子块 —— 可直接照单下刀
            order = walk(first, order)
            order = walk(second, order)
            return order

        walk(root, 0)
        return {
            "piece_count": root[PIECES],
            "cut_count": root[CUTS],
            "pieces": pieces,
            "scraps": scraps,
            "cuts": cuts,
            "tree": _node_to_json(root),
        }


def _node_to_json(node: Node) -> dict:
    kind = node[0]
    x, y, w, h = node[1]
    rect = {"x": x, "y": y, "width": w, "height": h}
    if kind in ("piece", "scrap"):
        return {"type": kind, "rect": rect}
    orientation, coord, first, second = node[4], node[5], node[6], node[7]
    return {
        "type": "cut",
        "orientation": orientation,
        "coord": coord,
        "rect": rect,
        "piece_count": node[PIECES],
        "cut_count": node[CUTS],
        "first": _node_to_json(first),
        "second": _node_to_json(second),
    }
