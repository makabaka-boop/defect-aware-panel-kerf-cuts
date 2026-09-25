# 板材直切排样 (Guillotine Nesting Workbench)

从空仓库建立的轻量全栈排样台：

- `web/` — React + Vite，用 SVG 编辑板宽高、点击格子标记瑕疵、发起求解并把最优切割树叠画在板材上。
- `api/` — FastAPI，在**全部 guillotine 直切树**中做动态规划：先最大化成品件数，再最小化切割次数，并按确定性规则打破并列。
- `docker-compose.yml` — 一条命令运行 `web`（nginx 托管静态资源并反代 `/api`）与 `api`（uvicorn）。

## 坐标约定

原点在板材左上角，x 向右、y 向下，均为整数网格单位。瑕疵格坐标为格子左上角 `(x, y)`，取值
`0 <= x < board_width`、`0 <= y < board_height`。目标件宽高 1–5；板材宽高 2–10。

叶块只有两种命运：

1. **成品**：尺寸恰好等于目标件（允许旋转时 `(ph, pw)` 也可），且块内不含任何瑕疵格；
2. **废料**：其余一律为废料。

每一刀必须沿整数网格线贯穿当前矩形（H：水平线；V：竖直线）。

## 锯缝（kerfCells）

实际锯机每下一刀会吃掉一条单位格锯缝。请求中的 `kerf_cells` 取 `0` 或 `1`
（缺省 `0`，即旧版的零宽切线，既有方案逐项不变）：

- `kerf_cells: 1` 时，每一刀从当前矩形移除**坐标 `coord` 起的一整行（H 切）或
  一整列（V 切）**单元格，留下的两侧子矩形都必须非空（因此宽或高 ≤ 2 的矩形
  在该方向无法再切）；
- 锯缝格带随刀消失：**可包含瑕疵，但永远不能成为成品**；
- 目标不变：仍先最大化成品件数、再最小化刀数，并列时沿用 H 先于 V、全局坐标
  较小优先、递归比较先上后下（V 切先左后右）子树的顺序。

响应中每处被吃掉的格带都显式标出：顶层 `kerfs` 清单（与 `cuts` 同序一一对应）、
切割树每个 cut 节点上的 `kerf` 字段，以及前端 SVG 中的斜纹格带。面积账可由结果
复算：`板面积 = Σ成品 + Σ废料 + Σ锯缝`。

## 运行

```bash
docker compose up --build
# 浏览器打开 http://localhost:8080
```

本地开发：

```bash
# 后端
cd api
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端（vite 已配置 /api 代理到 8000）
cd web
npm install
npm run dev
```

测试（小板枚举全部切树核对目标值）：

```bash
cd api
pip install -r requirements-dev.txt
pytest
```

## API

`POST /api/solve`

```json
{
  "board_width": 5,
  "board_height": 2,
  "piece_width": 2,
  "piece_height": 2,
  "allow_rotation": false,
  "defects": [[4, 0]],
  "kerf_cells": 1
}
```

返回 `piece_count`、`cut_count`、成品块 `pieces`、废料块 `scraps`、锯缝格带
`kerfs`、按实际下刀顺序排列的 `cuts`（含全局切割坐标与被切矩形），以及递归
`tree`（`kerf_cells=1` 时每个 cut 节点带 `kerf` 字段标出该刀吃掉的格带）。
板材/件尺寸越界、瑕疵越界或重复、`kerf_cells` 非 0/1、出现额外字段等一律返回 `422`。

## 最优性与并列规则

对每个子矩形记忆化搜索：叶块候选（成品/废料）与所有整数 H/V 切法候选中，按

1. 成品件数最多；
2. 切割次数最少；
3. 仍并列：H 切先于 V 切、较小的全局切割坐标优先，并递归比较先上后下（V 切时先左后右）的子树

取唯一最优树。搜索候选即按该次序枚举，配合稳定选择即可得到确定结果；切割顺序按切割树
前序遍历输出，是排样员可以逐刀执行的顺序。
