# Multi-Agent Competitive Intelligence System

This repo contains an implemented multi-agent competitive intelligence system for an assignment in the MSBA Leveraging LLM Productivity course. The system accepts a public company name and produces a six-section Competitive Intelligence Brief using a `Supervisor-Worker` architecture in `LangGraph`.

## Current architecture

The implemented system uses:

- Framework: `LangGraph`
- LLM backend: configurable `OpenAI-compatible` provider
- default model path: `OpenRouter` using `google/gemma-4-26b-a4b-it:free`
- Topology: `Supervisor-Worker`
- Flow style: mostly `sequential`, with one validator-driven revision loop
- Company scope: `public companies only`
- Depth mechanism: `Validator Agent` to reduce hallucination risk and improve confidence in the final brief

This implementation is designed to:

- clear agent specialization instead of one monolithic prompt
- explicit orchestration and routing through a supervisor
- deterministic structure around probabilistic model calls
- retry and fallback as first-class workflow behavior
- evaluation-minded design through a validator/oracle layer

## Implemented pipeline

The current pipeline is:

1. `Supervisor`
2. `Company Profile Agent`
3. `Financial Analyst Agent`
4. `News Agent`
5. `Synthesis Agent`
6. `Validator Agent`
7. if validation passes -> return final brief
8. if validation fails once but is recoverable -> send back to `Synthesis Agent`
9. if validation still fails -> return partial brief with a disclaimer

This is a sequential backbone, but it still qualifies as `Supervisor-Worker` because the supervisor owns routing, retries, fallbacks, aggregation, and termination.

## Agent roles

### `Supervisor`

Responsibility:
- receives the company name
- initializes graph state
- routes control between nodes
- manages retry counts and fallback flags
- decides when the workflow terminates

### `Company Profile Agent`

Responsibility:
- gathers company overview facts
- gathers products/services
- identifies customer segments and value proposition

Primary assignment coverage:
- `Company Overview`
- `Products & Services`

Tools:
- web search
- Wikipedia fallback

### `Financial Analyst Agent`

Responsibility:
- resolves ticker as deterministically as possible
- pulls structured public-company financial metrics from `yfinance`
- builds the `Financial Snapshot` deterministically from raw fields
- identifies the top 3 competitors as a separate best-effort step
- provides one competitor differentiator for each

Primary assignment coverage:
- `Financial Snapshot`
- `Top 3 Competitors`

Tools:
- `yfinance`
- web search for annual-report / IR support and competitor support if needed

Important implementation detail:
- the `Financial Snapshot` is intentionally more deterministic than the rest of the pipeline
- once a ticker is resolved, the snapshot is constructed directly from structured `yfinance` fields rather than LLM-generated finance prose
- competitor discovery is allowed to degrade independently so a flaky search step does not invalidate the finance snapshot

### `News Agent`

Responsibility:
- finds 2-3 material developments from the last 12 months
- prioritizes items relevant to competitive position
- attaches sources

Primary assignment coverage:
- `Recent News`

Tools:
- web search

### `Synthesis Agent`

Responsibility:
- assembles the final six-section Competitive Intelligence Brief
- uses only upstream structured findings
- expresses uncertainty honestly instead of filling gaps with fabricated claims

Primary assignment coverage:
- all six final sections
- especially `Strategic Assessment`

### `Validator Agent`

Responsibility:
- checks completeness
- checks structural correctness
- checks for unsupported or likely hallucinated claims
- decides whether the brief passes, needs one revision, or should be returned with a disclaimer

Why this agent matters:
- improves pipeline confidence
- gives a stronger anti-hallucination story
- aligns directly with the course material on evaluation and deterministic envelopes
- may support bonus-credit positioning depending on final implementation quality

## Validation strategy

The validator should combine deterministic checks with an LLM-based review.

Deterministic checks:
- all 6 required section headings exist
- `Top 3 Competitors` contains exactly 3 competitors
- competitor names are not duplicated
- `Recent News` contains 2-3 items
- recent news includes source URLs
- no section is empty

LLM-based checks:
- are the competitors plausibly supported by upstream evidence?
- does the strategic assessment overclaim beyond the gathered facts?
- are any financial claims invented instead of explicitly marked unavailable?

## Retry and fallback behavior

The assignment requires both `retry` and `fallback`, and both are implemented in the workflow.

Retry:
- `Company Profile Agent`: retry with alternative search query if initial results are weak
- `Financial Analyst Agent`: retry ticker/company matching or secondary finance lookup path
- `News Agent`: retry with a different recency-focused search query
- `Synthesis Agent`: optionally retry once only if the output is malformed

Fallback:
- `Company Profile Agent`: use Wikipedia-first partial output with disclaimer
- `Financial Analyst Agent`: return a partial financial snapshot and explicitly mark unavailable structured fields; competitor discovery can degrade separately
- `News Agent`: return fewer news items with limited-coverage disclaimer
- `Synthesis Agent`: use deterministic template formatter if necessary

## LangGraph state

The graph maintains structured state such as:

- `company_name`
- `company_profile`
- `financial_data`
- `competitors`
- `recent_news`
- `draft_brief`
- `final_brief`
- `validation_pass`
- `validation_errors`
- `revision_count`
- `retry_counts`
- `fallback_flags`
- `agent_logs`

## What is implemented now

- `LangGraph` workflow with explicit nodes and conditional routing
- `Company Profile`, `Financial Analyst`, `News`, `Synthesis`, and `Validator` agents
- per-agent retry handling with log messages
- per-agent fallback behavior
- single validator-driven revision loop
- deterministic finance snapshot construction from structured ticker-based fields
- improved ticker resolution with overrides and exact matching
- deterministic finalization path that still returns a brief if live services fail

Main implementation files:

- `main.py`
- `ci_system/supervisor.py`
- `ci_system/agents.py`
- `ci_system/tools.py`
- `ci_system/models.py`

## Why this design fits the assignment

- It satisfies the requirement for at least 3 specialized agents.
- It uses an explicit supervisor/orchestrator.
- It cleanly names and justifies the `Supervisor-Worker` topology.
- It includes both mandatory failure-handling mechanisms.
- It adds depth in a way that is meaningful rather than decorative.
- It should be straightforward to explain in the write-up and architecture diagram.

## Setup

```bash
cd "/Users/luke/Desktop/leveraging llm prod/agent hw"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set your API keys in `.env`:

```bash
LLM_PROVIDER=openrouter

OPENROUTER_API_KEY=your_key_here
OPENROUTER_MODEL=google/gemma-4-26b-a4b-it:free
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

NVIDIA_API_KEY=your_key_here
NVIDIA_MODEL=minimaxai/minimax-m2.7
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1

OPENAI_MAX_RETRIES=0
SEARCH_REGION=us-en
```

Notes:
- The default provider path is `OpenRouter`.
- To use NVIDIA hosted inference instead, set `LLM_PROVIDER=nvidia`.
- The live run will depend on internet access because the research and finance workers call real-world data tools.
- If the LLM or external data sources are unavailable, the workflow should still terminate and return a partial-but-honest brief.
- The finance layer is now designed so the `Financial Snapshot` can remain deterministic and structured even if competitor discovery is weaker.

## How to run

Run with the local virtual environment:

```bash
.venv/bin/python main.py AMD
```

Low-rate mode (fewer LLM requests when free-tier limits are tight):

```bash
.venv/bin/python main.py AMD --low-rate
```

You can replace `AMD` with any public company name.

## Expected output

The system writes:

- A markdown Competitive Intelligence Brief to `outputs/latest_brief.md` by default
- Execution logs to `logs/run.log` by default

The brief contains exactly these six sections:

1. `Company Overview`
2. `Products & Services`
3. `Financial Snapshot`
4. `Top 3 Competitors`
5. `Recent News`
6. `Strategic Assessment`

## Failure handling

This project implements both required mechanisms:

- `Retry`: each worker is retried up to three times on failure
- `Fallback`: if retries are exhausted, the worker returns a partial-but-honest result

Example log messages:

- `CompanyProfileAgent failed. Retrying (attempt 2 of 3)...`
- `FinancialAnalystAgent failed after 3 retries. Falling back to alternative strategy.`

## Verification status

What has been verified:

- the source compiles
- the LangGraph workflow builds successfully
- the graph terminates correctly
- the validator loop revises at most once
- a brief is still returned when live services fail
- the finance path is now structured so ticker-based snapshot generation is isolated from competitor-search failures

Important caveat:

- the Codex desktop sandbox used during development had restricted outbound access, so live calls to Wikipedia, web search, Yahoo/yfinance, and OpenRouter failed in-tool
- because of that, the in-tool runtime primarily exercised retry and fallback behavior rather than the full live-data path
- the system should be re-run in a normal local environment with network access for a true live brief

## Framework choice

Framework choice: `LangGraph`

Reason:
- best fit for explicit graph/state orchestration
- strong support for supervisor-worker routing and controlled loops
- easier to express validator feedback and conditional edges than a plain script
- still close enough to the mechanics that the system remains explainable in the write-up

## Suggested submission bundle

- code folder
- `README.md`
- `requirements.txt`
- `AGENTS.md`
- `docs/PROJECT_CONTEXT.md`
- architecture diagram from `docs/architecture_diagram.md`
- write-up PDF based on `docs/writeup_draft.md`
- sample output from `outputs/sample_nvidia_brief.md`
