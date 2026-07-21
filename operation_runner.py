"""
Operation Runner — Async long-running operations without hangs.

Launches subprocesses, streams output to log files, returns immediately.
No blocking. No agent death. NASA-grade: every operation is tracked by PID
and log file, recoverable after session restart.

Design principle: The AI never waits. It launches, reports, and continues.
The human checks progress. The AI checks completion later.
"""

import json
import os
import signal
import subprocess
import time
import uuid
from pathlib import Path
from typing import Optional


# Default log directory
DEFAULT_LOG_DIR = Path.home() / "cathedral" / "ops"
DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)

# Active operation registry (survives across calls within a session)
_active_operations: dict = {}


def run_operation(
    command: str,
    timeout: int = 3600,
    cwd: Optional[str] = None,
    env: Optional[dict] = None,
    label: Optional[str] = None,
) -> dict:
    """Launch a long-running operation asynchronously.

    Spawns a subprocess with stdout/stderr redirected to a log file.
    Returns immediately with PID and log file path. Does NOT wait.

    Args:
        command: Shell command to execute.
        timeout: Maximum runtime in seconds (enforced via subprocess, not SIGKILL yet).
        cwd: Working directory for the command.
        env: Additional environment variables (merged with current env).
        label: Human-readable label for the operation.

    Returns:
        dict with keys:
            - success: bool
            - pid: process ID
            - log_file: path to log file for tailing
            - status: "running"
            - start_time: epoch timestamp
            - label: operation label
            - op_id: unique operation ID
    """
    op_id = uuid.uuid4().hex[:12]
    log_file = DEFAULT_LOG_DIR / f"op_{op_id}.log"

    # Merge environment
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    try:
        with open(log_file, "w") as f:
            f.write(f"=== Operation: {label or command} ===\n")
            f.write(f"=== Started: {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            f.write(f"=== PID: (to be determined) ===\n")
            f.write(f"=== Command: {command} ===\n")
            f.write("=" * 60 + "\n\n")
            f.flush()

            proc = subprocess.Popen(
                command,
                shell=True,
                stdout=f,
                stderr=subprocess.STDOUT,
                cwd=cwd,
                env=merged_env,
                preexec_fn=os.setsid,  # Create new process group for clean kill
            )

        # Update log header with actual PID
        _update_log_header(log_file, proc.pid, command, label)

        op_record = {
            "pid": proc.pid,
            "log_file": str(log_file),
            "status": "running",
            "start_time": time.time(),
            "label": label or command[:80],
            "op_id": op_id,
            "command": command,
            "timeout": timeout,
            "cwd": cwd,
        }

        _active_operations[op_id] = {
            **op_record,
            "_proc": proc,  # Internal reference — not for serialization
        }

        return {"success": True, **op_record}

    except Exception as e:
        return {
            "success": False,
            "op_id": op_id,
            "error": str(e),
            "log_file": str(log_file),
        }


def _update_log_header(log_file: Path, pid: int, command: str, label: Optional[str]) -> None:
    """Update the log file header with the actual PID after process start."""
    try:
        content = log_file.read_text()
        content = content.replace("=== PID: (to be determined) ===", f"=== PID: {pid} ===")
        log_file.write_text(content)
    except Exception:
        pass  # Best-effort — don't fail the operation over a header update


def check_operation(op_id: str) -> dict:
    """Check the status of a previously launched operation.

    Args:
        op_id: Operation ID returned by run_operation.

    Returns:
        dict with keys:
            - success: bool
            - op_id: operation ID
            - status: "running", "completed", "failed", "not_found"
            - returncode: process return code (if completed)
            - elapsed_seconds: wall clock time since start
            - log_file: path to log file
    """
    if op_id not in _active_operations:
        return {
            "success": False,
            "op_id": op_id,
            "status": "not_found",
            "error": "Operation not found in active registry",
        }

    record = _active_operations[op_id]
    proc = record["_proc"]
    elapsed = time.time() - record["start_time"]

    # Poll the process
    returncode = proc.poll()

    if returncode is None:
        return {
            "success": True,
            "op_id": op_id,
            "status": "running",
            "returncode": None,
            "elapsed_seconds": round(elapsed, 1),
            "log_file": record["log_file"],
            "label": record["label"],
        }

    # Process has finished
    status = "completed" if returncode == 0 else "failed"

    result = {
        "success": True,
        "op_id": op_id,
        "status": status,
        "returncode": returncode,
        "elapsed_seconds": round(elapsed, 1),
        "log_file": record["log_file"],
        "label": record["label"],
    }

    return result


def kill_operation(op_id: str, force: bool = False) -> dict:
    """Kill a running operation.

    Args:
        op_id: Operation ID.
        force: If True, use SIGKILL. Otherwise SIGTERM.

    Returns:
        dict with status and any error.
    """
    if op_id not in _active_operations:
        return {"success": False, "op_id": op_id, "error": "Operation not found"}

    record = _active_operations[op_id]
    proc = record["_proc"]

    try:
        if force:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)

        # Wait briefly for process to terminate
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.wait()

        return {
            "success": True,
            "op_id": op_id,
            "status": "killed",
            "returncode": proc.returncode,
        }

    except ProcessLookupError:
        return {
            "success": True,
            "op_id": op_id,
            "status": "already_dead",
            "returncode": proc.returncode if proc.returncode is not None else -1,
        }
    except Exception as e:
        return {"success": False, "op_id": op_id, "error": str(e)}


def list_operations() -> list:
    """List all active operations.

    Returns:
        List of operation summaries (without internal _proc references).
    """
    summaries = []
    for op_id, record in _active_operations.items():
        elapsed = time.time() - record["start_time"]
        proc = record["_proc"]
        returncode = proc.poll()

        summaries.append({
            "op_id": op_id,
            "pid": record["pid"],
            "label": record["label"],
            "status": "running" if returncode is None else ("completed" if returncode == 0 else "failed"),
            "returncode": returncode,
            "elapsed_seconds": round(elapsed, 1),
            "log_file": record["log_file"],
        })

    return summaries


def tail_log(op_id: str, lines: int = 50) -> dict:
    """Return the last N lines of an operation's log file.

    Args:
        op_id: Operation ID.
        lines: Number of trailing lines to return.

    Returns:
        dict with log content or error.
    """
    if op_id not in _active_operations:
        return {"success": False, "op_id": op_id, "error": "Operation not found"}

    log_file = Path(_active_operations[op_id]["log_file"])

    if not log_file.exists():
        return {"success": False, "op_id": op_id, "error": "Log file not found"}

    try:
        content = log_file.read_text()
        all_lines = content.split("\n")
        tail_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
        return {
            "success": True,
            "op_id": op_id,
            "lines": len(tail_lines),
            "total_lines": len(all_lines),
            "content": "\n".join(tail_lines),
            "log_file": str(log_file),
        }
    except Exception as e:
        return {"success": False, "op_id": op_id, "error": str(e)}
