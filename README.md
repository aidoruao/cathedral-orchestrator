# Cathedral Orchestrator v1.0.0

**Deterministic · Polymath · NASA-Grade · No Hidden State**

Replaces TUI agents with an API loop. Survives AI death. Enforces structural integrity.

---

## What It Is

The Cathedral Orchestrator is a Python-based AI orchestrator that replaces traditional TUI agents (like Codewhale) with a deterministic, transparent API loop. It talks to DeepSeek V4 Pro directly, keeps context alive across sessions, and enforces structural integrity via real-time pattern detection.

**Why it exists:** TUI agents hang on long operations, require approval gates, and lose context when they die. The Cathedral Orchestrator never hangs, never hides state, and preserves the "ought" across AI deaths.

---

## Key Features

| Component | Purpose |
|---|---|
| **Main Loop** (`cathedral.py`) | DeepSeek API client with streaming, session persistence |
| **Context Engine** | Tiered context: active ring buffer + working summary + JSONL archive |
| **File Protocol** | Base64 read/write with MD5 verification. No heredocs. No corruption. |
| **Operation Runner** | Async subprocess launch, PID tracking, log tailing. No hangs. |
| **Audit Logger** | JSONL audit trail with SHA-256 hashing. Every action is verifiable. |
| **Domain Router** | Deterministic regex-based dispatch: physics, graphics, code, docs, pedagogy |
| **State Bridge** | Human/AI shared viewport. No hidden state. |
| **Integrity Watchdog** | Real-time detection of Patch Default, Completion Theater, Lie Layer, RLHF contamination |

---

## Installation

```bash
git clone https://github.com/aidoruao/cathedral-orchestrator.git
cd cathedral-orchestrator
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your DEEPSEEK_API_KEY
python3 cathedral.py
```

---

## Usage

Interactive mode:
```bash
python3 cathedral.py
```

One-shot mode:
```bash
python3 cathedral.py --oneshot "What is the Helmholtz EOS for R134a?"
```

Commands:
- `/help` — show commands
- `/covenant` — reload project vision from COVENANT.json
- `/audit` — show recent audit log
- `/domain` — show current domain focus
- `exit` — quit

---

## Architecture

```
cathedral.py          # Main loop
context_engine.py     # Context management
file_protocol.py      # Safe file ops
operation_runner.py   # Long-running ops
audit_logger.py       # Audit trail
domain_router.py      # Polymath dispatch
state_bridge.py       # Human/AI shared state
integrity_watchdog.py # Real-time structural monitoring
COVENANT.json         # Project vision, invariants, anti-patterns
```

---

## Yeshua Standard

- **Anti-proprietary:** Free forever. No vendor lock-in.
- **Anti-gatekeeping:** Every formula cited with primary sources.
- **Glass box:** Every state inspectable. No hidden assumptions.
- **Structural integrity:** No patches at integration boundaries. FR-SV-005 enforced.
- **Truth Theater:** Verification over completion. Every claim requires proof.

---

## License

MIT License — see [LICENSE](LICENSE)

Copyright (c) 2026 capybaras incorporated
