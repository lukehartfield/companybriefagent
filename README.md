# Multi-Agent Competitive Intelligence System

This repo contains planning and implementation work for an individual assignment in the MSBA Leveraging LLM Productivity course. The target system will accept a public company name and produce a six-section Competitive Intelligence Brief using a `Supervisor-Worker` multi-agent architecture in `LangGraph`.

## Current architecture decision

The design direction for this assignment is now locked in:

- Framework: `LangGraph`
- LLM backend: `OpenRouter` using `nvidia/nemotron-3-super-120b-a12b:free`
- Topology: `Supervisor-Worker`
- Flow style: mostly `sequential`, with one controlled validation loop
- Company scope: `public companies only`
- Depth mechanism: `Validator Agent` to reduce hallucination risk and improve confidence in the final brief

This direction matches the course themes well:

- clear agent specialization instead of one monolithic prompt
- explicit orchestration and routing through a supervisor
- deterministic structure around probabilistic model calls
- retry and fallback as first-class workflow behavior
- evaluation-minded design through a validator/oracle layer

## Proposed pipeline

The planned pipeline is:

1. `Supervisor`
2. `Company Profile Agent`
3. `Financial Analyst Agent`
4. `News Agent`
5. `Synthesis Agent`
6. `Validator Agent`
7. if validation passes -> return final brief
8. if validation fails once but is recoverable -> send back to `Synthesis Agent`
9. if validation still fails -> return partial brief with a disclaimer

This is a sequential backbone, but it still qualifies as `Supervisor-Worker` because the supervisor owns routing, aggregation, retries, fallbacks, and termination.

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

Planned tools:
- web search
- Wikipedia fallback

### `Financial Analyst Agent`

Responsibility:
- pulls public-company financial metrics
- produces revenue/growth/profitability summary
- identifies the top 3 competitors
- provides one competitor differentiator for each

Primary assignment coverage:
- `Financial Snapshot`
- `Top 3 Competitors`

Planned tools:
- `yfinance`
- web search for competitor support if needed

### `News Agent`

Responsibility:
- finds 2-3 material developments from the last 12 months
- prioritizes items relevant to competitive position
- attaches sources

Primary assignment coverage:
- `Recent News`

Planned tools:
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
- `Recent News` contains 2-3 items
- recent news includes source URLs
- no section is empty

LLM-based checks:
- are the competitors plausibly supported by upstream evidence?
- does the strategic assessment overclaim beyond the gathered facts?
- are any financial claims invented instead of explicitly marked unavailable?

## Retry and fallback plan

The assignment requires both `retry` and `fallback`, so they are part of the intended architecture from the start.

Retry:
- `Company Profile Agent`: retry with alternative search query if initial results are weak
- `Financial Analyst Agent`: retry ticker/company matching or secondary finance lookup path
- `News Agent`: retry with a different recency-focused search query
- `Synthesis Agent`: optionally retry once only if the output is malformed

Fallback:
- `Company Profile Agent`: use Wikipedia-first partial output with disclaimer
- `Financial Analyst Agent`: return partial financial snapshot and explicitly mark unavailable data
- `News Agent`: return fewer news items with limited-coverage disclaimer
- `Synthesis Agent`: use deterministic template formatter if necessary

## Planned LangGraph state

The graph will likely maintain structured state such as:

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

## Why this design is a strong fit for the assignment

- It satisfies the requirement for at least 3 specialized agents.
- It uses an explicit supervisor/orchestrator.
- It cleanly names and justifies the `Supervisor-Worker` topology.
- It includes both mandatory failure-handling mechanisms.
- It adds depth in a way that is meaningful rather than decorative.
- It should be straightforward to explain in the write-up and architecture diagram.

## Build plan

The implementation plan is:

1. Set up the LangGraph project skeleton and provider abstraction for OpenRouter/Nemotron.
2. Define the shared graph state and output schemas.
3. Implement worker nodes: `Company Profile`, `Financial Analyst`, and `News`.
4. Implement `Synthesis Agent` and deterministic brief formatter fallback.
5. Implement `Validator Agent` with deterministic checks plus one revision loop.
6. Add retry/fallback handling and logging that can be shown in the submission.
7. Test on a public company with strong public data coverage.
8. Finalize README, architecture diagram, sample output, and write-up.

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
OPENROUTER_API_KEY=your_key_here
OPENROUTER_MODEL=nvidia/nemotron-3-super-120b-a12b:free
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
SEARCH_REGION=us-en
```

Notes:
- The default provider path is now `OpenRouter` with a free `Nemotron` model.
- The live run will depend on internet access because the research and finance workers call real-world data tools.

## How to run

Run with the local virtual environment:

```bash
.venv/bin/python main.py AMD
```

## Expected output

The target system will write:

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

This project is planned to implement both required mechanisms:

- `Retry`: each worker is retried up to three times on failure
- `Fallback`: if retries are exhausted, the worker returns a partial-but-honest result

Example log messages:

- `CompanyProfileAgent failed. Retrying (attempt 2 of 3)...`
- `FinancialAnalystAgent failed after 3 retries. Falling back to alternative strategy.`

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
- architecture diagram from `docs/architecture_diagram.md`
- write-up PDF based on `docs/writeup_draft.md`
- sample output from `outputs/sample_nvidia_brief.md`
