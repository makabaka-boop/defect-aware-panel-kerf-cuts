"""pytest：对小板枚举全部切树核对目标值，并校验结构、并列规则与 API。"""

import pytest

from app.models import SolveRequest
from app.solver import Solver

from .bruteforce import optimal_objective
from .helpers import validate_solution


def run_solver(W, H, pw, ph, rotation, defects):
    return Solver(W, H, pw, ph, rotation, tuple(tuple(d) for d in defects)).solve()


def make_req(W, H, pw, ph, rotation, defects):
    return SolveRequest(
        board_width=W,
        board_height=H,
        piece_width=pw,
        piece_height=ph,
        allow_rotation=rotation,
        defects=[tuple(d) for d in defects],
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
            for defects in defect_sets(W, H):
                enumeration_cases.append((W, H, pw, ph, rotation, defects))


@pytest.mark.parametrize("W,H,pw,ph,rotation,defects", enumeration_cases)
def test_optimal_matches_bruteforce(W, H, pw, ph, rotation, defects):
    result = run_solver(W, H, pw, ph, rotation, defects)
    bp, bc = optimal_objective(W, H, pw, ph, rotation, defects)
    assert (result["piece_count"], result["cut_count"]) == (bp, bc)
    req = make_req(W, H, pw, ph, rotation, defects)
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

    r1 = run_solver(5, 4, 2, 3, True, [(0, 0), (4, 3), (2, 1)])
    r2 = run_solver(5, 4, 2, 3, True, [(0, 0), (4, 3), (2, 1)])
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
    result = run_solver(10, 10, 3, 2, True, defects)
    req = make_req(10, 10, 3, 2, True, defects)
    validate_solution(result, req)
    assert result["piece_count"] >= 1


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
    assert {"piece_count", "cut_count", "pieces", "scraps", "cuts", "tree"} <= set(data)


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
    ],
)
def test_api_validation_422(patch):
    body = {**VALID_BODY, **patch}
    r = _client().post("/api/solve", json=body)
    assert r.status_code == 422
