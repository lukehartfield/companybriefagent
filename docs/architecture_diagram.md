# Architecture Diagram

```mermaid
flowchart TD
    U[User enters public company name] --> S[Supervisor / Orchestrator]
    S --> P[Company Profile Agent]
    P --> PR{Retry up to 3x}
    PR -->|success| F[Financial Analyst Agent]
    PR -->|fail after retries| PF[Profile fallback:
    partial overview/products disclaimer]

    PF --> F
    F --> FR{Retry up to 3x}
    FR -->|success| N[News Agent]
    FR -->|fail after retries| FF[Finance fallback:
    deterministic unavailable snapshot + partial competitors]

    FF --> N
    N --> NR{Retry up to 3x}
    NR -->|success| Y[Synthesis Agent]
    NR -->|fail after retries| NF[News fallback:
    partial news disclaimer]

    NF --> Y
    Y --> V[Validator Agent]
    V --> VC{Pass?}
    VC -->|yes| O[Final Competitive Intelligence Brief]
    VC -->|no, first failure| Y2[One synthesis revision pass]
    Y2 --> V2[Validator Agent]
    V2 --> O2[Final brief or partial brief with validation note]
```

Chosen topology: `Supervisor-Worker`

Why it fits:
- The supervisor owns routing, retries, aggregation, revision control, and termination.
- Workers stay specialized and do not communicate directly with each other.
- The finance layer is intentionally split so ticker-based `Financial Snapshot` generation is more deterministic than competitor discovery.
- The validator adds a deterministic-envelope layer around the final LLM-generated brief.
