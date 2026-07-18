from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.routers import best_route  # noqa: E402  (must load .env first)

app = FastAPI(title="Route API")

app.include_router(best_route.router)

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
