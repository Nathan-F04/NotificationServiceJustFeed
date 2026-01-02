"""Test File for Notification Service"""
from unittest.mock import AsyncMock, patch
import asyncio
import json
import pytest
from notification_service.notification import send_notification, clients, rabbit_mq_listener

def test_websocket_connection(client):
    """Test websocket"""

    with client.websocket_connect("/ws") as websocket:
        # Send a message to keep the loop alive
        websocket.send_text("ping")
        assert len(clients) == 1
        websocket.close()

    # After disconnect, client should be removed
    assert len(clients) == 0

class WebSocketSendError(RuntimeError):
    """Simulate an error"""

class FakeWebSocket:
    """Class to create websockets, set if they failed, or append to sent list"""
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    #Used to simulate the read send_json for testing
    async def send_json(self, data):
        """Checks for fail and apends data if success"""
        if self.fail:
            raise WebSocketSendError("WebSocket failed")
        self.sent.append(data)

@pytest.mark.asyncio
async def test_send_notification_sends_to_all_clients():
    """Send a notification for multiple clients to receive"""
    ws1 = FakeWebSocket()
    ws2 = FakeWebSocket()

    clients.add(ws1)
    clients.add(ws2)

    await send_notification("Success")

    expected_payload = [{"type": "notification", "message": "Success"}]
    assert ws1.sent == expected_payload
    assert ws2.sent == expected_payload

@pytest.mark.asyncio
async def test_send_notification_removes_failed_client():
    """Send notification with one failure"""
    ws1 = FakeWebSocket()
    ws2 = FakeWebSocket(fail=True)

    clients.add(ws1)
    clients.add(ws2)

    await send_notification("Success")

    assert ws1.sent == [{"type": "notification", "message": "Success"}]
    assert ws2 not in clients

class FakeQueueIterator:
    """Simulates queue.iterator()"""
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

class FakeProcessCM:
    """Fake async context manager for msg.process()"""
    async def __aenter__(self):
        return None

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

class FakeMessage:
    """Fake message"""
    def __init__(self, body, routing_key):
        self.body = body
        self.routing_key = routing_key

    def process(self):
        """Fake proccess"""
        return FakeProcessCM()


class FakeQueue:
    """Fake queue"""
    def __init__(self, messages):
        self._messages = messages

    async def bind(self, *args, **kwargs):
        """Bind"""
        return None

    def iterator(self):
        """Iterator"""
        return FakeQueueIterator(self._messages)

class FakeChannel:
    """Fake channel"""
    def __init__(self, messages_by_queue):
        self._messages_by_queue = messages_by_queue

    async def declare_exchange(self, *args, **kwargs):
        """Exchange object isn't used in test"""
        return self

    async def declare_queue(self, queue_name, *args, **kwargs):
        """Declare queue - return messages specific to this queue"""
        messages = self._messages_by_queue.get(queue_name, [])
        return FakeQueue(messages)

class FakeConnection:
    """Fake connection"""
    def __init__(self, messages_by_queue):
        self._messages_by_queue = messages_by_queue
        self._channel = FakeChannel(messages_by_queue)

    async def channel(self):
        """Channel"""
        return self._channel

@pytest.mark.asyncio
async def test_rabbit_listener():
    """Set up fake message"""
    fake_msg = FakeMessage(body=json.dumps("Success").encode(), routing_key="order.success")

    async def fake_connect(*args, **kwargs):
        """Async function to patch connect_robust"""
        # Only order queue gets the message
        return FakeConnection({
            "order_events_queue": [fake_msg],
            "account_events_queue": [],
        })

    #Replace objects here
    with patch("notification_service.notification.aio_pika.connect_robust", new=fake_connect), \
         patch("notification_service.notification.send_notification", new_callable=AsyncMock) as mock_send:

        # Run listener as a task
        task = asyncio.create_task(rabbit_mq_listener())
        # Allow listener to pick up message
        await asyncio.sleep(0.1)
        task.cancel()
        #Cancel the task, let the error be caught after the await
        try:
            await task
        except asyncio.CancelledError:
            pass

        mock_send.assert_called_once_with("Success")
