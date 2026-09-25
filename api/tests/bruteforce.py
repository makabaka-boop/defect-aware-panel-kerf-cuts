"""小板暴力枚举：穷举全部 guillotine 直切树，收集所有可达的 (成品数, 切割数)。

仅用于 pytest 中对小规模板材（宽高 <= 4）核对动态规划结果的目标值。

kerf_cells=1 时每刀从当前矩形吃掉坐标处的一整行/列（锯缝格带），两侧子矩形
都必须非空；锯缝不是叶块，永远不能成为成品（可含瑕疵，不影响目标值）。
"""

from functools import lru_cache
from typing import FrozenSet, Tuple

Rect = Tuple[int, int, int, int]
Objective = Tuple[int, int]  # (成品件数, 切割次数)


def brute_objectives(
    width: int,
    height: int,
    piece_w: int,
    piece_h: int,
    allow_rotation: bool,
    defects: FrozenSet[Tuple[int, int]],
    kerf_cells: int = 0,
) -> FrozenSet[Objective]:
    targets = {(piece_w, piece_h)}
    if allow_rotation:
        targets.add((piece_h, piece_w))

    def has_defect(x: int, y: int, w: int, h: int) -> bool:
        for dx, dy in defects:
            if x <= dx < x + w and y <= dy < y + h:
                return True
        return False

    @lru_cache(maxsize=None)
    def outcomes(rect: Rect) -> FrozenSet[Objective]:
        x, y, w, h = rect
        vals = {(0, 0)}  # 整块作废料叶，永远合法
        if (w, h) in targets and not has_defect(x, y, w, h):
            vals.add((1, 0))  # 成品叶
        # 全部整数网格线 H 切；kerf=1 时吃掉 coord 整行，两侧都必须非空
        for k in range(1, h - kerf_cells):
            for p1, c1 in outcomes((x, y, w, k)):
                for p2, c2 in outcomes((x, y + k + kerf_cells, w, h - k - kerf_cells)):
                    vals.add((p1 + p2, 1 + c1 + c2))
        # 全部整数网格线 V 切；kerf=1 时吃掉 coord 整列，两侧都必须非空
        for k in range(1, w - kerf_cells):
            for p1, c1 in outcomes((x, y, k, h)):
                for p2, c2 in outcomes((x + k + kerf_cells, y, w - k - kerf_cells, h)):
                    vals.add((p1 + p2, 1 + c1 + c2))
        return frozenset(vals)

    return outcomes((0, 0, width, height))


def optimal_objective(
    width: int,
    height: int,
    piece_w: int,
    piece_h: int,
    allow_rotation: bool,
    defects,
    kerf_cells: int = 0,
) -> Objective:
    objectives = brute_objectives(
        width,
        height,
        piece_w,
        piece_h,
        allow_rotation,
        frozenset(tuple(d) for d in defects),
        kerf_cells,
    )
    return max(objectives, key=lambda pc: (pc[0], -pc[1]))
