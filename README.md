# AI-Collab

Terminal-native multi-AI-model collaboration workstation.

Orchestrate Claude Code, Codex CLI, Gemini CLI (and more) in a unified workspace with role-based coordination, structured inter-model communication, and per-project isolation.

## Status

**Early development** — see [docs/PRD.md](docs/PRD.md) for the product requirements document.

## The Problem

Developers using multiple AI coding CLIs face:
- **Context leakage** between projects (shared logs, state files)
- **No collaboration protocol** between models (ad-hoc shell scripts)
- **Manual session management** (tmux crashes, nested attach failures)
- **Scattered configuration** across dotfiles

## The Vision

```bash
# One command to start a multi-model workspace
ai-collab start ~/workspace/myproject

# Layout:
# ┌──────────────────────┬──────────────┐
# │                      │   Codex      │
# │   Claude Code        │  (reviewer)  │
# │   (designer)         ├──────────────┤
# │                      │   Gemini     │
# │                      │ (inspiration)│
# └──────────────────────┴──────────────┘

# Claude auto-coordinates with Codex for code review
# Gemini provides creative input on demand
# Everything isolated per-project
```

## License

MIT
