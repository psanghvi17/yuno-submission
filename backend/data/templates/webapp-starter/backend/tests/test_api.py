import os
import sqlite3
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

import main


def test_health_and_booking_flow():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        os.environ["DATABASE_PATH"] = str(db_path)
        main.DB_PATH = db_path
        main.init_db()
        client = TestClient(main.app)

        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        response = client.post(
            "/api/bookings",
            json={
                "name": "Test User",
                "phone": "+1-555-0100",
                "date": "2026-06-01",
                "party_size": 2,
                "notes": "Demo booking",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["id"] >= 1

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
        conn.close()
        assert count == 1
