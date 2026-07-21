"""
Domain Router — Polymath dispatch system.

Routes user requests to the appropriate domain handler based on content analysis.
Each domain has a dedicated prompt template, tool configuration, and validation rules.

NASA-Grade Requirement: Domain detection must be deterministic — no LLM-based routing.
Use keyword and pattern matching, not AI judgment, to decide which domain handles a request.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable


# Domain definitions with keyword triggers and prompt templates
DOMAIN_DEFINITIONS = {
    "physics": {
        "name": "Physics & Thermodynamics",
        "triggers": [
            r"\bthermodynamic", r"\bhelmholtz", r"\benthalpy", r"\bentropy",
            r"\brefrigerant", r"\bHVAC", r"\bheat\s+transfer", r"\bcompressor",
            r"\bcondenser", r"\bevaporator", r"\bpressure.drop", r"\bphase\s+change",
            r"\bCoolProp", r"\bREFPROP", r"\bASHRAE", r"\bpsychrometric",
            r"\bR\d{2,4}",  # Refrigerant designations: R134a, R410A, etc.
            r"\bCOP\b", r"\bEER\b", r"\bSEER\b",
        ],
        "system_prompt_suffix": """
## Physics Domain Active
You are operating in physics/thermodynamics mode.
- Use CoolProp for refrigerant property calculations when available
- Cite ASHRAE standards for all HVAC claims
- Show units in all calculations (SI primary, IP secondary)
- Every equation must reference a primary source
- Report numerical results with appropriate significant figures""",
    },
    "graphics": {
        "name": "Graphics & Rendering",
        "triggers": [
            r"\bGodot\b", r"\bshader", r"\bmaterial", r"\bmesh\b", r"\btexture",
            r"\bviewport", r"\brender", r"\bscene\b", r"\b3D\b", r"\bPBR\b",
            r"\bGPU\b", r"\bVulkan\b", r"\bOpenGL\b", r"\blighting\b",
            r"\bnormal.map", r"\bambient.occlusion", r"\bSSAO\b",
            r"\bGDScript\b", r"\bglsl\b", r"\bHLSL\b",
        ],
        "system_prompt_suffix": """
## Graphics Domain Active
You are operating in graphics/rendering mode.
- Target Godot 4.x engine integration
- Use PBR material standards
- Scene changes go through Godot API calls
- Viewport captures for verification
- Serialize scene state for reproducibility""",
    },
    "code": {
        "name": "Software Engineering",
        "triggers": [
            r"\bdef\s+\w+\(", r"\bfn\s+\w+", r"\bclass\s+\w+", r"\bimport\s+\w+",
            r"\bfunction\s+\w+", r"\bconst\s+\w+\s*=", r"\blet\s+\w+\s*=",
            r"\bpytest", r"\bunittest", r"\bcompil", r"\bbuild", r"\blint",
            r"\brefactor", r"\bdebug", r"\bgit\s+", r"\bcommit\b",
            r"\bPython\b", r"\bRust\b", r"\bC\+\+", r"\bC#\b", r"\bJavaScript\b",
            r"\.py\b", r"\.rs\b", r"\.cpp\b", r"\.cs\b", r"\.gd\b",
        ],
        "system_prompt_suffix": """
## Code Domain Active
You are operating in software engineering mode.
- All file operations use the Base64 protocol — no heredocs
- Long builds run async via operation_runner
- Test output goes to files, not context
- Every code change is verified (lint, test, or manual review)
- File paths are absolute or relative to workspace""",
    },
    "documentation": {
        "name": "Documentation & Specifications",
        "triggers": [
            r"\bdocument", r"\bSRS\b", r"\bspec", r"\bREADME\b", r"\bmanual\b",
            r"\bchangelog\b", r"\bAPI\s+doc", r"\bdesign\s+doc", r"\bADR\b",
            r"\bmarkdown\b", r"\b\.md\b", r"\bISO\b", r"\bstandard\b",
            r"\btraceability\b", r"\brequirements?\b", r"\bcampaign\b",
        ],
        "system_prompt_suffix": """
## Documentation Domain Active
You are operating in documentation mode.
- Maintain SRS traceability matrices
- Every requirement gets a unique ID (FR-xxx, NFR-xxx)
- Campaign files are append-only — never delete historical data
- Documentation is versioned alongside code
- Invariant enforcement: every claim links to a requirement""",
    },
    "pedagogy": {
        "name": "Pedagogy & Training",
        "triggers": [
            r"\btraining\b", r"\bscenario\b", r"\bfault\s+injection", r"\bscoring\b",
            r"\bcompetency\b", r"\bassessment\b", r"\bquiz\b", r"\bexercise\b",
            r"\bcurriculum\b", r"\blearning\b", r"\bpedagog", r"\bteach\b",
        ],
        "system_prompt_suffix": """
## Pedagogy Domain Active
You are operating in training/pedagogy mode.
- Scenarios use randomized fault injection
- Scoring is competency-based, not pass/fail
- Every exercise has clear learning objectives
- Anti-trade-school: scenarios are real-world, not simplified
- Progress is tracked per-learner in session files""",
    },
}


@dataclass
class DomainRouter:
    """Routes requests to domain handlers based on content analysis.

    Deterministic keyword/pattern matching — no LLM-based routing.
    Multiple domains can be active simultaneously for cross-domain requests.
    """

    # Loaded domain definitions
    domains: dict = field(default_factory=lambda: DOMAIN_DEFINITIONS.copy())

    # Currently active domains
    active_domains: set = field(default_factory=set)

    def detect_domains(self, text: str) -> list[str]:
        """Detect which domains are relevant to the given text.

        Uses regex pattern matching against domain triggers. Returns all
        matching domains. If no domain matches, returns ["code"] as default.

        Args:
            text: The user input to analyze.

        Returns:
            List of domain keys (e.g., ["physics", "code"]).
        """
        matched = []
        text_lower = text.lower()

        for domain_key, domain_def in self.domains.items():
            score = 0
            for pattern in domain_def["triggers"]:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    score += 1

            if score > 0:
                matched.append((domain_key, score))

        # Sort by match score descending
        matched.sort(key=lambda x: x[1], reverse=True)

        # Return domain keys, defaulting to "code" if nothing matches
        if not matched:
            return ["code"]

        return [m[0] for m in matched]

    def get_system_prompt_suffix(self, domains: list[str]) -> str:
        """Build the domain-specific system prompt suffix.

        Args:
            domains: List of domain keys.

        Returns:
            str: Combined domain prompt suffix.
        """
        suffixes = []
        for domain_key in domains:
            if domain_key in self.domains:
                suffixes.append(self.domains[domain_key]["system_prompt_suffix"])

        return "\n\n".join(suffixes)

    def set_active_domains(self, domains: list[str]) -> None:
        """Set the currently active domains.

        Args:
            domains: List of domain keys to activate.
        """
        self.active_domains = set(domains)

    def add_domain(self, domain_key: str) -> None:
        """Activate an additional domain.

        Args:
            domain_key: Domain key to add.
        """
        if domain_key in self.domains:
            self.active_domains.add(domain_key)

    def get_active_summary(self) -> str:
        """Return a human-readable summary of active domains.

        Returns:
            str: Comma-separated domain names.
        """
        if not self.active_domains:
            return "code (default)"
        return ", ".join(
            self.domains[d]["name"]
            for d in sorted(self.active_domains)
            if d in self.domains
        )

    def register_custom_domain(
        self,
        key: str,
        name: str,
        triggers: list[str],
        prompt_suffix: str,
    ) -> None:
        """Register a custom domain definition.

        Args:
            key: Unique domain key.
            name: Human-readable domain name.
            triggers: List of regex patterns for detection.
            prompt_suffix: System prompt addition when domain is active.
        """
        self.domains[key] = {
            "name": name,
            "triggers": triggers,
            "system_prompt_suffix": prompt_suffix,
        }
