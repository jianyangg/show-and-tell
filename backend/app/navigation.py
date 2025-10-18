from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional
from urllib.parse import urlparse

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

_DEFAULT_IFRAME_TIMEOUT = float(os.environ.get("RUNNER_EMBEDDED_FRAME_TIMEOUT", "20"))
_IGNORED_URL_PREFIXES = ("about:", "chrome-error://", "data:")


async def wait_for_embedded_page(
    page: Page,
    start_url: Optional[str],
    *,
    timeout: float = _DEFAULT_IFRAME_TIMEOUT,
) -> None:
    """
    Ensure an embedded iframe finishes loading before automation begins.

    If the Playwright page already hosts the expected domain, this returns immediately.
    Otherwise we poll for a child iframe whose host matches the recorded start URL and
    wait for it to reach a ready state. This prevents Computer Use from issuing actions
    against an empty viewer shell while the real site is still loading.
    """
    if timeout <= 0:
        return

    expected_host = ""
    if start_url:
        parsed = urlparse(start_url)
        expected_host = (parsed.hostname or "").lstrip("www.").lower()

    main_host = (urlparse(page.url).hostname or "").lstrip("www.").lower()
    if expected_host and main_host == expected_host:
        try:
            await page.wait_for_load_state("networkidle", timeout=4000)
        except PlaywrightTimeoutError:
            pass
        return

    deadline = time.monotonic() + timeout
    last_error: Optional[Exception] = None
    saw_frame = False

    while time.monotonic() < deadline:
        target_frame = None
        fallback_frame = None

        for frame in page.frames:
            if frame is page.main_frame:
                continue
            frame_url = frame.url or ""
            if not frame_url or frame_url.startswith(_IGNORED_URL_PREFIXES):
                continue
            parsed_frame = urlparse(frame_url)
            frame_host = (parsed_frame.hostname or "").lstrip("www.").lower()

            if expected_host and frame_host == expected_host:
                target_frame = frame
                break
            if fallback_frame is None:
                fallback_frame = frame

        candidate = target_frame or fallback_frame
        if candidate is None:
            await asyncio.sleep(0.25)
            continue

        saw_frame = True
        try:
            await candidate.wait_for_load_state("domcontentloaded", timeout=4000)
            try:
                ready_state = await candidate.evaluate("document.readyState")
            except Exception:
                ready_state = "unknown"
            if ready_state != "complete":
                await candidate.wait_for_load_state("load", timeout=2000)
        except PlaywrightTimeoutError as exc:
            last_error = exc
            await asyncio.sleep(0.25)
            continue

        logger.info("Iframe ready for automation at %s", candidate.url)
        return

    if not saw_frame:
        logger.info(
            "No child iframe detected for %s; continuing without embedded frame wait.",
            page.url,
        )
        return

    msg = "Embedded iframe did not finish loading before timeout"
    if expected_host:
        msg += f" (expected host: {expected_host})"
    if last_error:
        raise RuntimeError(msg) from last_error
    raise RuntimeError(msg)
