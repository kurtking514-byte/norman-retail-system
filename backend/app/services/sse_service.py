"""
In-process pub/sub for Server-Sent Events (SSE).

Provides a lightweight ``SSEManager`` singleton that maintains a set of
per-client ``asyncio.Queue`` instances, fed by the existing message-logging
and thread-state code paths.  No external message broker (Redis, RabbitMQ,
etc.) is introduced — this is purely in-process, consistent with the
project's SQLite / single-instance scale.

Usage
-----
On the backend side (e.g. from ``messenger_service.log_conversation``
or ``thread_state_service.update_thread_state``)::

    from app.services.sse_service import sse_manager
    await sse_manager.emit({...})

On the endpoint side (in the FastAPI route)::

    from app.services.sse_service import sse_manager
    # sse_manager.subscribe() returns an asyncio.Queue
    # sse_manager.unsubscribe(queue) cleans up on disconnect
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class SSEManager:
    """Simple in-process pub/sub manager for SSE events.

    Attributes
    ----------
    _queues : set[asyncio.Queue]
        All currently connected client queues.
    """

    def __init__(self) -> None:
        self._queues: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue:
        """Create a new queue for a connected client.

        Returns
        -------
        asyncio.Queue
            An unbounded queue that will receive event dicts.
        """
        queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._queues.add(queue)
        logger.debug("SSE client subscribed (total: %d)", len(self._queues))
        return queue

    async def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Remove a client's queue (on disconnect)."""
        async with self._lock:
            self._queues.discard(queue)
        logger.debug("SSE client unsubscribed (total: %d)", len(self._queues))

    async def emit(self, event: dict[str, Any]) -> None:
        """Publish an event to all connected clients.

        Parameters
        ----------
        event : dict
            The event payload.  Must be JSON-serializable.
        """
        async with self._lock:
            queues = list(self._queues)

        dead_queues: list[asyncio.Queue] = []
        for queue in queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Unbounded queue — should never be full, but guard anyway.
                logger.warning("SSE queue full, dropping event")
            except Exception:
                logger.exception("Error putting event on SSE queue")
                dead_queues.append(queue)

        if dead_queues:
            async with self._lock:
                for q in dead_queues:
                    self._queues.discard(q)

    @property
    def client_count(self) -> int:
        return len(self._queues)


# Module-level singleton — import and use directly.
sse_manager = SSEManager()
