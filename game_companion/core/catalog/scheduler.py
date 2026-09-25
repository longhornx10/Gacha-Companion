"""Background auto-refresh (M25): codes daily, catalog weekly, banners 6-hourly.

The service is long-lived, so a simple loop in the app lifespan keeps data
current without any cron/CLI involvement — the self-containment rule. Every
run goes through the same services as the manual buttons, so outcomes land in
``source_runs`` and show up in the UI. All failures are recorded and logged,
never raised: a blocked source must not kill the app.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import timedelta
from typing import Any

from game_companion.core.catalog.service import CatalogService
from game_companion.core.codes.service import CodeService
from game_companion.core.games.registry import list_adapters

logger = logging.getLogger(__name__)

CODES_MAX_AGE = timedelta(hours=24)
CATALOG_MAX_AGE = timedelta(days=7)
# banners rotate every few weeks and Home shows them live — weekly is too slow
BANNER_MAX_AGE = timedelta(hours=6)
FIRST_RUN_DELAY_SECONDS = 20
TICK_SECONDS = 3600


def _is_stale(run: Any, max_age: timedelta) -> bool:
    if run is None or run.status != "ok" or run.fetched_at is None:
        return True
    from game_companion.utils import utcnow

    return (utcnow() - run.fetched_at) > max_age


def run_due_refreshes(app) -> list[dict[str, Any]]:
    """Refresh every installed game's codes (daily) and catalog (weekly)."""
    transport = getattr(app.state, "llm_transport", None)
    summaries: list[dict[str, Any]] = []
    for adapter in list_adapters():
        with app.state.session_factory() as session:
            codes_spec = adapter.codes_source()
            if codes_spec and _is_stale(
                CatalogService(session, adapter).run_for(codes_spec["key"]), CODES_MAX_AGE
            ):
                summary = CodeService(session, adapter).refresh_from_source(transport=transport)
                summary.update({"game": adapter.game_id, "kind": "codes"})
                summaries.append(summary)
            if adapter.catalog_sources():
                service = CatalogService(session, adapter)
                sources = adapter.catalog_sources()
                banner_keys = [
                    k for k, spec in sources.items() if spec.get("entity") == "banner"
                ]
                plain_keys = [k for k in sources if k not in banner_keys]
                due_plain = any(_is_stale(service.run_for(k), CATALOG_MAX_AGE) for k in plain_keys)
                due_banner = any(_is_stale(service.run_for(k), BANNER_MAX_AGE) for k in banner_keys)
                if due_plain:
                    summary = service.refresh(
                        "auto", transport=transport,
                        skip_entities={"banner"} if banner_keys else None,
                    )
                    summaries.append({"game": adapter.game_id, "kind": "catalog", "sources": summary})
                if due_banner:
                    for key in banner_keys:
                        summary = service.refresh(key, transport=transport)
                        summaries.append({"game": adapter.game_id, "kind": "banners", "sources": summary})
            session.commit()
    return summaries


async def refresh_loop(app) -> None:
    """Sleep, refresh once, then check staleness hourly until cancelled."""
    await asyncio.sleep(FIRST_RUN_DELAY_SECONDS)
    while True:
        try:
            for summary in await asyncio.to_thread(run_due_refreshes, app):
                logger.info("auto-refresh: %s", summary)
        except Exception:  # noqa: BLE001 — the loop must survive anything
            logger.exception("auto-refresh tick failed")
        await asyncio.sleep(TICK_SECONDS)


def start_refresh_loop(app) -> asyncio.Task | None:
    if not app.state.settings.auto_refresh:
        return None
    return asyncio.create_task(refresh_loop(app), name="catalog-auto-refresh")


async def stop_refresh_loop(task: asyncio.Task | None) -> None:
    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task  # let an in-flight to_thread tick finish cleanly
