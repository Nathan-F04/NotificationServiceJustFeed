"""Test File for Notification Service"""
import pytest
import asyncio
from notification_service.order_success_worker import send_notification, clients, rabbit_mq_listener
import json
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
def test_websocket_connection(client):
    # Ensure clients set is empty at the start
    clients.clear()

    with client.websocket_connect("/ws") as websocket:
        # Send a message to keep the loop alive (like frontend ping)
        websocket.send_text("ping")

        # Check that the WebSocket was added to clients
        assert len(clients) == 1

        # Close the WebSocket
        websocket.close()

    # After disconnect, client should be removed
    assert len(clients) == 0

# -----------------------------
# Fake WebSocket for testing
# -----------------------------
class FakeWebSocket:
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail  # simulate a failure
    async def send_json(self, data):
        if self.fail:
            raise Exception("WebSocket failed")  # simulate disconnected client
        self.sent.append(data)

# -----------------------------
# Test sending notification to all clients
# -----------------------------
@pytest.mark.asyncio
async def test_send_notification_sends_to_all_clients():
    ws1 = FakeWebSocket()
    ws2 = FakeWebSocket()

    clients.clear()
    clients.add(ws1)
    clients.add(ws2)

    await send_notification("Success")

    expected_payload = [{"type": "notification", "message": "Success"}]
    assert ws1.sent == expected_payload
    assert ws2.sent == expected_payload

# -----------------------------
# Test that failed WebSocket is removed from clients
# -----------------------------
@pytest.mark.asyncio
async def test_send_notification_removes_failed_client():
    ws1 = FakeWebSocket()
    ws2 = FakeWebSocket(fail=True)  # this one will raise an exception

    clients.clear()
    clients.add(ws1)
    clients.add(ws2)

    await send_notification("Test")

    # ws1 should still have received the message
    assert ws1.sent == [{"type": "notification", "message": "Test"}]
    # ws2 failed and should be removed from clients
    assert ws2 not in clients

# -----------------------------
# Fake async iterator for queue
# -----------------------------
class FakeQueueIterator:
    def __init__(self, messages):
        self._messages = messages

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    def __aiter__(self):
        async def gen():
            for msg in self._messages:
                yield msg
        return gen()

# -----------------------------
# Fake async context manager for msg.process()
# -----------------------------
class FakeProcessCM:
    async def __aenter__(self):
        return None

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

# -----------------------------
# Fake message
# -----------------------------
class FakeMessage:
    def __init__(self, body, routing_key):
        self.body = body
        self.routing_key = routing_key

    def process(self):
        return FakeProcessCM()

# -----------------------------
# Fake queue
# -----------------------------
class FakeQueue:
    def __init__(self, messages):
        self._messages = messages

    async def bind(self, *args, **kwargs):
        return None  # ✅ must be async because listener does `await queue.bind(...)`

    def iterator(self):
        return FakeQueueIterator(self._messages)

# -----------------------------
# Fake channel
# -----------------------------
class FakeChannel:
    def __init__(self, messages):
        self._messages = messages

    async def declare_exchange(self, *args, **kwargs):
        return self  # exchange object isn’t used in test

    async def declare_queue(self, *args, **kwargs):
        return FakeQueue(self._messages)

# -----------------------------
# Fake connection
# -----------------------------
class FakeConnection:
    def __init__(self, messages):
        self._messages = messages
        self._channel = FakeChannel(messages)

    async def channel(self):
        return self._channel

# -----------------------------
# The test
# -----------------------------
@pytest.mark.asyncio
async def test_rabbit_listener_calls_send_notification():
    # --- Setup fake message ---
    fake_msg = FakeMessage(body=json.dumps({"order_id": 123}).encode(), routing_key="order.success")

    # --- Async function to patch connect_robust ---
    async def fake_connect(*args, **kwargs):
        return FakeConnection([fake_msg])

    # --- Patch connect_robust and send_notification ---
    with patch("notification_service.order_success_worker.aio_pika.connect_robust", new=fake_connect), \
         patch("notification_service.order_success_worker.send_notification", new_callable=AsyncMock) as mock_send:

        # Run listener as a task
        task = asyncio.create_task(rabbit_mq_listener())
        await asyncio.sleep(0.1)  # allow listener to pick up message
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Assert send_notification was called correctly
        mock_send.assert_called_once_with({"order_id": 123})

