"""FastAPI 入口：POST /api/solve 返回最优直切排样方案。"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .models import SolveRequest, SolveResponse
from .solver import Solver

app = FastAPI(title="Guillotine Nesting API", version="1.0.0")

# 本地 vite dev server (5173) 直连 api (8000) 时需要；容器内经 nginx 同源反代
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/solve", response_model=SolveResponse)
def solve(req: SolveRequest):
    solver = Solver(
        board_width=req.board_width,
        board_height=req.board_height,
        piece_width=req.piece_width,
        piece_height=req.piece_height,
        allow_rotation=req.allow_rotation,
        defects=req.defects,
        kerf_cells=req.kerf_cells,
    )
    return solver.solve()
