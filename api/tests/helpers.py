"""测试辅助：校验求解结果的结构、叶块划分与切割序列可执行性。"""

from typing import List, Tuple


def rect_area(r) -> int:
    return r["width"] * r["height"]


def iter_leaves(node):
    if node["type"] in ("piece", "scrap"):
        yield node
    else:
        yield from iter_leaves(node["first"])
        yield from iter_leaves(node["second"])


def validate_solution(result: dict, req, expect_piece_size=True):
    """通用合法性校验。"""
    W, H = req.board_width, req.board_height
    pw, ph = req.piece_width, req.piece_height
    defects = {tuple(d) for d in req.defects}

    # 1) 顶层统计一致
    assert result["piece_count"] == len(result["pieces"])
    assert result["cut_count"] == len(result["cuts"])

    leaves = list(iter_leaves(result["tree"]))
    piece_leaves = [n for n in leaves if n["type"] == "piece"]
    scrap_leaves = [n for n in leaves if n["type"] == "scrap"]

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

    # 2) 叶块平铺整块板材，互不重叠
    covered = 0
    for n in leaves:
        r = n["rect"]
        assert 0 <= r["x"] and r["x"] + r["width"] <= W
        assert 0 <= r["y"] and r["y"] + r["height"] <= H
        covered += rect_area(r)
    assert covered == W * H
    # 无重叠：所有 cell 恰好属于一个叶块
    cells = set()
    for n in leaves:
        r = n["rect"]
        for cx in range(r["x"], r["x"] + r["width"]):
            for cy in range(r["y"], r["y"] + r["height"]):
                assert (cx, cy) not in cells, "叶块重叠"
                cells.add((cx, cy))
    assert cells == {(x, y) for x in range(W) for y in range(H)}

    # 3) 成品尺寸恰好等于目标件且无瑕疵
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

    # 4) 树结构与每刀一致（切分位置 = coord，子块拼接回父块）
    def check_tree(node):
        if node["type"] in ("piece", "scrap"):
            return
        r, f, s = node["rect"], node["first"]["rect"], node["second"]["rect"]
        if node["orientation"] == "H":
            assert f == {"x": r["x"], "y": r["y"], "width": r["width"], "height": node["coord"] - r["y"]}
            assert s == {
                "x": r["x"],
                "y": node["coord"],
                "width": r["width"],
                "height": r["y"] + r["height"] - node["coord"],
            }
        else:
            assert f == {"x": r["x"], "y": r["y"], "width": node["coord"] - r["x"], "height": r["height"]}
            assert s == {
                "x": node["coord"],
                "y": r["y"],
                "width": r["x"] + r["width"] - node["coord"],
                "height": r["height"],
            }
        check_tree(node["first"])
        check_tree(node["second"])

    check_tree(result["tree"])

    # 5) cuts 是前序遍历：切某矩形时，该矩形必须作为现存整块可被贯穿
    #    （按顺序应用切割，记录现存块集合，每刀必须命中其中一块并将其替换）
    alive: List[dict] = [{"x": 0, "y": 0, "width": W, "height": H}]
    for cut in result["cuts"]:
        r = cut["rect"]
        assert r in alive, f"第 {cut['order']} 刀切的矩形不存在"
        alive.remove(r)
        if cut["orientation"] == "H":
            assert r["y"] < cut["coord"] < r["y"] + r["height"]
            k = cut["coord"] - r["y"]
            alive.append({"x": r["x"], "y": r["y"], "width": r["width"], "height": k})
            alive.append(
                {"x": r["x"], "y": cut["coord"], "width": r["width"], "height": r["height"] - k}
            )
        else:
            assert r["x"] < cut["coord"] < r["x"] + r["width"]
            k = cut["coord"] - r["x"]
            alive.append({"x": r["x"], "y": r["y"], "width": k, "height": r["height"]})
            alive.append(
                {"x": cut["coord"], "y": r["y"], "width": r["width"] - k, "height": r["height"]}
            )
    # 切完后的存活块恰好是全部叶块
    assert sorted((r["x"], r["y"], r["width"], r["height"]) for r in alive) == sorted(
        (n["rect"]["x"], n["rect"]["y"], n["rect"]["width"], n["rect"]["height"]) for n in leaves
    )
    # order 连续
    assert [c["order"] for c in result["cuts"]] == list(range(1, len(result["cuts"]) + 1))
