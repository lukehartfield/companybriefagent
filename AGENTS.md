# Agent Instructions

This repository contains a course assignment project for the MSBA `Leveraging LLM Productivity` course.

## Project goal

Build a multi-agent competitive intelligence system for `public companies` that produces a six-section Competitive Intelligence Brief.

## Locked architecture

- Framework: `LangGraph`
- LLM provider path: `OpenRouter`
- Default model: `nvidia/nemotron-3-super-120b-a12b:free`
- Topology: `Supervisor-Worker`
- Flow: mostly sequential with one validator-driven revision loop

## Required pipeline

1. `Supervisor`
2. `Company Profile Agent`
3. `Financial Analyst Agent`
4. `News Agent`
5. `Synthesis Agent`
6. `Validator Agent`
7. optional single revision pass
8. finalize output

## Assignment requirements that must stay intact

- At least 3 specialized agents
- Explicit supervisor/orchestrator
- Retry behavior with visible logs
- Fallback behavior with visible logs
- Final brief must contain exactly:
  - `Company Overview`
  - `Products & Services`
  - `Financial Snapshot`
  - `Top 3 Competitors`
  - `Recent News`
  - `Strategic Assessment`

## Implementation notes

- The project should work for any public company with sufficient public information.
- Never fabricate financial data. If unavailable, say so explicitly.
- The validator is part of the architecture, not an optional extra.
- The system should terminate cleanly even when live network calls fail.
- Keep deterministic fallback behavior in place.

## Environment notes

- The Codex desktop tool environment may have restricted outbound network access.
- A run that falls back due to network/tool failure is not necessarily a code bug.
- Do not commit `.env` or `.venv`.

## Useful commands

```bash
cd "/Users/luke/Desktop/leveraging llm prod/agent hw"
.venv/bin/python main.py AMD
python3 -m py_compile main.py ci_system/*.py
```

