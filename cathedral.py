#!/usr/bin/env python3
"""
Cathedral Orchestrator — Main Loop.

Replaces Codewhale's TUI with a deterministic, polymath, NASA-grade API loop.
No TUI. No approval gates. No hangs. No hidden state.

Architecture:
  cathedral.py          <- You are here (main loop, API client, session manager)
  context_engine.py     <- Tiered context window management
  file_protocol.py      <- Base64 file I/O with verification
  operation_runner.py   <- Async long-running operations
  audit_logger.py       <- Immutable audit trail
  domain_router.py      <- Polymath domain dispatch
  state_bridge.py       <- Human/AI shared viewport
  integrity_watchdog.py <- Real-time structural integrity monitoring

Usage:
  python cathedral.py                    # Interactive mode
  python cathedral.py --oneshot "prompt" # Single query, print response, exit
  python cathedral.py --resume <session> # Resume a saved session

Environment:
  DEEPSEEK_API_KEY       (required) DeepSeek API key
  DEEPSEEK_BASE_URL      (optional) API base URL, default https://api.deepseek.com
  COVENANT_PATH          (optional) Path to COVENANT.json
  CATHEDRAL_MODEL        (optional) Model name, default deepseek-v4-pro
  CATHEDRAL_TEMPERATURE  (optional) Temperature, default 0.0
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

# --- Bootstrap: ensure ~/cathedral is on sys.path ---
CATHEDRAL_HOME = Path.home() / "cathedral"
sys.path.insert(0, str(CATHEDRAL_HOME))

# --- Lazy imports for graceful degradation ---
_import_errors = []

try:
    from openai import OpenAI
except ImportError:
    _import_errors.append("openai package not installed. Run: pip install openai")
    OpenAI = None

try:
    from dotenv import load_dotenv
except ImportError:
    _import_errors.append("python-dotenv not installed. Run: pip install python-dotenv")
    load_dotenv = lambda: None  # noqa: E731

# Local modules
try:
    from context_engine import ContextEngine
except ImportError:
    _import_errors.append("context_engine.py not found in ~/cathedral/")
    ContextEngine = None

try:
    from domain_router import DomainRouter
except ImportError:
    _import_errors.append("domain_router.py not found in ~/cathedral/")
    DomainRouter = None

try:
    from file_protocol import write_file, read_file, append_file
except ImportError:
    _import_errors.append("file_protocol.py not found in ~/cathedral/")
    write_file = read_file = append_file = None

try:
    from operation_runner import run_operation, check_operation, list_operations, tail_log
except ImportError:
    _import_errors.append("operation_runner.py not found in ~/cathedral/")
    run_operation = check_operation = list_operations = tail_log = None

try:
    from audit_logger import log as audit_log, read_log
except ImportError:
    _import_errors.append("audit_logger.py not found in ~/cathedral/")
    audit_log = read_log = None

try:
    from state_bridge import StateBridge
except ImportError:
    _import_errors.append("state_bridge.py not found in ~/cathedral/")
    StateBridge = None

try:
    from integrity_watchdog import analyze as watchdog_analyze
except ImportError:
    _import_errors.append("integrity_watchdog.py not found in ~/cathedral/")
    watchdog_analyze = None


# --- ASCII Banner ---
BANNER = r"""
  ┌─────────────────────────────────────────────────────────┐
  │           CATHEDRAL ORCHESTRATOR v1.0.0                 │
  │   Deterministic · Polymath · NASA-Grade · No Hidden State  │
  │   Replaces TUI with API loop. Survives AI death.        │
  └─────────────────────────────────────────────────────────┘
"""

# --- Reserved commands (interpreted locally, not sent to API) ---
RESERVED_COMMANDS = {
    "exit": "Exit the orchestrator",
    "quit": "Exit the orchestrator",
    "covenant": "Reload COVENANT.json from disk",
    "status": "Show session status: token usage, active ops, domain",
    "ops": "List active long-running operations",
    "audit": "Show recent audit log entries",
    "state": "Show shared state snapshot",
    "help": "Show this help",
    "domains": "Show active domains and available domain list",
    "compress": "Trigger manual context compression",
    "clear": "Clear the screen",
}


def print_banner() -> None:
    """Print the startup banner."""
    print(BANNER)


def print_help() -> None:
    """Print available commands."""
    print("\nReserved commands (interpreted locally):")
    for cmd, desc in RESERVED_COMMANDS.items():
        print(f"  /{cmd:<15} {desc}")
    print("\nEverything else is sent to the AI.\n")


def load_covenant(path: str) -> dict:
    """Load the covenant from disk. Fatal if not found.

    Args:
        path: Path to COVENANT.json.

    Returns:
        dict: The covenant.
    """
    resolved = Path(path).expanduser()
    if not resolved.exists():
        print(f"FATAL: Covenant not found at {resolved}")
        print("Create ~/cathedral/COVENANT.json before starting.")
        sys.exit(1)
    with open(resolved) as f:
        return json.load(f)


def handle_reserved(
    command: str,
    covenant: dict,
    context_engine,
    domain_router,
    state_bridge,
) -> Optional[str]:
    """Handle a reserved command locally. Returns response text or None.

    Args:
        command: The command without the leading '/'.
        covenant: The loaded covenant.
        context_engine: ContextEngine instance.
        domain_router: DomainRouter instance.
        state_bridge: StateBridge instance.

    Returns:
        str: Response to display, or None if command was not reserved.
    """
    cmd = command.strip().lower()

    if cmd in ("exit", "quit"):
        print("\nShutting down Cathedral Orchestrator.")
        _save_session(context_engine, state_bridge)
        if audit_log:
            audit_log("session_end", "orchestrator", {"reason": "user_exit"})
        sys.exit(0)

    elif cmd == "covenant":
        try:
            covenant = load_covenant("~/cathedral/COVENANT.json")
            print("✓ Covenant reloaded from disk.")
            print(f"  Project: {covenant['project']}")
            print(f"  Focus: {covenant.get('current_focus', 'N/A')}")
            if audit_log:
                audit_log("covenant_reload", "orchestrator", {"project": covenant["project"]})
            return "covenant_reloaded"
        except Exception as e:
            print(f"✗ Failed to reload covenant: {e}")
            return "covenant_reload_failed"

    elif cmd == "status":
        if context_engine:
            usage = context_engine.token_usage
            print(f"\n--- Session Status ---")
            print(f"  Tokens: {usage['total_tokens']} / {usage['max_active_tokens']} ({usage['usage_pct']}%)")
            print(f"  Active turns: {usage['active_turns']}")
            print(f"  Compressed turns: {usage['compressed_turns']}")
        if domain_router:
            print(f"  Active domains: {domain_router.get_active_summary()}")
        if run_operation:
            ops = list_operations()
            print(f"  Active operations: {len(ops)}")
            for op in ops:
                print(f"    [{op['op_id']}] {op['label']} — {op['status']} ({op['elapsed_seconds']}s)")
        return "status_displayed"

    elif cmd == "ops":
        if run_operation:
            ops = list_operations()
            if not ops:
                print("No active operations.")
            else:
                print(f"\n--- Active Operations ({len(ops)}) ---")
                for op in ops:
                    print(f"  [{op['op_id']}] PID {op['pid']} | {op['label']}")
                    print(f"    Status: {op['status']} | Elapsed: {op['elapsed_seconds']}s")
                    print(f"    Log: {op['log_file']}")
        else:
            print("operation_runner not available.")
        return "ops_displayed"

    elif cmd == "audit":
        if read_log:
            result = read_log(max_entries=20)
            if result["success"]:
                print(f"\n--- Audit Log ({result['total_entries']} total entries) ---")
                for entry in result["entries"][:20]:
                    ts = entry.get("timestamp", "?")[:19]
                    actor = entry.get("actor", "?")
                    action = entry.get("action", "?")
                    print(f"  [{ts}] {actor:>8}: {action}")
            else:
                print(f"Failed to read audit log: {result.get('error')}")
        else:
            print("audit_logger not available.")
        return "audit_displayed"

    elif cmd == "state":
        if state_bridge:
            snap = state_bridge.snapshot()
            if not snap:
                print("No shared state.")
            else:
                print(f"\n--- Shared State ({len(snap)} keys) ---")
                for key, value in sorted(snap.items()):
                    val_str = str(value)[:100]
                    print(f"  {key}: {val_str}")
        else:
            print("state_bridge not available.")
        return "state_displayed"

    elif cmd == "domains":
        if domain_router:
            print(f"\nActive domains: {domain_router.get_active_summary()}")
            print("\nAvailable domains:")
            for key, defn in domain_router.domains.items():
                active = "✓" if key in domain_router.active_domains else " "
                print(f"  [{active}] {key:<15} {defn['name']}")
        return "domains_displayed"

    elif cmd == "compress":
        if context_engine:
            before = context_engine.token_usage
            context_engine._compress()
            after = context_engine.token_usage
            print(f"Compression: {before['total_tokens']} → {after['total_tokens']} tokens")
        return "compress_done"

    elif cmd == "clear":
        print("\033[2J\033[H", end="")
        return "clear_done"

    elif cmd == "help":
        print_help()
        return "help_displayed"

    return None  # Not a reserved command


def _save_session(context_engine, state_bridge) -> None:
    """Save session state to disk for resumption."""
    session_dir = CATHEDRAL_HOME / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)

    session_file = session_dir / f"session_{int(time.time())}.json"
    try:
        data = {
            "timestamp": time.time(),
            "token_usage": context_engine.token_usage if context_engine else {},
            "working_summary": context_engine.working_summary if context_engine else {},
            "shared_state": state_bridge.snapshot() if state_bridge else {},
        }
        with open(session_file, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Session saved to {session_file}")
    except Exception as e:
        print(f"Warning: Could not save session: {e}")


def interactive_loop(
    covenant: dict,
    client,
    context_engine,
    domain_router,
    state_bridge,
    model: str,
    temperature: float,
    base_url: str,
) -> None:
    """Run the interactive stdin/stdout loop.

    Args:
        covenant: Loaded covenant dict.
        client: OpenAI client instance.
        context_engine: ContextEngine instance.
        domain_router: DomainRouter instance.
        state_bridge: StateBridge instance.
        model: Model name.
        temperature: Sampling temperature.
        base_url: API base URL.
    """
    print_banner()
    print(f"Model: {model}  |  Temperature: {temperature}")
    print(f"Endpoint: {base_url}")
    print(f"Project: {covenant['project']}")
    print(f"Focus: {covenant.get('current_focus', 'General')}")
    print(f"\nType '/help' for commands. Everything else is sent to the AI.\n")

    if audit_log:
        audit_log("session_start", "orchestrator", {
            "model": model,
            "temperature": temperature,
            "project": covenant["project"],
        })

    # Build initial system prompt
    if context_engine:
        system_prompt = context_engine.build_system_prompt(covenant)
    else:
        system_prompt = f"You are the Cathedral Orchestrator for {covenant['project']}."

    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n")
            _save_session(context_engine, state_bridge)
            break

        if not user_input:
            continue

        # Handle reserved commands (prefixed with /)
        if user_input.startswith("/"):
            command = user_input[1:]
            result = handle_reserved(
                command, covenant, context_engine, domain_router, state_bridge
            )
            if result is not None:
                continue  # Command was handled locally

        # --- Domain detection ---
        active_domains = ["code"]  # default
        if domain_router:
            active_domains = domain_router.detect_domains(user_input)
            domain_router.set_active_domains(active_domains)

        # Build full system prompt with domain suffix
        domain_suffix = ""
        if domain_router and active_domains:
            domain_suffix = domain_router.get_system_prompt_suffix(active_domains)
        full_system = system_prompt + "\n" + domain_suffix if domain_suffix else system_prompt

        # --- Add to context ---
        if context_engine:
            context_engine.add_turn("user", user_input)
            messages = context_engine.get_context_for_api(full_system)
        else:
            # Fallback: simple message list without context engine
            messages = [
                {"role": "system", "content": full_system},
                {"role": "user", "content": user_input},
            ]

        # --- Log the query ---
        if audit_log:
            audit_log("user_query", "human", {
                "content": user_input[:200],
                "domains": active_domains,
            })

        # --- API call with streaming ---
        print("\n" + "─" * 60)

        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                stream=True,
            )

            full_response = ""
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    print(content, end="", flush=True)
                    full_response += content

            print("\n" + "─" * 60)

            # --- Integrity watchdog scan ---
            if watchdog_analyze:
                warnings = watchdog_analyze(full_response)
                if warnings:
                    from integrity_watchdog import _emit_alert
                    for w in warnings:
                        _emit_alert(w, "AI")

            # --- Add response to context ---
            if context_engine:
                context_engine.add_turn("assistant", full_response)

            # --- Log the response ---
            if audit_log:
                audit_log("ai_response", "ai", {
                    "length": len(full_response),
                    "domains": active_domains,
                })

        except Exception as e:
            print(f"\n✗ API Error: {e}")
            if audit_log:
                audit_log("api_error", "system", {"error": str(e)})

        # --- Update state ---
        if state_bridge:
            state_bridge.set(
                "session.last_query",
                user_input[:200],
                actor="system",
                reason="Track last user query",
            )
            state_bridge.set(
                "session.last_response_time",
                time.time(),
                actor="system",
                reason="Track response timestamp",
            )


def oneshot_mode(
    prompt: str,
    covenant: dict,
    client,
    context_engine,
    domain_router,
    model: str,
    temperature: float,
) -> None:
    """Run a single query and print the response.

    Args:
        prompt: The user prompt.
        covenant: Loaded covenant.
        client: OpenAI client.
        context_engine: ContextEngine instance.
        domain_router: DomainRouter instance.
        model: Model name.
        temperature: Sampling temperature.
    """
    system_prompt = context_engine.build_system_prompt(covenant) if context_engine else ""

    if domain_router:
        domains = domain_router.detect_domains(prompt)
        system_prompt += "\n" + domain_router.get_system_prompt_suffix(domains)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            stream=True,
        )

        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                print(chunk.choices[0].delta.content, end="", flush=True)
        print()

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """Entry point — parse args, load config, start loop."""

    parser = argparse.ArgumentParser(
        description="Cathedral Orchestrator — Deterministic, polymath, NASA-grade API loop.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cathedral.py                          # Interactive mode
  python cathedral.py --oneshot "What is Helmholtz EOS?"
  python cathedral.py --model deepseek-v4-pro --temperature 0.0
        """,
    )
    parser.add_argument(
        "--oneshot", "-1",
        type=str,
        help="Single query mode: send prompt, print response, exit.",
    )
    parser.add_argument(
        "--model", "-m",
        type=str,
        default=os.environ.get("CATHEDRAL_MODEL", "deepseek-v4-pro"),
        help="Model name (default: deepseek-v4-pro or $CATHEDRAL_MODEL).",
    )
    parser.add_argument(
        "--temperature", "-t",
        type=float,
        default=float(os.environ.get("CATHEDRAL_TEMPERATURE", "0.0")),
        help="Sampling temperature (default: 0.0).",
    )
    parser.add_argument(
        "--covenant", "-c",
        type=str,
        default=os.environ.get("COVENANT_PATH", "~/cathedral/COVENANT.json"),
        help="Path to COVENANT.json.",
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="Disable streaming output.",
    )
    args = parser.parse_args()

    # --- Load environment ---
    load_dotenv()

    # --- Check imports ---
    if _import_errors:
        print("Warning: Some modules could not be imported:")
        for err in _import_errors:
            print(f"  - {err}")
        print()

    # --- Validate API key ---
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("FATAL: DEEPSEEK_API_KEY not set.")
        print("Create ~/cathedral/.env with your API key, or export DEEPSEEK_API_KEY.")
        sys.exit(1)

    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

    # --- Load covenant ---
    covenant = load_covenant(args.covenant)

    # --- Initialize client ---
    if OpenAI is None:
        print("FATAL: openai package not installed. Run: pip install openai")
        sys.exit(1)

    client = OpenAI(api_key=api_key, base_url=base_url)

    # --- Initialize subsystems ---
    context_engine = ContextEngine(
        max_active_tokens=covenant.get("session_defaults", {}).get("max_context_tokens", 120000),
        compression_trigger=covenant.get("session_defaults", {}).get("compression_trigger_tokens", 90000),
    ) if ContextEngine else None

    domain_router = DomainRouter() if DomainRouter else None
    state_bridge = StateBridge() if StateBridge else None

    # --- Log startup ---
    if audit_log:
        audit_log("orchestrator_start", "system", {
            "model": args.model,
            "temperature": args.temperature,
            "covenant_path": args.covenant,
            "base_url": base_url,
        })

    # --- Dispatch mode ---
    if args.oneshot:
        oneshot_mode(
            prompt=args.oneshot,
            covenant=covenant,
            client=client,
            context_engine=context_engine,
            domain_router=domain_router,
            model=args.model,
            temperature=args.temperature,
        )
    else:
        interactive_loop(
            covenant=covenant,
            client=client,
            context_engine=context_engine,
            domain_router=domain_router,
            state_bridge=state_bridge,
            model=args.model,
            temperature=args.temperature,
            base_url=base_url,
        )


if __name__ == "__main__":
    main()
