# Orqestra - Documentation Index

Documentation for **Orqestra**, the multi-agent orchestration platform (FastAPI).

| Document | Description |
|----------|-------------|
| [Architecture](./architecture/README.md) | System design, request lifecycle, auth, DI, middleware |
| [API Reference](./api/README.md) | REST (`/api/v1`), web UI routes, webhooks |
| [Database](./database/README.md) | Schema `app`, tables, relationships, migrations |
| [Environment Variables](./development/environment.md) | Full env var table |
| [Developer Onboarding](./development/README.md) | Local setup, conventions, extending the app |
| [Deployment](./deployment/README.md) | Docker, CapRover, scaling, secrets |

**Additional guides:**

- [ARCHITECTURE.md](./ARCHITECTURE.md) - high-level overview (see `architecture/README.md` for implementation detail)
- [DEMO.md](./DEMO.md) - demo script including required live Telegram segment

**Quick links**

| Resource | URL (default) |
|----------|----------------|
| Web UI | http://localhost:3000 |
| Swagger (REST only) | http://localhost:3000/docs |
| ReDoc | http://localhost:3000/redoc |
| Health | http://localhost:3000/health |
