"""请求/响应模型与入参校验。

板材宽高 2–10、件宽高 1–5；瑕疵格为不重复且不越界的整数坐标。
kerf_cells 取 0 或 1（缺省 0）：为 1 时每一刀从当前矩形吃掉一整行/列单元格。
任何越界、重复瑕疵、非法 kerf_cells 或额外字段都由 FastAPI 返回 422。
"""

from typing import List, Literal, Tuple

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

    @field_validator("board_width", "board_height", "piece_width", "piece_height")
    @classmethod
    def _reject_bool(cls, v):
        # True/False 是 int 子类，会被静默当作 1/0；尺寸字段显式拒绝
        if isinstance(v, bool):
            raise ValueError("尺寸必须是整数，不能是布尔值")
        return v

    @field_validator("kerf_cells", mode="before")
    @classmethod
    def _reject_bool_kerf(cls, v):
        # Literal[0, 1] 会把 True/False 静默当作 1/0，须在 coercion 前拒绝
        if isinstance(v, bool):
            raise ValueError("kerf_cells 必须是 0 或 1，不能是布尔值")
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


class CutOut(BaseModel):
    order: int
    orientation: Literal["H", "V"]
    coord: int
    rect: RectOut


class SolveResponse(BaseModel):
    piece_count: int
    cut_count: int
    pieces: List[PieceOut]
    scraps: List[RectOut]
    kerfs: List[RectOut]
    cuts: List[CutOut]
    tree: dict
