from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user_web
from app.models.user import User
from app.services.dashboard_service import DashboardService
from app.templating import templates

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_class=HTMLResponse, name="dashboard")
def dashboard(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: Session = Depends(get_db),
):
    service = DashboardService(db)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "active_nav": "dashboard",
            "stats": service.get_stats(),
            "active_runs": service.get_active_runs(),
            "recent_runs": service.get_recent_runs(),
            "failed_runs": service.get_failed_runs(),
            "recent_messages": service.get_recent_messages(),
        },
    )
