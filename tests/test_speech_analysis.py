from __future__ import annotations

import shutil
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import respx

from kalshi_agents.agents import speech_analysis


def _set_cache_dir(cache_name: str) -> Path:
    cache_dir = Path(__file__).resolve().parent / cache_name
    shutil.rmtree(cache_dir, ignore_errors=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    speech_analysis._CACHE_DIR = cache_dir
    return cache_dir


def test_get_speech_frequency_counts_mentions_across_sources():
    cache_dir = _set_cache_dir("_speech_cache_counts")
    recent = datetime.now().strftime("%Y-%m-%d")

    with respx.mock(assert_all_called=True) as router:
        router.get("https://millercenter.org/the-presidency/presidential-speeches").mock(
            return_value=httpx.Response(
                200,
                json={
                    "speeches": [
                        {
                            "title": "Campaign Speech",
                            "date": recent,
                            "transcript": "China was mentioned. China remained central.",
                        },
                        {
                            "title": "Economic Remarks",
                            "date": recent,
                            "transcript": "Jobs and growth only.",
                        },
                    ]
                },
            )
        )
        router.get("https://www.whitehouse.gov/wp-json/wp/v2/posts").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "title": {"rendered": "Statement on Trade"},
                        "date": recent,
                        "content": {"rendered": "<p>China remains important.</p>"},
                    }
                ],
            )
        )

        report = speech_analysis.get_speech_frequency("Trump", "China", lookback_days=30)

    assert "Total documents analyzed: 3" in report
    assert "Documents mentioning 'China': 2 (66.7%)" in report
    assert "Total mentions: 3" in report
    assert '"Campaign Speech" — 2 mention(s)' in report
    assert '"Statement on Trade" — 1 mention(s)' in report
    assert "Assessment: 'China' is a FREQUENT topic for Trump" in report

    shutil.rmtree(cache_dir, ignore_errors=True)


def test_get_speech_frequency_excludes_old_documents():
    cache_dir = _set_cache_dir("_speech_cache_lookback")
    recent = datetime.now().strftime("%Y-%m-%d")
    old = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

    with respx.mock(assert_all_called=True) as router:
        router.get("https://millercenter.org/the-presidency/presidential-speeches").mock(
            return_value=httpx.Response(
                200,
                json={
                    "speeches": [
                        {
                            "title": "Recent Remarks",
                            "date": recent,
                            "transcript": "Tariffs and trade policy.",
                        },
                        {
                            "title": "Old Remarks",
                            "date": old,
                            "transcript": "Tariffs appeared here too.",
                        },
                    ]
                },
            )
        )
        router.get("https://www.whitehouse.gov/wp-json/wp/v2/posts").mock(
            return_value=httpx.Response(200, json=[])
        )

        report = speech_analysis.get_speech_frequency("Trump", "tariffs", lookback_days=30)

    assert "Total documents analyzed: 1" in report
    assert '"Recent Remarks" — 1 mention(s)' in report
    assert '"Old Remarks"' not in report

    shutil.rmtree(cache_dir, ignore_errors=True)


def test_get_speech_frequency_gracefully_handles_unavailable_sources():
    cache_dir = _set_cache_dir("_speech_cache_failures")

    with respx.mock(assert_all_called=True) as router:
        router.get("https://millercenter.org/the-presidency/presidential-speeches").mock(
            return_value=httpx.Response(503)
        )
        router.get("https://www.whitehouse.gov/wp-json/wp/v2/posts").mock(
            side_effect=httpx.ConnectError("boom")
        )

        report = speech_analysis.get_speech_frequency("Trump", "China", lookback_days=30)

    assert "No speech/statement data found for 'Trump'" in report
    assert "Cannot compute keyword frequency for 'China'." in report

    shutil.rmtree(cache_dir, ignore_errors=True)
