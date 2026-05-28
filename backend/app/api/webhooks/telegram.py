from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.database import get_db

router = APIRouter(tags=["webhooks"])


def _verify_telegram_secret(
    secret_header: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
) -> None:
    settings = get_settings()
    expected = settings.telegram_webhook_secret.strip()
    if not expected:
        return
    if secret_header != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Telegram webhook secret",
        )


@router.post("/webhooks/telegram")
async def telegram_webhook(
    request: Request,
    _db: Session = Depends(get_db),
    _secret: None = Depends(_verify_telegram_secret),
):
    """Telegram Bot API webhook — enqueues async processing."""
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")

    from app.workers.tasks import process_telegram_update

    process_telegram_update.delay(payload)
    return {"ok": True}
