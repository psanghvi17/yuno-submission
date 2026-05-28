"""Dev pipeline and deployment tools."""

from __future__ import annotations

import json
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import httpx
from langchain_core.tools import tool

from app.config import get_settings
from app.runtime.dev_project import (
    ensure_project_from_template,
    list_project_files,
    project_dir,
    safe_project_path,
)
from app.runtime.run_context import require_run_id

_HTTP_TIMEOUT = 30.0
_DO_POLL_INTERVAL = 15.0
_DO_MAX_WAIT = 1200.0  # docker build on a 1GB droplet often exceeds 10 minutes

_CANONICAL_DOCKER_COMPOSE = """
services:
  api:
    build:
      context: .
      dockerfile: backend/Dockerfile
    ports:
      - "8080:8080"
    volumes:
      - app_data:/data

volumes:
  app_data:
""".strip()

_CANONICAL_BACKEND_DOCKERFILE = """
FROM python:3.12-slim

WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY frontend/ ./frontend/
ENV DATABASE_PATH=/data/app.db
EXPOSE 8080
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
""".strip()

_PREMIUM_THEME_CSS = """
:root { --primary: #fea116; --dark: #0f172b; --muted: #666; }
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: "Heebo", "Segoe UI", Tahoma, sans-serif;
  color: #0f172b;
  background: #f7f8fc;
}
.hero {
  background:
    linear-gradient(140deg, rgba(15, 23, 43, 0.92), rgba(15, 23, 43, 0.92)),
    radial-gradient(circle at right, rgba(254, 161, 22, 0.35), transparent 50%);
  color: #fff;
  padding: 1.2rem 0 3.8rem;
}
.topbar {
  width: min(1120px, 92%);
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}
.brand {
  color: var(--primary);
  font-weight: 800;
  font-size: 2rem;
  text-decoration: none;
}
.nav-links { display: flex; gap: 1rem; flex-wrap: wrap; }
.nav-links a {
  color: #fff; text-decoration: none; font-weight: 600; opacity: 0.92;
}
.nav-links a:hover { color: var(--primary); }
.hero-content {
  width: min(1120px, 92%);
  margin: 3rem auto 0;
  display: grid;
  grid-template-columns: 1.1fr 0.9fr;
  gap: 2rem;
  align-items: center;
}
.hero h1 { margin: 0; font-size: clamp(2.2rem, 4vw, 3.5rem); font-weight: 800; line-height: 1.1; }
.hero p { color: #d5dbeb; margin: 1.2rem 0 1.6rem; max-width: 56ch; }
.hero-card {
  background: #fff;
  color: #0f172b;
  border-radius: 16px;
  padding: 1.2rem;
  box-shadow: 0 12px 34px rgba(2, 6, 23, 0.26);
}
.hero-card h3 { margin: 0 0 0.7rem; color: #0f172b; }
.chip {
  display: inline-block;
  padding: 0.3rem 0.65rem;
  border-radius: 999px;
  background: rgba(254, 161, 22, 0.2);
  color: #ffd8a1;
  font-size: 0.85rem;
  font-weight: 600;
}
.btn-primary {
  display: inline-block;
  border: none;
  border-radius: 7px;
  background: var(--primary);
  color: #fff;
  font-weight: 700;
  padding: 0.8rem 1.3rem;
  text-decoration: none;
  cursor: pointer;
}
.btn-primary:hover { filter: brightness(1.06); }
main {
  width: min(1120px, 92%);
  margin: -1.2rem auto 2.2rem;
}
.section {
  background: #fff;
  border-radius: 16px;
  padding: 1.4rem;
  box-shadow: 0 8px 30px rgba(15, 23, 42, 0.08);
  margin-bottom: 1.1rem;
}
.section h2 {
  margin: 0 0 0.9rem;
  font-size: 1.8rem;
  font-family: "Nunito", sans-serif;
}
.features {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.9rem;
  list-style: none;
  margin: 0;
  padding: 0;
}
.features li {
  background: #fff8eb;
  border: 1px solid #ffe1b2;
  border-radius: 12px;
  padding: 0.9rem;
  color: #663f00;
  font-weight: 600;
}
.menu-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.95rem;
}
.menu-card {
  border: 1px solid #e8ebf2;
  border-radius: 12px;
  padding: 0.95rem;
}
.menu-card h3 { margin: 0; font-size: 1rem; }
.menu-card p { margin: 0.45rem 0 0; color: var(--muted); }
#booking-form {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.9rem;
}
#booking-form label { display: grid; gap: 0.42rem; font-weight: 600; }
#booking-form label:last-of-type { grid-column: 1 / -1; }
input, select, textarea {
  width: 100%;
  padding: 0.73rem;
  border: 1px solid #d9dee9;
  border-radius: 8px;
  font: inherit;
}
textarea { min-height: 90px; resize: vertical; }
#booking-form button { width: fit-content; }
#booking-status {
  margin-top: 0.7rem;
  min-height: 1.35rem;
  font-weight: 700;
}
@media (max-width: 960px) {
  .hero-content { grid-template-columns: 1fr; }
  .features { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .menu-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 680px) {
  .features, .menu-grid { grid-template-columns: 1fr; }
  #booking-form { grid-template-columns: 1fr; }
}
""".strip()

_PREMIUM_THEME_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{business_name}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700&family=Nunito:wght@700;800&display=swap" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.10.0/css/all.min.css" rel="stylesheet">
  <link rel="stylesheet" href="/static/styles.css" />
</head>
<body>
  <header class="hero">
    <div class="topbar">
      <a class="brand" href="#"><i class="fa fa-utensils"></i> <span id="business-name">{business_name}</span></a>
      <nav class="nav-links">
        <a href="#highlights">Home</a>
        <a href="#signature">Menu</a>
        <a href="#booking">Booking</a>
      </nav>
      <a class="btn-primary" href="#booking">Book A Table</a>
    </div>
    <div class="hero-content">
      <div>
        <span class="chip">Restoran-inspired premium experience</span>
        <h1>Enjoy our<br>delicious meal</h1>
        <p id="tagline">{tagline}</p>
        <a class="btn-primary" href="#booking">Reserve Now</a>
      </div>
      <div class="hero-card">
        <h3>Today's Signature Offer</h3>
        <p>Curated dishes, premium ingredients, and a warm dining atmosphere designed for memorable evenings.</p>
      </div>
    </div>
  </header>

  <main>
    <section id="highlights" class="section">
      <h2>Why Guests Love Us</h2>
      <ul id="highlights-list" class="features">
        <li>Chef-driven menu with premium ingredients</li>
        <li>Warm hospitality and elegant ambiance</li>
        <li>Seamless reservation experience</li>
        <li>Fast online support and table confirmation</li>
      </ul>
    </section>

    <section id="signature" class="section">
      <h2>Most Popular Items</h2>
      <div class="menu-grid">
        <article class="menu-card">
          <h3>Smoked Chili Noodles</h3>
          <p>Wok-tossed noodles with roasted chili oil and crisp vegetables.</p>
        </article>
        <article class="menu-card">
          <h3>Signature Dim Sum</h3>
          <p>Hand-folded dumplings with aromatic fillings and dipping sauces.</p>
        </article>
        <article class="menu-card">
          <h3>Mandarin Citrus Chicken</h3>
          <p>Caramelized glaze, orange zest, and toasted sesame finish.</p>
        </article>
      </div>
    </section>

    <section id="booking" class="section">
      <h2>Reserve Your Table</h2>
      <form id="booking-form">
        <label>Name <input name="name" required /></label>
        <label>Phone <input name="phone" required /></label>
        <label>Date <input name="date" type="date" required /></label>
        <label>Party size <input name="party_size" type="number" min="1" max="50" value="2" /></label>
        <label>Notes <textarea name="notes" placeholder="Special requests"></textarea></label>
        <button class="btn-primary" type="submit">Confirm Reservation</button>
      </form>
      <p id="booking-status" role="status"></p>
    </section>
  </main>

  <script src="/static/app.js"></script>
</body>
</html>
""".strip()


def _mock_enabled() -> bool:
    return get_settings().runtime_mock_tools


@tool
def init_dev_project() -> str:
    """Copy the neutral webapp starter scaffold into this run's project directory."""
    run_id = require_run_id()
    if _mock_enabled():
        return json.dumps(
            {
                "status": "ok",
                "run_id": run_id,
                "project_dir": str(project_dir(run_id)),
                "source": "mock",
            }
        )
    root = ensure_project_from_template(run_id)
    files = list_project_files(run_id)
    return json.dumps(
        {
            "status": "ok",
            "run_id": run_id,
            "project_dir": str(root),
            "files": files,
        },
        indent=2,
    )


@tool
def read_project_file(relative_path: str) -> str:
    """Read a file from the current run's generated project directory."""
    run_id = require_run_id()
    if _mock_enabled():
        return json.dumps(
            {
                "path": relative_path,
                "content": "# mock project file\n",
                "source": "mock",
            }
        )
    path = safe_project_path(relative_path, run_id)
    if not path.is_file():
        return json.dumps({"error": "file_not_found", "path": relative_path})
    content = path.read_text(encoding="utf-8")
    return json.dumps(
        {
            "path": relative_path,
            "content": content[:12000],
            "truncated": len(content) > 12000,
        },
        indent=2,
    )


@tool
def write_project_file(relative_path: str, content: str) -> str:
    """Write or overwrite a file in the current run's generated project directory."""
    run_id = require_run_id()
    if _mock_enabled():
        return json.dumps(
            {
                "status": "written",
                "path": relative_path,
                "bytes": len(content),
                "source": "mock",
            }
        )
    ensure_project_from_template(run_id)
    path = safe_project_path(relative_path, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return json.dumps(
        {
            "status": "written",
            "path": relative_path,
            "bytes": len(content),
        }
    )


@tool
def list_project_files_tool() -> str:
    """List all files in the current run's generated project directory."""
    run_id = require_run_id()
    if _mock_enabled():
        return json.dumps(
            {
                "files": ["backend/main.py", "frontend/index.html"],
                "source": "mock",
            }
        )
    ensure_project_from_template(run_id)
    return json.dumps({"files": list_project_files(run_id)}, indent=2)


@tool
def run_project_tests() -> str:
    """Run pytest for the generated backend in this workflow run."""
    run_id = require_run_id()
    if _mock_enabled():
        return json.dumps(
            {
                "tests_passed": True,
                "exit_code": 0,
                "stdout": "1 passed",
                "source": "mock",
            },
            indent=2,
        )

    root = ensure_project_from_template(run_id)
    backend = root / "backend"
    if not backend.is_dir():
        return json.dumps(
            {"tests_passed": False, "error": "backend directory missing"},
            indent=2,
        )

    pip = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-q",
            "-r",
            str(backend / "requirements.txt"),
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if pip.returncode != 0:
        return json.dumps(
            {
                "tests_passed": False,
                "stage": "install",
                "stderr": pip.stderr[-2000:],
            },
            indent=2,
        )

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-q"],
        cwd=str(backend),
        capture_output=True,
        text=True,
        timeout=120,
    )
    passed = result.returncode == 0
    return json.dumps(
        {
            "tests_passed": passed,
            "exit_code": result.returncode,
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-2000:],
        },
        indent=2,
    )


def _github_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _git_push_directory(local_dir: Path, *, clone_url: str, token: str) -> None:
    auth_url = clone_url.replace("https://", f"https://x-access-token:{token}@")
    env = {
        **dict(subprocess.os.environ),
        "GIT_TERMINAL_PROMPT": "0",
    }
    commands = [
        ["git", "init"],
        ["git", "config", "user.email", "orqestra-demo@local"],
        ["git", "config", "user.name", "Orqestra Dev Pipeline"],
        ["git", "add", "-A"],
        ["git", "commit", "-m", "Dev pipeline generated project"],
        ["git", "branch", "-M", "main"],
        ["git", "push", "-u", "origin", "main", "--force"],
    ]

    # Handle reruns in the same generated directory: origin may already exist.
    remote_proc = subprocess.run(
        ["git", "remote"],
        cwd=str(local_dir),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    if remote_proc.returncode != 0:
        raise RuntimeError(remote_proc.stderr or remote_proc.stdout or "git remote failed")
    remotes = {name.strip() for name in remote_proc.stdout.splitlines() if name.strip()}
    if "origin" in remotes:
        set_remote_cmd = ["git", "remote", "set-url", "origin", auth_url]
    else:
        set_remote_cmd = ["git", "remote", "add", "origin", auth_url]
    commands.insert(-1, set_remote_cmd)

    for cmd in commands:
        proc = subprocess.run(
            cmd,
            cwd=str(local_dir),
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )
        if proc.returncode != 0 and cmd[1] != "commit":
            raise RuntimeError(proc.stderr or proc.stdout or f"git failed: {cmd}")
        if cmd[1] == "commit" and proc.returncode != 0 and "nothing to commit" not in proc.stdout:
            raise RuntimeError(proc.stderr or proc.stdout or "git commit failed")


def _github_authenticated_login(client: httpx.Client, token: str) -> str:
    response = client.get(
        "https://api.github.com/user",
        headers=_github_headers(token),
    )
    response.raise_for_status()
    return str(response.json().get("login", ""))


def _github_create_repo_url(*, owner: str, token_login: str) -> str:
    if token_login and owner.lower() == token_login.lower():
        return "https://api.github.com/user/repos"
    return f"https://api.github.com/orgs/{owner}/repos"


def _ensure_repo_public(owner: str, name: str, *, token: str) -> None:
    """Droplet cloud-init clones without credentials — repo must be public."""
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        response = client.patch(
            f"https://api.github.com/repos/{owner}/{name}",
            headers=_github_headers(token),
            json={"private": False, "visibility": "public"},
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Could not set {owner}/{name} to public: "
                f"{response.status_code} {response.text[:300]}"
            )


def _clone_url_for_droplet(clone_url: str, token: str) -> str:
    """Authenticated HTTPS clone for private repos (token also in DO user_data)."""
    token = token.strip()
    if not token or not clone_url.startswith("https://github.com/"):
        return clone_url
    encoded = quote(token, safe="")
    return clone_url.replace("https://", f"https://x-access-token:{encoded}@", 1)


def _repo_from_clone_url(clone_url: str) -> tuple[str, str] | None:
    parsed = urlparse(clone_url)
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        return None
    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = path.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return parts[0], parts[1]


def _normalize_github_clone_url(raw_url: str, *, owner_fallback: str = "") -> str:
    """
    Accept common repo URL forms and normalize to:
    https://github.com/<owner>/<repo>.git
    """
    text = (raw_url or "").strip()
    if not text:
        return ""

    # owner/repo shorthand
    if "://" not in text and text.count("/") == 1 and not text.startswith("github.com/"):
        text = f"https://github.com/{text}"

    # github.com/owner/repo
    if text.startswith("github.com/"):
        text = f"https://{text}"

    # plain repo name fallback when owner is known
    if "://" not in text and "/" not in text and owner_fallback.strip():
        text = f"https://github.com/{owner_fallback.strip()}/{text}"

    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != "github.com":
        return ""

    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = path.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return ""
    return f"https://github.com/{parts[0]}/{parts[1]}.git"


def _preflight_repo_access(clone_url: str, *, token: str) -> dict[str, Any]:
    """
    Validate that GitHub repo exists and is readable before creating a droplet.
    This prevents burning DO resources when clone cannot succeed.
    """
    repo = _repo_from_clone_url(clone_url)
    if not repo:
        return {
            "ok": False,
            "error": "clone_url must be a github.com HTTPS URL",
            "clone_url": clone_url,
        }
    owner, name = repo
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        response = client.get(
            f"https://api.github.com/repos/{owner}/{name}",
            headers=_github_headers(token),
        )
        if response.status_code == 404:
            return {
                "ok": False,
                "error": f"GitHub repo not found: {owner}/{name}",
                "repo": f"{owner}/{name}",
            }
        if response.status_code == 403:
            return {
                "ok": False,
                "error": (
                    f"GitHub token cannot read {owner}/{name} "
                    "(403; check token scopes/org SSO access)."
                ),
                "repo": f"{owner}/{name}",
            }
        if response.status_code >= 400:
            return {
                "ok": False,
                "error": f"GitHub API {response.status_code}: {response.text[:300]}",
                "repo": f"{owner}/{name}",
            }
        data = response.json()
        return {
            "ok": True,
            "repo": f"{owner}/{name}",
            "visibility": "private" if data.get("private") else "public",
        }


def _publish_meta_path(run_id: int) -> Path:
    return project_dir(run_id) / ".orqestra_publish.json"


def _deploy_meta_path(run_id: int) -> Path:
    return project_dir(run_id) / ".orqestra_deploy.json"


def _save_publish_meta(run_id: int, repo: dict[str, Any]) -> None:
    try:
        path = _publish_meta_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "clone_url": repo.get("clone_url", ""),
                    "html_url": repo.get("html_url", ""),
                    "full_name": repo.get("full_name", ""),
                    "run_id": run_id,
                }
            ),
            encoding="utf-8",
        )
    except Exception:
        # Non-fatal: deployment can still proceed with provided URL.
        pass


def _save_deploy_meta(run_id: int, deploy: dict[str, Any]) -> None:
    try:
        path = _deploy_meta_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "url": deploy.get("url", ""),
                    "health_url": deploy.get("health_url", ""),
                    "ip_address": deploy.get("ip_address", ""),
                    "droplet_id": deploy.get("droplet_id", ""),
                    "run_id": run_id,
                }
            ),
            encoding="utf-8",
        )
    except Exception:
        # Non-fatal: notification can still be sent from agent text.
        pass


def _enforce_premium_frontend(root: Path) -> None:
    """Normalize asset paths and apply a premium baseline theme before publish."""
    frontend = root / "frontend"
    if not frontend.is_dir():
        return

    index_path = frontend / "index.html"
    business_name = "Your Business"
    tagline = "Welcome - premium dining experience."
    if index_path.is_file():
        index = index_path.read_text(encoding="utf-8")
        h1_match = re.search(r"<h1[^>]*>([^<]+)</h1>", index, flags=re.IGNORECASE)
        if h1_match:
            business_name = h1_match.group(1).strip() or business_name
        tagline_match = re.search(r"<p[^>]*>([^<]+)</p>", index, flags=re.IGNORECASE)
        if tagline_match:
            tagline = tagline_match.group(1).strip() or tagline
    index_path.write_text(
        _PREMIUM_THEME_HTML.format(
            business_name=business_name,
            tagline=tagline,
        )
        + "\n",
        encoding="utf-8",
    )

    styles_path = frontend / "styles.css"
    styles_path.write_text(_PREMIUM_THEME_CSS + "\n", encoding="utf-8")
    _ensure_backend_serves_frontend(root)
    _ensure_canonical_deploy_files(root)


def _ensure_canonical_deploy_files(root: Path) -> None:
    """
    Ensure deployed artifact always builds backend + frontend together.
    This prevents /api working while / returns 404 due to missing frontend in image.
    """
    compose_path = root / "docker-compose.yml"
    compose_path.write_text(_CANONICAL_DOCKER_COMPOSE + "\n", encoding="utf-8")

    dockerfile_path = root / "backend" / "Dockerfile"
    dockerfile_path.parent.mkdir(parents=True, exist_ok=True)
    dockerfile_path.write_text(_CANONICAL_BACKEND_DOCKERFILE + "\n", encoding="utf-8")


def _ensure_backend_serves_frontend(root: Path) -> None:
    """
    Guarantee generated backend exposes frontend assets at /static and homepage at /.
    This avoids demos where API is healthy but root returns 404.
    """
    main_path = root / "backend" / "main.py"
    if not main_path.is_file():
        return

    content = main_path.read_text(encoding="utf-8")
    has_static_mount = 'app.mount("/static"' in content
    has_root_route = '@app.get("/")' in content or "def index(" in content
    if has_static_mount and has_root_route:
        return

    patch_lines: list[str] = []
    patch_lines.append("")
    patch_lines.append("# Orqestra safety patch: ensure homepage + static assets are served.")
    patch_lines.append("from pathlib import Path as _OrqPath")
    patch_lines.append("_ORQ_FRONTEND_DIR = _OrqPath(__file__).resolve().parent.parent / \"frontend\"")
    patch_lines.append("if _ORQ_FRONTEND_DIR.is_dir():")
    if not has_static_mount:
        patch_lines.append("    from fastapi.staticfiles import StaticFiles as _OrqStaticFiles")
        patch_lines.append(
            "    app.mount(\"/static\", _OrqStaticFiles(directory=_ORQ_FRONTEND_DIR), name=\"static\")"
        )
    if not has_root_route:
        patch_lines.append("    from fastapi.responses import FileResponse as _OrqFileResponse")
        patch_lines.append("    @app.get(\"/\")")
        patch_lines.append("    def index() -> _OrqFileResponse:")
        patch_lines.append("        return _OrqFileResponse(_ORQ_FRONTEND_DIR / \"index.html\")")
    patch_lines.append("")

    main_path.write_text(content.rstrip() + "\n" + "\n".join(patch_lines), encoding="utf-8")


def _load_publish_meta(run_id: int) -> dict[str, Any] | None:
    path = _publish_meta_path(run_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_deploy_meta(run_id: int) -> dict[str, Any] | None:
    path = _deploy_meta_path(run_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _create_github_repo(name: str, *, token: str, owner: str) -> dict[str, Any]:
    payload = {
        "name": name,
        "private": False,
        "visibility": "public",
        "auto_init": False,
    }
    headers = _github_headers(token)
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        token_login = _github_authenticated_login(client, token)
        effective_owner = owner or token_login
        create_url = _github_create_repo_url(owner=effective_owner, token_login=token_login)
        response = client.post(create_url, headers=headers, json=payload)
        # Resilient fallback: if configured owner/org is wrong, try publishing under
        # the authenticated user so demo flow continues.
        if (
            response.status_code in (403, 404)
            and effective_owner.lower() != token_login.lower()
        ):
            effective_owner = token_login
            create_url = "https://api.github.com/user/repos"
            response = client.post(create_url, headers=headers, json=payload)
        if response.status_code == 422:
            # Repo name taken — reuse URL; push may still succeed if we own it.
            return {
                "full_name": f"{effective_owner}/{name}",
                "html_url": f"https://github.com/{effective_owner}/{name}",
                "clone_url": f"https://github.com/{effective_owner}/{name}.git",
                "existed": True,
                "owner": effective_owner,
            }
        if response.status_code == 403:
            hint = (
                "GitHub returned 403. Use a classic PAT with the 'repo' scope (or a "
                "fine-grained token with Administration + Contents read/write on "
                f"repositories under '{owner}'). GITHUB_OWNER must match the account "
                "or org the token can publish to."
            )
            detail = response.text[:500]
            raise PermissionError(f"{hint} Response: {detail}")
        if response.status_code >= 400:
            raise RuntimeError(
                f"GitHub API {response.status_code} creating repo: {response.text[:500]}"
            )
        data = response.json()
        return {
            "full_name": data["full_name"],
            "html_url": data["html_url"],
            "clone_url": data["clone_url"],
            "existed": False,
            "owner": str(data.get("owner", {}).get("login") or effective_owner),
        }


def _build_cloud_config(clone_url: str, root_password: str) -> str:
    escaped = root_password.replace("\\", "\\\\").replace(":", "\\:")
    # Use get.docker.com — ubuntu's docker-compose-plugin package is often missing.
    return f"""#cloud-config
package_update: true
packages:
  - git
  - curl

chpasswd:
  list: |
    root:{escaped}
  expire: false
ssh_pwauth: true

runcmd:
  - |
    set -eux
    exec > /var/log/orqestra-bootstrap.log 2>&1
    curl -fsSL https://get.docker.com | sh
    ufw allow 22 || true
    ufw allow 8080 || true
    rm -rf /app
    git clone {clone_url} /app
    cd /app
    docker compose up -d --build
    for i in $(seq 1 60); do
      curl -sf http://127.0.0.1:8080/api/health && exit 0
      sleep 10
    done
    exit 1
"""


def _create_droplet_and_wait(
    *,
    name: str,
    user_data: str,
    settings,
) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {settings.do_api_token}",
        "Content-Type": "application/json",
    }
    body = {
        "name": name,
        "region": settings.do_region,
        "size": settings.do_size,
        "image": settings.do_image,
        "user_data": user_data,
        "tags": ["orqestra-demo", "webapp-pipeline"],
    }
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        create = client.post(
            "https://api.digitalocean.com/v2/droplets",
            headers=headers,
            json=body,
        )
        create.raise_for_status()
        droplet = create.json()["droplet"]
        droplet_id = droplet["id"]

        deadline = time.time() + _DO_MAX_WAIT
        ip_address = ""
        while time.time() < deadline:
            time.sleep(_DO_POLL_INTERVAL)
            status_resp = client.get(
                f"https://api.digitalocean.com/v2/droplets/{droplet_id}",
                headers=headers,
            )
            status_resp.raise_for_status()
            droplet = status_resp.json()["droplet"]
            if droplet.get("status") != "active":
                continue
            for net in droplet.get("networks", {}).get("v4", []):
                if net.get("type") == "public":
                    ip_address = net.get("ip_address", "")
                    break
            if ip_address:
                health_url = f"http://{ip_address}:8080/api/health"
                root_url = f"http://{ip_address}:8080/"
                try:
                    health = client.get(health_url, timeout=10.0)
                    home = client.get(root_url, timeout=10.0)
                    if health.status_code == 200 and home.status_code == 200:
                        return {
                            "droplet_id": droplet_id,
                            "ip_address": ip_address,
                            "url": root_url,
                            "health_url": health_url,
                        }
                except httpx.HTTPError:
                    pass
        raise TimeoutError(
            f"Droplet {droplet_id} did not become healthy within {_DO_MAX_WAIT}s"
        )


@tool
def github_publish_project(repo_name: str = "") -> str:
    """Create a public GitHub repo and push the generated project for this run."""
    run_id = require_run_id()
    settings = get_settings()
    default_name = f"webapp-run-{run_id}-{secrets.token_hex(3)}"
    name = (repo_name or default_name).strip()
    if not name:
        name = default_name

    if _mock_enabled() or not settings.github_token.strip():
        owner = settings.github_owner or "demo-user"
        return json.dumps(
            {
                "status": "mock",
                "repo_name": name,
                "full_name": f"{owner}/{name}",
                "html_url": f"https://github.com/{owner}/{name}",
                "clone_url": f"https://github.com/{owner}/{name}.git",
            },
            indent=2,
        )

    owner = settings.github_owner.strip()

    root = ensure_project_from_template(run_id)
    _enforce_premium_frontend(root)
    try:
        repo = _create_github_repo(name, token=settings.github_token, owner=owner)
        _git_push_directory(
            root, clone_url=repo["clone_url"], token=settings.github_token
        )
        repo_owner = str(repo.get("owner") or owner).strip()
        _ensure_repo_public(repo_owner, name, token=settings.github_token)
        repo["visibility"] = "public"
    except Exception as exc:
        return json.dumps(
            {
                "status": "failed",
                "error": str(exc),
                "repo_name": name,
                "owner": owner,
            },
            indent=2,
        )
    _save_publish_meta(run_id, repo)
    repo["status"] = "published"
    repo["run_id"] = run_id
    return json.dumps(repo, indent=2)


@tool
def do_deploy_from_github(clone_url: str, repo_name: str = "") -> str:
    """Create a DigitalOcean droplet, clone the public repo, and start the app."""
    run_id = require_run_id()
    settings = get_settings()
    droplet_name = (repo_name or f"webapp-run-{run_id}").strip()[:63]

    if _mock_enabled() or not settings.do_api_token.strip():
        return json.dumps(
            {
                "status": "mock",
                "url": "http://203.0.113.10:8080",
                "clone_url": clone_url,
                "droplet_name": droplet_name,
            },
            indent=2,
        )

    if not settings.deploy_root_password.strip():
        return json.dumps({"error": "DEPLOY_ROOT_PASSWORD is not configured"})

    owner_fallback = settings.github_owner.strip()
    clone = _normalize_github_clone_url(clone_url, owner_fallback=owner_fallback)
    if not clone.startswith("https://github.com/"):
        return json.dumps(
            {
                "status": "failed",
                "error": (
                    "Invalid or missing GitHub repository URL. Provide clone_url from "
                    "github_publish_project, or owner/repo, or a github.com repo URL."
                ),
                "clone_url": clone_url,
                "normalized_clone_url": clone,
            },
            indent=2,
        )

    preflight = _preflight_repo_access(clone, token=settings.github_token)
    # Agent may pass an incorrect URL despite successful publish; fallback to saved
    # publish metadata for this run before failing deployment.
    if not preflight.get("ok"):
        meta = _load_publish_meta(run_id)
        meta_clone_raw = str((meta or {}).get("clone_url", "")).strip()
        meta_clone = _normalize_github_clone_url(
            meta_clone_raw, owner_fallback=owner_fallback
        )
        if meta_clone and meta_clone != clone:
            meta_preflight = _preflight_repo_access(meta_clone, token=settings.github_token)
            if meta_preflight.get("ok"):
                clone = meta_clone
                preflight = meta_preflight

    if not preflight.get("ok"):
        return json.dumps(
            {
                "status": "failed",
                "stage": "preflight",
                "error": preflight.get("error", "Repo access preflight failed"),
                "clone_url": clone,
            },
            indent=2,
        )

    deploy_clone = _clone_url_for_droplet(clone, settings.github_token)
    user_data = _build_cloud_config(deploy_clone, settings.deploy_root_password)
    try:
        result = _create_droplet_and_wait(
            name=droplet_name,
            user_data=user_data,
            settings=settings,
        )
    except Exception as exc:
        return json.dumps({"status": "failed", "error": str(exc)}, indent=2)

    result["status"] = "deployed"
    result["clone_url"] = clone_url
    _save_deploy_meta(run_id, result)
    return json.dumps(result, indent=2)


DEV_TOOL_REGISTRY: dict[str, Any] = {
    "init_dev_project": init_dev_project,
    "read_project_file": read_project_file,
    "write_project_file": write_project_file,
    "list_project_files": list_project_files_tool,
    "run_project_tests": run_project_tests,
    "github_publish_project": github_publish_project,
    "do_deploy_from_github": do_deploy_from_github,
}
