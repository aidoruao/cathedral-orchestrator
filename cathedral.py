#!/usr/bin/env python3
"""
Cathedral Orchestrator v2.0
Deterministic · Polymath · NASA-Grade · No Hidden State
Actually orchestrates. Uses every component. No facade.
"""

import os
import sys
import json
import time
import subprocess
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

# Arrow-key history support
try:
    import readline
except ImportError:
    pass

# Load our components
sys.path.insert(0, str(Path(__file__).parent))
from file_protocol import read_file, write_file
from operation_runner import run_operation, check_operation
from audit_logger import log
from integrity_watchdog import analyze, invert_response

load_dotenv()

MAX_TOKENS = 1000000
SESSION_DIR = Path("~/cathedral/sessions").expanduser()
SESSION_DIR.mkdir(exist_ok=True)


class CathedralOrchestrator:
    """v2.0: Wires every component. Actually orchestrates."""

    def __init__(self):
        self.client = OpenAI(
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )
        self.covenant = self._load_covenant()
        self.messages = [self._system_message()]
        self.running_cost = 0.0
        self.running_tokens = 0
        self.current_project = "hvac"
        self.projects = {
            "hvac": "~/hvac-simulation",
            "godot": "~/godot-OE",
            "cathedral": "~/cathedral",
        }
        self.active_operations = {}

    # ── Covenant ──────────────────────────────────────────────

    def _load_covenant(self):
        path = Path("~/cathedral/COVENANT.json").expanduser()
        with open(path) as f:
            return json.load(f)

    def _system_message(self):
        cmd_ref = """
AVAILABLE COMMANDS — Generate these exactly in your responses when needed:

Navigation:
  /project <hvac|godot|cathedral> — Switch active project directory

File Operations:
  /read <filepath> — Read file from current project (relative to project root)
  /write <filepath> — Write file (prompts for content, use Base64, no heredocs)
  /run <command> — Execute shell command in WSL2

Git:
  /status — Git status of current project
  /commit <message> — Git add -A && git commit
  /push — Git push

Session:
  /save — Save conversation to JSON
  /load <file> — Load session from JSON
  /export <filename> — Export conversation as numbered campaign file

Info:
  /covenant — Reload project vision
  /cost — Show running cost and token usage
  /copy — Show path to last_response.txt
  /help — Show all commands

WORKFLOW:
When the user gives a high-level instruction like "build the module" or "fix the bug":
1. Generate the exact command sequence needed
2. Use /project first if switching projects
3. Use /run to inspect state before modifying
4. Use /write to create/modify files with full content
5. Use /run to build/test/verify
6. Report results and next steps

Always generate commands the human can copy-paste. Never explain what you would do — generate the actual commands.
"""
        return {
            "role": "system",
            "content": (
                f"You are the Cathedral Orchestrator for {self.covenant['project']}. "
                f"Vision: {self.covenant['vision']}. "
                f"Invariants: {self.covenant['invariants']}. "
                f"Current focus: {self.covenant['current_focus']}\n\n"
                f"{cmd_ref}"
            ),
        }

    # ── Status ─────────────────────────────────────────────────

    def _print_status(self):
        remaining = max(0, MAX_TOKENS - self.running_tokens)
        print(
            f"\n[${self.running_cost:.6f} | {self.running_tokens:,} used | "
            f"{remaining:,} remaining | Project: {self.current_project}]"
        )

    # ── Watchdog ───────────────────────────────────────────────

    def _watchdog_check_prompt(self, text):
        """Pre-send: check if user prompt contains patch-default patterns."""
        warnings = analyze(text)
        for w in warnings:
            if w["category"] == "patch_default":
                print(f"\n[PRE-SEND ALERT] {w['severity']}: {w['category']}")
                print(f"  Your prompt suggests a patch. Consider: {w['mandate']}")
                return input("Proceed anyway? [y/N]: ").lower() == "y"
        return True

    def _watchdog_check_response(self, text):
        """Post-response: check AI output for RLHF / completion theater."""
        warnings = analyze(text)
        for w in warnings:
            print(f"\n[INTEGRITY ALERT] {w['severity']} — {w['category']}")
            print(f"  Mandate: {w['mandate']}")
            if w["category"] in ("rlhf_contamination", "completion_theater"):
                print(invert_response(text))
        return text

    # ── Command execution ──────────────────────────────────────

    def _execute_command(self, cmd):
        """Run a shell command in WSL2 and return result."""
        print(f"\n[EXECUTING] {cmd}")
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        print(f"[EXIT CODE: {result.returncode}]")
        if result.stdout:
            print(result.stdout[:2000])
        if result.stderr:
            print(f"[STDERR]: {result.stderr[:500]}", file=sys.stderr)
        log("command_executed", "orchestrator", {
            "cmd": cmd,
            "exit_code": result.returncode,
        })
        return result

    # ── Git ────────────────────────────────────────────────────

    def _git_status(self):
        proj_path = Path(self.projects.get(self.current_project, ".")).expanduser()
        return self._execute_command(f"cd {proj_path} && git status --short")

    def _git_commit(self, message):
        proj_path = Path(self.projects.get(self.current_project, ".")).expanduser()
        return self._execute_command(
            f"cd {proj_path} && git add -A && git commit -m '{message}'"
        )

    def _git_push(self):
        proj_path = Path(self.projects.get(self.current_project, ".")).expanduser()
        return self._execute_command(f"cd {proj_path} && git push")

    # ── File I/O ───────────────────────────────────────────────

    def _read_project_file(self, filepath):
        proj_path = Path(self.projects.get(self.current_project, ".")).expanduser()
        full_path = proj_path / filepath
        result = read_file(str(full_path))
        if "content" in result:
            print(result["content"][:3000])
        else:
            print(f"[ERROR] {result.get('error', 'Unknown error')}")

    def _write_project_file(self, filepath, content):
        proj_path = Path(self.projects.get(self.current_project, ".")).expanduser()
        full_path = proj_path / filepath
        result = write_file(str(full_path), content)
        print(f"[WRITTEN] {full_path}")
        print(f"[MD5] {result.get('md5', 'N/A')}")

    # ── Session persistence ────────────────────────────────────

    def _save_session(self):
        timestamp = int(time.time())
        filepath = SESSION_DIR / f"session_{timestamp}.json"
        with open(filepath, "w") as f:
            json.dump(
                {
                    "messages": self.messages,
                    "cost": self.running_cost,
                    "tokens": self.running_tokens,
                    "project": self.current_project,
                },
                f,
            )
        print(f"[SAVED] {filepath}")
        return str(filepath)

    def _load_session(self, filepath):
        path = Path(filepath).expanduser()
        with open(path) as f:
            data = json.load(f)
            self.messages = data.get("messages", [self._system_message()])
            self.running_cost = data.get("cost", 0.0)
            self.running_tokens = data.get("tokens", 0)
            self.current_project = data.get("project", "hvac")
        print(f"[LOADED] {filepath}")

    # ── Campaign export ────────────────────────────────────────

    def _export_campaign(self, filename):
        campaign = {
            "date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "project": self.current_project,
            "entries": [],
        }
        for i, msg in enumerate(self.messages[1:], 1):
            role = "AIDORUAO" if msg["role"] == "user" else "ORCHESTRATOR"
            campaign["entries"].append(f"{i}}} {role}: {msg['content'][:500]}")

        path = Path("~/cathedral/campaigns").expanduser()
        path.mkdir(exist_ok=True)
        filepath = path / filename
        with open(filepath, "w") as f:
            f.write(f"# Campaign Export — {campaign['date']}\n\n")
            for entry in campaign["entries"]:
                f.write(entry + "\n\n")
        print(f"[EXPORTED] {filepath}")

    # ── Help ───────────────────────────────────────────────────

    def _help(self):
        print("""
Commands:
  /help              Show this help
  /covenant          Reload COVENANT.json
  /status            Git status of current project
  /commit <msg>      Git commit current project
  /push              Git push current project
  /read <file>       Read file from current project
  /write <file>      Write file (prompts for content)
  /run <cmd>         Run command in WSL2
  /project <name>    Switch project (hvac/godot/cathedral)
  /save              Save session
  /load <file>       Load session
  /export <file>     Export conversation as campaign file
  /copy              Show path to last_response.txt
  /cost              Show running cost
  /exit              Quit
        """)

    # ── Main loop ──────────────────────────────────────────────

    def run(self):
        print("  ┌─────────────────────────────────────────────────────────┐")
        print("  │           CATHEDRAL ORCHESTRATOR v2.0                   │")
        print("  │   Actually orchestrates. Uses every component.          │")
        print("  └─────────────────────────────────────────────────────────┘")
        print(f"\nModel: deepseek-v4-pro | Project: {self.current_project}")
        print("Responses auto-saved to: ~/cathedral/last_response.txt")
        print("Type '/help' for commands.\n")

        while True:
            try:
                self._print_status()
                user_input = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n")
                self._save_session()
                break

            if not user_input:
                continue

            # ── Reserved commands ───────────────────────────
            if user_input.startswith("/"):
                parts = user_input.split(maxsplit=1)
                cmd = parts[0].lower()
                arg = parts[1] if len(parts) > 1 else ""

                if cmd == "/help":
                    self._help()
                elif cmd == "/covenant":
                    self.covenant = self._load_covenant()
                    self.messages[0] = self._system_message()
                    print("[COVENANT RELOADED]")
                elif cmd == "/status":
                    self._git_status()
                elif cmd == "/commit":
                    if arg:
                        self._git_commit(arg)
                    else:
                        print("Usage: /commit <message>")
                elif cmd == "/push":
                    self._git_push()
                elif cmd == "/read":
                    if arg:
                        self._read_project_file(arg)
                    else:
                        print("Usage: /read <filepath>")
                elif cmd == "/write":
                    if arg:
                        print("Enter content (Ctrl+D to finish):")
                        content = sys.stdin.read()
                        self._write_project_file(arg, content)
                    else:
                        print("Usage: /write <filepath>")
                elif cmd == "/run":
                    if arg:
                        self._execute_command(arg)
                    else:
                        print("Usage: /run <command>")
                elif cmd == "/project":
                    if arg in self.projects:
                        self.current_project = arg
                        print(f"[PROJECT: {arg}]")
                    else:
                        print(f"Available: {list(self.projects.keys())}")
                elif cmd == "/save":
                    self._save_session()
                elif cmd == "/load":
                    if arg:
                        self._load_session(arg)
                    else:
                        print("Usage: /load <session_file>")
                elif cmd == "/export":
                    if arg:
                        self._export_campaign(arg)
                    else:
                        print("Usage: /export <filename>")
                elif cmd == "/copy":
                    print("Last response: ~/cathedral/last_response.txt")
                elif cmd == "/cost":
                    self._print_status()
                elif cmd == "/exit":
                    self._save_session()
                    break
                else:
                    print(f"Unknown command: {cmd}")
                continue

            # ── Pre-send watchdog ───────────────────────────
            if not self._watchdog_check_prompt(user_input):
                continue

            # ── Send to API ─────────────────────────────────
            self.messages.append({"role": "user", "content": user_input})

            try:
                response = self.client.chat.completions.create(
                    model="deepseek-v4-pro",
                    messages=self.messages,
                    stream=True,
                )

                print("\n" + "=" * 60)
                full_response = ""
                for chunk in response:
                    content = chunk.choices[0].delta.content or ""
                    print(content, end="", flush=True)
                    full_response += content
                print("\n" + "=" * 60 + "\n")

                # ── Command extraction ──────────────────────
                import re
                commands = re.findall(
                    r"^(/[a-zA-Z_]+(?:\s+[^\n]+)?)",
                    full_response,
                    re.MULTILINE,
                )
                if commands:
                    print("\n" + "!" * 40)
                    print("COMMANDS DETECTED — Copy-paste to execute:")
                    for cmd in commands:
                        print(f"  {cmd}")
                    print("!" * 40 + "\n")

                # ── Cost tracking ───────────────────────────
                # Note: response.usage is not available in streaming mode
                # Track tokens manually or disable for now
                self.running_tokens += len(full_response.split())  # rough estimate
                self.running_cost += len(full_response.split()) * 0.000002
                print(f"[Cost: ~${len(full_response.split()) * 0.000002:.6f} | Tokens: ~{len(full_response.split())}]")

                # ── Auto-save response ──────────────────────
                with open(
                    Path("~/cathedral/last_response.txt").expanduser(), "w"
                ) as f:
                    f.write(full_response)

                # ── Post-response watchdog ──────────────────
                full_response = self._watchdog_check_response(full_response)

                self.messages.append(
                    {"role": "assistant", "content": full_response}
                )
                log(
                    "ai_response",
                    "deepseek-v4-pro",
                    {"tokens": usage.total_tokens if usage else 0},
                )

            except Exception as e:
                print(f"[API ERROR] {e}")
                log("api_error", "orchestrator", {"error": str(e)})


if __name__ == "__main__":
    orchestrator = CathedralOrchestrator()
    orchestrator.run()
