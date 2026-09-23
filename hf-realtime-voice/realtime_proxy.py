"""Fixed-target, same-origin relay: Docker hostnames never reach the browser."""
import asyncio
import contextlib
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import WebSocket, WebSocketDisconnect
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed


def pool_url(target: str) -> str:
    parts = urlsplit(target)
    if parts.scheme not in {"ws", "wss"} or not parts.hostname:
        raise ValueError("SPEECH_TO_SPEECH_URL must be an absolute ws:// or wss:// URL")
    return urlunsplit(("https" if parts.scheme == "wss" else "http", parts.netloc, "/v1/pool", "", ""))


async def backend_ready(target: str) -> bool:
    if not target:
        return False
    try:
        async with httpx.AsyncClient(timeout=2, trust_env=False) as client:
            response = await client.get(pool_url(target))
            return response.status_code == 200
    except (httpx.HTTPError, ValueError):
        return False


async def relay(websocket: WebSocket, target: str) -> None:
    # This is a local demo, not an arbitrary outbound WebSocket proxy.
    origin = websocket.headers.get("origin")
    if origin and urlsplit(origin).netloc != websocket.headers.get("host"):
        await websocket.close(code=1008, reason="Use the demo's own origin")
        return
    await websocket.accept()
    if not target:
        await websocket.close(code=1013, reason="Speech backend is not configured")
        return
    tasks = []
    try:
        async with connect(target, open_timeout=10, close_timeout=3, max_size=8 * 1024 * 1024, proxy=None) as upstream:
            async def upload():
                while True:
                    message = await websocket.receive()
                    if message["type"] == "websocket.disconnect":
                        return
                    data = message.get("text")
                    if data is None:
                        data = message.get("bytes")
                    if data is not None:
                        await upstream.send(data)

            async def download():
                async for message in upstream:
                    if isinstance(message, str):
                        await websocket.send_text(message)
                    else:
                        await websocket.send_bytes(message)

            tasks = [asyncio.create_task(upload()), asyncio.create_task(download())]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                task.result()
    except WebSocketDisconnect:
        pass
    except Exception:
        # Never return target URLs, auth query strings or exception internals.
        with contextlib.suppress(RuntimeError, WebSocketDisconnect):
            await websocket.send_json({"type": "error", "error": {
                "type": "server_error", "code": "backend_unavailable",
                "message": "Speech backend unavailable or busy. Check its logs and try again."
            }})
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        with contextlib.suppress(RuntimeError, WebSocketDisconnect):
            await websocket.close()
