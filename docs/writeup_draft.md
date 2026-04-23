# Multi-Agent Competitive Intelligence System

## 1. Design Decisions

I built the system from scratch in Python rather than using a higher-level framework. The main reason was control and explainability: the assignment emphasizes topology, routing, retry, fallback, and honest engineering reflection more than framework-specific abstractions. The chosen topology is `Supervisor-Worker`, which maps naturally to this task and to the lecture recommendation. A single `CompetitiveIntelligenceSupervisor` receives the company name, dispatches the `ResearchAgent` and `FinancialAnalystAgent`, aggregates their outputs, and hands them to the `SynthesisAgent` to assemble the final six-section brief.

The problem is decomposed along clear role boundaries. The `ResearchAgent` focuses on company background, products/services, and recent news using search plus Wikipedia fallback. The `FinancialAnalystAgent` handles revenue/growth/profitability and competitor identification using `yfinance` plus web-search evidence. The `SynthesisAgent` converts the intermediate findings into the final analyst-style brief. This matches the course theme that agentic systems perform better when tasks are broken into specialized units instead of pushed through one monolithic prompt. The prompts are role-specific: the research prompt emphasizes factual extraction and current news, the financial prompt emphasizes no-fabrication behavior and explicit uncertainty, and the synthesis prompt enforces the six required output sections and concise executive tone.

## 2. Failure Handling

Retry and fallback are implemented in code, not just described. The supervisor wraps each worker in a `run_with_retry(...)` helper that retries up to three times on exceptions or empty-source failures. The logs are intentionally explicit so they can be shown in the submission, for example: `ResearchAgent failed. Retrying (attempt 2 of 3)...` and `FinancialAnalystAgent failed after 3 retries. Falling back to alternative strategy.`

The fallback strategies are role-specific. If the `ResearchAgent` fails repeatedly, it falls back to a Wikipedia-first partial response and inserts a disclaimer for missing product or news detail rather than fabricating it. If the `FinancialAnalystAgent` fails repeatedly, it marks revenue/growth/profitability as unavailable and avoids unsupported competitor claims. The `SynthesisAgent` also has a final deterministic formatter fallback in case the LLM call fails, which preserves system completion even when the language model is unavailable. This design follows the lecture idea of a probabilistic core inside a deterministic envelope: the LLM is helpful, but the system behavior around it is still controlled.

## 3. Results

The sample run uses NVIDIA because it has rich public information and current news coverage. In the strongest runs, the system produces a coherent brief covering all six required sections, with especially good performance on company overview, product positioning, and high-level financials. The most fragile areas are competitor quality and news freshness because both depend on external search quality. If the search layer returns weak snippets, the system still completes the brief but the strategic nuance becomes thinner. Those limitations are visible in the raw output and should be discussed rather than hidden.

## 4. Evaluation Reflection

If this were being evaluated for real business use, I would use both objective checks and judgment-based evals. Objective checks would verify that all six sections are present, that recent news items include citations, that private-company runs never fabricate revenue, and that the brief length stays within a target range. I would also create a held-out evaluation set of companies with known properties: one large public company, one fast-growing private company, one company with weak financial disclosure, and one company with ambiguous competitors. This follows the evaluation lecture's emphasis on held-out sets, target success rate, and failure-mode taxonomy.

The failure taxonomy would include fabricated financial data, stale news outside the 12-month window, wrong competitor identification, unsupported strategic claims, and malformed section structure. For subjective evaluation, I would use an LLM-as-judge rubric or human rubric asking whether the brief is useful for a strategy analyst, whether uncertainty is communicated honestly, and whether the synthesis captures strengths, risks, and forward-looking implications. I would consider the system "good enough" only if it passes structure checks nearly always and reaches a clearly defined usefulness threshold across a held-out company set.

