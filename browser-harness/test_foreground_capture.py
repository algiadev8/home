import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, call


spec = importlib.util.spec_from_file_location(
    "foreground_capture", Path(__file__).with_name("foreground-capture.py")
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def daemon(cdp):
    return SimpleNamespace(cdp=cdp, _screenshot_lock=asyncio.Lock())


class ForegroundCaptureTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolves_session_and_activates_before_capture(self):
        cdp = AsyncMock()
        cdp.send_raw.side_effect = [
            {"targetInfo": {"targetId": "other-target", "type": "page"}},
            {},
            {"data": "image"},
        ]
        result = await module.capture_screenshot(daemon(cdp), {"format": "png"}, "other-session")
        self.assertEqual(result, {"data": "image"})
        self.assertEqual(cdp.send_raw.await_args_list, [
            call("Target.getTargetInfo", session_id="other-session"),
            call("Target.activateTarget", {"targetId": "other-target"}),
            call("Page.captureScreenshot", {"format": "png"}, session_id="other-session"),
        ])

    async def test_invalid_session_fails_without_activating_or_capturing(self):
        cdp = AsyncMock()
        with self.assertRaisesRegex(RuntimeError, "no attached page session"):
            await module.capture_screenshot(daemon(cdp), {}, None)
        cdp.send_raw.assert_not_awaited()

    async def test_non_page_session_fails_before_activation(self):
        cdp = AsyncMock()
        cdp.send_raw.return_value = {"targetInfo": {"targetId": "browser", "type": "browser"}}
        with self.assertRaisesRegex(RuntimeError, "not attached to a page"):
            await module.capture_screenshot(daemon(cdp), {}, "session")
        self.assertEqual(cdp.send_raw.await_count, 1)

    async def test_activation_failure_does_not_capture_wrong_tab(self):
        cdp = AsyncMock()
        cdp.send_raw.side_effect = [
            {"targetInfo": {"targetId": "target", "type": "page"}},
            RuntimeError("target closed"),
        ]
        with self.assertRaisesRegex(RuntimeError, "target closed"):
            await module.capture_screenshot(daemon(cdp), {}, "session")
        self.assertEqual(cdp.send_raw.await_count, 2)

    async def test_timeout_releases_lock(self):
        cdp = AsyncMock()
        async def stalled(*args, **kwargs):
            await asyncio.sleep(10)
        cdp.send_raw.side_effect = stalled
        d = daemon(cdp)
        old_timeout = module.SCREENSHOT_TIMEOUT
        module.SCREENSHOT_TIMEOUT = 0.01
        try:
            with self.assertRaisesRegex(RuntimeError, "Screenshot timed out"):
                await module.capture_screenshot(d, {}, "session")
            self.assertFalse(d._screenshot_lock.locked())
            await d._screenshot_lock.acquire()
            with self.assertRaisesRegex(RuntimeError, "Screenshot timed out"):
                await module.capture_screenshot(d, {}, "session")
            d._screenshot_lock.release()
        finally:
            module.SCREENSHOT_TIMEOUT = old_timeout

    async def test_parallel_captures_are_serialized(self):
        calls = []

        class CDP:
            async def send_raw(self, method, params=None, session_id=None):
                if method == "Target.getTargetInfo":
                    calls.append(("resolve", session_id))
                    return {"targetInfo": {"targetId": session_id, "type": "page"}}
                if method == "Target.activateTarget":
                    calls.append(("activate", params["targetId"]))
                    await asyncio.sleep(0)
                    return {}
                calls.append(("capture", session_id))
                return {"data": session_id}

        d = daemon(CDP())
        result = await asyncio.gather(
            module.capture_screenshot(d, {}, "first"),
            module.capture_screenshot(d, {}, "second"),
        )
        self.assertEqual(result, [{"data": "first"}, {"data": "second"}])
        self.assertEqual(calls, [
            ("resolve", "first"), ("activate", "first"), ("capture", "first"),
            ("resolve", "second"), ("activate", "second"), ("capture", "second"),
        ])


if __name__ == "__main__":
    unittest.main()
