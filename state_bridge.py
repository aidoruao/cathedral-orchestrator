"""
State Bridge — Human/AI shared viewport. No hidden state.

Enforces the invariant: what the human sees = what the AI knows.
All state is file-backed — survives session death, recoverable after restart.

NASA-Grade Requirement: No hidden state. The AI must not maintain internal state
that diverges from what the human can inspect. Every state transition is logged.

Design principle: If the human can't see it, the AI can't depend on it.
"""

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any


DEFAULT_STATE_DIR = Path.home() / "cathedral" / "state"
DEFAULT_STATE_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class SharedState:
    """A single shared state value with audit trail.

    Every mutation records: who changed it, when, what the old value was,
    and why. This is the "glass box" — the human can inspect every state
    transition.
    """

    key: str
    value: Any
    history: list = field(default_factory=list)  # List of (timestamp, actor, old_value, reason)
    created_at: float = field(default_factory=time.time)


@dataclass
class StateBridge:
    """Human/AI shared state manager.

    All state is stored in JSON files under ~/cathedral/state/.
    The human can inspect any file. The AI reads/writes through this bridge.

    Usage:
        bridge = StateBridge()
        bridge.set("build.status", "running", actor="ai", reason="Launched scons build")
        status = bridge.get("build.status")  # "running"
        history = bridge.history("build.status")  # full mutation log
    """

    state_dir: Path = DEFAULT_STATE_DIR
    _cache: dict = field(default_factory=dict)

    def _state_path(self, key: str) -> Path:
        """Get the file path for a state key.

        Keys with dots become nested directories for organization.
        E.g., "build.status" -> state_dir/build/status.json
        """
        parts = key.split(".")
        if len(parts) == 1:
            return self.state_dir / f"{key}.json"
        else:
            path = self.state_dir
            for part in parts[:-1]:
                path = path / part
            path.mkdir(parents=True, exist_ok=True)
            return path / f"{parts[-1]}.json"

    def get(self, key: str, default: Any = None) -> Any:
        """Get a shared state value.

        Args:
            key: Dot-separated state key (e.g., "build.status").
            default: Value to return if key doesn't exist.

        Returns:
            The current value, or default.
        """
        # Check cache first
        if key in self._cache:
            return self._cache[key].value

        path = self._state_path(key)
        if not path.exists():
            return default

        try:
            with open(path) as f:
                data = json.load(f)
            state = SharedState(
                key=key,
                value=data["value"],
                history=data.get("history", []),
                created_at=data.get("created_at", time.time()),
            )
            self._cache[key] = state
            return state.value
        except (json.JSONDecodeError, KeyError):
            return default

    def set(self, key: str, value: Any, actor: str = "ai", reason: str = "") -> SharedState:
        """Set a shared state value with audit trail.

        Args:
            key: Dot-separated state key.
            value: New value (must be JSON-serializable).
            actor: Who is making the change ("human", "ai", "system").
            reason: Why the change is being made.

        Returns:
            SharedState object with updated history.
        """
        old_value = self.get(key)
        timestamp = time.time()

        # Load or create state
        if key in self._cache:
            state = self._cache[key]
        else:
            state = SharedState(key=key, value=None)

        # Record mutation
        state.history.append({
            "timestamp": timestamp,
            "actor": actor,
            "old_value": old_value,
            "new_value": value,
            "reason": reason,
        })

        state.value = value
        self._cache[key] = state

        # Persist to disk
        path = self._state_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump({
                "key": key,
                "value": value,
                "history": state.history,
                "created_at": state.created_at,
                "updated_at": timestamp,
            }, f, indent=2, ensure_ascii=False)

        return state

    def history(self, key: str) -> list:
        """Get the full mutation history for a state key.

        Args:
            key: Dot-separated state key.

        Returns:
            List of mutation records (timestamp, actor, old_value, new_value, reason).
        """
        state = self._cache.get(key)
        if state:
            return state.history

        path = self._state_path(key)
        if path.exists():
            try:
                with open(path) as f:
                    data = json.load(f)
                return data.get("history", [])
            except (json.JSONDecodeError, KeyError):
                pass

        return []

    def delete(self, key: str, actor: str = "ai", reason: str = "") -> bool:
        """Delete a shared state key.

        Args:
            key: Dot-separated state key.
            actor: Who is making the deletion.
            reason: Why.

        Returns:
            True if deleted, False if key didn't exist.
        """
        if key in self._cache:
            # Record deletion in history before removing
            self.set(key, None, actor=actor, reason=f"Deletion: {reason}")
            del self._cache[key]

        path = self._state_path(key)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_keys(self, prefix: str = "") -> list:
        """List all state keys, optionally filtered by prefix.

        Args:
            prefix: Optional prefix to filter by (e.g., "build").

        Returns:
            List of state key strings.
        """
        keys = []
        base = self.state_dir / prefix if prefix else self.state_dir

        if not base.exists():
            return []

        for root, dirs, files in os.walk(base):
            for f in files:
                if f.endswith(".json"):
                    rel = Path(root).relative_to(self.state_dir)
                    key = str(rel / f[:-5]) if str(rel) != "." else f[:-5]
                    keys.append(key)

        return sorted(keys)

    def snapshot(self) -> dict:
        """Return a complete snapshot of all shared state.

        Returns:
            dict mapping all keys to their current values.
        """
        snap = {}
        for key in self.list_keys():
            snap[key] = self.get(key)
        return snap

    def reset(self) -> None:
        """Clear all state. Use with caution — requires explicit human confirmation."""
        self._cache.clear()
        for key in self.list_keys():
            path = self._state_path(key)
            if path.exists():
                path.unlink()
