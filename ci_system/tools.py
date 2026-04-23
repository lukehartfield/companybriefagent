from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from ci_system.models import Source


def search_web(query: str, max_results: int = 5, region: str = "us-en") -> list[Source]:
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise RuntimeError("Search dependencies are not installed.") from exc

    results: list[Source] = []
    try:
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}&kl={region}"
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for block in soup.select(".result")[:max_results]:
            title_el = block.select_one(".result__title")
            link_el = block.select_one(".result__url")
            snippet_el = block.select_one(".result__snippet")
            title = title_el.get_text(" ", strip=True) if title_el else ""
            href = ""
            anchor = title_el.find("a") if title_el else None
            if anchor and anchor.get("href"):
                href = anchor["href"]
            elif link_el:
                href = link_el.get_text(" ", strip=True)
            snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
            if title or href or snippet:
                results.append(
                    Source(
                        title=title,
                        url=href,
                        snippet=snippet,
                    )
                )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Web search failed for query '{query}'.") from exc
    return results


def get_wikipedia_summary(company_name: str) -> str:
    try:
        import wikipediaapi
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise RuntimeError("wikipedia-api is not installed.") from exc

    wiki = wikipediaapi.Wikipedia(
        user_agent="msba-multi-agent-ci-assignment/1.0",
        language="en",
    )
    try:
        page = wiki.page(company_name)
        if not page.exists():
            return ""
        return page.summary[:1200].strip()
    except Exception:  # noqa: BLE001
        return ""


def lookup_ticker(company_name: str) -> str | None:
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise RuntimeError("yfinance is not installed.") from exc

    _configure_yfinance_cache(yf)
    try:
        search = yf.Search(query=company_name, max_results=5)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Ticker lookup failed for {company_name}.") from exc
    for quote in search.quotes:
        symbol = quote.get("symbol")
        short_name = (quote.get("shortname") or "").lower()
        if symbol and company_name.lower() in short_name:
            return symbol
    if search.quotes:
        return search.quotes[0].get("symbol")
    return None


def get_financial_data(company_name: str) -> dict[str, Any]:
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise RuntimeError("yfinance is not installed.") from exc

    _configure_yfinance_cache(yf)
    ticker = lookup_ticker(company_name)
    if not ticker:
        return {"ticker": None, "status": "unavailable"}

    try:
        stock = yf.Ticker(ticker)
        info = stock.info or {}
        fast = getattr(stock, "fast_info", {}) or {}
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Financial lookup failed for ticker {ticker}.") from exc

    revenue = info.get("totalRevenue")
    employees = info.get("fullTimeEmployees")
    market_cap = fast.get("market_cap") or info.get("marketCap")
    current_price = fast.get("last_price") or info.get("currentPrice")
    gross_margins = info.get("grossMargins")
    operating_margins = info.get("operatingMargins")
    revenue_growth = info.get("revenueGrowth")
    profit_margins = info.get("profitMargins")

    return {
        "ticker": ticker,
        "status": "ok",
        "longName": info.get("longName") or company_name,
        "city": info.get("city"),
        "state": info.get("state"),
        "country": info.get("country"),
        "industry": info.get("industry"),
        "sector": info.get("sector"),
        "website": info.get("website"),
        "employees": employees,
        "revenue": revenue,
        "revenue_growth": revenue_growth,
        "profit_margins": profit_margins,
        "gross_margins": gross_margins,
        "operating_margins": operating_margins,
        "market_cap": market_cap,
        "current_price": current_price,
        "longBusinessSummary": info.get("longBusinessSummary"),
        "companyOfficers": info.get("companyOfficers", []),
    }


def load_fixture(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    return json.loads(Path(path).read_text())


def _configure_yfinance_cache(yf: Any) -> None:
    cache_dir = Path(__file__).resolve().parent.parent / ".cache" / "yfinance"
    cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        yf.set_tz_cache_location(str(cache_dir))
    except Exception:
        pass


def money_text(value: Any) -> str:
    if value in (None, "", "N/A"):
        return "unavailable"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return str(value)

    abs_value = abs(value)
    if abs_value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    if abs_value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    return f"${value:,.0f}"


def pct_text(value: Any) -> str:
    if value in (None, "", "N/A"):
        return "unavailable"
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return str(value)
