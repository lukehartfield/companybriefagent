# Multi-Agent Competitive Intelligence System

## 1. Design Decisions

I chose `LangGraph` because this assignment is mainly an orchestration problem: it needed explicit routing, retries, fallback behavior, shared state, and controlled termination. I considered frameworks such as `CrewAI` and `Hermes`, but `LangGraph` was a better fit for a structured workflow and faster to get working cleanly for this use case. I used a `Supervisor-Worker` topology with a mostly sequential flow because it mapped directly to the assignment and made debugging easier than a looser conversational agent pattern.

The final system uses five worker roles: `CompanyProfileAgent`, `FinancialAnalystAgent`, `NewsAgent`, `SynthesisAgent`, and `ValidatorAgent`. The most important design refinement was in the financial layer. Because financial numbers are a high-risk place to hallucinate, I changed the system to make the `Financial Snapshot` as deterministic as possible using structured `yfinance` fields once the ticker is resolved, while keeping competitor discovery as a separate best-effort step.

I also added two pieces of extra depth: a `ValidatorAgent` so the brief is checked before return, and PDF export so the generated markdown can become a cleaner report artifact. During development, I initially tested free OpenRouter models such as `Nemotron` and `Gemma`, but rate limits became an issue once retries and revision loops were involved. I then switched to free hosted models from `build.nvidia.com`, reduced unnecessary request volume, and found the resulting reliability better for the final pipeline.

## 2. Failure Handling

Retry and fallback are implemented directly in the workflow. The supervisor retries the `CompanyProfileAgent`, `FinancialAnalystAgent`, and `NewsAgent` when they fail, and the logs explicitly show this behavior. If those stages still fail, the system falls back to a role-specific alternative instead of crashing. For example, the profile step can return a partial overview, the news step can return a limited-coverage section, and the financial step can mark values unavailable instead of fabricating numbers.

The synthesis and validator stages are treated differently because they are pure LLM stages and can become expensive under free-tier limits. For those, I favored one attempt followed by deterministic fallback behavior. A concrete example came from the provider iteration: free OpenRouter models often hit rate limits when retries and validator revision were triggered, so I adjusted the system to reduce repeated LLM calls and still return an honest partial output.

## 3. Results

I tested the final live system on `AMD`. The full pipeline completed end-to-end: profile, financial, news, synthesis, and validator all ran successfully, the validator triggered one revision pass, and the system produced both markdown and PDF outputs. The strongest parts of the resulting brief were structure, company overview, and financial specificity.

The AMD run also surfaced useful weaknesses. The validator still rejected the final brief after one revision pass because it found a gross-margin discrepancy, an operating-margin calculation issue, and a few unsupported product and enterprise-penetration claims. I view that as a useful result rather than a failure to hide, because it shows the validator is acting as a real quality gate. The weakest areas remain competitor quality, news grounding, and strategic overclaiming.

## 4. Evaluation Reflection

If I were evaluating this system for real business use, I would separate deterministic checks from qualitative judgment. Deterministic checks would verify that all six sections exist, the competitor list has exactly three distinct names, the news section contains 2-3 sourced items, and missing financial data is explicitly disclosed rather than invented. I would also test the system on multiple public companies across industries to see whether the search and competitor logic generalize.

For qualitative evaluation, I would focus on usefulness, grounding, and honesty. A good brief should be understandable to a strategy analyst, tied clearly to upstream evidence, and explicit about uncertainty. The main failure modes I would test for are stale news, weak competitor selection, unsupported strategic claims, malformed structure, provider rate limits, and finance-source resolution problems. The main lesson from building this system is that multi-agent quality depends as much on orchestration and verification as on model quality itself.
