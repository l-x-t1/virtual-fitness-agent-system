from __future__ import annotations

from collections import Counter, defaultdict
from threading import RLock


class LocalMetrics:
    def __init__(self):
        self._lock = RLock()
        self._counters: Counter[str] = Counter()
        self._timings: dict[str, list[float]] = defaultdict(list)

    def increment(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counters[name] += value

    def timing(self, name: str, milliseconds: float) -> None:
        with self._lock:
            self._timings[name].append(max(0.0, float(milliseconds)))

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "timings": {
                    name: {
                        "count": len(values),
                        "average_ms": round(sum(values) / len(values), 3) if values else 0,
                        "max_ms": round(max(values), 3) if values else 0,
                    }
                    for name, values in self._timings.items()
                },
            }


metrics = LocalMetrics()
