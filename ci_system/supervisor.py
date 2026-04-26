from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

from ci_system.agents import (
    CompanyProfileAgent,
    FinancialAnalystAgent,
    NewsAgent,
    SynthesisAgent,
    ValidatorAgent,
)
from ci_system.llm import LLMClient
from ci_system.models import GraphState
from ci_system.pdf_export import export_brief_pdf
from ci_system.tools import load_fixture


logger = logging.getLogger(__name__)


def configure_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(log_path, mode="w"),
            logging.StreamHandler(),
        ],
        force=True,
    )


def _append_log(state: GraphState, message: str) -> None:
    logs = list(state.get("agent_logs", []))
    logs.append(message)
    state["agent_logs"] = logs
    logger.info(message)


def _is_rate_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "429" in text or "rate limit" in text or "too many requests" in text


def _run_with_retry(state: GraphState, agent_name: str, primary, fallback):
    retry_counts = dict(state.get("retry_counts", {}))
    fallback_flags = dict(state.get("fallback_flags", {}))
    low_rate_mode = bool(state.get("low_rate_mode", False))
    max_attempts = 1 if low_rate_mode else 3
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            payload = primary()
            retry_counts[agent_name] = attempt
            state["retry_counts"] = retry_counts
            fallback_flags[agent_name] = False
            state["fallback_flags"] = fallback_flags
            _append_log(state, f"{agent_name} succeeded on attempt {attempt}.")
            return payload
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            if _is_rate_limit_error(exc):
                state["rate_limited"] = True
                if low_rate_mode:
                    _append_log(
                        state,
                        f"{agent_name} hit a rate limit in low-rate mode; skipping retries and using fallback.",
                    )
                    break
            if attempt < max_attempts:
                _append_log(state, f"{agent_name} failed. Retrying (attempt {attempt + 1} of {max_attempts})... Error: {exc}")
                if _is_rate_limit_error(exc):
                    # Gentle throttle to avoid flooding provider buckets.
                    time.sleep(2)
            else:
                _append_log(state, f"{agent_name} failed on final attempt ({attempt} of {max_attempts}). Error: {exc}")
    _append_log(state, f"{agent_name} failed after {max_attempts} attempts. Falling back to alternative strategy.")
    retry_counts[agent_name] = max_attempts
    fallback_flags[agent_name] = True
    state["retry_counts"] = retry_counts
    state["fallback_flags"] = fallback_flags
    return fallback()


def _run_once_with_fallback_log(state: GraphState, agent_name: str, primary, fallback):
    try:
        payload = primary()
        _append_log(state, f"{agent_name} succeeded on first attempt.")
        return payload
    except Exception as exc:  # noqa: BLE001
        if _is_rate_limit_error(exc):
            state["rate_limited"] = True
        _append_log(state, f"{agent_name} failed. Using deterministic fallback. Error: {exc}")
        return fallback()


class CompetitiveIntelligenceSupervisor:
    def __init__(self, llm: LLMClient, fixture: dict | None = None) -> None:
        self.llm = llm
        self.fixture = fixture
        self.profile_agent = CompanyProfileAgent(llm)
        self.financial_agent = FinancialAnalystAgent(llm)
        self.news_agent = NewsAgent(llm)
        self.synthesis_agent = SynthesisAgent(llm)
        self.validator_agent = ValidatorAgent(llm)
        self.graph = self._build_graph()

    def _build_graph(self):
        from langgraph.graph import END, START, StateGraph

        graph = StateGraph(GraphState)
        graph.add_node("supervisor", self.supervisor_node)
        graph.add_node("company_profile", self.company_profile_node)
        graph.add_node("financial_analyst", self.financial_analyst_node)
        graph.add_node("news_agent", self.news_agent_node)
        graph.add_node("synthesis", self.synthesis_node)
        graph.add_node("validator", self.validator_node)
        graph.add_node("finalize", self.finalize_node)

        graph.add_edge(START, "supervisor")
        graph.add_edge("supervisor", "company_profile")
        graph.add_edge("company_profile", "financial_analyst")
        graph.add_edge("financial_analyst", "news_agent")
        graph.add_edge("news_agent", "synthesis")
        graph.add_edge("synthesis", "validator")
        graph.add_conditional_edges(
            "validator",
            self.validator_router,
            {
                "revise": "synthesis",
                "finalize": "finalize",
            },
        )
        graph.add_edge("finalize", END)
        return graph.compile()

    def supervisor_node(self, state: GraphState) -> GraphState:
        state.setdefault("agent_logs", [])
        state.setdefault("retry_counts", {})
        state.setdefault("fallback_flags", {})
        state.setdefault("revision_count", 0)
        state.setdefault("low_rate_mode", False)
        state.setdefault("rate_limited", False)
        _append_log(state, f"Supervisor starting CI workflow for {state['company_name']}.")
        return state

    def company_profile_node(self, state: GraphState) -> GraphState:
        fixture = state.get("fixture")
        state["company_profile"] = _run_with_retry(
            state,
            self.profile_agent.name,
            lambda: self.profile_agent.run(state["company_name"], fixture=fixture),
            lambda: self.profile_agent.fallback(state["company_name"], fixture=fixture),
        )
        return state

    def financial_analyst_node(self, state: GraphState) -> GraphState:
        fixture = state.get("fixture")
        state["financial_analysis"] = _run_with_retry(
            state,
            self.financial_agent.name,
            lambda: self.financial_agent.run(state["company_name"], fixture=fixture),
            lambda: self.financial_agent.fallback(state["company_name"], fixture=fixture),
        )
        return state

    def news_agent_node(self, state: GraphState) -> GraphState:
        fixture = state.get("fixture")
        state["news_analysis"] = _run_with_retry(
            state,
            self.news_agent.name,
            lambda: self.news_agent.run(state["company_name"], fixture=fixture),
            lambda: self.news_agent.fallback(state["company_name"], fixture=fixture),
        )
        return state

    def synthesis_node(self, state: GraphState) -> GraphState:
        revision_feedback = state.get("validation_errors", []) if state.get("revision_count", 0) > 0 else []
        state["draft_brief"] = _run_once_with_fallback_log(
            state,
            self.synthesis_agent.name,
            lambda: self.synthesis_agent.run(
                state["company_name"],
                state["company_profile"],
                state["financial_analysis"],
                state["news_analysis"],
                revision_feedback=revision_feedback,
            ),
            lambda: self.synthesis_agent.fallback(
                state["company_name"],
                state["company_profile"],
                state["financial_analysis"],
                state["news_analysis"],
                revision_feedback=revision_feedback,
            ),
        )
        return state

    def validator_node(self, state: GraphState) -> GraphState:
        result = _run_once_with_fallback_log(
            state,
            self.validator_agent.name,
            lambda: self.validator_agent.run(
                state["company_name"],
                state["draft_brief"],
                state["company_profile"],
                state["financial_analysis"],
                state["news_analysis"],
            ),
            lambda: {
                "validation_pass": False,
                "errors": ["Validator fallback triggered due to repeated validation failure."],
                "confidence_summary": "Validation failed repeatedly; returning partial result.",
            },
        )
        state["validation_pass"] = bool(result.get("validation_pass"))
        state["validation_errors"] = list(result.get("errors", []))
        if state["validation_pass"]:
            state["next_action"] = "finalize"
        elif state.get("rate_limited", False):
            state["next_action"] = "finalize"
            _append_log(
                state,
                "Validator requested revision, but rate limiting was detected; skipping revision pass to conserve quota.",
            )
        elif state.get("revision_count", 0) < 1:
            state["revision_count"] = state.get("revision_count", 0) + 1
            state["next_action"] = "revise"
            _append_log(state, "Validator requested one synthesis revision pass.")
        else:
            state["next_action"] = "finalize"
            _append_log(state, "Validator did not pass after one revision. Returning partial brief with disclaimer.")
        _append_log(
            state,
            "ValidatorAgent pass status: "
            + ("pass." if state["validation_pass"] else f"fail with {len(state['validation_errors'])} issue(s)."),
        )
        return state

    def validator_router(self, state: GraphState) -> str:
        return state.get("next_action", "finalize")

    def finalize_node(self, state: GraphState) -> GraphState:
        brief = state.get("draft_brief", "")
        if not state.get("validation_pass"):
            brief += (
                "\n\n## Validation Note\n"
                "This brief is being returned with one or more unresolved validation concerns. "
                "Potential issues identified during the validator step include:\n"
                + "\n".join(f"- {item}" for item in state.get("validation_errors", []))
            )
        state["final_brief"] = brief
        _append_log(state, f"Supervisor completed the Competitive Intelligence Brief for {state['company_name']}.")
        return state

    def run(self, company_name: str, low_rate_mode: bool = False) -> GraphState:
        initial_state: GraphState = {
            "company_name": company_name,
            "fixture": self.fixture,
            "agent_logs": [],
            "retry_counts": {},
            "fallback_flags": {},
            "revision_count": 0,
            "next_action": "finalize",
            "low_rate_mode": low_rate_mode,
            "rate_limited": False,
        }
        return self.graph.invoke(initial_state)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the multi-agent competitive intelligence system.")
    parser.add_argument("company", help="Public company name, e.g. AMD")
    parser.add_argument("--fixture", help="Optional JSON fixture for reproducible offline runs.", default=None)
    parser.add_argument("--output", help="Where to save the generated markdown brief.", default="outputs/latest_brief.md")
    parser.add_argument("--pdf-output", help="Where to save the generated PDF brief.", default=None)
    parser.add_argument("--log", help="Where to save execution logs.", default="logs/run.log")
    parser.add_argument(
        "--low-rate",
        action="store_true",
        help="Minimize LLM requests by reducing retries and skipping validator revision after rate limits.",
    )
    return parser.parse_args()


def main() -> int:
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None
    if load_dotenv is not None:
        load_dotenv()

    args = parse_args()
    base_dir = Path(__file__).resolve().parent.parent
    output_path = (base_dir / args.output).resolve()
    pdf_output_path = (base_dir / args.pdf_output).resolve() if args.pdf_output else output_path.with_suffix(".pdf")
    log_path = (base_dir / args.log).resolve()
    configure_logging(log_path)

    fixture = load_fixture(args.fixture) if args.fixture else None
    llm = LLMClient()
    supervisor = CompetitiveIntelligenceSupervisor(llm=llm, fixture=fixture)
    final_state = supervisor.run(args.company, low_rate_mode=args.low_rate)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(final_state["final_brief"])
    export_brief_pdf(final_state["final_brief"], pdf_output_path, title=f"Competitive Intelligence Brief: {args.company}")
    logger.info("Saved brief to %s", output_path)
    logger.info("Saved PDF brief to %s", pdf_output_path)
    return 0
