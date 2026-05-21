import httpx
import respx

from kalshi_agents.agents import social_media
from kalshi_agents.agents.social_media import (
    _format_truth_posts,
    _format_tweets,
    fetch_political_reddit_posts,
    fetch_social_media_signals,
    fetch_truth_social_posts,
    fetch_twitter_posts,
)


def test_format_truth_posts_strips_html_and_entities():
    rendered = _format_truth_posts(
        [
            {
                "created_at": "2025-01-01T12:00:00Z",
                "content": "<p>Hello &amp; welcome</p>",
                "reblogs_count": 4,
                "favourites_count": 9,
            }
        ],
        "realDonaldTrump",
    )

    assert "Hello & welcome" in rendered
    assert "<p>" not in rendered
    assert "❤️ 9" in rendered
    assert "🔁 4" in rendered


def test_format_tweets_includes_public_metrics():
    rendered = _format_tweets(
        [
            {
                "created_at": "2025-01-02T08:30:00Z",
                "text": "Testing social metrics",
                "public_metrics": {
                    "like_count": 7,
                    "retweet_count": 3,
                    "reply_count": 2,
                },
            }
        ],
        "POTUS",
    )

    assert "Testing social metrics" in rendered
    assert "❤️ 7" in rendered
    assert "🔁 3" in rendered
    assert "💬 2" in rendered


@respx.mock
def test_fetch_truth_social_posts_success():
    lookup_route = respx.get("https://truthsocial.com/api/v1/accounts/lookup").mock(
        return_value=httpx.Response(200, json={"id": "123"})
    )
    statuses_route = respx.get("https://truthsocial.com/api/v1/accounts/123/statuses").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "created_at": "2025-01-03T10:00:00Z",
                    "content": "<p>Statement posted</p>",
                    "reblogs_count": 1,
                    "favourites_count": 5,
                }
            ],
        )
    )

    rendered = fetch_truth_social_posts("realDonaldTrump", limit=3)

    assert lookup_route.called
    assert statuses_route.called
    assert statuses_route.calls.last.request.url.params["limit"] == "3"
    assert "Statement posted" in rendered


@respx.mock
def test_fetch_political_reddit_posts_collects_and_sorts_by_score():
    respx.get("https://www.reddit.com/r/politics/search.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "children": [
                        {
                            "data": {
                                "title": "Lower score post",
                                "score": 10,
                                "num_comments": 5,
                                "created_utc": 1735900000,
                                "selftext": "politics body",
                            }
                        }
                    ]
                }
            },
        )
    )
    respx.get("https://www.reddit.com/r/news/search.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "children": [
                        {
                            "data": {
                                "title": "Higher score post",
                                "score": 25,
                                "num_comments": 8,
                                "created_utc": 1735901000,
                                "selftext": "news body",
                            }
                        }
                    ]
                }
            },
        )
    )

    rendered = fetch_political_reddit_posts("trump", subreddits=["politics", "news"], limit=2)

    assert rendered.index("Higher score post") < rendered.index("Lower score post")
    assert "r/news" in rendered
    assert "r/politics" in rendered


def test_fetch_twitter_posts_requires_bearer_token(monkeypatch):
    monkeypatch.delenv("TWITTER_BEARER_TOKEN", raising=False)

    rendered = fetch_twitter_posts("POTUS")

    assert "TWITTER_BEARER_TOKEN" in rendered


@respx.mock
def test_fetch_twitter_posts_success(monkeypatch):
    monkeypatch.setenv("TWITTER_BEARER_TOKEN", "test-token")
    user_route = respx.get("https://api.twitter.com/2/users/by/username/POTUS").mock(
        return_value=httpx.Response(200, json={"data": {"id": "42"}})
    )
    tweets_route = respx.get("https://api.twitter.com/2/users/42/tweets").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "created_at": "2025-01-04T09:15:00Z",
                        "text": "Policy update",
                        "public_metrics": {
                            "like_count": 100,
                            "retweet_count": 20,
                            "reply_count": 15,
                        },
                    }
                ]
            },
        )
    )

    rendered = fetch_twitter_posts("POTUS", limit=20)

    assert user_route.called
    assert tweets_route.called
    assert user_route.calls.last.request.headers["Authorization"] == "Bearer test-token"
    assert "Policy update" in rendered


def test_fetch_social_media_signals_auto_detects_trump(monkeypatch):
    monkeypatch.setattr(
        social_media,
        "fetch_truth_social_posts",
        lambda username, limit=20: f"truth:{username}:{limit}",
    )
    monkeypatch.setattr(
        social_media,
        "fetch_political_reddit_posts",
        lambda query, subreddits=None, limit=15: f"reddit:{query}:{limit}",
    )

    rendered = fetch_social_media_signals("Will Trump mention Powell this week?")

    assert "### Donald Trump — Truth Social" in rendered
    assert "truth:realDonaldTrump:20" in rendered
    assert "### Reddit Political Discussion" in rendered
    assert "reddit:Will Trump mention Powell this week?:15" in rendered
