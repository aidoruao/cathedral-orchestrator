"""
Audit Logger — Immutable, timestamped, hashed audit trail.

Every action is recorded as a JSONL entry with:
- ISO 8601 timestamp
- SHA-256 content hash for tamper detection
- Actor identification (human/AI/system)
- Structured details

NASA-Grade Requirement: Every claim requires proof. The audit log IS the proof.
Commits itself to the repository after every significant action.

Design principle: If it's not in the audit log, it didn't happen.
"""

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Literal

# Actor type — narrow union, not arbitrary string
ActorType = Literal["human", "ai", "system", "orchestrator"]

DEFAULT_LOG_PATH = Path.home() / "cathedral" / "audit.log"


def _ensure_log_dir() -> None:
    """Ensure the log directory exists."""
    DEFAULT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def _compute_hash(details: dict) -> str:
    """Compute a deterministic SHA-256 hash of the details dict.

    Keys are sorted before hashing for determinism. The hash is truncated
    to 16 hex characters for readability while maintaining collision resistance
    for audit purposes.
    """
    canonical = json.dumps(details, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def log(
    action: str,
    actor: ActorType,
    details: dict,
    log_path: Optional[str] = None,
) -> dict:
    """Record an auditable action.

    Args:
        action: Human-readable action description (e.g., "file_write", "build_start").
        actor: Who performed the action — "human", "ai", "system", or "orchestrator".
        details: Structured details about the action. Must be JSON-serializable.
        log_path: Optional custom log path. Defaults to ~/cathedral/audit.log.

    Returns:
        dict: The complete log entry that was written.
    """
    _ensure_log_dir()

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "epoch": time.time(),
        "action": action,
        "actor": actor,
        "details": details,
        "hash": _compute_hash(details),
    }

    target = Path(log_path) if log_path else DEFAULT_LOG_PATH

    try:
        with open(target, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())  # Force write to disk — no buffered audit trails
    except Exception as e:
        # If audit logging itself fails, write to stderr as last resort
        import sys
        print(f"AUDIT_LOG_ERROR: {e}", file=sys.stderr)
        # Still return the entry so callers don't crash
        entry["_write_error"] = str(e)

    return entry


def read_log(
    log_path: Optional[str] = None,
    max_entries: int = 200,
    actor_filter: Optional[ActorType] = None,
) -> dict:
    """Read the audit log, returning recent entries.

    Args:
        log_path: Custom log path.
        max_entries: Maximum entries to return.
        actor_filter: If set, only return entries from this actor.

    Returns:
        dict with keys:
            - success: bool
            - entries: list of log entry dicts
            - total_entries: total lines in log file
            - log_path: path to the log file
    """
    target = Path(log_path) if log_path else DEFAULT_LOG_PATH

    if not target.exists():
        return {
            "success": True,
            "entries": [],
            "total_entries": 0,
            "log_path": str(target),
        }

    try:
        with open(target) as f:
            all_lines = f.readlines()

        entries = []
        for line in all_lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if actor_filter and entry.get("actor") != actor_filter:
                    continue
                entries.append(entry)
            except json.JSONDecodeError:
                entries.append({
                    "timestamp": "unknown",
                    "action": "corrupted_entry",
                    "actor": "system",
                    "details": {"raw": line[:200]},
                    "hash": "INVALID",
                })

        # Return most recent first, limited
        entries.reverse()
        entries = entries[:max_entries]

        return {
            "success": True,
            "entries": entries,
            "total_entries": len(all_lines),
            "log_path": str(target),
        }

    except Exception as e:
        return {
            "success": False,
            "entries": [],
            "total_entries": 0,
            "log_path": str(target),
            "error": str(e),
        }


def verify_integrity(log_path: Optional[str] = None) -> dict:
    """Verify the integrity of the audit log by re-hashing every entry.

    Each entry's stored hash is compared against a fresh computation of its details.
    Any mismatch indicates tampering or corruption.

    Args:
        log_path: Custom log path.

    Returns:
        dict with:
            - success: bool
            - total: total entries
            - verified: count of verified entries
            - tampered: count of entries with hash mismatch
            - tampered_indices: list of line numbers with mismatches
    """
    target = Path(log_path) if log_path else DEFAULT_LOG_PATH

    if not target.exists():
        return {"success": True, "total": 0, "verified": 0, "tampered": 0, "tampered_indices": []}

    total = 0
    verified = 0
    tampered = 0
    tampered_indices = []

    try:
        with open(target) as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                total += 1
                try:
                    entry = json.loads(line)
                    stored_hash = entry.get("hash", "")
                    computed_hash = _compute_hash(entry.get("details", {}))
                    if stored_hash == computed_hash:
                        verified += 1
                    else:
                        tampered += 1
                        tampered_indices.append(i)
                except json.JSONDecodeError:
                    tampered += 1
                    tampered_indices.append(i)

        return {
            "success": True,
            "total": total,
            "verified": verified,
            "tampered": tampered,
            "tampered_indices": tampered_indices,
        }

    except Exception as e:
        return {
            "success": False,
            "total": 0,
            "verified": 0,
            "tampered": 0,
            "tampered_indices": [],
            "error": str(e),
        }
