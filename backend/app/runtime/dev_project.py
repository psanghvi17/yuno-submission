"""Generated dev-project paths and starter template helpers."""

from __future__ import annotations

import shutil
from pathlib import Path

from app.runtime.run_context import require_run_id

# Parents: runtime -> app -> backend (repo root where data/ and app/ live).
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = _BACKEND_ROOT / "data"
TEMPLATE_DIR = DATA_DIR / "templates" / "webapp-starter"
GENERATED_ROOT = DATA_DIR / "generated_projects"


def project_dir(run_id: int | None = None) -> Path:
    rid = run_id if run_id is not None else require_run_id()
    return GENERATED_ROOT / str(rid)


def ensure_project_from_template(run_id: int | None = None) -> Path:
    target = project_dir(run_id)
    if target.exists() and any(target.iterdir()):
        return target
    if not TEMPLATE_DIR.is_dir():
        raise FileNotFoundError(f"Starter template missing: {TEMPLATE_DIR}")
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(TEMPLATE_DIR, target, dirs_exist_ok=True)
    return target


def safe_project_path(relative_path: str, run_id: int | None = None) -> Path:
    rel = Path(relative_path.strip().lstrip("/\\"))
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("Path must stay inside the project directory")
    root = project_dir(run_id).resolve()
    target = (root / rel).resolve()
    if root not in target.parents and target != root:
        raise ValueError("Path must stay inside the project directory")
    return target


def list_project_files(run_id: int | None = None) -> list[str]:
    root = project_dir(run_id)
    if not root.is_dir():
        return []
    files: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            files.append(str(path.relative_to(root)).replace("\\", "/"))
    return files
