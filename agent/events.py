import queue
import threading
import time
from collections import deque


class EventHub:
    """Keeps recent events and pushes new ones to every connected viewer."""

    def __init__(self, keep: int = 1000) -> None:
        self._lock = threading.Lock()
        self._history: deque[dict] = deque(maxlen=keep)
        self._subscribers: list[queue.Queue] = []
        self._next_id = 1

    def publish(self, kind: str, **data) -> dict:
        with self._lock:
            event = {"id": self._next_id, "time": time.strftime("%H:%M:%S"), "kind": kind, **data}
            self._next_id += 1
            self._history.append(event)
            for subscriber in self._subscribers:
                subscriber.put(event)
        return event

    def subscribe(self) -> tuple[list[dict], queue.Queue]:
        """Return the history so far and a queue for new events. Both happen under one lock,
        so no event is missed or shown twice."""
        live: queue.Queue = queue.Queue()
        with self._lock:
            replay = list(self._history)
            self._subscribers.append(live)
        return replay, live

    def unsubscribe(self, live: queue.Queue) -> None:
        with self._lock:
            if live in self._subscribers:
                self._subscribers.remove(live)