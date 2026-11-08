import asyncio
import unittest

from cdp_use.client import CDPClient


class FakeSocket:
    def __init__(self, fail=False):
        self.fail = fail

    async def send(self, message):
        if self.fail:
            raise RuntimeError("send failed")


class CDPCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancellation_clears_pending_request(self):
        client = CDPClient("ws://unused")
        client.ws = FakeSocket()
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(client.send_raw("Page.captureScreenshot"), timeout=0.01)
        self.assertEqual(client.pending_requests, {})

    async def test_send_failure_clears_pending_request(self):
        client = CDPClient("ws://unused")
        client.ws = FakeSocket(fail=True)
        with self.assertRaisesRegex(RuntimeError, "send failed"):
            await client.send_raw("Page.captureScreenshot")
        self.assertEqual(client.pending_requests, {})


if __name__ == "__main__":
    unittest.main()
