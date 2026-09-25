"""测试辅助：校验求解结果的结构、叶块划分、锯缝格带与切割序列可执行性。"""

from typing import List, Tuple


def rect_area(r) -> int:
    return r["width"] * r["height"]


def iter_leaves(node):
    if node["type"] in ("piece", "scrap"):
        yield node
    else:
        yield from iter_leaves(node["first"])
        yield from iter_leaves(node["second"])


def iter_kerf_bands(node):
    """前序遍历切割节点，产出每刀吃掉的锯缝格带（kerfCells=0 时为空）。"""
    if node["type"] == "cut":
        if "kerf" in node:
            yield node["kerf"]
        yield from iter_kerf_bands(node["first"])
        yield from iter_kerf_bands(node["second"])


def expected_kerf(cut_rect, orientation, coord):
    """一刀在 cut_rect 上于 coord 处下刀时应吃掉的格带。"""
    if orientation == "H":
        return {
            "x": cut_rect["x"],
            "y": coord,
            "width": cut_rect["width"],
            "height": 1,
        }
    return {
        "x": coord,
        "y": cut_rect["y"],
        "width": 1,
        "height": cut_rect["height"],
    }


def validate_solution(result: dict, req, expect_piece_size=True):
    """通用合法性校验（按 req.kerf_cells 分别校验零宽切线与整格锯缝两种语义）。"""
    W, H = req.board_width, req.board_height
    pw, ph = req.piece_width, req.piece_height
    kerf = req.kerf_cells
    defects = {tuple(d) for d in req.defects}

    # 1) 顶层统计一致；锯缝清单与切割一一对应
    assert result["piece_count"] == len(result["pieces"])
    assert result["cut_count"] == len(result["cuts"])
    if kerf:
        assert len(result["kerfs"]) == result["cut_count"]
    else:
        assert result["kerfs"] == []

    leaves = list(iter_leaves(result["tree"]))
    piece_leaves = [n for n in leaves if n["type"] == "piece"]
    scrap_leaves = [n for n in leaves if n["type"] == "scrap"]
    tree_bands = list(iter_kerf_bands(result["tree"]))

    if result["tree"]["type"] == "cut":
        assert result["tree"]["piece_count"] == result["piece_count"]
        assert result["tree"]["cut_count"] == result["cut_count"]
    else:
        assert result["piece_count"] == (1 if result["tree"]["type"] == "piece" else 0)
        assert result["cut_count"] == 0

    assert len(piece_leaves) == result["piece_count"]
    assert {tuple(sorted(r.items())) for r in result["scraps"]} == {
        tuple(sorted(n["rect"].items())) for n in scrap_leaves
    }
    piece_rects_tree = [n["rect"] for n in piece_leaves]
    assert len(piece_rects_tree) == len(result["pieces"])
    # 切割树中显式标出的格带与顶层 kerfs 清单（前序）逐项一致
    assert tree_bands == result["kerfs"]

    # 2) 叶块 + 锯缝格带平铺整块板材，互不重叠（面积账可复算：
    #    板面积 = 成品 + 废料 + 锯缝）
    covered = sum(rect_area(n["rect"]) for n in leaves) + sum(
        rect_area(b) for b in result["kerfs"]
    )
    assert covered == W * H
    cells = set()
    for r in [n["rect"] for n in leaves] + result["kerfs"]:
        assert 0 <= r["x"] and r["x"] + r["width"] <= W
        assert 0 <= r["y"] and r["y"] + r["height"] <= H
        for cx in range(r["x"], r["x"] + r["width"]):
            for cy in range(r["y"], r["y"] + r["height"]):
                assert (cx, cy) not in cells, "叶块/锯缝重叠"
                cells.add((cx, cy))
    assert cells == {(x, y) for x in range(W) for y in range(H)}

    # 3) 成品尺寸恰好等于目标件且无瑕疵；锯缝格带永不成为成品
    allowed = {(pw, ph)}
    if req.allow_rotation:
        allowed.add((ph, pw))
    for r in result["pieces"]:
        if expect_piece_size:
            assert (r["width"], r["height"]) in allowed
            assert r["rotated"] == ((r["width"], r["height"]) != (pw, ph))
            for dx, dy in defects:
                assert not (
                    r["x"] <= dx < r["x"] + r["width"]
                    and r["y"] <= dy < r["y"] + r["height"]
                ), "成品含瑕疵"
    # 锯缝可含瑕疵（不加限制），但不得与任何成品叶重叠 —— 由上方无重叠平铺保证

    # 4) 树结构与每刀一致（切分位置 = coord，锯缝从 coord 起被吃掉，
    #    子块拼接回父块需跳过格带；两侧子矩形都必须非空）
    def check_tree(node):
        if node["type"] in ("piece", "scrap"):
            return
        r, f, s = node["rect"], node["first"]["rect"], node["second"]["rect"]
        if node["orientation"] == "H":
            assert f == {"x": r["x"], "y": r["y"], "width": r["width"], "height": node["coord"] - r["y"]}
            assert s == {
                "x": r["x"],
                "y": node["coord"] + kerf,
                "width": r["width"],
                "height": r["y"] + r["height"] - node["coord"] - kerf,
            }
        else:
            assert f == {"x": r["x"], "y": r["y"], "width": node["coord"] - r["x"], "height": r["height"]}
            assert s == {
                "x": node["coord"] + kerf,
                "y": r["y"],
                "width": r["x"] + r["width"] - node["coord"] - kerf,
                "height": r["height"],
            }
        assert f["width"] > 0 and f["height"] > 0, "切割后一侧子矩形为空"
        assert s["width"] > 0 and s["height"] > 0, "切割后一侧子矩形为空"
        if kerf:
            assert node.get("kerf") == expected_kerf(r, node["orientation"], node["coord"])
        else:
            assert "kerf" not in node, "kerfCells=0 的树不应带锯缝字段"
        check_tree(node["first"])
        check_tree(node["second"])

    check_tree(result["tree"])

    # 5) cuts 是前序遍历：切某矩形时，该矩形必须作为现存整块可被贯穿
    #    （按顺序应用切割，记录现存块集合，每刀必须命中其中一块并将其替换；
    #    锯缝格带随刀消失，不进入存活块集合）
    alive: List[dict] = [{"x": 0, "y": 0, "width": W, "height": H}]
    for i, cut in enumerate(result["cuts"]):
        r = cut["rect"]
        assert r in alive, f"第 {cut['order']} 刀切的矩形不存在"
        alive.remove(r)
        if cut["orientation"] == "H":
            assert r["y"] < cut["coord"] and cut["coord"] + kerf < r["y"] + r["height"]
            k = cut["coord"] - r["y"]
            alive.append({"x": r["x"], "y": r["y"], "width": r["width"], "height": k})
            alive.append(
                {
                    "x": r["x"],
                    "y": cut["coord"] + kerf,
                    "width": r["width"],
                    "height": r["height"] - k - kerf,
                }
            )
        else:
            assert r["x"] < cut["coord"] and cut["coord"] + kerf < r["x"] + r["width"]
            k = cut["coord"] - r["x"]
            alive.append({"x": r["x"], "y": r["y"], "width": k, "height": r["height"]})
            alive.append(
                {
                    "x": cut["coord"] + kerf,
                    "y": r["y"],
                    "width": r["width"] - k - kerf,
                    "height": r["height"],
                }
            )
        if kerf:
            # 顶层 kerfs 与 cuts 同序对应，且几何上正是该刀吃掉的格带
            assert result["kerfs"][i] == expected_kerf(r, cut["orientation"], cut["coord"])
    # 切完后的存活块恰好是全部叶块（锯缝不在其中）
    assert sorted((r["x"], r["y"], r["width"], r["height"]) for r in alive) == sorted(
        (n["rect"]["x"], n["rect"]["y"], n["rect"]["width"], n["rect"]["height"]) for n in leaves
    )
    # order 连续
    assert [c["order"] for c in result["cuts"]] == list(range(1, len(result["cuts"]) + 1))
