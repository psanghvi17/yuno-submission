from __future__ import annotations

import logging
import os
import socket
import threading
import time
import uuid

import redis
from redis.exceptions import RedisError

from app.channels.telegram import TelegramChannel, TelegramPollingConflictError
from app.config import get_settings

logger = logging.getLogger(__name__)

POLLING_LOCK_KEY = "orqestra:telegram:polling:lock"
POLLING_LOCK_TTL_SECONDS = 45
PROCESSED_UPDATE_PREFIX = "orqestra:telegram:processed:"
PROCESSED_UPDATE_TTL_SECONDS = 3600

_poller_thread: threading.Thread | None = None
_stop_event = threading.Event()
_instance_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
_redis_client: redis.Redis | None = None


def _get_redis() -> redis.Redis | None:
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        client = redis.from_url(get_settings().redis_url, decode_responses=True)
        client.ping()
        _redis_client = client
        return _redis_client
    except RedisError:
        logger.warning(
            "Redis unavailable for Telegram polling leader election; "
            "use a single API replica or webhooks in production"
        )
        return None


def _acquire_polling_lock() -> bool:
    client = _get_redis()
    if client is None:
        return True
    return bool(
        client.set(
            POLLING_LOCK_KEY,
            _instance_id,
            nx=True,
            ex=POLLING_LOCK_TTL_SECONDS,
        )
    )


def _renew_polling_lock() -> bool:
    client = _get_redis()
    if client is None:
        return True
    try:
        current = client.get(POLLING_LOCK_KEY)
        if current != _instance_id:
            return False
        client.expire(POLLING_LOCK_KEY, POLLING_LOCK_TTL_SECONDS)
        return True
    except RedisError:
        return False


def _mark_update_seen(update_id: int) -> bool:
    """Return True if this update_id is new and should be processed."""
    client = _get_redis()
    if client is None:
        return True
    key = f"{PROCESSED_UPDATE_PREFIX}{update_id}"
    try:
        return bool(
            client.set(key, "1", nx=True, ex=PROCESSED_UPDATE_TTL_SECONDS)
        )
    except RedisError:
        return True


def _enqueue_telegram_update(update: dict) -> None:
    """Hand off to Celery so the poll loop is not blocked by LLM/DB work."""
    update_id = update.get("update_id")
    if isinstance(update_id, int) and not _mark_update_seen(update_id):
        logger.debug("Skipping duplicate Telegram update_id=%s", update_id)
        return

    from app.workers.tasks import process_telegram_update

    settings = get_settings()
    if settings.celery_task_always_eager:
        process_telegram_update(payload=update)
    else:
        process_telegram_update.delay(update)


def _release_polling_lock() -> None:
    client = _get_redis()
    if client is None:
        return
    try:
        if client.get(POLLING_LOCK_KEY) == _instance_id:
            client.delete(POLLING_LOCK_KEY)
    except RedisError:
        logger.debug("Failed to release Telegram polling lock", exc_info=True)


def _poll_loop() -> None:
    telegram = TelegramChannel()
    offset: int | None = None
    conflict_backoff = 5
    while not _stop_event.is_set():
        if not _renew_polling_lock():
            logger.info(
                "Telegram polling stopped — another replica holds the leader lock"
            )
            break
        try:
            # timeout=8: Telegram returns immediately when a message arrives;
            # shorter wait improves recovery after 409 without adding user-visible delay.
            updates = telegram.get_updates(offset=offset, timeout=8)
            conflict_backoff = 5
            for update in updates:
                if not isinstance(update, dict):
                    continue
                update_id = update.get("update_id")
                if isinstance(update_id, int):
                    offset = update_id + 1
                try:
                    _enqueue_telegram_update(update)
                except Exception:
                    logger.exception("Telegram polling enqueue failed")
        except TelegramPollingConflictError:
            logger.warning(
                "Telegram getUpdates conflict (409); backing off %ss "
                "(close any browser tab on .../getUpdates; only one poller per bot)",
                conflict_backoff,
            )
            try:
                telegram.delete_webhook(drop_pending_updates=False)
            except Exception:
                pass
            time.sleep(conflict_backoff)
            conflict_backoff = min(conflict_backoff * 2, 60)
        except Exception:
            logger.exception("Telegram polling error")
            time.sleep(5)
    _release_polling_lock()


def start_telegram_polling() -> None:
    global _poller_thread
    settings = get_settings()
    if not settings.telegram_use_polling or not settings.telegram_bot_token.strip():
        return
    if _poller_thread and _poller_thread.is_alive():
        return
    if not _acquire_polling_lock():
        logger.info(
            "Telegram polling skipped — another API replica is the polling leader"
        )
        return
    telegram = TelegramChannel()
    try:
        telegram.delete_webhook(drop_pending_updates=False)
        logger.info("Cleared Telegram webhook before starting long-polling")
    except Exception:
        logger.warning("Could not clear Telegram webhook before polling", exc_info=True)
    # Let any other getUpdates client (browser tab, previous container) release the slot.
    time.sleep(2)
    _stop_event.clear()
    _poller_thread = threading.Thread(
        target=_poll_loop,
        name="telegram-poller",
        daemon=True,
    )
    _poller_thread.start()
    logger.info("Telegram long-polling started (leader %s)", _instance_id)


def stop_telegram_polling() -> None:
    """Stop the poller and wait for an in-flight long-poll to finish (up to ~25s)."""
    _stop_event.set()
    thread = _poller_thread
    if thread is not None and thread.is_alive():
        thread.join(timeout=25)
    _release_polling_lock()


def reset_telegram_connections(*, wait_seconds: int = 0) -> dict[str, object]:
    """
    Release local polling + webhook so Telegram frees the getUpdates slot.
    Safe to call while the API is running or stopped.
    """
    stop_telegram_polling()
    client = _get_redis()
    lock_cleared = False
    if client is not None:
        try:
            client.delete(POLLING_LOCK_KEY)
            lock_cleared = True
        except RedisError:
            pass

    telegram = TelegramChannel()
    webhook_result: dict = {"skipped": True}
    webhook_info: dict = {}
    if telegram.is_configured():
        try:
            webhook_result = telegram.delete_webhook(drop_pending_updates=True)
        except Exception as exc:
            webhook_result = {"ok": False, "error": str(exc)}
        try:
            import httpx

            response = httpx.get(
                f"{telegram._api_url}/getWebhookInfo",
                timeout=15.0,
            )
            webhook_info = response.json()
        except Exception as exc:
            webhook_info = {"ok": False, "error": str(exc)}

    if wait_seconds > 0:
        time.sleep(wait_seconds)

    return {
        "lock_cleared": lock_cleared,
        "delete_webhook": webhook_result,
        "webhook_info": webhook_info,
    }
