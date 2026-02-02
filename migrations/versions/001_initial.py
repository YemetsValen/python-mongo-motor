"""
Initial migration: Create all indexes for collections.

Migration version: 001
Created: 2024-01-01
Description: Sets up indexes for users, matches, predictions, and user_stats collections.
"""

from datetime import datetime
from typing import Any

from pymongo import ASCENDING, DESCENDING, IndexModel

# Migration metadata
VERSION = 1
DESCRIPTION = "Create initial indexes for all collections"
CREATED_AT = datetime.utcnow()


# Index definitions
INDEXES: dict[str, list[IndexModel]] = {
    "users": [
        IndexModel(
            [("username", ASCENDING)],
            unique=True,
            name="idx_users_username_unique",
        ),
        IndexModel(
            [("email", ASCENDING)],
            unique=True,
            name="idx_users_email_unique",
        ),
        IndexModel(
            [("is_active", ASCENDING), ("created_at", DESCENDING)],
            name="idx_users_active_created",
        ),
        IndexModel(
            [("username", "text"), ("email", "text")],
            name="idx_users_text_search",
        ),
    ],
    "matches": [
        IndexModel(
            [("status", ASCENDING), ("scheduled_at", ASCENDING)],
            name="idx_matches_status_scheduled",
        ),
        IndexModel(
            [("scheduled_at", ASCENDING)],
            name="idx_matches_scheduled",
        ),
        IndexModel(
            [("home_team", ASCENDING), ("away_team", ASCENDING)],
            name="idx_matches_teams",
        ),
        IndexModel(
            [("status", ASCENDING), ("finished_at", DESCENDING)],
            name="idx_matches_finished",
            partialFilterExpression={"status": "finished"},
        ),
        IndexModel(
            [("home_team", "text"), ("away_team", "text")],
            name="idx_matches_text_search",
        ),
        IndexModel(
            [("league", ASCENDING), ("season", ASCENDING)],
            name="idx_matches_league_season",
        ),
    ],
    "predictions": [
        IndexModel(
            [("user_id", ASCENDING), ("match_id", ASCENDING)],
            unique=True,
            name="idx_predictions_user_match_unique",
        ),
        IndexModel(
            [("match_id", ASCENDING), ("created_at", DESCENDING)],
            name="idx_predictions_match_created",
        ),
        IndexModel(
            [("user_id", ASCENDING), ("created_at", DESCENDING)],
            name="idx_predictions_user_history",
        ),
        IndexModel(
            [("user_id", ASCENDING), ("points", DESCENDING)],
            name="idx_predictions_user_points",
            partialFilterExpression={"points": {"$exists": True}},
        ),
        IndexModel(
            [("is_scored", ASCENDING), ("points", DESCENDING)],
            name="idx_predictions_scored_points",
        ),
        IndexModel(
            [("match_id", ASCENDING), ("is_scored", ASCENDING)],
            name="idx_predictions_match_scored",
        ),
    ],
    "user_stats": [
        IndexModel(
            [("user_id", ASCENDING)],
            unique=True,
            name="idx_user_stats_user_unique",
        ),
        IndexModel(
            [("total_points", DESCENDING)],
            name="idx_user_stats_leaderboard_points",
        ),
        IndexModel(
            [("accuracy_percent", DESCENDING)],
            name="idx_user_stats_leaderboard_accuracy",
        ),
        IndexModel(
            [("total_predictions", DESCENDING), ("accuracy_percent", DESCENDING)],
            name="idx_user_stats_activity_accuracy",
        ),
    ],
}


async def upgrade(db: Any) -> dict[str, list[str]]:
    """
    Apply migration: Create all indexes.

    Args:
        db: Motor database instance

    Returns:
        Dictionary mapping collection names to created index names
    """
    results: dict[str, list[str]] = {}

    for collection_name, indexes in INDEXES.items():
        collection = db[collection_name]

        # Ensure collection exists by inserting and deleting a dummy doc
        # (MongoDB creates collections lazily)
        try:
            created = await collection.create_indexes(indexes)
            results[collection_name] = created
        except Exception as e:
            print(f"Warning: Could not create indexes for {collection_name}: {e}")
            results[collection_name] = []

    # Record migration in migrations collection
    await db["_migrations"].insert_one(
        {
            "version": VERSION,
            "description": DESCRIPTION,
            "applied_at": datetime.utcnow(),
            "status": "applied",
        }
    )

    return results


async def downgrade(db: Any) -> dict[str, bool]:
    """
    Revert migration: Drop all custom indexes.

    Args:
        db: Motor database instance

    Returns:
        Dictionary mapping collection names to success status
    """
    results: dict[str, bool] = {}

    for collection_name, indexes in INDEXES.items():
        collection = db[collection_name]

        try:
            for index in indexes:
                index_name = index.document.get("name")
                if index_name:
                    try:
                        await collection.drop_index(index_name)
                    except Exception:
                        pass  # Index might not exist
            results[collection_name] = True
        except Exception as e:
            print(f"Warning: Could not drop indexes for {collection_name}: {e}")
            results[collection_name] = False

    # Remove migration record
    await db["_migrations"].delete_one({"version": VERSION})

    return results


async def is_applied(db: Any) -> bool:
    """
    Check if this migration has been applied.

    Args:
        db: Motor database instance

    Returns:
        True if migration was already applied
    """
    record = await db["_migrations"].find_one({"version": VERSION})
    return record is not None


# For CLI usage
if __name__ == "__main__":
    import asyncio

    from motor.motor_asyncio import AsyncIOMotorClient

    async def main():
        # Connect to local MongoDB
        client = AsyncIOMotorClient("mongodb://localhost:27017")
        db = client["predictions_db"]

        if await is_applied(db):
            print(f"Migration {VERSION} already applied")
        else:
            print(f"Applying migration {VERSION}: {DESCRIPTION}")
            results = await upgrade(db)
            print("Created indexes:")
            for collection, indexes in results.items():
                print(f"  {collection}: {indexes}")

        client.close()

    asyncio.run(main())
