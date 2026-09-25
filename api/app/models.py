"""请求/响应模型与入参校验。

板材宽高 2–10、件宽高 1–5；瑕疵格为不重复且不越界的整数坐标。
kerf_cells 为锯缝厚度（单位格）：0 表示零宽切线（既有行为），1 表示每刀
从当前矩形吃掉坐标处的一整行/列，两侧子矩形都必须非空。
任何越界、重复瑕疵或额外字段都由 FastAPI 返回 422。
"""

from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

BOARD_MIN, BOARD_MAX = 2, 10
PIECE_MIN, PIECE_MAX = 1, 5


class SolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    board_width: int = Field(ge=BOARD_MIN, le=BOARD_MAX)
    board_height: int = Field(ge=BOARD_MIN, le=BOARD_MAX)
    piece_width: int = Field(ge=PIECE_MIN, le=PIECE_MAX)
    piece_height: int = Field(ge=PIECE_MIN, le=PIECE_MAX)
    allow_rotation: bool
    defects: List[Tuple[int, int]]
    kerf_cells: Literal[0, 1] = 0

    @field_validator("board_width", "board_height", "piece_width", "piece_height", "kerf_cells", mode="before")
    @classmethod
    def _reject_bool(cls, v):
        # True/False 是 int 子类，会被静默当作 1/0；尺寸字段显式拒绝。
        # before 模式：Literal 校验会把 True 归一成 1，必须在类型转换前拦截
        if isinstance(v, bool):
            raise ValueError("尺寸必须是整数，不能是布尔值")
        return v

    @field_validator("defects")
    @classmethod
    def _check_defects(cls, v):
        seen = set()
        for cell in v:
            if not isinstance(cell, (list, tuple)) or len(cell) != 2:
                raise ValueError("每个瑕疵格必须是 [x, y] 坐标对")
            x, y = cell
            if isinstance(x, bool) or isinstance(y, bool):
                raise ValueError("瑕疵坐标必须是整数")
            if (x, y) in seen:
                raise ValueError(f"瑕疵格 ({x}, {y}) 重复")
            seen.add((x, y))
        return v

    @model_validator(mode="after")
    def _check_defects_in_board(self):
        """依赖板宽高的越界校验（字段间约束）。"""
        bad = [
            (x, y)
            for x, y in self.defects
            if not (0 <= x < self.board_width and 0 <= y < self.board_height)
        ]
        if bad:
            raise ValueError(f"瑕疵格越界: {bad}")
        return self


class RectOut(BaseModel):
    x: int
    y: int
    width: int
    height: int


class PieceOut(RectOut):
    rotated: bool


class ScrapOut(RectOut):
    # 仅锯缝格带为 True；普通废料不带该字段（响应中省略，kerf_cells=0 时逐项不变）
    kerf: Optional[bool] = None


class CutOut(BaseModel):
    order: int
    orientation: Literal["H", "V"]
    coord: int
    rect: RectOut
    # kerf_cells=1 时该刀吃掉的整行/列格带；kerf_cells=0 时省略
    kerf: Optional[RectOut] = None


class SolveResponse(BaseModel):
    piece_count: int
    cut_count: int
    pieces: List[PieceOut]
    scraps: List[ScrapOut]
    cuts: List[CutOut]
    tree: dict
