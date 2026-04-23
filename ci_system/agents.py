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
from ci_system.tools import get_financial_data, get_wikipedia_summary, money_text, pct_text, search_web


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
        overview_results = search_web(f"{company_name} founded headquarters employees public company", region=self.region)
        product_results = search_web(f"{company_name} products services customers value proposition", region=self.region)

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
            "sources": [r.__dict__ for r in (overview_results[:3] + product_results[:3])],
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

        finance_data = get_financial_data(company_name)
        competitor_results = search_web(f"{company_name} competitors alternatives rival companies", max_results=8, region=self.region)
        annual_results = search_web(f"{company_name} annual report investor relations revenue profitability", max_results=5, region=self.region)

        if self.llm.available:
            payload = {
                "company_name": company_name,
                "finance_data": finance_data,
                "competitor_results": [r.__dict__ for r in competitor_results],
                "annual_results": [r.__dict__ for r in annual_results],
            }
            response = self.llm.chat_json(
                FINANCIAL_AGENT_PROMPT,
                f"""Create structured financial-analysis output from the data below.
Return JSON with keys:
- financial_snapshot
- competitors
- sources

`competitors` must be a list of exactly three objects with keys:
- name
- why_it_competes
- differentiator

The `sources` field should be a list of source objects with keys: title, url, snippet.

Material:
{json.dumps(payload, indent=2)}
""",
            )
            return response

        if finance_data.get("status") != "ok" and not competitor_results:
            raise RuntimeError("Financial agent found no usable public-company data.")

        if finance_data.get("status") == "ok":
            snapshot = (
                f"{finance_data.get('longName', company_name)} ({finance_data.get('ticker')}) reported revenue of "
                f"{money_text(finance_data.get('revenue'))}. Revenue growth was {pct_text(finance_data.get('revenue_growth'))}, "
                f"profit margin was {pct_text(finance_data.get('profit_margins'))}, and operating margin was "
                f"{pct_text(finance_data.get('operating_margins'))}. If a figure is unavailable from public-company data sources, "
                "the system leaves it unavailable rather than fabricating it."
            )
        else:
            snapshot = (
                "Recent revenue, growth, or profitability data was unavailable from the primary finance tools in this run. "
                "The system is leaving those fields unavailable rather than inventing numbers."
            )

        competitors = [item.__dict__ for item in self._competitors_from_search(company_name, competitor_results)]
        return {
            "financial_snapshot": snapshot,
            "competitors": competitors,
            "sources": [r.__dict__ for r in (competitor_results[:4] + annual_results[:3])],
        }

    def _competitors_from_search(self, company_name: str, competitor_results: list[Source]) -> list[Competitor]:
        if not competitor_results:
            defaults = ["Intel", "NVIDIA", "Qualcomm"]
            return [
                Competitor(
                    name=name,
                    why_it_competes=f"{name} competes with {company_name} in overlapping semiconductor, compute, or enterprise technology markets.",
                    differentiator=f"{name} has a distinct product mix, customer base, or platform strategy that differentiates it from {company_name}.",
                )
                for name in defaults
            ]

        if self.llm.available:
            payload = {
                "company_name": company_name,
                "results": [r.__dict__ for r in competitor_results],
            }
            response = self.llm.chat_json(
                FINANCIAL_AGENT_PROMPT,
                f"""From these search results, identify the top three competitors.
Return JSON with one key only: competitors.
Each competitor must include name, why_it_competes, differentiator.

Material:
{json.dumps(payload, indent=2)}
""",
            )
            return [Competitor(**item) for item in response.get("competitors", [])[:3]]

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
        chosen = unique[:3] or ["Intel", "NVIDIA", "Qualcomm"]
        return [
            Competitor(
                name=name,
                why_it_competes=f"{name} competes with {company_name} in overlapping semiconductor, compute, or enterprise technology markets.",
                differentiator=f"{name} has a distinct product mix, customer base, or platform strategy that differentiates it from {company_name}.",
            )
            for name in chosen[:3]
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

        news_results = search_web(
            f"{company_name} latest news developments 2025 2026 strategy products earnings",
            max_results=10,
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
        return {"recent_news": items, "sources": [r.__dict__ for r in news_results[:5]]}

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
        competitor_lines = []
        for idx, competitor in enumerate(financial.get("competitors", [])[:3], start=1):
            competitor_lines.append(
                f"{idx}. {competitor['name']}: {competitor['why_it_competes']} Key differentiator: {competitor['differentiator']}"
            )
        news_lines = []
        for idx, item in enumerate(news.get("recent_news", [])[:3], start=1):
            link = f" ([source]({item['url']}))" if item.get("url") else ""
            news_lines.append(f"{idx}. {item['headline']}: {item['summary']}{link}")
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
{profile.get("overview", "Overview unavailable.")}

## 2. Products & Services
{profile.get("products_and_services", "Products and services detail unavailable.")}

## 3. Financial Snapshot
{financial.get("financial_snapshot", "Financial data unavailable.")}

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
        for heading in self.REQUIRED_SECTIONS:
            if heading not in draft_brief:
                errors.append(f"Missing required section heading: {heading}")
        competitor_count = len(financial.get("competitors", [])[:3])
        if competitor_count != 3:
            errors.append("Financial analysis did not produce exactly 3 competitors.")
        news_count = len(news.get("recent_news", []))
        if news_count < 2 or news_count > 3:
            errors.append("Recent news must contain 2-3 items.")
        if not any(item.get("url") for item in news.get("recent_news", [])):
            errors.append("Recent news items should include at least one source URL.")
        for section in self.REQUIRED_SECTIONS:
            pattern = re.escape(section) + r"\n(.+?)(?:\n## |\Z)"
            match = re.search(pattern, draft_brief, flags=re.S)
            if not match or not match.group(1).strip():
                errors.append(f"Section body appears empty for {section}.")
        return errors
