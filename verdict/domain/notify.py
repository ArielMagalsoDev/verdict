"""Fire-and-forget notification to an external automation platform (n8n) —
port of lib/notify.ts. Deliberately opt-in and best-effort: only fires when
N8N_OUTBOUND_WEBHOOK_URL is set (unset by default, so demo visitors never
trigger a real notification), and can never raise — a notification failure
is not a pipeline failure."""

import httpx

from ..config import settings

TIMEOUT_S = 4.0


def notify_sales_ready(params: dict) -> None:
    url = settings().n8n_outbound_webhook_url
    if not url or params.get("band") != "sales_ready":
        return

    try:
        httpx.post(url, json=params, timeout=TIMEOUT_S)
    except Exception:  # noqa: BLE001 — best-effort only, never propagate
        pass
