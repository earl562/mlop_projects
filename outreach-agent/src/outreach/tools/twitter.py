from __future__ import annotations

import structlog
import tweepy

from outreach.config import settings

logger = structlog.get_logger(__name__)


def _get_client() -> tweepy.Client | None:
    """Build a Tweepy v2 client. Requires Basic tier for DMs to non-followers."""
    if not settings.twitter_bearer_token:
        logger.warning("twitter_not_configured")
        return None
    return tweepy.Client(
        bearer_token=settings.twitter_bearer_token,
        consumer_key=settings.twitter_api_key,
        consumer_secret=settings.twitter_api_secret,
        access_token=settings.twitter_access_token,
        access_token_secret=settings.twitter_access_secret,
    )


async def send_dm(username: str, message: str) -> dict:
    """
    Send a Twitter/X DM to a user by handle.
    Requires Basic API tier ($100/month) to DM non-followers.
    Returns {dm_conversation_id, status} or {error}.
    """
    client = _get_client()
    if not client:
        return {"error": "twitter_not_configured", "status": "skipped"}

    try:
        # Resolve username → user ID
        user = client.get_user(username=username.lstrip("@"))
        if not user.data:
            return {"error": f"user_not_found: {username}", "status": "failed"}

        recipient_id = user.data.id
        dm = client.create_direct_message(participant_id=recipient_id, text=message)
        dm_id = dm.data.get("dm_conversation_id") if dm.data else None
        logger.info("twitter_dm_sent", username=username, dm_id=dm_id)
        return {"dm_conversation_id": dm_id, "status": "sent"}
    except tweepy.errors.Forbidden as exc:
        logger.error("twitter_dm_forbidden", username=username, error=str(exc))
        return {"error": "forbidden — Basic API tier required for DMs", "status": "failed"}
    except Exception as exc:
        logger.error("twitter_dm_error", username=username, error=str(exc))
        return {"error": str(exc), "status": "failed"}


async def lookup_user(username: str) -> dict | None:
    """Fetch public profile data for a Twitter handle."""
    client = _get_client()
    if not client:
        return None
    try:
        user = client.get_user(
            username=username.lstrip("@"),
            user_fields=["name", "description", "public_metrics", "location"],
        )
        if not user.data:
            return None
        u = user.data
        return {
            "id": u.id,
            "name": u.name,
            "username": u.username,
            "description": u.description,
            "location": getattr(u, "location", None),
            "followers": u.public_metrics.get("followers_count") if u.public_metrics else None,
        }
    except Exception as exc:
        logger.error("twitter_lookup_error", username=username, error=str(exc))
        return None
