import { useState } from "react";

// SVG 每格像素
const CELL = 56;

function NumberField({ label, value, min, max, onChange }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </label>
  );
}

export default function App() {
  const [boardW, setBoardW] = useState(5);
  const [boardH, setBoardH] = useState(2);
  const [pieceW, setPieceW] = useState(2);
  const [pieceH, setPieceH] = useState(2);
  const [allowRotation, setAllowRotation] = useState(false);
  const [defects, setDefects] = useState([{ x: 4, y: 0 }]);
  const [solution, setSolution] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  // 板尺寸变化后，清掉越界瑕疵与旧方案
  function resizeBoard(nw, nh) {
    setBoardW(nw);
    setBoardH(nh);
    setDefects((ds) => ds.filter((d) => d.x < nw && d.y < nh));
    setSolution(null);
    setError(null);
  }

  function toggleCell(x, y) {
    setDefects((ds) => {
      const exists = ds.some((d) => d.x === x && d.y === y);
      return exists
        ? ds.filter((d) => !(d.x === x && d.y === y))
        : [...ds, { x, y }];
    });
    setSolution(null);
    setError(null);
  }

  async function solve() {
    setLoading(true);
    setError(null);
    setSolution(null);
    try {
      const resp = await fetch("/api/solve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          board_width: boardW,
          board_height: boardH,
          piece_width: pieceW,
          piece_height: pieceH,
          allow_rotation: allowRotation,
          defects: defects.map((d) => [d.x, d.y]),
        }),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        const msg =
          data?.detail?.map?.((d) => `${d.loc.slice(1).join(".")}: ${d.msg}`) ||
          data?.detail ||
          `请求失败 (${resp.status})`;
        throw new Error(Array.isArray(msg) ? msg.join("\n") : String(msg));
      }
      setSolution(await resp.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  const svgW = boardW * CELL;
  const svgH = boardH * CELL;
  const cuts = solution?.cuts ?? [];

  return (
    <div className="app">
      <header>
        <h1>板材直切排样台</h1>
        <p>
          点击格子标记/取消瑕疵，求解后在全部直切树中取成品最多、刀数最少的方案，
          红线按编号顺序即可逐刀下切。
        </p>
      </header>

      <main>
        <section className="panel">
          <div className="form">
            <NumberField label="板宽 (2–10)" value={boardW} min={2} max={10}
              onChange={(v) => resizeBoard(v, boardH)} />
            <NumberField label="板高 (2–10)" value={boardH} min={2} max={10}
              onChange={(v) => resizeBoard(boardW, v)} />
            <NumberField label="件宽 (1–5)" value={pieceW} min={1} max={5}
              onChange={(v) => { setPieceW(v); setSolution(null); }} />
            <NumberField label="件高 (1–5)" value={pieceH} min={1} max={5}
              onChange={(v) => { setPieceH(v); setSolution(null); }} />
            <label className="field checkbox">
              <input
                type="checkbox"
                checked={allowRotation}
                onChange={(e) => { setAllowRotation(e.target.checked); setSolution(null); }}
              />
              <span>允许旋转 90°</span>
            </label>
            <button onClick={solve} disabled={loading}>
              {loading ? "求解中…" : "求解"}
            </button>
          </div>

          <div className="board-scroll">
            <svg
              width={svgW}
              height={svgH}
              viewBox={`0 0 ${svgW} ${svgH}`}
              className="board"
              role="img"
              aria-label="板材编辑与排样结果"
            >
              {/* 板材底 */}
              <rect x={0} y={0} width={svgW} height={svgH} className="board-bg" />

              {/* 废料块（叠画层 1） */}
              {solution?.scraps.map((r, i) => (
                <rect
                  key={`scrap-${i}`}
                  x={r.x * CELL}
                  y={r.y * CELL}
                  width={r.width * CELL}
                  height={r.height * CELL}
                  className="scrap"
                />
              ))}

              {/* 成品块（叠画层 2） */}
              {solution?.pieces.map((r, i) => (
                <g key={`piece-${i}`}>
                  <rect
                    x={r.x * CELL}
                    y={r.y * CELL}
                    width={r.width * CELL}
                    height={r.height * CELL}
                    className="piece"
                  />
                  <text
                    x={(r.x + r.width / 2) * CELL}
                    y={(r.y + r.height / 2) * CELL}
                    className="piece-label"
                    textAnchor="middle"
                    dominantBaseline="central"
                  >
                    {r.width}×{r.height}
                    {r.rotated ? " ↻" : ""}
                  </text>
                </g>
              ))}

              {/* 网格线（叠画层 3） */}
              {Array.from({ length: boardW + 1 }, (_, i) => (
                <line key={`gv-${i}`} x1={i * CELL} y1={0} x2={i * CELL} y2={svgH}
                  className="grid" />
              ))}
              {Array.from({ length: boardH + 1 }, (_, i) => (
                <line key={`gh-${i}`} x1={0} y1={i * CELL} x2={svgW} y2={i * CELL}
                  className="grid" />
              ))}

              {/* 瑕疵格（叠画层 4，编辑层，可点） */}
              {Array.from({ length: boardH }, (_, y) =>
                Array.from({ length: boardW }, (_, x) => {
                  const defected = defects.some((d) => d.x === x && d.y === y);
                  return (
                    <g
                      key={`cell-${x}-${y}`}
                      className="cell"
                      onClick={() => toggleCell(x, y)}
                    >
                      <rect
                        x={x * CELL}
                        y={y * CELL}
                        width={CELL}
                        height={CELL}
                        className={defected ? "defect" : "cell-hit"}
                      />
                      {defected && (
                        <text
                          x={(x + 0.5) * CELL}
                          y={(y + 0.5) * CELL}
                          className="defect-x"
                          textAnchor="middle"
                          dominantBaseline="central"
                        >
                          ✕
                        </text>
                      )}
                    </g>
                  );
                })
              )}

              {/* 切线（叠画层 5，贯穿当前矩形，带顺序号） */}
              {cuts.map((c) => {
                const r = c.rect;
                const x1 = c.orientation === "H" ? r.x * CELL : c.coord * CELL;
                const y1 = c.orientation === "H" ? c.coord * CELL : r.y * CELL;
                const x2 =
                  c.orientation === "H"
                    ? (r.x + r.width) * CELL
                    : c.coord * CELL;
                const y2 =
                  c.orientation === "H"
                    ? c.coord * CELL
                    : (r.y + r.height) * CELL;
                return (
                  <g key={`cut-${c.order}`}>
                    <line x1={x1} y1={y1} x2={x2} y2={y2} className="cut-line" />
                    <circle
                      cx={c.orientation === "H" ? r.x * CELL + 14 : c.coord * CELL}
                      cy={c.orientation === "H" ? c.coord * CELL : r.y * CELL + 14}
                      r={11}
                      className="cut-badge"
                    />
                    <text
                      x={c.orientation === "H" ? r.x * CELL + 14 : c.coord * CELL}
                      y={c.orientation === "H" ? c.coord * CELL : r.y * CELL + 14}
                      className="cut-num"
                      textAnchor="middle"
                      dominantBaseline="central"
                    >
                      {c.order}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>

          <div className="legend">
            <span><i className="sw piece" />成品</span>
            <span><i className="sw scrap" />废料</span>
            <span><i className="sw defect" />瑕疵格（点击切换）</span>
            <span><i className="sw cut" />切割线（编号即下刀顺序）</span>
          </div>
        </section>

        <aside className="panel side">
          {error && <pre className="error">{error}</pre>}

          {solution && (
            <>
              <div className="stats">
                <div><strong>{solution.piece_count}</strong><span>成品件数</span></div>
                <div><strong>{solution.cut_count}</strong><span>切割次数</span></div>
              </div>

              <h2>下刀顺序</h2>
              {solution.cuts.length === 0 && (
                <p className="muted">无需切割：整板直接作为{solution.piece_count ? "成品" : "废料"}。</p>
              )}
              <ol className="cuts">
                {solution.cuts.map((c) => (
                  <li key={c.order}>
                    第 {c.order} 刀：
                    {c.orientation === "H" ? "水平切" : "竖直切"}，
                    全局坐标 {c.orientation === "H" ? "y" : "x"} = {c.coord}
                    <span className="muted">
                      {" "}（切 {c.rect.width}×{c.rect.height} 块于 (
                      {c.rect.x}, {c.rect.y})）
                    </span>
                  </li>
                ))}
              </ol>

              <h2>成品坐标</h2>
              <ul className="coords">
                {solution.pieces.map((p, i) => (
                  <li key={i}>
                    ({p.x}, {p.y}) {p.width}×{p.height}
                    {p.rotated ? "（旋转）" : ""}
                  </li>
                ))}
                {solution.pieces.length === 0 && <li className="muted">无成品</li>}
              </ul>
            </>
          )}

          {!solution && !error && (
            <p className="muted hint">
              编辑板材参数与瑕疵格后点击「求解」。目标件含瑕疵格的叶块只能作废料，
              普通面积除法会高估件数。
            </p>
          )}
        </aside>
      </main>
    </div>
  );
}
