"""Test doubles and deterministic fixtures for rate limiting tests (S2.4)."""

from __future__ import annotations

import math
import time


class FakeValkey:
    """In-memory test double executing Valkey sliding-window Lua semantics in Python."""

    def __init__(self) -> None:
        """Initialize empty key-value store and expiration tracker."""
        self._data: dict[str, int] = {}
        self._expires: dict[str, float] = {}
        self._fixed_time: float | None = None

    def set_time(self, timestamp: float | None) -> None:
        """Freeze or unfreeze simulated Valkey TIME clock."""
        self._fixed_time = timestamp

    def get_time(self) -> float:
        """Return current simulated or real timestamp."""
        if self._fixed_time is not None:
            return self._fixed_time
        return time.time()

    def _purge_expired(self, now: float) -> None:
        """Purge keys whose PEXPIRE has lapsed."""
        for key in list(self._expires.keys()):
            if self._expires[key] <= now:
                self._data.pop(key, None)
                self._expires.pop(key, None)

    def _handle_reset(self, prefix: str, script_args: list[object]) -> list[int]:
        """Emulate Lua reset script clearing sliding-window bucket keys."""
        window_s = int(str(script_args[0])) if script_args else 60
        now_sec = self.get_time()
        if len(script_args) > 1 and script_args[1]:
            now_sec = float(str(script_args[1]))

        window_idx = math.floor(now_sec / window_s)
        for offset in (0, -1, 1):
            key = f"{prefix}:{window_idx + offset}"
            self._data.pop(key, None)
            self._expires.pop(key, None)

        for k in list(self._data.keys()):
            if k.startswith(f"{prefix}:"):
                self._data.pop(k, None)
                self._expires.pop(k, None)
        return [1, 0, 0]

    def _handle_hit(self, prefix: str, script_args: list[object]) -> list[int]:
        """Emulate Lua sliding-window hit script incrementing bucket and testing threshold."""
        limit = int(str(script_args[0]))
        window_s = int(str(script_args[1]))

        if len(script_args) > 2 and script_args[2] and float(str(script_args[2])) > 0:
            now_sec = float(str(script_args[2]))
        else:
            now_sec = self.get_time()

        self._purge_expired(now_sec)

        window_idx = math.floor(now_sec / window_s)
        curr_key = f"{prefix}:{window_idx}"
        prev_key = f"{prefix}:{window_idx - 1}"

        curr_count = self._data.get(curr_key, 0) + 1
        self._data[curr_key] = curr_count
        if curr_count == 1:
            self._expires[curr_key] = now_sec + (window_s * 2)

        prev_count = self._data.get(prev_key, 0)
        elapsed = now_sec - (window_idx * window_s)
        weight = max(0.0, min(1.0, (window_s - elapsed) / window_s))
        total = math.floor(prev_count * weight) + curr_count

        if total <= limit:
            return [1, limit - total, 0]

        retry_after = max(1, math.ceil(window_s - elapsed))
        return [0, 0, retry_after]

    async def eval(self, script: str, numkeys: int, *args: object) -> list[int]:
        """Execute Lua script emulation for sliding-window rate limit and reset."""
        keys: list[str] = [str(args[i]) for i in range(numkeys)]
        script_args: list[object] = list(args[numkeys:])

        prefix = keys[0] if keys else str(script_args[0])

        if "DEL" in script and "INCR" not in script:
            return self._handle_reset(prefix, script_args)

        return self._handle_hit(prefix, script_args)
