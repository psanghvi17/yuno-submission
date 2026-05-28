"""Generic webapp scaffold — business content is filled in by the dev pipeline agents."""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

DB_PATH = Path(os.getenv("DATABASE_PATH", "app.db"))
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="Webapp API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class BookingCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=5, max_length=40)
    date: str = Field(min_length=4, max_length=32)
    party_size: int = Field(default=1, ge=1, le=50)
    notes: str = Field(default="", max_length=500)


@contextmanager
def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                date TEXT NOT NULL,
                party_size INTEGER NOT NULL DEFAULT 1,
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/info")
def info() -> dict:
    """Placeholder site metadata — agents replace with business-specific content."""
    return {
        "business_name": "Your Business",
        "tagline": "Welcome",
        "highlights": [],
    }


# RFC/rest convention + scaffold tests/code reviewer expect 201 for POST creates — not FastAPI default 200.
@app.post("/api/bookings", status_code=201)
def create_booking(payload: BookingCreate) -> dict:
    created_at = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO bookings (name, phone, date, party_size, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                payload.name.strip(),
                payload.phone.strip(),
                payload.date.strip(),
                payload.party_size,
                payload.notes.strip(),
                created_at,
            ),
        )
        booking_id = cursor.lastrowid
    return {
        "id": booking_id,
        "message": "Booking saved",
        "booking": {**payload.model_dump(), "id": booking_id},
    }


@app.get("/api/bookings")
def list_bookings() -> dict:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, name, phone, date, party_size, notes, created_at "
            "FROM bookings ORDER BY id DESC LIMIT 50"
        ).fetchall()
    return {"bookings": [dict(row) for row in rows]}


if FRONTEND_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")
