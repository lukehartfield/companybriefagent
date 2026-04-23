# Architecture Diagram

```mermaid
flowchart TD
    U[User enters company name] --> S[Supervisor / Orchestrator]
    S --> R[Research Agent]
    S --> F[Financial Analyst Agent]
    R --> RT{Retry up to 3x}
    F --> FT{Retry up to 3x}
    RT -->|fail after retries| RF[Research fallback:
    Wikipedia-only / partial brief disclaimer]
    FT -->|fail after retries| FF[Finance fallback:
    unavailable metrics / partial competitor set]
    RT -->|success| RA[Research findings]
    FT -->|success| FA[Financial findings]
    RF --> A[Aggregation]
    FF --> A
    RA --> A
    FA --> A
    A --> SY[Synthesis Agent]
    SY --> O[Competitive Intelligence Brief]
```

Chosen topology: `Supervisor-Worker`

Why it fits:
- The supervisor owns routing, aggregation, and termination.
- Workers stay specialized and do not talk directly to each other.
- Retry and fallback happen cleanly at the worker boundary, which matches the lecture's deterministic-envelope framing.

