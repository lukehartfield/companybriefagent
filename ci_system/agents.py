from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from ci_system.llm import LLMClient
from ci_system.models import Competitor, NewsItem, Source
from ci_system.prompts import (
    FINANCIAL_AGENT_PROMPT,
    NEWS_AGENT_PROMPT,
    PROFILE_AGENT_PROMPT,
    SYNTHESIS_AGENT_PROMPT,
    VALIDATOR_AGENT_PROMPT,
)
from ci_system.tools import (
    dedupe_sources,
    get_financial_data,
    get_wikipedia_summary,
    looks_like_ticker,
    money_text,
    normalize_company_name,
    pct_text,
    search_web_queries,
    source_domain,
)


logger = logging.getLogger(__name__)


class CompanyProfileAgent:
    name = "CompanyProfileAgent"

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm
        self.region = os.getenv("SEARCH_REGION", "us-en")

    def run(self, company_name: str, fixture: dict[str, Any] | None = None) -> dict[str, Any]:
        if fixture and fixture.get("profile"):
            return fixture["profile"]

        wiki_summary = get_wikipedia_summary(company_name)
        overview_results = search_web_queries(
            [
                f"{company_name} founded headquarters employees public company",
                f"{company_name} investor relations about company headquarters employees",
                f"{company_name} annual report company overview",
            ],
            region=self.region,
        )
        product_results = search_web_queries(
            [
                f"{company_name} products services customers value proposition",
                f"{company_name} investor relations segments products customers",
                f"{company_name} markets product portfolio enterprise consumer",
            ],
            region=self.region,
        )

        if self.llm.available:
            payload = {
                "company_name": company_name,
                "wikipedia_summary": wiki_summary,
                "overview_results": [r.__dict__ for r in overview_results],
                "product_results": [r.__dict__ for r in product_results],
            }
            response = self.llm.chat_json(
                PROFILE_AGENT_PROMPT,
                f"""Extract structured profile findings from this material.
Return JSON with keys:
- overview
- products_and_services
- sources

The `sources` field should be a list of source objects with keys: title, url, snippet.

Material:
{json.dumps(payload, indent=2)}
""",
            )
            return response

        if not (wiki_summary or overview_results or product_results):
            raise RuntimeError("Profile agent found no usable public-company data.")

        overview = wiki_summary or "Public overview coverage was limited in this run."
        if overview_results:
            overview = (overview + " " + " ".join(r.snippet for r in overview_results[:2] if r.snippet)).strip()

        products = " ".join(r.snippet for r in product_results[:3] if r.snippet).strip()
        if not products:
            products = "Product and customer-segment detail was limited in this run."

        return {
            "overview": overview,
            "products_and_services": products,
            "sources": [r.__dict__ for r in dedupe_sources(overview_results[:3] + product_results[:3])],
        }

    def fallback(self, company_name: str, fixture: dict[str, Any] | None = None) -> dict[str, Any]:
        if fixture and fixture.get("profile"):
            return fixture["profile"]
        return {
            "overview": (
                f"Fallback mode: limited source coverage prevented a fuller profile for {company_name}. "
                "The system is returning a partial company overview rather than fabricating unsupported facts."
            ),
            "products_and_services": "Fallback mode: product and customer detail was unavailable from live search sources.",
            "sources": [],
        }


class FinancialAnalystAgent:
    name = "FinancialAnalystAgent"

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm
        self.region = os.getenv("SEARCH_REGION", "us-en")

    def run(self, company_name: str, fixture: dict[str, Any] | None = None) -> dict[str, Any]:
        if fixture and fixture.get("financial"):
            return fixture["financial"]

        try:
            finance_data = get_financial_data(company_name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Financial data lookup degraded for %s: %s", company_name, exc)
            finance_data = {"ticker": None, "status": "unavailable", "lookup_error": str(exc)}

        financial_snapshot = self._build_deterministic_snapshot(company_name, finance_data)
        annual_results = self._safe_search(
            [
                f"{company_name} annual report investor relations revenue profitability",
                f"{company_name} earnings release revenue operating margin investor relations",
                f"{company_name} 10-k annual report revenue profitability",
            ],
            max_results_per_query=3,
        )
        competitor_results = self._safe_search(
            [
                f"{company_name} competitors alternatives rival companies",
                f"{company_name} competes with which companies semiconductor cloud software",
                f"{company_name} market competitors investor relations",
            ],
            max_results_per_query=4,
        )
        competitors = [item.__dict__ for item in self._competitors_from_search(company_name, competitor_results, finance_data)]
        if finance_data.get("status") != "ok" and not annual_results and not competitor_results:
            raise RuntimeError("Financial agent found no usable public-company data.")

        return {
            "financial_snapshot": financial_snapshot,
            "competitors": competitors,
            "sources": [r.__dict__ for r in dedupe_sources(self._finance_sources(company_name, finance_data, annual_results) + competitor_results[:4])],
            "ticker": finance_data.get("ticker"),
            "finance_data": finance_data,
        }

    def _safe_search(self, queries: list[str], max_results_per_query: int) -> list[Source]:
        try:
            return search_web_queries(
                queries,
                max_results_per_query=max_results_per_query,
                region=self.region,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Financial agent search degraded: %s", exc)
            return []

    def _build_deterministic_snapshot(self, company_name: str, finance_data: dict[str, Any]) -> str:
        if finance_data.get("status") != "ok":
            return (
                "Recent revenue, growth, or profitability data was unavailable from the primary finance tools in this run. "
                "The system is leaving those fields unavailable rather than inventing numbers."
            )

        company_label = finance_data.get("longName", company_name)
        ticker = finance_data.get("ticker") or "unavailable"
        revenue = money_text(finance_data.get("revenue"))
        growth = pct_text(finance_data.get("revenue_growth"))
        profit = pct_text(finance_data.get("profit_margins"))
        operating = pct_text(finance_data.get("operating_margins"))
        gross = pct_text(finance_data.get("gross_margins"))
        employees = finance_data.get("employees")
        employees_text = f"{employees:,}" if isinstance(employees, int) else "unavailable"

        return (
            f"{company_label} ({ticker}) has a deterministic financial snapshot sourced from structured yfinance fields. "
            f"Revenue is {revenue}, revenue growth is {growth}, profit margin is {profit}, operating margin is {operating}, "
            f"gross margin is {gross}, and full-time employee count is {employees_text}. "
            "Any unavailable field is left unavailable rather than estimated or fabricated."
        )

    def _finance_sources(self, company_name: str, finance_data: dict[str, Any], annual_results: list[Source]) -> list[Source]:
        sources: list[Source] = list(annual_results[:4])
        website = finance_data.get("website")
        if website:
            sources.insert(
                0,
                Source(
                    title=f"{company_name} corporate website",
                    url=website,
                    snippet="Corporate or investor-relations source associated with the company.",
                ),
            )
        ticker = finance_data.get("ticker")
        if ticker:
            sources.insert(
                0,
                Source(
                    title=f"{ticker} yfinance structured data",
                    url="https://finance.yahoo.com/",
                    snippet="Deterministic ticker-based finance fields pulled through yfinance.",
                ),
            )
        return sources

    def _competitors_from_search(
        self,
        company_name: str,
        competitor_results: list[Source],
        finance_data: dict[str, Any],
    ) -> list[Competitor]:
        defaults = self._default_competitors(company_name, finance_data)
        if not competitor_results:
            return defaults

        if self.llm.available:
            payload = {
                "company_name": company_name,
                "results": [r.__dict__ for r in competitor_results],
                "finance_data": finance_data,
            }
            try:
                response = self.llm.chat_json(
                    FINANCIAL_AGENT_PROMPT,
                    f"""From these search results, identify the top three competitors.
Return JSON with one key only: competitors.
Each competitor must include name, why_it_competes, differentiator.

Material:
{json.dumps(payload, indent=2)}
""",
                )
                competitors = [Competitor(**item) for item in response.get("competitors", [])[:3]]
                if len(competitors) == 3:
                    return competitors
            except Exception as exc:  # noqa: BLE001
                logger.warning("Competitor LLM extraction degraded for %s: %s", company_name, exc)

        names: list[str] = []
        pattern = re.compile(r"\b[A-Z][A-Za-z0-9&.-]{2,}\b")
        stopwords = {company_name.lower(), "Top", "Best", "Compare", "Companies", "Company"}
        for item in competitor_results:
            for match in pattern.findall(f"{item.title} {item.snippet}"):
                if match.lower() not in {word.lower() for word in stopwords}:
                    names.append(match)
        unique: list[str] = []
        for name in names:
            if name not in unique:
                unique.append(name)
        chosen = unique[:3]
        defaults_by_name = {item.name: item for item in defaults}
        if len(chosen) < 3:
            for item in defaults:
                if item.name not in chosen:
                    chosen.append(item.name)
                if len(chosen) == 3:
                    break
        return [
            defaults_by_name[name] if name in defaults_by_name else Competitor(
                name=name,
                why_it_competes=f"{name} competes with {company_name} in overlapping semiconductor, compute, or enterprise technology markets.",
                differentiator=f"{name} has a distinct product mix, customer base, or platform strategy that differentiates it from {company_name}.",
            )
            for name in chosen[:3]
        ]

    def _default_competitors(self, company_name: str, finance_data: dict[str, Any]) -> list[Competitor]:
        normalized = normalize_company_name(company_name)
        sector = normalize_company_name(finance_data.get("sector") or "")
        industry = normalize_company_name(finance_data.get("industry") or "")
        ticker = (finance_data.get("ticker") or "").upper()
        if normalized in {"amd", "advanced micro devices"} or ticker == "AMD" or "semiconductor" in industry:
            names = ["Intel", "NVIDIA", "Qualcomm"]
        elif "software" in sector or "cloud" in industry:
            names = ["Microsoft", "Oracle", "SAP"]
        elif "internet retail" in industry:
            names = ["Walmart", "Alibaba", "eBay"]
        else:
            names = ["Microsoft", "Alphabet", "Amazon"]
        return [
            Competitor(
                name=name,
                why_it_competes=f"{name} competes with {company_name} in overlapping markets, customer budgets, or adjacent enterprise demand.",
                differentiator=f"{name} has a distinct product mix, platform strategy, or customer footprint that differentiates it from {company_name}.",
            )
            for name in names
        ]

    def fallback(self, company_name: str, fixture: dict[str, Any] | None = None) -> dict[str, Any]:
        if fixture and fixture.get("financial"):
            return fixture["financial"]
        return {
            "financial_snapshot": (
                "Fallback mode: the financial data tool could not return reliable public-company results after retries. "
                "Revenue, growth, and profitability are therefore marked unavailable in this run."
            ),
            "competitors": [
                {
                    "name": "Competitor identification unavailable",
                    "why_it_competes": "The system could not confidently identify competitors from public sources after retries.",
                    "differentiator": "No differentiator is provided in fallback mode to avoid unsupported claims.",
                },
                {
                    "name": "Competitor identification unavailable",
                    "why_it_competes": "The system could not confidently identify competitors from public sources after retries.",
                    "differentiator": "No differentiator is provided in fallback mode to avoid unsupported claims.",
                },
                {
                    "name": "Competitor identification unavailable",
                    "why_it_competes": "The system could not confidently identify competitors from public sources after retries.",
                    "differentiator": "No differentiator is provided in fallback mode to avoid unsupported claims.",
                },
            ],
            "sources": [],
        }


class NewsAgent:
    name = "NewsAgent"

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm
        self.region = os.getenv("SEARCH_REGION", "us-en")

    def run(self, company_name: str, fixture: dict[str, Any] | None = None) -> dict[str, Any]:
        if fixture and fixture.get("news"):
            return fixture["news"]

        news_results = search_web_queries(
            [
                f"{company_name} latest news developments 2025 2026 strategy products earnings",
                f"{company_name} Reuters earnings product launch partnership regulation 2025 2026",
                f"{company_name} investor relations press release earnings guidance product launch",
            ],
            max_results_per_query=4,
            region=self.region,
        )
        if self.llm.available:
            payload = {
                "company_name": company_name,
                "news_results": [r.__dict__ for r in news_results],
            }
            response = self.llm.chat_json(
                NEWS_AGENT_PROMPT,
                f"""Extract 2-3 recent, material news items.
Return JSON with keys:
- recent_news
- sources

`recent_news` must be a list of 2-3 objects with keys:
- headline
- summary
- source
- url

The `sources` field should be a list of source objects with keys: title, url, snippet.

Material:
{json.dumps(payload, indent=2)}
""",
            )
            return response

        if not news_results:
            raise RuntimeError("News agent found no usable current-news data.")

        items = [
            NewsItem(
                headline=item.title or "Recent development",
                summary=item.snippet or "No snippet returned from search.",
                source=item.url,
                url=item.url,
            ).__dict__
            for item in news_results[:3]
        ]
        return {"recent_news": items, "sources": [r.__dict__ for r in dedupe_sources(news_results[:6])]}

    def fallback(self, company_name: str, fixture: dict[str, Any] | None = None) -> dict[str, Any]:
        if fixture and fixture.get("news"):
            return fixture["news"]
        return {
            "recent_news": [
                {
                    "headline": "Recent news retrieval fallback triggered",
                    "summary": "The system could not confidently gather 2-3 recent material developments after retries, so this section is being returned as partial.",
                    "source": "system fallback",
                    "url": "",
                }
            ],
            "sources": [],
        }


class SynthesisAgent:
    name = "SynthesisAgent"

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def run(
        self,
        company_name: str,
        profile: dict[str, Any],
        financial: dict[str, Any],
        news: dict[str, Any],
        revision_feedback: list[str] | None = None,
    ) -> str:
        if self.llm.available:
            payload = {
                "company_name": company_name,
                "profile": profile,
                "financial": financial,
                "news": news,
                "revision_feedback": revision_feedback or [],
            }
            feedback_text = (
                "Revise the previous draft to address these validator issues:\n"
                + "\n".join(f"- {item}" for item in revision_feedback)
            ) if revision_feedback else "Create the first draft."
            return self.llm.chat_text(
                SYNTHESIS_AGENT_PROMPT,
                f"""{feedback_text}

Build the final brief from this JSON:
{json.dumps(payload, indent=2)}
""",
            )
        return self.fallback(company_name, profile, financial, news, revision_feedback)

    def fallback(
        self,
        company_name: str,
        profile: dict[str, Any],
        financial: dict[str, Any],
        news: dict[str, Any],
        revision_feedback: list[str] | None = None,
    ) -> str:
        logger.warning("SynthesisAgent fallback activated. Using deterministic formatter.")
        # Defensive normalization: fallback should never crash even if upstream
        # payload shape is degraded (e.g., financial passed as a raw list).
        financial_payload = financial if isinstance(financial, dict) else {}
        news_payload = news if isinstance(news, dict) else {}
        profile_payload = profile if isinstance(profile, dict) else {}
        competitors = financial_payload.get("competitors", [])
        if isinstance(financial, list):
            competitors = financial[:]
        if not isinstance(competitors, list):
            competitors = []
        recent_news = news_payload.get("recent_news", [])
        if isinstance(news, list):
            recent_news = news[:]
        if not isinstance(recent_news, list):
            recent_news = []

        competitor_lines = []
        for idx, competitor in enumerate(competitors[:3], start=1):
            if not isinstance(competitor, dict):
                continue
            competitor_lines.append(
                f"{idx}. {competitor.get('name', 'Competitor unavailable')}: "
                f"{competitor.get('why_it_competes', 'Competitive rationale unavailable.')} "
                f"Key differentiator: {competitor.get('differentiator', 'Differentiator unavailable.')}"
            )
        news_lines = []
        for idx, item in enumerate(recent_news[:3], start=1):
            if not isinstance(item, dict):
                continue
            link = f" ([source]({item['url']}))" if item.get("url") else ""
            news_lines.append(
                f"{idx}. {item.get('headline', 'Recent development')}: "
                f"{item.get('summary', 'Summary unavailable.')}{link}"
            )
        strategic_assessment = (
            f"{company_name} appears to have a visible position in its market with enough public-company information to support "
            "a basic competitive intelligence assessment. The strongest signals in this run come from the company profile, "
            "available financial data, and recent public developments, while the main residual risk is that some competitor "
            "or strategy claims may still require analyst review against primary sources. Looking forward, the company's "
            "trajectory will depend on how effectively it converts its current market position into sustained growth while managing execution and competitive pressure."
        )
        if revision_feedback:
            strategic_assessment += " This draft also incorporates a single validator-driven revision pass."

        return f"""# Competitive Intelligence Brief: {company_name}

## 1. Company Overview
{profile_payload.get("overview", "Overview unavailable.")}

## 2. Products & Services
{profile_payload.get("products_and_services", "Products and services detail unavailable.")}

## 3. Financial Snapshot
{financial_payload.get("financial_snapshot", "Financial data unavailable.")}

## 4. Top 3 Competitors
{chr(10).join(competitor_lines) if competitor_lines else "Competitor detail unavailable."}

## 5. Recent News
{chr(10).join(news_lines) if news_lines else "Recent news was unavailable in this run, and the system is leaving the section partial rather than fabricating it."}

## 6. Strategic Assessment
{strategic_assessment}
"""


class ValidatorAgent:
    name = "ValidatorAgent"

    REQUIRED_SECTIONS = [
        "## 1. Company Overview",
        "## 2. Products & Services",
        "## 3. Financial Snapshot",
        "## 4. Top 3 Competitors",
        "## 5. Recent News",
        "## 6. Strategic Assessment",
    ]

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def run(
        self,
        company_name: str,
        draft_brief: str,
        profile: dict[str, Any],
        financial: dict[str, Any],
        news: dict[str, Any],
    ) -> dict[str, Any]:
        deterministic_errors = self._deterministic_checks(draft_brief, financial, news)
        if self.llm.available:
            payload = {
                "company_name": company_name,
                "draft_brief": draft_brief,
                "profile": profile,
                "financial": financial,
                "news": news,
                "deterministic_errors": deterministic_errors,
            }
            response = self.llm.chat_json(
                VALIDATOR_AGENT_PROMPT,
                f"Validate this draft against the upstream findings.\n{json.dumps(payload, indent=2)}",
            )
            llm_errors = response.get("errors", [])
            all_errors = deterministic_errors + [err for err in llm_errors if err not in deterministic_errors]
            return {
                "validation_pass": not all_errors and bool(response.get("validation_pass", True)),
                "errors": all_errors,
                "confidence_summary": response.get("confidence_summary", ""),
            }

        return {
            "validation_pass": not deterministic_errors,
            "errors": deterministic_errors,
            "confidence_summary": "Deterministic validation only; no LLM judge was available.",
        }

    def _deterministic_checks(self, draft_brief: str, financial: dict[str, Any], news: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        section_bodies = self._extract_sections(draft_brief)
        for heading in self.REQUIRED_SECTIONS:
            if heading not in section_bodies:
                errors.append(f"Missing required section heading: {heading}")
        competitor_count = len(financial.get("competitors", [])[:3])
        if competitor_count != 3:
            errors.append("Financial analysis did not produce exactly 3 competitors.")
        competitor_names = [item.get("name", "").strip().lower() for item in financial.get("competitors", [])[:3]]
        if len([name for name in competitor_names if name]) != len(set(name for name in competitor_names if name)):
            errors.append("Competitor list contains duplicate names.")
        news_count = len(news.get("recent_news", []))
        if news_count < 2 or news_count > 3:
            errors.append("Recent news must contain 2-3 items.")
        if not any(item.get("url") for item in news.get("recent_news", [])):
            errors.append("Recent news items should include at least one source URL.")
        weak_domains = {source_domain(item.get("url", "")) for item in news.get("recent_news", [])}
        if weak_domains == {""}:
            errors.append("Recent news sources could not be resolved to real domains.")
        for section in self.REQUIRED_SECTIONS:
            body = section_bodies.get(section, "").strip()
            if not body:
                errors.append(f"Section body appears empty for {section}.")
        return errors

    def _extract_sections(self, draft_brief: str) -> dict[str, str]:
        normalized = draft_brief
        aliases = {
            r"^\*\*1\.\s+Company Overview\*\*$": "## 1. Company Overview",
            r"^\*\*2\.\s+Products\s*&\s*Services\*\*$": "## 2. Products & Services",
            r"^\*\*3\.\s+Financial Snapshot\*\*$": "## 3. Financial Snapshot",
            r"^\*\*4\.\s+Top 3 Competitors\*\*$": "## 4. Top 3 Competitors",
            r"^\*\*5\.\s+Recent News\*\*$": "## 5. Recent News",
            r"^\*\*6\.\s+Strategic Assessment\*\*$": "## 6. Strategic Assessment",
        }
        for pattern, replacement in aliases.items():
            normalized = re.sub(pattern, replacement, normalized, flags=re.M)

        sections: dict[str, str] = {}
        for idx, heading in enumerate(self.REQUIRED_SECTIONS):
            start = normalized.find(heading)
            if start == -1:
                continue
            body_start = start + len(heading)
            next_positions = [
                normalized.find(other_heading, body_start)
                for other_heading in self.REQUIRED_SECTIONS[idx + 1 :]
                if normalized.find(other_heading, body_start) != -1
            ]
            body_end = min(next_positions) if next_positions else len(normalized)
            body = normalized[body_start:body_end]
            body = body.strip()
            body = re.sub(r"^[-*]{3,}\s*$", "", body, flags=re.M).strip()
            sections[heading] = body
        return sections
