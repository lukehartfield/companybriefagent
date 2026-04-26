from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypedDict


@dataclass
class Source:
    title: str
    url: str
    snippet: str = ""


@dataclass
class NewsItem:
    headline: str
    summary: str
    source: str
    url: str


@dataclass
class Competitor:
    name: str
    why_it_competes: str
    differentiator: str


@dataclass
class ResearchFinding:
    company_name: str
    overview: str
    products_and_services: str
    recent_news: list[NewsItem]
    sources: list[Source] = field(default_factory=list)
    mode: str = "live"


@dataclass
class FinancialFinding:
    company_name: str
    financial_snapshot: str
    competitors: list[Competitor]
    sources: list[Source] = field(default_factory=list)
    mode: str = "live"


@dataclass
class AgentResult:
    agent_name: str
    success: bool
    payload: Any
    attempts: int
    fallback_used: bool = False
    error: str | None = None


class GraphState(TypedDict, total=False):
    company_name: str
    company_profile: dict[str, Any]
    financial_analysis: dict[str, Any]
    news_analysis: dict[str, Any]
    draft_brief: str
    final_brief: str
    validation_pass: bool
    validation_errors: list[str]
    next_action: str
    revision_count: int
    retry_counts: dict[str, int]
    fallback_flags: dict[str, bool]
    agent_logs: list[str]
    fixture: dict[str, Any] | None
    low_rate_mode: bool
    rate_limited: bool
