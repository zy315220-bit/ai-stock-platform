from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.competition import router as competition_router
from app.api.stocks import router as stocks_router
from app.core.config import settings


app = FastAPI(
    title="AI 台股分析 API",
    version="0.1.0",
)

# =========================
# CORS
# =========================

origins = [
    origin.strip()
    for origin in settings.frontend_origin.split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# Router
# =========================

app.include_router(
    stocks_router,
    prefix="/api/stocks",
    tags=["stocks"],
)

app.include_router(
    competition_router,
    prefix="/api/competition",
    tags=["competition"],
)

# =========================
# API
# =========================

@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "AI 台股分析 API",
        "docs": "/docs",
    }


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "demo_mode": settings.use_demo_data,
    }
