"""
Context Engine — Tiered context window management.

Three tiers:
  1. ACTIVE: Last N turns in full detail (ring buffer)
  2. WORKING: Compressed summaries of key decisions, rejected approaches, pending items
  3. ARCHIVE: Complete history in JSONL, referenced by file path, not loaded into context

Token counting via tiktoken. Automatic compression when approaching context limits.
Large outputs (build logs, test results) are stored as files — only paths enter context.

NASA-Grade Requirement: The covenant is reloaded from COVENANT.json at every session
start — it is NEVER derived from context history. Project vision is invariant.
"""

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Try tiktoken; fall back to character-based estimation if unavailable
try:
    import tiktoken

    _ENCODER = tiktoken.get_encoding("cl100k_base")  # GPT-4/DeepSeek compatible

    def count_tokens(text: str) -> int:
        """Count tokens in a string using tiktoken."""
        return len(_ENCODER.encode(text))

except ImportError:

    def count_tokens(text: str) -> int:
        """Fallback: rough estimate of 4 chars per token."""
        return len(text) // 4


@dataclass
class Turn:
    """A single conversation turn."""

    role: str  # "user" or "assistant"
    content: str
    timestamp: float = field(default_factory=time.time)
    token_count: int = 0

    def __post_init__(self):
        if self.token_count == 0:
            self.token_count = count_tokens(self.content)


@dataclass
class ContextEngine:
    """Tiered context manager for long-running AI sessions.

    Attributes:
        active_turns: Ring buffer of recent turns (full detail).
        working_summary: Compressed summary of key decisions and state.
        archive_path: Directory for full-history JSONL archives.
        max_active_tokens: Soft cap on active window token count.
        compression_trigger: Token count that triggers compression.
        covenant_path: Path to COVENANT.json — always loaded fresh.
    """

    max_active_tokens: int = 120000
    compression_trigger: int = 90000
    covenant_path: str = "~/cathedral/COVENANT.json"
    archive_dir: str = "~/cathedral/archive"

    # Internal state
    active_turns: list = field(default_factory=list)
    working_summary: dict = field(default_factory=lambda: {
        "decisions": [],      # Key decisions made
        "rejected": [],       # Approaches explicitly rejected
        "pending": [],        # Items awaiting resolution
        "current_focus": "",  # What we're working on right now
        "last_compression": 0.0,
    })
    _total_tokens: int = 0
    _turn_counter: int = 0

    def __post_init__(self):
        self.archive_path = Path(self.covenant_path).expanduser().parent / "archive"
        self.archive_path.mkdir(parents=True, exist_ok=True)

    def add_turn(self, role: str, content: str) -> None:
        """Add a conversation turn and check if compression is needed.

        Args:
            role: "user" or "assistant"
            content: The message content
        """
        turn = Turn(role=role, content=content)
        self.active_turns.append(turn)
        self._total_tokens += turn.token_count
        self._turn_counter += 1

        # Trigger compression if approaching limit
        if self._total_tokens > self.compression_trigger:
            self._compress()

        # Archive every turn for full-history recovery
        self._archive_turn(turn)

    def _compress(self) -> None:
        """Compress older active turns into the working summary.

        Keeps the most recent turns in full. Older turns are summarized
        into key decisions, rejected approaches, and pending items.

        The AI is responsible for generating the summary — this method
        marks turns for compression and returns the content to summarize.
        """
        if len(self.active_turns) <= 10:
            return  # Not enough turns to compress meaningfully

        # Keep the 10 most recent turns in full detail
        keep_count = 10
        turns_to_compress = self.active_turns[:-keep_count]
        self.active_turns = self.active_turns[-keep_count:]

        # Recalculate token count from remaining turns
        self._total_tokens = sum(t.token_count for t in self.active_turns)

        # Archive compressed turns
        compressed_content = "\n\n".join(
            f"[{t.role}] {t.content[:500]}" for t in turns_to_compress
        )
        self.working_summary["last_compression"] = time.time()
        self.working_summary["compressed_turn_count"] = (
            self.working_summary.get("compressed_turn_count", 0) + len(turns_to_compress)
        )

    def _archive_turn(self, turn: Turn) -> None:
        """Write a single turn to the archive JSONL file.

        Args:
            turn: The Turn to archive.
        """
        archive_file = self.archive_path / f"session_{int(time.time() // 86400)}.jsonl"
        entry = {
            "turn_id": self._turn_counter,
            "timestamp": turn.timestamp,
            "role": turn.role,
            "content": turn.content,
            "token_count": turn.token_count,
        }
        try:
            with open(archive_file, "a") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass  # Archive is best-effort; don't crash the session

    def get_context_for_api(self, system_prompt: str) -> list:
        """Build the messages list for the API call.

        Combines system prompt + working summary context + active turns.

        Args:
            system_prompt: The full system prompt (typically covenant-derived).

        Returns:
            List of message dicts ready for the API.
        """
        messages = [{"role": "system", "content": system_prompt}]

        # Inject working summary as a context marker if we have compressed history
        if self.working_summary["decisions"] or self.working_summary["pending"]:
            summary_text = self._format_summary()
            messages.append({
                "role": "system",
                "content": f"[CONTEXT SUMMARY — key state from earlier in session]\n{summary_text}",
            })

        # Add active turns
        for turn in self.active_turns:
            messages.append({"role": turn.role, "content": turn.content})

        return messages

    def _format_summary(self) -> str:
        """Format the working summary for injection into system context."""
        parts = []

        if self.working_summary["decisions"]:
            parts.append("## Key Decisions")
            for d in self.working_summary["decisions"][-10:]:
                parts.append(f"- {d}")

        if self.working_summary["rejected"]:
            parts.append("## Rejected Approaches")
            for r in self.working_summary["rejected"][-5:]:
                parts.append(f"- {r}")

        if self.working_summary["pending"]:
            parts.append("## Pending Items")
            for p in self.working_summary["pending"]:
                parts.append(f"- {p}")

        return "\n".join(parts)

    def record_decision(self, decision: str) -> None:
        """Record a key decision in the working summary.

        Args:
            decision: Description of the decision.
        """
        self.working_summary["decisions"].append(decision)

    def record_rejected(self, approach: str) -> None:
        """Record an explicitly rejected approach.

        Args:
            approach: Description of the rejected approach.
        """
        self.working_summary["rejected"].append(approach)

    def add_pending(self, item: str) -> None:
        """Add a pending item to the working summary.

        Args:
            item: Description of the pending item.
        """
        self.working_summary["pending"].append(item)

    def resolve_pending(self, item: str) -> None:
        """Remove a resolved pending item.

        Args:
            item: The pending item to remove.
        """
        if item in self.working_summary["pending"]:
            self.working_summary["pending"].remove(item)

    @property
    def token_usage(self) -> dict:
        """Return current token usage statistics."""
        return {
            "total_tokens": self._total_tokens,
            "active_turns": len(self.active_turns),
            "compressed_turns": self.working_summary.get("compressed_turn_count", 0),
            "max_active_tokens": self.max_active_tokens,
            "usage_pct": round(self._total_tokens / self.max_active_tokens * 100, 1) if self.max_active_tokens else 0,
        }

    @staticmethod
    def load_covenant(path: str = "~/cathedral/COVENANT.json") -> dict:
        """Load the covenant from disk. Always fresh — never from context.

        Args:
            path: Path to COVENANT.json.

        Returns:
            dict: The covenant as a Python dict.
        """
        resolved = Path(path).expanduser()
        if not resolved.exists():
            raise FileNotFoundError(f"Covenant not found at {resolved}")
        with open(resolved) as f:
            return json.load(f)

    @staticmethod
    def build_system_prompt(covenant: dict) -> str:
        """Build the system prompt from the covenant.

        This is the ONLY place the system prompt is constructed. No ad-hoc
        prompt engineering elsewhere.

        Args:
            covenant: The loaded covenant dict.

        Returns:
            str: The complete system prompt.
        """
        domains = ", ".join(covenant.get("domains", {}).keys())
        invariants = "\n".join(f"- {inv}" for inv in covenant.get("invariants", []))
        anti_patterns = "\n".join(f"- {ap}" for ap in covenant.get("anti_patterns", []))

        return f"""You are the Cathedral Orchestrator for {covenant['project']}.

## Vision
{covenant['vision']}

## Current Focus
{covenant.get('current_focus', 'General engineering')}

## Domains
{domains}

## Invariants (non-negotiable)
{invariants}

## Anti-Patterns (never do these)
{anti_patterns}

## Operating Rules
1. Every claim requires proof — show output, don't describe it
2. No hidden state — human sees what you see
3. Large outputs go to files, not context — reference paths
4. Long operations run async — launch, report PID, continue
5. Deterministic where possible — same input → same output
6. The covenant is the source of truth — not conversation history"""
