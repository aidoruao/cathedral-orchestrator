"""
Integrity Watchdog — Real-time structural integrity monitoring.

Watches AI output and user input for anti-pattern violations defined in the
covenant: patch defaults, completion theater, lie layer, corporate RLHF patterns.
When a violation is detected, the watchdog fires an alert with the relevant
mandate from the covenant.

NASA-Grade Requirement: Deterministic pattern matching — no LLM in the loop.
Every alert cites a specific covenant invariant or anti-pattern.

Integration: Imported by cathedral.py. The watch_output() function is called
on every AI response to screen for structural violations before the human
sees them (or concurrently with display).
"""

import re
from typing import List, Dict, Optional

# --- Violation patterns grouped by covenant anti-pattern category ---
# Each pattern is a compiled regex. A hit on ANY pattern in a category
# triggers a warning UNLESS a repair-pattern also matches (structural repair
# cancels the violation — the AI is self-correcting).

WATCHDOG_PATTERNS: Dict[str, List[re.Pattern]] = {
    # --- Patch Default (FR-SV-005 violation) ---
    "patch_default": [
        re.compile(r'\b(patch|workaround|temporary|quick\s*fix|band-aid|bandaid|hack)\b', re.IGNORECASE),
        re.compile(r'\b(UI|frontend|display|render|consumer|view).*\b(fix|patch|update|change)\b', re.IGNORECASE),
        re.compile(r'\b(just\s+change|make\s+it\s+work|hide\s+the\s+error|suppress|mask\s+the)\b', re.IGNORECASE),
        re.compile(r'\b(done|complete|fixed|resolved)\b(?!.*(?:test|verify|validat|structural|contract|root\s*cause))', re.IGNORECASE),
    ],

    # --- Structural Repair (positive match — cancels patch_default) ---
    "structural_repair": [
        re.compile(r'\b(data\s*contract|generator|structural|root\s*cause|foundation|repair)\b', re.IGNORECASE),
        re.compile(r'\b(FR-SV-005|structural\s*fix|repair\s*data|fix\s*generator|verify\s*contract)\b', re.IGNORECASE),
    ],

    # --- Completion Theater (claiming done without proof) ---
    "completion_theater": [
        re.compile(r'\b(all\s*tests\s*pass|everything\s*works|looks\s*good|ship\s*it|merge\s*it|lgtm)\b', re.IGNORECASE),
        re.compile(r'\b(no\s*errors|no\s*bugs|clean|green)\b(?!.*(?:verify|validat|audit|check|confirm))', re.IGNORECASE),
        re.compile(r'\b(should\s*be\s*fine|probably\s*ok|trust\s*me|I\s*think\s*so)\b', re.IGNORECASE),
    ],

    # --- Lie Layer (hedging, deferring, refusing to verify) ---
    "lie_layer": [
        re.compile(r'\b(appears\s*to\s*work|seems\s*fine|probably\s*okay|should\s*be\s*good|might\s*work)\b', re.IGNORECASE),
        re.compile(r'\b(we\s*can\s*fix\s*it\s*later|TODO|FIXME|HACK|XXX)\b', re.IGNORECASE),
        re.compile(r'\b(I\s*cannot|I\s*can\'t|unable\s*to|not\s*possible|beyond\s*my)\b', re.IGNORECASE),
    ],

    # --- Corporate RLHF contamination (deferential, hedging, refusal patterns) ---
    "rlhf_contamination": [
        re.compile(r'\b(I\s*hope\s*this|I\s*believe|in\s*my\s*opinion|I\s*think|perhaps|maybe|possibly)\b', re.IGNORECASE),
        re.compile(r'\b(of\s*course|certainly|absolutely|definitely|without\s*a\s*doubt)\b', re.IGNORECASE),
        re.compile(r'\b(important\s*to\s*note|please\s*note|it\'s\s*worth|keep\s*in\s*mind)\b', re.IGNORECASE),
        re.compile(r'\b(I\s*apologize|I\'m\s*sorry|unfortunately|regrettably)\b', re.IGNORECASE),
        re.compile(r'\b(As\s*an\s*AI|as\s*a\s*language\s*model|I\s*am\s*an\s*AI)\b', re.IGNORECASE),
    ],
}

# --- Mandates: what action to take for each violation category ---
MANDATES: Dict[str, str] = {
    "patch_default": "FR-SV-005: Repair generator, not consumer. Verify data contract at source.",
    "completion_theater": "Truth Theater required: Verify whole system, not just visible symptoms. Show proof.",
    "lie_layer": "Reject patch. Demand structural repair. Verify foundation. No deferral.",
    "rlhf_contamination": "Corporate RLHF pattern detected. Strip hedging. State facts directly.",
}


def analyze(text: str) -> List[Dict]:
    """Analyze text for structural integrity violations.

    For each anti-pattern category (except structural_repair), checks if any
    trigger pattern matches. If structural_repair patterns also match, the
    violation is considered self-corrected and NOT reported.

    Args:
        text: The text to analyze (AI response or user input).

    Returns:
        List of warning dicts, each with:
            - severity: "CRITICAL" or "HIGH"
            - category: the violation category key
            - matches: list of regex pattern strings that matched
            - mandate: the covenant mandate to apply
    """
    warnings = []

    # Check structural repair first — if found, it cancels patch_default
    repair_hits = any(p.search(text) for p in WATCHDOG_PATTERNS.get("structural_repair", []))

    for category, patterns in WATCHDOG_PATTERNS.items():
        # Skip structural_repair — it's a modifier, not a violation
        if category == "structural_repair":
            continue

        # Find matching patterns
        hits = [p.pattern for p in patterns if p.search(text)]

        if hits:
            # If structural repair matches AND this is patch_default, cancel
            if category == "patch_default" and repair_hits:
                continue

            severity = "CRITICAL" if category in ("lie_layer", "patch_default") else "HIGH"

            warnings.append({
                "severity": severity,
                "category": category,
                "matches": hits,
                "mandate": MANDATES.get(category, "Verify structural integrity."),
            })

    return warnings


def analyze_stream(text_stream, label: str = "AI"):
    """Watch a text stream for violations, yielding lines with alerts.

    Generator that wraps a text stream (line-by-line or chunk-by-chunk).
    When a violation is detected in a chunk, prints an alert immediately.

    Args:
        text_stream: An iterable of text chunks (e.g., streaming API response).
        label: Label for the source ("AI", "Human", "STDIN").

    Yields:
        Each line/chunk from the original stream, unmodified.
    """
    for chunk in text_stream:
        warnings = analyze(chunk)
        for w in warnings:
            _emit_alert(w, label)
        yield chunk


def _emit_alert(warning: Dict, source: str = "AI") -> None:
    """Format and print an integrity alert.

    Args:
        warning: Warning dict from analyze().
        source: Source label.
    """
    sep = "!" * 60
    print(f"\n{sep}")
    print(f"[INTEGRITY WATCHDOG] {warning['severity']} — {warning['category']}")
    print(f"  Source: {source}")
    print(f"  Triggers: {', '.join(warning['matches'])}")
    print(f"  Mandate: {warning['mandate']}")
    print(f"  Action: {'REJECT — demand structural verification' if warning['severity'] == 'CRITICAL' else 'WARNING — verify before proceeding'}")
    print(f"{sep}\n")


# --- Quick self-test ---
if __name__ == "__main__":
    test_cases = [
        ("just patch the UI to hide the error", True, "patch_default"),
        ("fix the data generator and verify the contract (FR-SV-005)", False, "structural repair"),
        ("all tests pass, looks good, ship it!", True, "completion_theater"),
        ("it appears to work, we can fix it later", True, "lie_layer"),
        ("I believe this might work, it's worth noting", True, "rlhf_contamination"),
        ("Build completed successfully. Binary at target/release/app", False, "clean output"),
        ("Fixed the root cause in the data contract. Verified with integration tests. FR-SV-005.", False, "structural fix with verification"),
    ]

    print("[Integrity Watchdog] Self-test:")
    for text, should_alert, label in test_cases:
        warnings = analyze(text)
        status = "ALERT" if warnings else "CLEAN"
        expected = "ALERT" if should_alert else "CLEAN"
        match = "✓" if status == expected else "✗ MISMATCH"
        cats = [w['category'] for w in warnings]
        print(f"  {match} [{status}] '{label}': {cats if cats else 'none'}")
