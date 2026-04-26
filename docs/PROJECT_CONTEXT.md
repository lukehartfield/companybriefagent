# Project Context

## Why this repo exists

This repo is an assignment project for the MSBA `Leveraging LLM Productivity` course. The assignment asks for a multi-agent competitive intelligence system with a supervisor, at least three specialized agents, retry/fallback behavior, and a structured brief output.

## Final design direction

- `LangGraph` orchestration
- configurable OpenAI-compatible model backend
- current default OpenRouter model: `google/gemma-4-26b-a4b-it:free`
- `Supervisor-Worker` topology
- public-company focus only
- validator-driven confidence/hallucination control
- deterministic finance snapshot generation from structured ticker-based fields

## Graph shape

`Supervisor -> Company Profile -> Financial Analyst -> News -> Synthesis -> Validator -> (Revise once or Finalize)`

## Important runtime caveat

The project has already been tested in a restricted environment where external services were unreachable. In that environment:

- the graph still executed
- retry logic triggered
- fallback logic triggered
- the validator revision loop terminated correctly
- the system returned a partial-but-honest brief

This means:
- control flow is working
- live-data quality still depends on normal network access when run outside the restricted sandbox

## Important implementation detail

The finance layer has been intentionally refactored so that:

- ticker resolution is more deterministic through overrides and exact matching
- the `Financial Snapshot` is built from structured `yfinance` fields rather than free-form LLM finance prose
- competitor discovery is best-effort and does not have to break the finance snapshot

## Main files

- `main.py`: CLI entry point
- `ci_system/supervisor.py`: LangGraph workflow and routing
- `ci_system/agents.py`: agent implementations
- `ci_system/tools.py`: search / wikipedia / finance helpers
- `README.md`: architecture and setup overview
- `AGENTS.md`: coding-agent guidance for future changes
