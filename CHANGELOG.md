# Cathedral Orchestrator Changelog

## v2.0.0 — Structural Rebuild (2026-07-21)

### Added
- AI-native command generation: system prompt includes full `/` command reference
- Auto-extraction of commands from AI responses into `COMMANDS DETECTED` box
- `/project`, `/read`, `/write`, `/run`, `/status`, `/commit`, `/push` commands
- Session save/load with JSON persistence
- Campaign file export (`/export`)
- Pre-send watchdog: blocks patch-default prompts before API call
- Post-response watchdog with RLHF inversion
- Running cost + token remaining display at every prompt
- Command history via readline (arrow keys)

### Fixed
- Cost tracking scope bug: `response.usage` referenced outside try block during
  live godot-OE DeepSeek module build test. Discovered when AI generated correct
  build commands but cost tracking failed with [API ERROR].

### Known Issues
- Auto-execution of commands not yet implemented: human must still copy-paste
  from COMMANDS DETECTED box
