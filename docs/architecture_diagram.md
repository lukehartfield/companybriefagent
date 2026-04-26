# Architecture Diagram

```mermaid
flowchart TD
    U["User input: public company name"] --> S["Supervisor / Orchestrator<br/>LangGraph state machine"]

    S --> P["CompanyProfileAgent<br/>web search + Wikipedia fallback"]
    P --> PR{"Retry up to 3x"}
    PR -->|success| F["FinancialAnalystAgent"]
    PR -->|fallback| PF["Profile fallback<br/>partial company overview"]
    PF --> F

    F --> FT["Deterministic finance path<br/>ticker resolution -> yfinance fields"]
    F --> FC["Best-effort competitor path<br/>search-supported competitor selection"]
    FT --> FR{"Retry up to 3x"}
    FC --> FR
    FR -->|success| N["NewsAgent<br/>recent material developments"]
    FR -->|fallback| FF["Finance fallback<br/>mark unavailable fields<br/>partial competitors if needed"]
    FF --> N

    N --> NR{"Retry up to 3x"}
    NR -->|success| Y["SynthesisAgent<br/>assemble six-section brief"]
    NR -->|fallback| NF["News fallback<br/>partial news section with disclaimer"]
    NF --> Y

    Y --> V["ValidatorAgent<br/>structure + grounding checks"]
    V --> VC{"Validation pass?"}
    VC -->|yes| M["Final markdown brief"]
    VC -->|no, first failure| Y2["One revision pass through SynthesisAgent"]
    Y2 --> V2["ValidatorAgent re-check"]
    V2 --> V3{"Validation pass?"}
    V3 -->|yes| M
    V3 -->|no| MP["Return partial brief<br/>with validation note"]

    M --> PDF["PDF export"]
    MP --> PDF
```

Chosen topology: `Supervisor-Worker`

Why it fits:
- The supervisor owns routing, retries, aggregation, revision control, and termination.
- Workers stay specialized and do not communicate directly with one another.
- The flow is mostly sequential, which made failure handling and debugging easier than a looser agent-to-agent conversation pattern.
- The finance layer is intentionally split so the `Financial Snapshot` is more deterministic than competitor discovery.
- The validator adds a confidence layer before final output, and the PDF export turns the same generated brief into a more submission-ready artifact.
