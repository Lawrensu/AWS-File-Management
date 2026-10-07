"""Workstream C. FastAPI app. Routes are specified in contracts/api.md.

Modules:
  main.py      C1  app, lifespan (opens the store), /health, error shape
  models.py    C1  pydantic models mirroring contracts/
  deps.py      C   store dependency, filters, query embedding
  search.py    C2  POST /search
  ask.py       C3  POST /ask (+ prompts/answer.md)
  documents.py C4  GET /documents, /documents/{id}, /documents/{id}/pages/{n}.png
  upload.py    C5  POST /documents/upload
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api import ask, documents, search, upload
from api.models import HealthResponse

load_dotenv()
log = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    path = os.environ.get("INDEX_PATH", "data/index.sqlite")
    try:
        from engine.index.store import SqliteStore

        app.state.store = SqliteStore(path)
        log.info("index opened at %s", path)
    except Exception as exc:  # noqa: BLE001 - keep the API up for the UI team
        from engine.testing import FakeStore

        log.warning("SqliteStore(%s) failed (%s); using an empty FakeStore", path, exc)
        app.state.store = FakeStore()
    yield
    close = getattr(app.state.store, "close", None)
    if close is not None:
        close()


app = FastAPI(title="Rujuk API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Rujuk-Provider", "X-Rujuk-Model"],
)


@app.exception_handler(StarletteHTTPException)
async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    where = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
    message = f"{where}: {first.get('msg', 'invalid request')}" if where else "invalid request"
    return JSONResponse(status_code=422, content={"error": message})


@app.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    store = getattr(request.app.state, "store", None)
    docs, chunks = store.count() if store else (0, 0)
    return HealthResponse(ok=True, documents=docs, chunks=chunks)


app.include_router(search.router)
app.include_router(ask.router)
app.include_router(documents.router)
app.include_router(upload.router)
