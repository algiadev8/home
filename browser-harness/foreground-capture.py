"""Make captures reliable on the shared Xvfb-backed browser.

Chromium can indefinitely defer screenshots of a background tab after navigation
or resizing. Run in the harness daemon so helper, raw-CDP, and recorder captures
all use the same attached target, including explicit CDP sessions.
"""

import asyncio


SCREENSHOT_TIMEOUT = 50


async def capture_screenshot(daemon, params, session_id):
    """Capture the requested session while serializing virtual-screen captures."""
    if not session_id:
        raise RuntimeError("Cannot capture screenshot: no attached page session")

    try:
        # Includes lock wait, resolution, activation, and capture. This remains
        # shorter than the helper's 60-second IPC timeout.
        async with asyncio.timeout(SCREENSHOT_TIMEOUT):
            async with daemon._screenshot_lock:
                cdp = daemon.cdp
                # Explicit sessions may refer to another tab. Resolve the exact
                # session instead of using the daemon's mutable default target.
                info = await cdp.send_raw("Target.getTargetInfo", session_id=session_id)
                target = info.get("targetInfo", {})
                target_id = target.get("targetId")
                if not target_id or target.get("type") != "page":
                    raise RuntimeError("Cannot capture screenshot: session is not attached to a page")

                # Foregrounding submits a current compositor frame on Xvfb.
                await cdp.send_raw("Target.activateTarget", {"targetId": target_id})
                return await cdp.send_raw("Page.captureScreenshot", params, session_id=session_id)
    except asyncio.TimeoutError as exc:
        raise RuntimeError("Screenshot timed out while preparing or capturing the page") from exc
