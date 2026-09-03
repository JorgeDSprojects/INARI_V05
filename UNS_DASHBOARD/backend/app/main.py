from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import create_tables
from app.routers import dashboards, charts, history, signals

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield


app = FastAPI(
    title="UNS Dashboard",
    description="Real-time SCADA dashboard authoring and viewing",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboards.router)
app.include_router(charts.router)
app.include_router(history.router)
app.include_router(signals.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
