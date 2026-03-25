from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Optional

from app.monitoring.metrics import MetricsCollector

logger = logging.getLogger(__name__)


class HealthCheck:
    """Lightweight HTTP health check server.

    GET /health  -> 200 {"status": "ok", "uptime": ...}
    GET /metrics -> 200 Prometheus text format
    """

    def __init__(self, metrics: MetricsCollector, port: int = 8080) -> None:
        self._metrics = metrics
        self._port = port
        self._start_time = time.time()
        self._server: Optional[asyncio.Server] = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "0.0.0.0", self._port)
        logger.info("health check server started on :%d", self._port)

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            logger.info("health check server stopped")

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            data = await asyncio.wait_for(reader.read(4096), timeout=5.0)
            request = data.decode("utf-8", errors="replace")
            path = self._parse_path(request)

            if path == "/health":
                body = json.dumps({
                    "status": "ok",
                    "uptime_seconds": round(time.time() - self._start_time, 1),
                })
                response = self._http_response(200, body, "application/json")
            elif path == "/metrics":
                body = self._metrics.to_prometheus()
                response = self._http_response(200, body, "text/plain")
            elif path == "/status":
                body = json.dumps(self._metrics.snapshot(), indent=2)
                response = self._http_response(200, body, "application/json")
            else:
                response = self._http_response(404, "Not Found", "text/plain")

            writer.write(response.encode("utf-8"))
            await writer.drain()
        except Exception:
            logger.debug("health check request error", exc_info=True)
        finally:
            writer.close()

    def _parse_path(self, request: str) -> str:
        parts = request.split(" ")
        if len(parts) >= 2:
            return parts[1].split("?")[0]
        return "/"

    def _http_response(self, status: int, body: str, content_type: str) -> str:
        status_text = {200: "OK", 404: "Not Found", 500: "Internal Server Error"}.get(status, "")
        return (
            f"HTTP/1.1 {status} {status_text}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
            f"{body}"
        )
