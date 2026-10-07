"""Workstream C. FastAPI app. Routes are specified in contracts/api.md.

Modules:
  main.py      C1  app, lifespan (opens the store), /health
  models.py    C1  pydantic models mirroring contracts/
  search.py    C2  POST /search
  ask.py       C3  POST /ask (+ prompts/answer.md)
  documents.py C4  GET /documents, /documents/{id}, /documents/{id}/pages/{n}.png
  upload.py    C5  POST /documents/upload
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # TODO(C1): open SqliteStore(os.environ.get("INDEX_PATH", "data/index.sqlite"))
    # and attach it to app.state.store
    app.state.store = None
    yield


app = FastAPI(title="Rujuk API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


@app.get("/health")
def health():
    store = app.state.store
    docs, chunks = store.count() if store else (0, 0)
    return {"ok": True, "documents": docs, "chunks": chunks}
