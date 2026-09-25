"""Guillotine 直切排样核心求解器。

在全部直切树（每刀沿整数网格线贯穿当前矩形）中：

1. 最大化成品件数；
2. 最小化切割次数；
3. 并列时按 H 先于 V、全局切割坐标较小优先，并递归比较
   先上后下（V 切时先左后右）的子树。

叶块只能是废料，或尺寸恰好等于目标件（允许旋转时含旋转尺寸）且不含瑕疵的成品。

锯缝（kerfCells）：为 1 时每一刀除了沿全局坐标 ``coord`` 划开当前矩形，还要
吃掉 ``coord`` 起的一整行（H 切）或一整列（V 切）单元格，留下的两侧子矩形都必须
非空。锯缝格带随刀消失，可包含瑕疵但永远不能成为成品；为 0 时退化为零宽切线，
行为与旧版逐项一致。

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
#   切割内: ("cut",   rect, pieces, cuts, orientation, coord, first, second, band)
# band 为该刀吃掉的锯缝格带矩形（kerfCells=0 时为 None）。
Node = Tuple

PIECES = 2
CUTS = 3
BAND = 8


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
        kerf_cells: int = 0,
    ):
        self.W = board_width
        self.H = board_height
        self.pw = piece_width
        self.ph = piece_height
        self.allow_rotation = allow_rotation
        # 每刀吃掉的格带宽度（0 或 1）
        self.kerf = kerf_cells
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

        kerf=1 时一切从当前矩形移除坐标处的一整行/列，两侧子矩形都必须非空
        （故 k 的上界随之收紧一格）；锯缝格带记入节点，不再参与递归，因而
        可含瑕疵且永远不会成为成品。
        """
        x, y, w, h = rect
        kerf = self.kerf

        # 叶候选：恰好等于目标件尺寸且无瑕疵 -> 成品叶（1 件 0 刀，恒优于废料叶）
        if (w, h) in self.targets and self._defect_count(rect) == 0:
            best: Node = ("piece", rect, 1, 0)
        else:
            # 其余一律可整块作为废料叶（0 件 0 刀）
            best = ("scrap", rect, 0, 0)

        # 所有整数网格线 H 切，坐标升序（上块 first，下块 second）；
        # kerf=1 时吃掉 y+k 整行，下块从 y+k+1 开始
        for k in range(1, h - kerf):
            top = (x, y, w, k)
            bottom = (x, y + k + kerf, w, h - k - kerf)
            band = (x, y + k, w, kerf) if kerf else None
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
                band,
            )
            if (cand[PIECES], -cand[CUTS]) > (best[PIECES], -best[CUTS]):
                best = cand

        # 所有整数网格线 V 切，坐标升序（左块 first，右块 second）；
        # kerf=1 时吃掉 x+k 整列，右块从 x+k+1 开始
        for k in range(1, w - kerf):
            left = (x, y, k, h)
            right = (x + k + kerf, y, w - k - kerf, h)
            band = (x + k, y, kerf, h) if kerf else None
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
                band,
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
        kerfs: List[dict] = []

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
            # 该刀吃掉的锯缝格带（kerfCells=1 时必有一条），与 cuts 同序一一对应
            band = node[BAND]
            if band is not None:
                kerfs.append(rect_dict(band))
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
            "kerfs": kerfs,
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
    out = {
        "type": "cut",
        "orientation": orientation,
        "coord": coord,
        "rect": rect,
    }
    # kerfCells=1 时显式标出该刀吃掉的格带；为 0 时不输出该字段，树与旧版逐项一致
    band = node[BAND]
    if band is not None:
        bx, by, bw, bh = band
        out["kerf"] = {"x": bx, "y": by, "width": bw, "height": bh}
    out.update(
        {
            "piece_count": node[PIECES],
            "cut_count": node[CUTS],
            "first": _node_to_json(first),
            "second": _node_to_json(second),
        }
    )
    return out
