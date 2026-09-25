"""pytest：对小板枚举全部切树核对目标值，并校验结构、并列规则、锯缝语义与 API。"""

import pytest

from app.models import SolveRequest
from app.solver import Solver

from .bruteforce import optimal_objective
from .helpers import validate_solution


def run_solver(W, H, pw, ph, rotation, defects, kerf=0):
    return Solver(
        W, H, pw, ph, rotation, tuple(tuple(d) for d in defects), kerf_cells=kerf
    ).solve()


def make_req(W, H, pw, ph, rotation, defects, kerf=0):
    return SolveRequest(
        board_width=W,
        board_height=H,
        piece_width=pw,
        piece_height=ph,
        allow_rotation=rotation,
        defects=[tuple(d) for d in defects],
        kerf_cells=kerf,
    )


# ---------------- 小板暴力枚举核对（宽高 <= 4） ----------------

BOARDS = [(2, 2), (2, 3), (3, 2), (2, 4), (4, 2), (3, 3), (3, 4), (4, 3), (4, 4)]
PIECE_SIZES = [(1, 1), (1, 2), (2, 1), (2, 2), (3, 1), (1, 3), (3, 2), (2, 3), (3, 3), (4, 1), (1, 4), (4, 2), (2, 4), (4, 3), (3, 4), (4, 4)]


def fit_sizes(W, H):
    out = []
    for pw, ph in PIECE_SIZES:
        if pw <= W and ph <= H:
            out.append((pw, ph))
    return out


def defect_sets(W, H):
    """小板的代表性瑕疵集合；2x2 穷举全部子集。"""
    if (W, H) == (2, 2):
        cells = [(0, 0), (1, 0), (0, 1), (1, 1)]
        sets = []
        for mask in range(1 << len(cells)):
            sets.append([c for i, c in enumerate(cells) if mask & (1 << i)])
        return sets
    base = [
        [],
        [(0, 0)],
        [(W - 1, H - 1)],
        [(0, 0), (W - 1, H - 1)],
        [(W // 2, H // 2)],
        [(x, 0) for x in range(W)],  # 顶行全瑕
    ]
    return base


enumeration_cases = []
for (W, H) in BOARDS:
    for pw, ph in fit_sizes(W, H):
        for rotation in (False, True):
            for kerf in (0, 1):
                for defects in defect_sets(W, H):
                    enumeration_cases.append((W, H, pw, ph, rotation, kerf, defects))


@pytest.mark.parametrize("W,H,pw,ph,rotation,kerf,defects", enumeration_cases)
def test_optimal_matches_bruteforce(W, H, pw, ph, rotation, kerf, defects):
    result = run_solver(W, H, pw, ph, rotation, defects, kerf)
    bp, bc = optimal_objective(W, H, pw, ph, rotation, defects, kerf)
    assert (result["piece_count"], result["cut_count"]) == (bp, bc)
    req = make_req(W, H, pw, ph, rotation, defects, kerf)
    validate_solution(result, req)


# ---------------- 并列打破规则的结构性测试 ----------------

def test_h_before_v_on_tie():
    """4x2 板切 2x1 件（不旋转）：V1 方案与 H1 方案均为 4 件 3 刀，
    并列规则要求第一刀取 H（先于 V）。"""
    result = run_solver(4, 2, 2, 1, False, [])
    assert result["piece_count"] == 4
    assert result["cut_count"] == 3
    first = result["cuts"][0]
    assert first["orientation"] == "H"
    assert first["coord"] == 1


def test_smaller_coord_within_orientation_on_tie():
    """5x2 板切 2x2 件（不旋转）：2 件需两刀竖切，切成
    1 | 2 | 1 | 1（coord 1,3）与 2 | 1 | 2（coord 2,3）等布局目标值相同，
    并列规则取全局坐标最小者，故第一刀为 V@1。"""
    result = run_solver(5, 2, 2, 2, False, [])
    assert result["piece_count"] == 2
    assert result["cut_count"] == 2
    first = result["cuts"][0]
    assert first["orientation"] == "V"
    assert first["coord"] == 1
    xs = sorted((p["x"], p["y"], p["width"], p["height"]) for p in result["pieces"])
    assert xs == [(1, 0, 2, 2), (3, 0, 2, 2)]


def test_subtree_first_top_then_bottom():
    """H 切后上块先于下块被加工（cuts 前序：上块内的切序号在前）。"""
    result = run_solver(4, 2, 2, 1, False, [])
    # 第一刀 H@1；随后上条带(y=0) 的 V@2，再下条带(y=1) 的 V@2
    seq = [(c["rect"]["y"], c["orientation"], c["coord"]) for c in result["cuts"]]
    assert seq == [(0, "H", 1), (0, "V", 2), (1, "V", 2)]


def test_determinism():
    """相同输入多次求解，返回完全一致。"""
    import json

    r1 = run_solver(5, 4, 2, 3, True, [(0, 0), (4, 3), (2, 1)], kerf=1)
    r2 = run_solver(5, 4, 2, 3, True, [(0, 0), (4, 3), (2, 1)], kerf=1)
    assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)


# ---------------- 语义边界 ----------------

def test_piece_larger_than_board_is_all_scrap():
    result = run_solver(2, 2, 5, 5, False, [])
    assert result["piece_count"] == 0
    assert result["cut_count"] == 0
    assert len(result["scraps"]) == 1


def test_all_defected_cells_no_piece():
    defects = [(x, y) for x in range(3) for y in range(3)]
    result = run_solver(3, 3, 1, 1, False, defects)
    assert result["piece_count"] == 0
    # 整板废料 0 刀即最优
    assert result["cut_count"] == 0
    assert len(result["scraps"]) == 1


def test_rotation_enables_piece():
    # 3x2 板，件 2x3 不旋转放不下；旋转后等价 3x2，整板一件 0 刀
    no_rot = run_solver(3, 2, 2, 3, False, [])
    assert no_rot["piece_count"] == 0
    rot = run_solver(3, 2, 2, 3, True, [])
    assert rot["piece_count"] == 1
    assert rot["cut_count"] == 0
    assert rot["pieces"][0]["rotated"] is True


def test_defect_blocks_full_board_piece():
    # 2x2 整板本可作一件；一个瑕疵迫使切割，最多只能出 1 件 1x 废料布局
    clean = run_solver(2, 2, 2, 2, False, [])
    assert clean["piece_count"] == 1 and clean["cut_count"] == 0
    defected = run_solver(2, 2, 1, 1, False, [(1, 1)])
    assert defected["piece_count"] == 3
    assert defected["cut_count"] == 3


def test_max_board_performance():
    # 10x10 + 件 3x2 + 旋转 + 若干瑕疵：穷举状态很少，应立即返回且结构合法
    defects = [(0, 0), (9, 9), (4, 4), (5, 5), (2, 7)]
    for kerf in (0, 1):
        result = run_solver(10, 10, 3, 2, True, defects, kerf)
        req = make_req(10, 10, 3, 2, True, defects, kerf)
        validate_solution(result, req)
        assert result["piece_count"] >= 1


# ---------------- 锯缝（kerfCells=1） ----------------

def test_kerf_zero_output_unchanged():
    """kerfCells=0 的既有方案逐项不变：无 kerfs 清单、树节点不带 kerf 字段，
    其余字段与零宽切线时代的完整输出一致。"""
    result = run_solver(4, 2, 2, 1, False, [], kerf=0)
    assert result == {
        "piece_count": 4,
        "cut_count": 3,
        "pieces": [
            {"x": 0, "y": 0, "width": 2, "height": 1, "rotated": False},
            {"x": 2, "y": 0, "width": 2, "height": 1, "rotated": False},
            {"x": 0, "y": 1, "width": 2, "height": 1, "rotated": False},
            {"x": 2, "y": 1, "width": 2, "height": 1, "rotated": False},
        ],
        "scraps": [],
        "kerfs": [],
        "cuts": [
            {"order": 1, "orientation": "H", "coord": 1,
             "rect": {"x": 0, "y": 0, "width": 4, "height": 2}},
            {"order": 2, "orientation": "V", "coord": 2,
             "rect": {"x": 0, "y": 0, "width": 4, "height": 1}},
            {"order": 3, "orientation": "V", "coord": 2,
             "rect": {"x": 0, "y": 1, "width": 4, "height": 1}},
        ],
        "tree": {
            "type": "cut", "orientation": "H", "coord": 1,
            "rect": {"x": 0, "y": 0, "width": 4, "height": 2},
            "piece_count": 4, "cut_count": 3,
            "first": {
                "type": "cut", "orientation": "V", "coord": 2,
                "rect": {"x": 0, "y": 0, "width": 4, "height": 1},
                "piece_count": 2, "cut_count": 1,
                "first": {"type": "piece", "rect": {"x": 0, "y": 0, "width": 2, "height": 1}},
                "second": {"type": "piece", "rect": {"x": 2, "y": 0, "width": 2, "height": 1}},
            },
            "second": {
                "type": "cut", "orientation": "V", "coord": 2,
                "rect": {"x": 0, "y": 1, "width": 4, "height": 1},
                "piece_count": 2, "cut_count": 1,
                "first": {"type": "piece", "rect": {"x": 0, "y": 1, "width": 2, "height": 1}},
                "second": {"type": "piece", "rect": {"x": 2, "y": 1, "width": 2, "height": 1}},
            },
        },
    }


def test_kerf_consumes_full_column():
    """5x3 板切 2x3 件（不旋转）：kerf=1 时一刀 V@2 吃掉整列 x=2，
    左右各出一件；kerf=0 的零宽方案则需要两刀。"""
    r0 = run_solver(5, 3, 2, 3, False, [], kerf=0)
    assert (r0["piece_count"], r0["cut_count"]) == (2, 2)

    r1 = run_solver(5, 3, 2, 3, False, [], kerf=1)
    assert (r1["piece_count"], r1["cut_count"]) == (2, 1)
    assert r1["kerfs"] == [{"x": 2, "y": 0, "width": 1, "height": 3}]
    assert sorted((p["x"], p["y"]) for p in r1["pieces"]) == [(0, 0), (3, 0)]
    assert r1["scraps"] == []
    # 面积账可复算：板面积 15 = 成品 12 + 废料 0 + 锯缝 3
    area = lambda rs: sum(r["width"] * r["height"] for r in rs)
    assert area(r1["pieces"]) + area(r1["scraps"]) + area(r1["kerfs"]) == 15


def test_kerf_may_contain_defect():
    """锯缝可包含瑕疵：3x5 板切 3x2 件，瑕疵 (1,2) 正落在被吃掉的行带
    y=2 上，产出与无瑕疵时完全一致（2 件 1 刀）。"""
    clean = run_solver(3, 5, 3, 2, False, [], kerf=1)
    defected = run_solver(3, 5, 3, 2, False, [(1, 2)], kerf=1)
    assert (clean["piece_count"], clean["cut_count"]) == (2, 1)
    assert defected == clean
    band = {"x": 0, "y": 2, "width": 3, "height": 1}
    assert defected["kerfs"] == [band]
    # 瑕疵格 (1,2) 确在锯缝带内
    assert band["x"] <= 1 < band["x"] + band["width"]
    assert band["y"] <= 2 < band["y"] + band["height"]


def test_kerf_band_never_becomes_piece():
    """锯缝带尺寸恰好等于目标件也不能算成品：3x3 板切 1x3 件（不旋转），
    kerf=1 一刀 V@1 后锯缝列 (1,0,1,3) 与件同尺寸且无瑕疵，仍只得 2 件。"""
    r1 = run_solver(3, 3, 1, 3, False, [], kerf=1)
    assert (r1["piece_count"], r1["cut_count"]) == (2, 1)
    assert r1["kerfs"] == [{"x": 1, "y": 0, "width": 1, "height": 3}]
    assert sorted((p["x"], p["y"]) for p in r1["pieces"]) == [(0, 0), (2, 0)]
    assert r1["scraps"] == []
    # 对照：kerf=0 时三列全成品
    r0 = run_solver(3, 3, 1, 3, False, [], kerf=0)
    assert (r0["piece_count"], r0["cut_count"]) == (3, 2)


def test_kerf_small_rect_cannot_be_cut():
    """kerf=1 时宽或高 <= 2 的矩形在该方向无法再切（切后一侧必为空）：
    2x2 板切 1x1 件只能整板作废料，而 kerf=0 能出 4 件。"""
    r1 = run_solver(2, 2, 1, 1, False, [], kerf=1)
    assert (r1["piece_count"], r1["cut_count"]) == (0, 0)
    assert len(r1["scraps"]) == 1
    assert r1["kerfs"] == []

    r0 = run_solver(2, 2, 1, 1, False, [], kerf=0)
    assert (r0["piece_count"], r0["cut_count"]) == (4, 3)


def test_kerf_tie_break_smaller_coord():
    """4x2 板切 2x2 件 kerf=1：V@1（右块成件）与 V@2（左块成件）同为
    1 件 1 刀，并列仍取全局坐标较小的 V@1。"""
    r1 = run_solver(4, 2, 2, 2, False, [], kerf=1)
    assert (r1["piece_count"], r1["cut_count"]) == (1, 1)
    assert r1["cuts"][0]["orientation"] == "V"
    assert r1["cuts"][0]["coord"] == 1
    assert r1["pieces"] == [{"x": 2, "y": 0, "width": 2, "height": 2, "rotated": False}]
    assert r1["kerfs"] == [{"x": 1, "y": 0, "width": 1, "height": 2}]


def test_kerf_with_rotation():
    """3x4 板切 2x3 件 kerf=1：不旋转时任何切割都留不下 2 宽的子块（0 件）；
    允许旋转后 H@1 与 H@2 同为 1 件 1 刀，并列取坐标较小的 H@1，
    旋转件落在下块，锯缝为整行 y=1。"""
    no_rot = run_solver(3, 4, 2, 3, False, [], kerf=1)
    assert no_rot["piece_count"] == 0

    rot = run_solver(3, 4, 2, 3, True, [], kerf=1)
    assert (rot["piece_count"], rot["cut_count"]) == (1, 1)
    assert rot["cuts"][0]["orientation"] == "H"
    assert rot["cuts"][0]["coord"] == 1
    assert rot["pieces"] == [{"x": 0, "y": 2, "width": 3, "height": 2, "rotated": True}]
    assert rot["kerfs"] == [{"x": 0, "y": 1, "width": 3, "height": 1}]


# ---------------- API 层 ----------------

def _client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


VALID_BODY = {
    "board_width": 5,
    "board_height": 2,
    "piece_width": 2,
    "piece_height": 2,
    "allow_rotation": False,
    "defects": [[4, 0]],
}


def test_api_health():
    r = _client().get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_api_solve_ok():
    r = _client().post("/api/solve", json=VALID_BODY)
    assert r.status_code == 200
    data = r.json()
    assert data["piece_count"] == 2
    assert {"piece_count", "cut_count", "pieces", "scraps", "kerfs", "cuts", "tree"} <= set(data)


def test_api_kerf_defaults_to_zero():
    """不带 kerf_cells 的旧式请求：按 0 处理，结果与零宽切线一致。"""
    r = _client().post("/api/solve", json=VALID_BODY)
    assert r.status_code == 200
    data = r.json()
    assert data["kerfs"] == []
    assert (data["piece_count"], data["cut_count"]) == (2, 2)


def test_api_kerf_one():
    """5x2 板切 2x2 件、瑕疵 (4,0)，kerf_cells=1：V@2 吃掉整列 x=2，
    左块成一件，右块因瑕疵作废料。"""
    r = _client().post("/api/solve", json={**VALID_BODY, "kerf_cells": 1})
    assert r.status_code == 200
    data = r.json()
    assert (data["piece_count"], data["cut_count"]) == (1, 1)
    assert data["kerfs"] == [{"x": 2, "y": 0, "width": 1, "height": 2}]
    assert data["pieces"] == [{"x": 0, "y": 0, "width": 2, "height": 2, "rotated": False}]
    assert data["tree"]["kerf"] == {"x": 2, "y": 0, "width": 1, "height": 2}


@pytest.mark.parametrize(
    "patch",
    [
        {"board_width": 1},
        {"board_height": 11},
        {"piece_width": 0},
        {"piece_height": 6},
        {"defects": [[5, 0]]},          # 越界 x
        {"defects": [[4, 2]]},          # 越界 y
        {"defects": [[-1, 0]]},
        {"defects": [[4, 0], [4, 0]]},  # 重复
        {"defects": [[0]]},             # 非坐标对
        {"board_width": True},
        {"extra": 1},                   # 额外字段
        {"defects": "not-a-list"},
        {"kerf_cells": 2},              # 锯缝只能 0 或 1
        {"kerf_cells": -1},
        {"kerf_cells": True},           # 布尔不是合法锯缝
        {"kerf_cells": "1"},
    ],
)
def test_api_validation_422(patch):
    body = {**VALID_BODY, **patch}
    r = _client().post("/api/solve", json=body)
    assert r.status_code == 422
