from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.auth import router as auth_router
from backend.app.api.gate import router as gate_router
from backend.app.api.routes.vehicle_import import router as vehicle_import_router
from backend.app.api.routes.vehicles import router as vehicle_router

app = FastAPI(
    title="National Intelligent Platform",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8080",
        "http://localhost:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
FRONTEND_FILE = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "index.html"
)

@app.get("/", include_in_schema=False)
def frontend():
    return FileResponse(FRONTEND_FILE)

app.include_router(auth_router)
app.include_router(gate_router)
app.include_router(vehicle_import_router)
app.include_router(vehicle_router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "national-intelligent-platform",
    }
