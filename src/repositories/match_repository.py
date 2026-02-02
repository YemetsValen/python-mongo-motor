"""
Match repository for MongoDB operations.

Provides async CRUD and query operations for Match documents.
"""

from datetime import datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase

from src.models.match import (
    Match,
    MatchCreate,
    MatchFilter,
    MatchResult,
    MatchStatus,
    MatchUpdate,
    MatchWithPredictionCount,
)
from src.repositories.base import BaseRepository


class MatchRepository(BaseRepository[Match, MatchCreate, MatchUpdate]):
    """
    Repository for Match document operations.

    Handles all database interactions for matches including
    status management, result setting, and filtering.
    """

    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        super().__init__(database, "matches", Match)

    # =========================================================================
    # Query Methods
    # =========================================================================

    async def find_by_status(
        self,
        status: MatchStatus | list[MatchStatus],
        skip: int = 0,
        limit: int = 20,
    ) -> list[Match]:
        """
        Find matches by status.

        Args:
            status: Single status or list of statuses to filter by
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of matches with the specified status(es)
        """
        if isinstance(status, list):
            query = {"status": {"$in": [s.value for s in status]}}
        else:
            query = {"status": status.value}

        cursor = self.collection.find(query).skip(skip).limit(limit)
        cursor = cursor.sort("scheduled_at", 1)  # Sort by scheduled date ascending

        documents = await cursor.to_list(length=limit)
        return [Match.model_validate(doc) for doc in documents]

    async def find_upcoming(
        self,
        limit: int = 20,
        include_postponed: bool = False,
    ) -> list[Match]:
        """
        Find upcoming matches (not yet started).

        Args:
            limit: Maximum number of matches to return
            include_postponed: Whether to include postponed matches

        Returns:
            List of upcoming matches sorted by scheduled time
        """
        statuses = [MatchStatus.PENDING.value]
        if include_postponed:
            statuses.append(MatchStatus.POSTPONED.value)

        query = {
            "status": {"$in": statuses},
            "scheduled_at": {"$gte": datetime.utcnow()},
        }

        cursor = self.collection.find(query).limit(limit)
        cursor = cursor.sort("scheduled_at", 1)

        documents = await cursor.to_list(length=limit)
        return [Match.model_validate(doc) for doc in documents]

    async def find_predictable(self, limit: int = 20) -> list[Match]:
        """
        Find matches that can still receive predictions.

        Returns matches that are:
        - Not locked for predictions
        - In pending or postponed status
        - Scheduled in the future

        Args:
            limit: Maximum number of matches to return

        Returns:
            List of predictable matches
        """
        query = {
            "predictions_locked": False,
            "status": {"$in": [MatchStatus.PENDING.value, MatchStatus.POSTPONED.value]},
        }

        cursor = self.collection.find(query).limit(limit)
        cursor = cursor.sort("scheduled_at", 1)

        documents = await cursor.to_list(length=limit)
        return [Match.model_validate(doc) for doc in documents]

    async def find_finished_unscored(self, limit: int = 100) -> list[Match]:
        """
        Find finished matches that have unscored predictions.

        This is used for batch scoring of predictions.

        Args:
            limit: Maximum number of matches to return

        Returns:
            List of finished matches with potential unscored predictions
        """
        query = {
            "status": MatchStatus.FINISHED.value,
            "home_score": {"$ne": None},
            "away_score": {"$ne": None},
        }

        cursor = self.collection.find(query).limit(limit)
        cursor = cursor.sort("finished_at", -1)

        documents = await cursor.to_list(length=limit)
        return [Match.model_validate(doc) for doc in documents]

    async def find_by_teams(
        self,
        team_name: str,
        status: MatchStatus | None = None,
        limit: int = 20,
    ) -> list[Match]:
        """
        Find matches involving a specific team.

        Args:
            team_name: Team name to search for (case-insensitive)
            status: Optional status filter
            limit: Maximum number of matches to return

        Returns:
            List of matches involving the team
        """
        query: dict[str, Any] = {
            "$or": [
                {"home_team": {"$regex": team_name, "$options": "i"}},
                {"away_team": {"$regex": team_name, "$options": "i"}},
            ]
        }

        if status is not None:
            query["status"] = status.value

        cursor = self.collection.find(query).limit(limit)
        cursor = cursor.sort("scheduled_at", -1)

        documents = await cursor.to_list(length=limit)
        return [Match.model_validate(doc) for doc in documents]

    async def find_by_league(
        self,
        league: str,
        season: str | None = None,
        status: MatchStatus | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[Match]:
        """
        Find matches in a specific league.

        Args:
            league: League name (case-insensitive partial match)
            season: Optional season filter
            status: Optional status filter
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of matches in the league
        """
        query: dict[str, Any] = {
            "league": {"$regex": league, "$options": "i"},
        }

        if season is not None:
            query["season"] = season

        if status is not None:
            query["status"] = status.value

        cursor = self.collection.find(query).skip(skip).limit(limit)
        cursor = cursor.sort("scheduled_at", -1)

        documents = await cursor.to_list(length=limit)
        return [Match.model_validate(doc) for doc in documents]

    async def find_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        status: MatchStatus | None = None,
        limit: int = 100,
    ) -> list[Match]:
        """
        Find matches within a date range.

        Args:
            start_date: Start of date range
            end_date: End of date range
            status: Optional status filter
            limit: Maximum number of matches to return

        Returns:
            List of matches in the date range
        """
        query: dict[str, Any] = {
            "scheduled_at": {
                "$gte": start_date,
                "$lte": end_date,
            }
        }

        if status is not None:
            query["status"] = status.value

        cursor = self.collection.find(query).limit(limit)
        cursor = cursor.sort("scheduled_at", 1)

        documents = await cursor.to_list(length=limit)
        return [Match.model_validate(doc) for doc in documents]

    async def find_with_filter(
        self,
        filter_params: MatchFilter,
        skip: int = 0,
        limit: int = 20,
    ) -> list[Match]:
        """
        Find matches using complex filter.

        Args:
            filter_params: MatchFilter instance with filter criteria
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of matches matching the filter
        """
        query = filter_params.to_query()

        cursor = self.collection.find(query).skip(skip).limit(limit)
        cursor = cursor.sort("scheduled_at", 1)

        documents = await cursor.to_list(length=limit)
        return [Match.model_validate(doc) for doc in documents]

    async def count_by_filter(self, filter_params: MatchFilter) -> int:
        """
        Count matches matching a filter.

        Args:
            filter_params: MatchFilter instance with filter criteria

        Returns:
            Number of matching documents
        """
        query = filter_params.to_query()
        return await self.collection.count_documents(query)

    # =========================================================================
    # Status Management
    # =========================================================================

    async def set_result(
        self,
        match_id: ObjectId | str,
        result: MatchResult,
    ) -> Match | None:
        """
        Set the final result for a match.

        Updates the match to finished status with scores.

        Args:
            match_id: Match document ID
            result: MatchResult with scores

        Returns:
            Updated match or None if not found
        """
        if isinstance(match_id, str):
            match_id = ObjectId(match_id)

        finished_at = result.finished_at or datetime.utcnow()

        update_result = await self.collection.find_one_and_update(
            {"_id": match_id},
            {
                "$set": {
                    "status": MatchStatus.FINISHED.value,
                    "home_score": result.home_score,
                    "away_score": result.away_score,
                    "finished_at": finished_at,
                    "predictions_locked": True,
                    "updated_at": datetime.utcnow(),
                }
            },
            return_document=True,
        )

        if update_result:
            return Match.model_validate(update_result)
        return None

    async def start_match(self, match_id: ObjectId | str) -> Match | None:
        """
        Mark a match as started (live).

        Also locks predictions for this match.

        Args:
            match_id: Match document ID

        Returns:
            Updated match or None if not found
        """
        if isinstance(match_id, str):
            match_id = ObjectId(match_id)

        update_result = await self.collection.find_one_and_update(
            {"_id": match_id},
            {
                "$set": {
                    "status": MatchStatus.LIVE.value,
                    "started_at": datetime.utcnow(),
                    "predictions_locked": True,
                    "updated_at": datetime.utcnow(),
                }
            },
            return_document=True,
        )

        if update_result:
            return Match.model_validate(update_result)
        return None

    async def cancel_match(
        self,
        match_id: ObjectId | str,
        reason: str | None = None,
    ) -> Match | None:
        """
        Cancel a match.

        Args:
            match_id: Match document ID
            reason: Optional cancellation reason

        Returns:
            Updated match or None if not found
        """
        if isinstance(match_id, str):
            match_id = ObjectId(match_id)

        update_data: dict[str, Any] = {
            "status": MatchStatus.CANCELLED.value,
            "cancelled_at": datetime.utcnow(),
            "predictions_locked": True,
            "updated_at": datetime.utcnow(),
        }

        if reason:
            update_data["cancellation_reason"] = reason

        update_result = await self.collection.find_one_and_update(
            {"_id": match_id},
            {"$set": update_data},
            return_document=True,
        )

        if update_result:
            return Match.model_validate(update_result)
        return None

    async def postpone_match(
        self,
        match_id: ObjectId | str,
        new_scheduled_at: datetime | None = None,
    ) -> Match | None:
        """
        Postpone a match.

        Args:
            match_id: Match document ID
            new_scheduled_at: New scheduled time (optional)

        Returns:
            Updated match or None if not found
        """
        if isinstance(match_id, str):
            match_id = ObjectId(match_id)

        update_data: dict[str, Any] = {
            "status": MatchStatus.POSTPONED.value,
            "updated_at": datetime.utcnow(),
        }

        if new_scheduled_at:
            update_data["scheduled_at"] = new_scheduled_at
            # Reopen predictions if match is rescheduled to future
            if new_scheduled_at > datetime.utcnow():
                update_data["predictions_locked"] = False

        update_result = await self.collection.find_one_and_update(
            {"_id": match_id},
            {"$set": update_data},
            return_document=True,
        )

        if update_result:
            return Match.model_validate(update_result)
        return None

    async def lock_predictions(self, match_id: ObjectId | str) -> bool:
        """
        Lock predictions for a match.

        Args:
            match_id: Match document ID

        Returns:
            True if match was updated, False otherwise
        """
        if isinstance(match_id, str):
            match_id = ObjectId(match_id)

        result = await self.collection.update_one(
            {"_id": match_id},
            {
                "$set": {
                    "predictions_locked": True,
                    "updated_at": datetime.utcnow(),
                }
            },
        )

        return result.modified_count > 0

    async def unlock_predictions(self, match_id: ObjectId | str) -> bool:
        """
        Unlock predictions for a match.

        Args:
            match_id: Match document ID

        Returns:
            True if match was updated, False otherwise
        """
        if isinstance(match_id, str):
            match_id = ObjectId(match_id)

        result = await self.collection.update_one(
            {"_id": match_id},
            {
                "$set": {
                    "predictions_locked": False,
                    "updated_at": datetime.utcnow(),
                }
            },
        )

        return result.modified_count > 0

    # =========================================================================
    # Prediction Count Management
    # =========================================================================

    async def increment_prediction_count(self, match_id: ObjectId | str) -> bool:
        """
        Increment the prediction count for a match.

        Args:
            match_id: Match document ID

        Returns:
            True if count was incremented
        """
        if isinstance(match_id, str):
            match_id = ObjectId(match_id)

        result = await self.collection.update_one(
            {"_id": match_id},
            {"$inc": {"total_predictions": 1}},
        )

        return result.modified_count > 0

    async def decrement_prediction_count(self, match_id: ObjectId | str) -> bool:
        """
        Decrement the prediction count for a match.

        Args:
            match_id: Match document ID

        Returns:
            True if count was decremented
        """
        if isinstance(match_id, str):
            match_id = ObjectId(match_id)

        result = await self.collection.update_one(
            {"_id": match_id, "total_predictions": {"$gt": 0}},
            {"$inc": {"total_predictions": -1}},
        )

        return result.modified_count > 0

    # =========================================================================
    # Aggregation Methods
    # =========================================================================

    async def get_with_prediction_counts(
        self,
        match_ids: list[ObjectId | str] | None = None,
        status: MatchStatus | None = None,
        limit: int = 20,
    ) -> list[MatchWithPredictionCount]:
        """
        Get matches with prediction statistics.

        Uses aggregation to join with predictions collection.

        Args:
            match_ids: Optional list of specific match IDs
            status: Optional status filter
            limit: Maximum number of results

        Returns:
            List of matches with prediction counts
        """
        pipeline: list[dict[str, Any]] = []

        # Match stage
        match_query: dict[str, Any] = {}
        if match_ids:
            object_ids = [ObjectId(mid) if isinstance(mid, str) else mid for mid in match_ids]
            match_query["_id"] = {"$in": object_ids}
        if status:
            match_query["status"] = status.value

        if match_query:
            pipeline.append({"$match": match_query})

        # Lookup predictions
        pipeline.append(
            {
                "$lookup": {
                    "from": "predictions",
                    "localField": "_id",
                    "foreignField": "match_id",
                    "as": "predictions",
                }
            }
        )

        # Add prediction counts
        pipeline.append(
            {
                "$addFields": {
                    "prediction_count": {"$size": "$predictions"},
                    "home_win_predictions": {
                        "$size": {
                            "$filter": {
                                "input": "$predictions",
                                "cond": {
                                    "$gt": [
                                        "$$this.predicted_home_score",
                                        "$$this.predicted_away_score",
                                    ]
                                },
                            }
                        }
                    },
                    "away_win_predictions": {
                        "$size": {
                            "$filter": {
                                "input": "$predictions",
                                "cond": {
                                    "$lt": [
                                        "$$this.predicted_home_score",
                                        "$$this.predicted_away_score",
                                    ]
                                },
                            }
                        }
                    },
                    "draw_predictions": {
                        "$size": {
                            "$filter": {
                                "input": "$predictions",
                                "cond": {
                                    "$eq": [
                                        "$$this.predicted_home_score",
                                        "$$this.predicted_away_score",
                                    ]
                                },
                            }
                        }
                    },
                }
            }
        )

        # Remove predictions array
        pipeline.append({"$project": {"predictions": 0}})

        # Sort and limit
        pipeline.append({"$sort": {"scheduled_at": 1}})
        pipeline.append({"$limit": limit})

        cursor = self.collection.aggregate(pipeline)
        documents = await cursor.to_list(length=limit)

        return [MatchWithPredictionCount.model_validate(doc) for doc in documents]

    async def get_stats_by_league(
        self,
        league: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get match statistics grouped by league.

        Args:
            league: Optional league to filter by

        Returns:
            List of league statistics
        """
        pipeline: list[dict[str, Any]] = []

        if league:
            pipeline.append({"$match": {"league": {"$regex": league, "$options": "i"}}})

        pipeline.extend(
            [
                {
                    "$group": {
                        "_id": "$league",
                        "total_matches": {"$sum": 1},
                        "finished_matches": {
                            "$sum": {"$cond": [{"$eq": ["$status", "finished"]}, 1, 0]}
                        },
                        "pending_matches": {
                            "$sum": {"$cond": [{"$eq": ["$status", "pending"]}, 1, 0]}
                        },
                        "total_predictions": {"$sum": "$total_predictions"},
                        "avg_home_goals": {
                            "$avg": {"$cond": [{"$ne": ["$home_score", None]}, "$home_score", None]}
                        },
                        "avg_away_goals": {
                            "$avg": {"$cond": [{"$ne": ["$away_score", None]}, "$away_score", None]}
                        },
                    }
                },
                {"$sort": {"total_matches": -1}},
            ]
        )

        cursor = self.collection.aggregate(pipeline)
        return await cursor.to_list(length=100)

    # =========================================================================
    # Bulk Operations
    # =========================================================================

    async def lock_all_starting_soon(self, minutes_before: int = 30) -> int:
        """
        Lock predictions for all matches starting within specified minutes.

        Args:
            minutes_before: Minutes before match start to lock predictions

        Returns:
            Number of matches locked
        """
        from datetime import timedelta

        cutoff = datetime.utcnow() + timedelta(minutes=minutes_before)

        result = await self.collection.update_many(
            {
                "status": {"$in": [MatchStatus.PENDING.value, MatchStatus.POSTPONED.value]},
                "predictions_locked": False,
                "scheduled_at": {"$lte": cutoff},
            },
            {
                "$set": {
                    "predictions_locked": True,
                    "updated_at": datetime.utcnow(),
                }
            },
        )

        return result.modified_count
