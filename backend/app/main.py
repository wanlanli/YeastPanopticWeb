from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import annotations, projects, quantification, series
from app.db import init_db

app = FastAPI(title="YeastPanopticWeb API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


app.include_router(projects.router)
app.include_router(series.router)
app.include_router(annotations.router)
app.include_router(quantification.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
