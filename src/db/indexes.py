"""
MongoDB index definitions for all collections.

This module defines indexes that should be created for optimal query performance.
Indexes are applied during application startup or via migrations.
"""

from dataclasses import dataclass
from typing import Any

from pymongo import ASCENDING, DESCENDING, IndexModel


@dataclass(frozen=True)
class IndexDefinition:
    """Index definition for a collection."""

    collection: str
    indexes: tuple[IndexModel, ...]


# =============================================================================
# Users Collection Indexes
# =============================================================================

USERS_INDEXES = IndexDefinition(
    collection="users",
    indexes=(
        # Unique index on username for fast lookups and uniqueness constraint
        IndexModel(
            [("username", ASCENDING)],
            unique=True,
            name="idx_users_username_unique",
        ),
        # Unique index on email
        IndexModel(
            [("email", ASCENDING)],
            unique=True,
            name="idx_users_email_unique",
        ),
        # Index for querying active users sorted by creation date
        IndexModel(
            [("is_active", ASCENDING), ("created_at", DESCENDING)],
            name="idx_users_active_created",
        ),
        # Text index for searching users
        IndexModel(
            [("username", "text"), ("email", "text")],
            name="idx_users_text_search",
        ),
    ),
)

# =============================================================================
# Matches Collection Indexes
# =============================================================================

MATCHES_INDEXES = IndexDefinition(
    collection="matches",
    indexes=(
        # Index for querying matches by status and date
        IndexModel(
            [("status", ASCENDING), ("scheduled_at", ASCENDING)],
            name="idx_matches_status_scheduled",
        ),
        # Index for finding upcoming matches
        IndexModel(
            [("scheduled_at", ASCENDING)],
            name="idx_matches_scheduled",
        ),
        # Compound index for team lookups
        IndexModel(
            [("home_team", ASCENDING), ("away_team", ASCENDING)],
            name="idx_matches_teams",
        ),
        # Index for querying finished matches with results
        IndexModel(
            [("status", ASCENDING), ("finished_at", DESCENDING)],
            name="idx_matches_finished",
            partialFilterExpression={"status": "finished"},
        ),
        # Text index for searching matches by team names
        IndexModel(
            [("home_team", "text"), ("away_team", "text")],
            name="idx_matches_text_search",
        ),
        # TTL index for auto-cleanup of old cancelled matches (optional)
        # Removes cancelled matches after 30 days
        IndexModel(
            [("cancelled_at", ASCENDING)],
            name="idx_matches_cancelled_ttl",
            expireAfterSeconds=30 * 24 * 60 * 60,  # 30 days
            partialFilterExpression={"status": "cancelled"},
        ),
    ),
)

# =============================================================================
# Predictions Collection Indexes
# =============================================================================

PREDICTIONS_INDEXES = IndexDefinition(
    collection="predictions",
    indexes=(
        # Unique compound index: one prediction per user per match
        IndexModel(
            [("user_id", ASCENDING), ("match_id", ASCENDING)],
            unique=True,
            name="idx_predictions_user_match_unique",
        ),
        # Index for getting all predictions for a match
        IndexModel(
            [("match_id", ASCENDING), ("created_at", DESCENDING)],
            name="idx_predictions_match_created",
        ),
        # Index for user's prediction history
        IndexModel(
            [("user_id", ASCENDING), ("created_at", DESCENDING)],
            name="idx_predictions_user_history",
        ),
        # Index for analytics: finding predictions with points
        IndexModel(
            [("user_id", ASCENDING), ("points", DESCENDING)],
            name="idx_predictions_user_points",
            partialFilterExpression={"points": {"$exists": True}},
        ),
        # Index for leaderboard calculations
        IndexModel(
            [("is_scored", ASCENDING), ("points", DESCENDING)],
            name="idx_predictions_scored_points",
        ),
    ),
)

# =============================================================================
# User Stats Collection Indexes (materialized analytics)
# =============================================================================

USER_STATS_INDEXES = IndexDefinition(
    collection="user_stats",
    indexes=(
        # Unique index on user_id (one stats document per user)
        IndexModel(
            [("user_id", ASCENDING)],
            unique=True,
            name="idx_user_stats_user_unique",
        ),
        # Index for leaderboard by total points
        IndexModel(
            [("total_points", DESCENDING)],
            name="idx_user_stats_leaderboard_points",
        ),
        # Index for leaderboard by accuracy
        IndexModel(
            [("accuracy_percent", DESCENDING)],
            name="idx_user_stats_leaderboard_accuracy",
        ),
        # Compound index for filtering active users in leaderboard
        IndexModel(
            [("total_predictions", DESCENDING), ("accuracy_percent", DESCENDING)],
            name="idx_user_stats_activity_accuracy",
        ),
    ),
)

# =============================================================================
# All Index Definitions
# =============================================================================

ALL_INDEXES: tuple[IndexDefinition, ...] = (
    USERS_INDEXES,
    MATCHES_INDEXES,
    PREDICTIONS_INDEXES,
    USER_STATS_INDEXES,
)


def get_index_definitions() -> dict[str, list[IndexModel]]:
    """
    Get all index definitions as a dictionary.

    Returns:
        Dictionary mapping collection names to their index models.
    """
    return {definition.collection: list(definition.indexes) for definition in ALL_INDEXES}


async def ensure_indexes(db: Any) -> dict[str, list[str]]:
    """
    Create all indexes in the database.

    Args:
        db: Motor database instance.

    Returns:
        Dictionary mapping collection names to created index names.
    """
    results: dict[str, list[str]] = {}

    for definition in ALL_INDEXES:
        collection = db[definition.collection]
        created_indexes = await collection.create_indexes(list(definition.indexes))
        results[definition.collection] = created_indexes

    return results


async def drop_all_indexes(db: Any, keep_id_index: bool = True) -> dict[str, bool]:
    """
    Drop all custom indexes from collections.

    Args:
        db: Motor database instance.
        keep_id_index: If True, keeps the default _id index.

    Returns:
        Dictionary mapping collection names to success status.
    """
    results: dict[str, bool] = {}

    for definition in ALL_INDEXES:
        collection = db[definition.collection]
        try:
            if keep_id_index:
                # Drop each index individually except _id
                for index in definition.indexes:
                    index_name = index.document.get("name")
                    if index_name:
                        try:
                            await collection.drop_index(index_name)
                        except Exception:
                            pass  # Index might not exist
            else:
                await collection.drop_indexes()
            results[definition.collection] = True
        except Exception:
            results[definition.collection] = False

    return results
