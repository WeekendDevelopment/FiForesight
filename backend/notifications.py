# backend/notifications.py
"""
Delivery channels for Alerts & Notifications (Feature 9).

  • Web Push (primary, free) — encrypted browser push via `pywebpush` + a server
    VAPID key pair. Works without any third-party service. When VAPID keys aren't
    configured (or pywebpush isn't installed), pushes are skipped (logged) so the
    rest of the alert pipeline still records fires.

  • Email (optional fallback) — Resend HTTP API, gated behind ALERT_EMAIL_ENABLED
    + RESEND_API_KEY. Resend's free tier (100 emails/day) keeps this free-only.
    Disabled by default; the feature is fully functional web-push-only.

pywebpush is synchronous (uses `requests`), so it runs in a worker thread to keep
the async evaluator non-blocking. Failures are swallowed and reported as a status
string — one bad subscription never aborts a batch.
"""
import asyncio
import json
import logging
from typing import Any, Dict

import httpx

from config import Config

logger = logging.getLogger(__name__)

try:
    from pywebpush import webpush, WebPushException
    _PYWEBPUSH_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only when the dep is absent
    webpush = None

    class WebPushException(Exception):  # type: ignore
        """Fallback so callers can reference the symbol when pywebpush is absent."""

    _PYWEBPUSH_AVAILABLE = False


def web_push_configured() -> bool:
    """True when a VAPID key pair is set and pywebpush is importable."""
    return bool(
        _PYWEBPUSH_AVAILABLE
        and Config.VAPID_PUBLIC_KEY
        and Config.VAPID_PRIVATE_KEY
    )


def email_configured() -> bool:
    """True when the optional email channel is enabled and keyed."""
    return bool(Config.ALERT_EMAIL_ENABLED and Config.RESEND_API_KEY)


def _send_web_push_sync(subscription_info: Dict[str, Any], payload_json: str) -> None:
    """Blocking pywebpush call. Raises WebPushException on a non-2xx response."""
    webpush(
        subscription_info=subscription_info,
        data=payload_json,
        vapid_private_key=Config.VAPID_PRIVATE_KEY,
        vapid_claims={"sub": Config.VAPID_SUBJECT},
        ttl=3600,
    )


async def send_web_push(subscription: Dict[str, Any], title: str, body: str, url: str = "/alerts") -> str:
    """Send one Web Push notification.

    Returns a status string:
      'sent'    — delivered to the Push Service
      'gone'    — subscription expired/unsubscribed (404/410) → caller should delete it
      'skipped' — push not configured (no VAPID keys / pywebpush missing)
      'error'   — transient failure (logged, not fatal)
    """
    if not web_push_configured():
        logger.info("[NOTIFY] web push skipped — VAPID keys/pywebpush not configured")
        return "skipped"

    endpoint = subscription.get("endpoint")
    p256dh = subscription.get("p256dh")
    auth_key = subscription.get("auth")
    if not (endpoint and p256dh and auth_key):
        logger.warning("[NOTIFY] web push skipped — incomplete subscription record")
        return "error"

    sub_info = {"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth_key}}
    payload = json.dumps({"title": title, "body": body, "url": url})
    try:
        await asyncio.to_thread(_send_web_push_sync, sub_info, payload)
        return "sent"
    except WebPushException as exc:  # type: ignore[misc]
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (404, 410):
            return "gone"
        logger.warning("[NOTIFY] web push failed (status=%s): %s", status, exc)
        return "error"
    except Exception as exc:
        logger.warning("[NOTIFY] web push unexpected error: %s", exc)
        return "error"


async def send_email(to_email: str, subject: str, html: str) -> bool:
    """Send an email via Resend (optional). Returns True on success, False when
    disabled/unconfigured or on any failure (best-effort, never raises)."""
    if not email_configured():
        return False
    if not to_email:
        return False
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {Config.RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": Config.ALERT_EMAIL_FROM,
                    "to": [to_email],
                    "subject": subject,
                    "html": html,
                },
            )
        if resp.status_code >= 400:
            logger.warning("[NOTIFY] Resend email failed HTTP %s: %s", resp.status_code, resp.text[:200])
            return False
        return True
    except Exception as exc:
        logger.warning("[NOTIFY] email error: %s", exc)
        return False
