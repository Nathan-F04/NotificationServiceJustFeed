"""
Docstring for notification_service.order_success_worker
"""
from contextlib import asynccontextmanager
import asyncio
import json
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import aio_pika

RABBIT_URL = os.getenv("RABBIT_URL")
EXCHANGE_NAME = "just_feed_exchange"

clients = set()

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Starts rabbit mq task"""
    task = asyncio.create_task(rabbit_mq_listener())
    try:
        yield
    finally:
        task.cancel()

app = FastAPI(lifespan=lifespan)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """Open websocket and keep alive"""
    await ws.accept()
    clients.add(ws)
    try:
        while True:
            await ws.receive_text()  # Keep connection alive
    except WebSocketDisconnect:
        clients.remove(ws)

async def send_notification(message: str):
    """Send payload through open socket"""
    payload = {"type": "notification", "message": message}
    disconnected_clients = set()

    for ws in clients:
        try:
            await ws.send_json(payload)
        except WebSocketDisconnect:
            disconnected_clients.add(ws)
        except Exception as e:
            print(f"Failed to send notification to a client: {e}")
            disconnected_clients.add(ws)

    # Remove all disconnected clients safely
    clients.difference_update(disconnected_clients)

async def rabbit_mq_listener():
    """
    Setup queue, exchange, set binding etc, then wait for messages
    """
    conn = await aio_pika.connect_robust(RABBIT_URL)
    ch = await conn.channel()

    # Declare the topic exchange
    ex = await ch.declare_exchange(EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC)

    # Queue for order events
    queue = await ch.declare_queue("order_events_queue")

    # Bind to all routing keys starting with 'order.'
    await queue.bind(ex, routing_key="order.*")

    print("Listening for order events (routing key: 'order.*')...")

    async with queue.iterator() as q:
        async for msg in q:
            async with msg.process():
                data = json.loads(msg.body)
                print("Order Event:", msg.routing_key, data)
                await send_notification(data)
