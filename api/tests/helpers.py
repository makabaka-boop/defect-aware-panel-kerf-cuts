"""测试辅助：校验求解结果的结构、叶块划分与切割序列可执行性。

kerf_cells=1 时，每刀从被切矩形吃掉坐标处的一整行（H）或一整列（V）：
切割树 cut 节点、cuts 条目都带 ``kerf`` 矩形，废料清单中带 ``"kerf": True``
的条目即锯缝格带。锯缝可含瑕疵但永不成为成品；叶块 + 锯缝恰好平铺整板，
面积账可由结果复算。kerf_cells=0 时结果中不得出现任何 kerf 字段。
"""

from typing import List, Tuple


def rect_area(r) -> int:
    return r["width"] * r["height"]


def iter_leaves(node):
    if node["type"] in ("piece", "scrap"):
        yield node
    else:
        yield from iter_leaves(node["first"])
        yield from iter_leaves(node["second"])


def iter_cuts(node):
    if node["type"] == "cut":
        yield node
        yield from iter_cuts(node["first"])
        yield from iter_cuts(node["second"])


def validate_solution(result: dict, req, expect_piece_size=True):
    """通用合法性校验。"""
    W, H = req.board_width, req.board_height
    pw, ph = req.piece_width, req.piece_height
    kerf_cells = getattr(req, "kerf_cells", 0)
    defects = {tuple(d) for d in req.defects}

    # 1) 顶层统计一致
    assert result["piece_count"] == len(result["pieces"])
    assert result["cut_count"] == len(result["cuts"])

    leaves = list(iter_leaves(result["tree"]))
    cut_nodes = list(iter_cuts(result["tree"]))
    piece_leaves = [n for n in leaves if n["type"] == "piece"]
    scrap_leaves = [n for n in leaves if n["type"] == "scrap"]
    kerf_strips = [n["kerf"] for n in cut_nodes if "kerf" in n]

    if result["tree"]["type"] == "cut":
        assert result["tree"]["piece_count"] == result["piece_count"]
        assert result["tree"]["cut_count"] == result["cut_count"]
    else:
        assert result["piece_count"] == (1 if result["tree"]["type"] == "piece" else 0)
        assert result["cut_count"] == 0

    assert len(piece_leaves) == result["piece_count"]
    assert len(cut_nodes) == result["cut_count"]

    # 锯缝格带：每刀恰好一条（kerf=1），或完全没有（kerf=0，逐项不变）
    if kerf_cells:
        assert len(kerf_strips) == result["cut_count"]
        assert all("kerf" in c for c in result["cuts"])
    else:
        assert kerf_strips == []
        assert all("kerf" not in c for c in result["cuts"])
        assert all("kerf" not in s for s in result["scraps"])

    # 废料清单 = 废料叶 + 锯缝格带（锯缝带 "kerf": True 标记）
    expected_scraps = [n["rect"] for n in scrap_leaves]
    expected_scraps += [{**k, "kerf": True} for k in kerf_strips]
    assert {tuple(sorted(r.items())) for r in result["scraps"]} == {
        tuple(sorted(r.items())) for r in expected_scraps
    }
    piece_rects_tree = [n["rect"] for n in piece_leaves]
    assert len(piece_rects_tree) == len(result["pieces"])

    # 2) 叶块与锯缝格带平铺整块板材，互不重叠（面积账可复算）
    tiles = [n["rect"] for n in leaves] + kerf_strips
    covered = 0
    for r in tiles:
        assert 0 <= r["x"] and r["x"] + r["width"] <= W
        assert 0 <= r["y"] and r["y"] + r["height"] <= H
        covered += rect_area(r)
    assert covered == W * H
    # 无重叠：所有 cell 恰好属于一个叶块或一条锯缝
    cells = set()
    for r in tiles:
        for cx in range(r["x"], r["x"] + r["width"]):
            for cy in range(r["y"], r["y"] + r["height"]):
                assert (cx, cy) not in cells, "叶块/锯缝重叠"
                cells.add((cx, cy))
    assert cells == {(x, y) for x in range(W) for y in range(H)}

    # 3) 成品尺寸恰好等于目标件且无瑕疵；锯缝永不成为成品（结构性：锯缝不是叶块）
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

    # 4) 树结构与每刀一致（切分位置 = coord，锯缝 = coord 处整行/列，子块拼接回父块）
    def check_tree(node):
        if node["type"] in ("piece", "scrap"):
            return
        r, f, s = node["rect"], node["first"]["rect"], node["second"]["rect"]
        kc = kerf_cells
        if node["orientation"] == "H":
            assert f == {"x": r["x"], "y": r["y"], "width": r["width"], "height": node["coord"] - r["y"]}
            assert s == {
                "x": r["x"],
                "y": node["coord"] + kc,
                "width": r["width"],
                "height": r["y"] + r["height"] - node["coord"] - kc,
            }
            if kc:
                assert node["kerf"] == {
                    "x": r["x"],
                    "y": node["coord"],
                    "width": r["width"],
                    "height": 1,
                }
        else:
            assert f == {"x": r["x"], "y": r["y"], "width": node["coord"] - r["x"], "height": r["height"]}
            assert s == {
                "x": node["coord"] + kc,
                "y": r["y"],
                "width": r["x"] + r["width"] - node["coord"] - kc,
                "height": r["height"],
            }
            if kc:
                assert node["kerf"] == {
                    "x": node["coord"],
                    "y": r["y"],
                    "width": 1,
                    "height": r["height"],
                }
        if not kc:
            assert "kerf" not in node
        # 两侧子矩形都非空（kerf=1 时锯缝之外必须各剩至少一格）
        assert f["width"] >= 1 and f["height"] >= 1
        assert s["width"] >= 1 and s["height"] >= 1
        check_tree(node["first"])
        check_tree(node["second"])

    check_tree(result["tree"])

    # 5) cuts 是前序遍历：切某矩形时，该矩形必须作为现存整块可被贯穿
    #    （按顺序应用切割，记录现存块集合，每刀必须命中其中一块并将其替换；
    #    kerf=1 时锯缝格带被吃掉，不进入存活块）
    alive: List[dict] = [{"x": 0, "y": 0, "width": W, "height": H}]
    for cut in result["cuts"]:
        r = cut["rect"]
        assert r in alive, f"第 {cut['order']} 刀切的矩形不存在"
        alive.remove(r)
        kc = kerf_cells
        if cut["orientation"] == "H":
            assert r["y"] < cut["coord"] < r["y"] + r["height"] - kc
            k = cut["coord"] - r["y"]
            if kc:
                assert cut["kerf"] == {"x": r["x"], "y": cut["coord"], "width": r["width"], "height": 1}
            alive.append({"x": r["x"], "y": r["y"], "width": r["width"], "height": k})
            alive.append(
                {
                    "x": r["x"],
                    "y": cut["coord"] + kc,
                    "width": r["width"],
                    "height": r["height"] - k - kc,
                }
            )
        else:
            assert r["x"] < cut["coord"] < r["x"] + r["width"] - kc
            k = cut["coord"] - r["x"]
            if kc:
                assert cut["kerf"] == {"x": cut["coord"], "y": r["y"], "width": 1, "height": r["height"]}
            alive.append({"x": r["x"], "y": r["y"], "width": k, "height": r["height"]})
            alive.append(
                {
                    "x": cut["coord"] + kc,
                    "y": r["y"],
                    "width": r["width"] - k - kc,
                    "height": r["height"],
                }
            )
    # 切完后的存活块恰好是全部叶块（锯缝已被吃掉，不在其中）
    assert sorted((r["x"], r["y"], r["width"], r["height"]) for r in alive) == sorted(
        (n["rect"]["x"], n["rect"]["y"], n["rect"]["width"], n["rect"]["height"]) for n in leaves
    )
    # order 连续
    assert [c["order"] for c in result["cuts"]] == list(range(1, len(result["cuts"]) + 1))
