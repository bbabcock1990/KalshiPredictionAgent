"""Historical speech and statement analysis tools for behavioral markets.

Provides keyword frequency analysis and speech transcript access for
political/behavioral markets (e.g., "Will Trump mention X in his speech?").

Data sources:
- Miller Center presidential speech archive (millercenter.org)
- White House briefings and statements
- Cached local index for fast keyword lookups
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta
from html import unescape
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Cache directory for downloaded transcripts
_CACHE_DIR = Path(os.getenv("KALSHI_AGENTS_DATA", "./data")) / "speech_cache"


def _ensure_cache_dir() -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR


def _read_cached_documents(cache_file: Path) -> list[dict[str, Any]] | None:
    if not cache_file.exists():
        return None

    age = datetime.now().timestamp() - cache_file.stat().st_mtime
    if age >= 86400:
        return None

    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    return data if isinstance(data, list) else None


def _write_cached_documents(cache_file: Path, documents: list[dict[str, Any]]) -> None:
    try:
        cache_file.write_text(
            json.dumps(documents, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        logger.debug("Failed to write speech cache file %s", cache_file)


# ---------------------------------------------------------------------------
# Miller Center presidential speech archive
# ---------------------------------------------------------------------------

def _fetch_miller_center_speeches(
    president: str = "donald-trump",
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Fetch speech metadata from Miller Center's public API.

    Returns list of dicts with keys: title, date, transcript.
    """
    cache_file = _ensure_cache_dir() / f"miller_{president}.json"
    cached = _read_cached_documents(cache_file)
    if cached is not None:
        return cached

    speeches: list[dict[str, Any]] = []
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                "https://millercenter.org/the-presidency/presidential-speeches",
                params={"president": president, "format": "json"},
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            payload = resp.json()
            items: list[dict[str, Any]]
            if isinstance(payload, dict):
                speeches_data = payload.get("speeches", [])
                items = speeches_data if isinstance(speeches_data, list) else []
            elif isinstance(payload, list):
                items = payload
            else:
                items = []

            for item in items[:limit]:
                if not isinstance(item, dict):
                    continue
                speeches.append(
                    {
                        "title": item.get("title", "Untitled"),
                        "date": item.get("date", "unknown"),
                        "transcript": item.get("transcript", ""),
                    }
                )
    except Exception as exc:  # pragma: no cover - network/library failures
        logger.warning("Miller Center fetch failed for %s: %s", president, exc)

    if speeches:
        _write_cached_documents(cache_file, speeches)

    return speeches


# ---------------------------------------------------------------------------
# White House statements / briefings
# ---------------------------------------------------------------------------

def _fetch_whitehouse_statements(
    query: str = "",
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Fetch recent White House statements and briefings.

    Uses whitehouse.gov public pages. Falls back gracefully.
    """
    statements: list[dict[str, Any]] = []
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            resp = client.get(
                "https://www.whitehouse.gov/wp-json/wp/v2/posts",
                params={
                    "search": query,
                    "per_page": limit,
                    "categories": "6",
                },
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            payload = resp.json()
            if not isinstance(payload, list):
                return statements

            for post in payload:
                if not isinstance(post, dict):
                    continue
                content = post.get("content", {})
                rendered = content.get("rendered", "") if isinstance(content, dict) else ""
                title = post.get("title", {})
                rendered_title = title.get("rendered", "Untitled") if isinstance(title, dict) else "Untitled"
                stripped = re.sub(r"<[^>]+>", "", rendered)
                statements.append(
                    {
                        "title": rendered_title,
                        "date": post.get("date", "unknown"),
                        "content": unescape(stripped)[:5000],
                    }
                )
    except Exception as exc:  # pragma: no cover - network/library failures
        logger.warning("White House statements fetch failed: %s", exc)

    return statements


# ---------------------------------------------------------------------------
# Keyword frequency analysis
# ---------------------------------------------------------------------------

def get_speech_frequency(
    person: str,
    keyword: str,
    lookback_days: int = 180,
) -> str:
    """Analyze how frequently a keyword appears in a public figure's speeches.

    Args:
        person: Name of the person (e.g., "Trump", "Biden")
        keyword: The keyword or phrase to search for
        lookback_days: How far back to search (default 180 days)

    Returns:
        Formatted analysis of keyword frequency with specific citations.
    """
    person_lower = person.lower().strip()
    keyword_lower = keyword.lower().strip()

    if not person_lower or not keyword_lower:
        return "Both person and keyword are required for speech frequency analysis."

    president_slugs = {
        "trump": "donald-trump",
        "donald trump": "donald-trump",
        "biden": "joe-biden",
        "joe biden": "joe-biden",
        "obama": "barack-obama",
        "barack obama": "barack-obama",
    }
    slug = president_slugs.get(person_lower, person_lower.replace(" ", "-"))

    speeches = _fetch_miller_center_speeches(slug)
    wh_statements = _fetch_whitehouse_statements(keyword)

    all_documents: list[dict[str, str]] = []
    cutoff = datetime.now() - timedelta(days=lookback_days)

    for speech in speeches:
        try:
            date = datetime.strptime(str(speech["date"])[:10], "%Y-%m-%d")
            if date >= cutoff:
                all_documents.append(
                    {
                        "source": "Miller Center",
                        "title": str(speech.get("title", "Untitled")),
                        "date": str(speech.get("date", "unknown")),
                        "text": str(speech.get("transcript", "")),
                    }
                )
        except (KeyError, ValueError, TypeError):
            all_documents.append(
                {
                    "source": "Miller Center",
                    "title": str(speech.get("title", "Untitled")),
                    "date": str(speech.get("date", "unknown")),
                    "text": str(speech.get("transcript", "")),
                }
            )

    for statement in wh_statements:
        try:
            date = datetime.strptime(str(statement["date"])[:10], "%Y-%m-%d")
            if date >= cutoff:
                all_documents.append(
                    {
                        "source": "White House",
                        "title": str(statement.get("title", "Untitled")),
                        "date": str(statement.get("date", "unknown")),
                        "text": str(statement.get("content", "")),
                    }
                )
        except (KeyError, ValueError, TypeError):
            all_documents.append(
                {
                    "source": "White House",
                    "title": str(statement.get("title", "Untitled")),
                    "date": str(statement.get("date", "unknown")),
                    "text": str(statement.get("content", "")),
                }
            )

    if not all_documents:
        return (
            f"No speech/statement data found for '{person}' in the last {lookback_days} days.\n"
            f"Cannot compute keyword frequency for '{keyword}'.\n"
            "Note: Data sources (Miller Center, White House) may have limited coverage."
        )

    total_mentions = 0
    docs_with_mention = 0
    mention_details: list[dict[str, Any]] = []

    for doc in all_documents:
        text = doc["text"].lower()
        count = text.count(keyword_lower)
        if count > 0:
            total_mentions += count
            docs_with_mention += 1
            mention_details.append(
                {
                    "source": doc["source"],
                    "title": doc["title"],
                    "date": doc["date"],
                    "count": count,
                }
            )

    lines = [
        f"## Keyword Frequency Analysis: '{keyword}' in {person}'s speeches/statements",
        f"Lookback period: {lookback_days} days",
        f"Total documents analyzed: {len(all_documents)}",
        (
            f"Documents mentioning '{keyword}': {docs_with_mention} "
            f"({docs_with_mention / len(all_documents) * 100:.1f}%)"
        ),
        f"Total mentions: {total_mentions}",
        "",
    ]

    if mention_details:
        mention_details.sort(key=lambda item: item["date"], reverse=True)
        lines.append("### Mentions by document:")
        for mention in mention_details[:20]:
            lines.append(
                f"- [{mention['date']}] {mention['source']}: \"{mention['title']}\" "
                f"— {mention['count']} mention(s)"
            )

    frequency_per_doc = total_mentions / len(all_documents)
    lines.append("\n### Summary")
    lines.append(f"Average mentions per document: {frequency_per_doc:.2f}")

    if docs_with_mention > len(all_documents) * 0.5:
        lines.append(
            f"Assessment: '{keyword}' is a FREQUENT topic for {person} (>50% of documents)"
        )
    elif docs_with_mention > len(all_documents) * 0.2:
        lines.append(
            f"Assessment: '{keyword}' is a RECURRING topic for {person} (20-50% of documents)"
        )
    elif docs_with_mention > 0:
        lines.append(
            f"Assessment: '{keyword}' is an OCCASIONAL topic for {person} (<20% of documents)"
        )
    else:
        lines.append(
            f"Assessment: '{keyword}' does NOT appear in recent {person} speeches/statements"
        )

    return "\n".join(lines)
