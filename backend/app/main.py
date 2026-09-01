from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import create_tables
from app.routers import enterprises, sites, areas, lines, cells, assets, tree, brokers
from app.services.mqtt_service import disconnect_mqtt

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield
    disconnect_mqtt()


app = FastAPI(
    title="UNS Manager",
    description="Unified Namespace Manager — ISA-95 hierarchy + EMQX integration",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(enterprises.router)
app.include_router(sites.router)
app.include_router(areas.router)
app.include_router(lines.router)
app.include_router(cells.router)
app.include_router(assets.router)
app.include_router(tree.router)
app.include_router(brokers.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
