"""Social media data tools for political and behavioral market analysis."""

from __future__ import annotations

import html
import logging
import os
import re
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_REDDIT_SUBREDDITS = ["politics", "conservative", "news", "worldnews"]
_TRUTH_SOCIAL_BASE_URL = "https://truthsocial.com"
_TWITTER_API_BASE_URL = "https://api.twitter.com/2"
_REDDIT_BASE_URL = "https://www.reddit.com"
_DEFAULT_TIMEOUT = 10.0


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", value or "")
    return html.unescape(text).strip()


def _clamp_limit(limit: int, minimum: int = 1, maximum: int = 100) -> int:
    return max(minimum, min(limit, maximum))


def fetch_truth_social_posts(username: str = "realDonaldTrump", limit: int = 20) -> str:
    """Fetch recent Truth Social posts for a public account."""
    try:
        with httpx.Client(timeout=_DEFAULT_TIMEOUT) as client:
            lookup = client.get(
                f"{_TRUTH_SOCIAL_BASE_URL}/api/v1/accounts/lookup",
                params={"acct": username},
                headers={"Accept": "application/json"},
            )
            if lookup.status_code == 200:
                account_id = lookup.json().get("id")
                if account_id:
                    statuses = client.get(
                        f"{_TRUTH_SOCIAL_BASE_URL}/api/v1/accounts/{account_id}/statuses",
                        params={
                            "limit": _clamp_limit(limit),
                            "exclude_replies": "true",
                        },
                        headers={"Accept": "application/json"},
                    )
                    if statuses.status_code == 200:
                        return _format_truth_posts(statuses.json(), username)
    except Exception as exc:  # pragma: no cover - defensive network handling
        logger.warning("Truth Social fetch failed for %s: %s", username, exc)

    return (
        f"<unavailable: Truth Social data for @{username} could not be fetched. "
        "The API may be restricted or rate-limited.>"
    )


def _format_truth_posts(posts: list[dict], username: str) -> str:
    """Format Truth Social posts into a readable block."""
    if not posts:
        return f"<no recent posts found for @{username}>"

    lines = [f"Recent Truth Social posts by @{username} ({len(posts)} posts):", "=" * 60]
    for post in posts:
        created = post.get("created_at", "unknown date")
        content = _strip_html(post.get("content", ""))
        reblogs = post.get("reblogs_count", 0)
        favourites = post.get("favourites_count", 0)

        lines.append(f"[{created}]")
        lines.append(content)
        lines.append(f"  ❤️ {favourites}  🔁 {reblogs}")
        lines.append("-" * 40)

    return "\n".join(lines)


def fetch_twitter_posts(username: str, limit: int = 20) -> str:
    """Fetch recent X posts for a public account using API v2."""
    bearer_token = os.getenv("TWITTER_BEARER_TOKEN")
    if not bearer_token:
        return (
            "<unavailable: X/Twitter data requires TWITTER_BEARER_TOKEN "
            "environment variable. Set it to enable social media analysis.>"
        )

    try:
        with httpx.Client(timeout=_DEFAULT_TIMEOUT) as client:
            headers = {"Authorization": f"Bearer {bearer_token}"}
            user_resp = client.get(
                f"{_TWITTER_API_BASE_URL}/users/by/username/{username}",
                headers=headers,
            )
            if user_resp.status_code != 200:
                return (
                    f"<unavailable: Could not look up X/Twitter user @{username} "
                    f"(status {user_resp.status_code})>"
                )

            user_id = user_resp.json().get("data", {}).get("id")
            if not user_id:
                return f"<unavailable: X/Twitter user @{username} not found>"

            tweets_resp = client.get(
                f"{_TWITTER_API_BASE_URL}/users/{user_id}/tweets",
                params={
                    "max_results": _clamp_limit(limit, minimum=5),
                    "tweet.fields": "created_at,public_metrics",
                    "exclude": "retweets,replies",
                },
                headers=headers,
            )
            if tweets_resp.status_code == 200:
                tweets = tweets_resp.json().get("data", [])
                return _format_tweets(tweets, username)
            return f"<unavailable: X/Twitter API returned status {tweets_resp.status_code}>"
    except Exception as exc:  # pragma: no cover - defensive network handling
        logger.warning("X/Twitter fetch failed for %s: %s", username, exc)

    return f"<unavailable: X/Twitter data for @{username} could not be fetched>"


def _format_tweets(tweets: list[dict], username: str) -> str:
    """Format X posts into a readable block."""
    if not tweets:
        return f"<no recent tweets found for @{username}>"

    lines = [f"Recent X/Twitter posts by @{username} ({len(tweets)} tweets):", "=" * 60]
    for tweet in tweets:
        created = tweet.get("created_at", "unknown date")
        metrics = tweet.get("public_metrics", {})
        lines.append(f"[{created}]")
        lines.append(tweet.get("text", ""))
        lines.append(
            f"  ❤️ {metrics.get('like_count', 0)}  🔁 {metrics.get('retweet_count', 0)}  💬 {metrics.get('reply_count', 0)}"
        )
        lines.append("-" * 40)

    return "\n".join(lines)


def fetch_political_reddit_posts(
    query: str,
    subreddits: list[str] | None = None,
    limit: int = 15,
) -> str:
    """Fetch recent Reddit posts from political subreddits matching a query."""
    subreddits = subreddits or list(_DEFAULT_REDDIT_SUBREDDITS)
    all_posts: list[dict] = []

    for subreddit in subreddits:
        try:
            with httpx.Client(timeout=_DEFAULT_TIMEOUT) as client:
                resp = client.get(
                    f"{_REDDIT_BASE_URL}/r/{subreddit}/search.json",
                    params={
                        "q": query,
                        "sort": "new",
                        "t": "week",
                        "limit": _clamp_limit(limit),
                        "restrict_sr": "on",
                    },
                    headers={"User-Agent": "KalshiPredictionAgent/0.1"},
                )
                if resp.status_code == 200:
                    for item in resp.json().get("data", {}).get("children", []):
                        post = item.get("data", {})
                        all_posts.append(
                            {
                                "subreddit": subreddit,
                                "title": post.get("title", ""),
                                "score": post.get("score", 0),
                                "num_comments": post.get("num_comments", 0),
                                "created_utc": post.get("created_utc", 0),
                                "selftext": (post.get("selftext", "") or "")[:200],
                            }
                        )
        except Exception as exc:  # pragma: no cover - defensive network handling
            logger.warning("Reddit fetch failed for r/%s: %s", subreddit, exc)

    if not all_posts:
        return f"<no Reddit posts found matching '{query}' in political subreddits>"

    all_posts.sort(key=lambda item: item["score"], reverse=True)
    lines = [
        f"Reddit political discussion matching '{query}' ({min(len(all_posts), limit)} posts):",
        "=" * 60,
    ]
    for post in all_posts[:limit]:
        created = datetime.fromtimestamp(post["created_utc"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        lines.append(
            f"r/{post['subreddit']} [{created}] ⬆️ {post['score']} 💬 {post['num_comments']}"
        )
        lines.append(f"  {post['title']}")
        if post["selftext"]:
            lines.append(f"  {post['selftext']}...")
        lines.append("-" * 40)

    return "\n".join(lines)


def fetch_social_media_signals(topic: str, figures: list[dict] | None = None) -> str:
    """Fetch social media signals relevant to a market topic."""
    if figures is None:
        lower = topic.lower()
        if "trump" in lower:
            figures = [{"name": "Donald Trump", "truth_social": "realDonaldTrump"}]
        elif "biden" in lower:
            figures = [{"name": "Joe Biden", "twitter": "POTUS"}]
        else:
            figures = []

    blocks: list[str] = []
    for figure in figures:
        name = figure.get("name", "Unknown")
        truth_handle = figure.get("truth_social")
        twitter_handle = figure.get("twitter")

        if truth_handle:
            blocks.append(f"### {name} — Truth Social")
            blocks.append(fetch_truth_social_posts(truth_handle))
            blocks.append("")

        if twitter_handle:
            blocks.append(f"### {name} — X/Twitter")
            blocks.append(fetch_twitter_posts(twitter_handle))
            blocks.append("")

    blocks.append("### Reddit Political Discussion")
    blocks.append(fetch_political_reddit_posts(topic))

    return "\n".join(blocks) if blocks else "<no social media data collected>"


__all__ = [
    "fetch_truth_social_posts",
    "fetch_twitter_posts",
    "fetch_political_reddit_posts",
    "fetch_social_media_signals",
    "_format_truth_posts",
    "_format_tweets",
]
