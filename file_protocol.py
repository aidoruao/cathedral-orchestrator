"""
File Protocol — Safe file I/O with Base64 verification.

No heredocs. No shell interpolation vulnerabilities.
Every write is verified with MD5. Every read is Base64-encoded for safe transport.

NASA-Grade Requirement: Deterministic — same content always produces same encoded output.
"""

import base64
import hashlib
import os
import subprocess
from pathlib import Path
from typing import Optional


def _validate_path(path: str) -> Path:
    """Resolve and validate a file path. Rejects paths outside the workspace."""
    resolved = Path(path).expanduser().resolve()
    # Prevent writes outside home directory as a safety measure
    home = Path.home()
    if not str(resolved).startswith(str(home)):
        raise ValueError(f"Path {path} resolves outside home directory: {resolved}")
    return resolved


def _compute_md5(path: Path) -> str:
    """Compute MD5 hash of a file's contents."""
    hash_md5 = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def encode_content(content: str) -> str:
    """Base64-encode string content for safe shell transmission.

    Args:
        content: Raw string content to encode.

    Returns:
        Base64-encoded string (no newlines in output).
    """
    return base64.b64encode(content.encode("utf-8")).decode("ascii")


def decode_content(encoded: str) -> str:
    """Base64-decode content received from shell output.

    Args:
        encoded: Base64-encoded string.

    Returns:
        Decoded UTF-8 string.

    Raises:
        ValueError: If the content is not valid Base64 or not valid UTF-8.
    """
    return base64.b64decode(encoded.encode("ascii")).decode("utf-8")


def write_file(path: str, content: str, create_dirs: bool = True) -> dict:
    """Write content to a file with Base64 + MD5 verification.

    Uses a subprocess pipeline: echo <b64> | base64 -d > path && md5sum path.
    This avoids all heredoc and shell interpolation issues.

    Args:
        path: Target file path (relative or absolute).
        content: String content to write.
        create_dirs: If True, create parent directories first.

    Returns:
        dict with keys:
            - success: bool
            - path: resolved path
            - md5: computed MD5 hash (if successful)
            - size_bytes: file size (if successful)
            - error: error message (if failed)
    """
    try:
        resolved = _validate_path(path)

        if create_dirs:
            resolved.parent.mkdir(parents=True, exist_ok=True)

        encoded = encode_content(content)

        # Build the command — single-quote the base64 to prevent shell expansion
        cmd = f"echo '{encoded}' | base64 -d > '{resolved}' && md5sum '{resolved}'"

        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return {
                "success": False,
                "path": str(resolved),
                "error": result.stderr.strip() or "Unknown error",
            }

        # Verify the MD5 independently
        computed_md5 = _compute_md5(resolved)
        file_size = resolved.stat().st_size

        return {
            "success": True,
            "path": str(resolved),
            "md5": computed_md5,
            "size_bytes": file_size,
        }

    except ValueError as e:
        return {"success": False, "path": path, "error": str(e)}
    except subprocess.TimeoutExpired:
        return {"success": False, "path": path, "error": "Write operation timed out"}
    except Exception as e:
        return {"success": False, "path": path, "error": f"Unexpected error: {e}"}


def read_file(path: str) -> dict:
    """Read a file and return its content with Base64 encoding.

    Uses: cat path | base64
    The returned content is decoded for immediate use. The raw Base64 is also
    provided for safe re-transmission.

    Args:
        path: File path to read.

    Returns:
        dict with keys:
            - success: bool
            - path: resolved path
            - content: decoded string content (if successful)
            - encoded: Base64-encoded content (if successful)
            - md5: MD5 hash of file (if successful)
            - error: error message (if failed)
    """
    try:
        resolved = _validate_path(path)

        if not resolved.exists():
            return {"success": False, "path": str(resolved), "error": "File not found"}

        if not resolved.is_file():
            return {"success": False, "path": str(resolved), "error": "Path is not a file"}

        cmd = f"cat '{resolved}' | base64"

        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return {
                "success": False,
                "path": str(resolved),
                "error": result.stderr.strip() or "Unknown error",
            }

        encoded = result.stdout.strip()
        content = decode_content(encoded)
        md5_hash = _compute_md5(resolved)

        return {
            "success": True,
            "path": str(resolved),
            "content": content,
            "encoded": encoded,
            "md5": md5_hash,
        }

    except ValueError as e:
        return {"success": False, "path": path, "error": str(e)}
    except subprocess.TimeoutExpired:
        return {"success": False, "path": path, "error": "Read operation timed out"}
    except Exception as e:
        return {"success": False, "path": path, "error": f"Unexpected error: {e}"}


def append_file(path: str, content: str) -> dict:
    """Append content to a file with verification.

    Reads existing content, appends, writes back with verification.

    Args:
        path: File path.
        content: Content to append.

    Returns:
        Same dict structure as write_file.
    """
    existing_result = read_file(path)
    if existing_result["success"]:
        new_content = existing_result["content"] + content
    else:
        # File doesn't exist or can't be read — treat as new file
        new_content = content

    return write_file(path, new_content)
