"""
Prediction repository for database operations on predictions.

Handles all prediction-related database interactions including
creation, updates, scoring, and analytics queries.
"""

from datetime import datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.models.prediction import (
    Prediction,
    PredictionCreate,
    PredictionUpdate,
    PredictionWithDetails,
    UserPredictionStats,
)
from src.repositories.base import BaseRepository


class PredictionRepository(BaseRepository[Prediction]):
    """
    Repository for prediction document operations.

    Handles CRUD operations and specialized queries for predictions.
    """

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        super().__init__(db, "predictions", Prediction)

    async def create_prediction(self, data: PredictionCreate) -> Prediction:
        """
        Create a new prediction.

        Args:
            data: Prediction creation data

        Returns:
            Created prediction document

        Raises:
            DuplicateKeyError: If user already has prediction for this match
        """
        prediction = Prediction(
            user_id=data.user_id,
            match_id=data.match_id,
            predicted_home_score=data.predicted_home_score,
            predicted_away_score=data.predicted_away_score,
        )

        doc = prediction.model_dump(by_alias=True)
        result = await self.collection.insert_one(doc)
        prediction.id = result.inserted_id

        return prediction

    async def get_by_user_and_match(
        self,
        user_id: ObjectId,
        match_id: ObjectId,
    ) -> Prediction | None:
        """
        Get a user's prediction for a specific match.

        Args:
            user_id: User's ObjectId
            match_id: Match's ObjectId

        Returns:
            Prediction if found, None otherwise
        """
        doc = await self.collection.find_one(
            {
                "user_id": user_id,
                "match_id": match_id,
            }
        )

        if doc is None:
            return None

        return Prediction.model_validate(doc)

    async def get_user_predictions(
        self,
        user_id: ObjectId,
        skip: int = 0,
        limit: int = 20,
        scored_only: bool = False,
    ) -> list[Prediction]:
        """
        Get all predictions for a user.

        Args:
            user_id: User's ObjectId
            skip: Number of documents to skip
            limit: Maximum number of documents to return
            scored_only: If True, only return scored predictions

        Returns:
            List of predictions
        """
        query: dict[str, Any] = {"user_id": user_id}

        if scored_only:
            query["is_scored"] = True

        cursor = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)

        docs = await cursor.to_list(length=limit)
        return [Prediction.model_validate(doc) for doc in docs]

    async def get_match_predictions(
        self,
        match_id: ObjectId,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Prediction]:
        """
        Get all predictions for a match.

        Args:
            match_id: Match's ObjectId
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of predictions
        """
        cursor = (
            self.collection.find({"match_id": match_id})
            .sort("created_at", 1)
            .skip(skip)
            .limit(limit)
        )

        docs = await cursor.to_list(length=limit)
        return [Prediction.model_validate(doc) for doc in docs]

    async def update_prediction(
        self,
        prediction_id: ObjectId,
        data: PredictionUpdate,
    ) -> Prediction | None:
        """
        Update a prediction (before match starts).

        Args:
            prediction_id: Prediction's ObjectId
            data: Update data

        Returns:
            Updated prediction if found, None otherwise
        """
        update_data = data.model_dump(exclude_none=True)

        if not update_data:
            # Nothing to update
            return await self.get_by_id(prediction_id)

        update_data["updated_at"] = datetime.utcnow()

        result = await self.collection.find_one_and_update(
            {"_id": prediction_id, "is_scored": False},  # Can only update unscored
            {"$set": update_data},
            return_document=True,
        )

        if result is None:
            return None

        return Prediction.model_validate(result)

    async def score_predictions_for_match(
        self,
        match_id: ObjectId,
        home_score: int,
        away_score: int,
    ) -> int:
        """
        Score all predictions for a finished match.

        Args:
            match_id: Match's ObjectId
            home_score: Actual home team score
            away_score: Actual away team score

        Returns:
            Number of predictions scored
        """
        # Get all unscored predictions for this match
        cursor = self.collection.find(
            {
                "match_id": match_id,
                "is_scored": False,
            }
        )

        scored_count = 0
        scored_at = datetime.utcnow()

        async for doc in cursor:
            prediction = Prediction.model_validate(doc)

            # Calculate points
            points, breakdown = prediction.calculate_points(home_score, away_score)

            # Update the prediction
            await self.collection.update_one(
                {"_id": prediction.id},
                {
                    "$set": {
                        "is_scored": True,
                        "points": points,
                        "points_breakdown": breakdown,
                        "actual_home_score": home_score,
                        "actual_away_score": away_score,
                        "scored_at": scored_at,
                    }
                },
            )

            scored_count += 1

        return scored_count

    async def get_user_stats(self, user_id: ObjectId) -> UserPredictionStats:
        """
        Calculate prediction statistics for a user.

        Uses MongoDB aggregation pipeline for efficient calculation.

        Args:
            user_id: User's ObjectId

        Returns:
            User prediction statistics
        """
        pipeline = [
            {"$match": {"user_id": user_id}},
            {
                "$group": {
                    "_id": "$user_id",
                    "total_predictions": {"$sum": 1},
                    "scored_predictions": {"$sum": {"$cond": ["$is_scored", 1, 0]}},
                    "total_points": {"$sum": {"$ifNull": ["$points", 0]}},
                    "exact_scores": {"$sum": {"$cond": [{"$eq": ["$points", 3]}, 1, 0]}},
                    "correct_differences": {"$sum": {"$cond": [{"$eq": ["$points", 2]}, 1, 0]}},
                    "correct_outcomes": {"$sum": {"$cond": [{"$eq": ["$points", 1]}, 1, 0]}},
                    "incorrect": {
                        "$sum": {
                            "$cond": [
                                {"$and": ["$is_scored", {"$eq": ["$points", 0]}]},
                                1,
                                0,
                            ]
                        }
                    },
                }
            },
        ]

        results = await self.collection.aggregate(pipeline).to_list(length=1)

        if not results:
            # No predictions for this user
            return UserPredictionStats(
                user_id=user_id,
                total_predictions=0,
                scored_predictions=0,
                total_points=0,
                exact_scores=0,
                correct_differences=0,
                correct_outcomes=0,
                incorrect=0,
            )

        data = results[0]
        return UserPredictionStats(
            user_id=user_id,
            total_predictions=data["total_predictions"],
            scored_predictions=data["scored_predictions"],
            total_points=data["total_points"],
            exact_scores=data["exact_scores"],
            correct_differences=data["correct_differences"],
            correct_outcomes=data["correct_outcomes"],
            incorrect=data["incorrect"],
        )

    async def get_predictions_with_details(
        self,
        user_id: ObjectId,
        skip: int = 0,
        limit: int = 20,
    ) -> list[PredictionWithDetails]:
        """
        Get user predictions with match and user details embedded.

        Uses aggregation with $lookup for joining collections.

        Args:
            user_id: User's ObjectId
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of predictions with embedded details
        """
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$sort": {"created_at": -1}},
            {"$skip": skip},
            {"$limit": limit},
            # Lookup match details
            {
                "$lookup": {
                    "from": "matches",
                    "localField": "match_id",
                    "foreignField": "_id",
                    "as": "match",
                }
            },
            {"$unwind": {"path": "$match", "preserveNullAndEmptyArrays": True}},
            # Lookup user details
            {
                "$lookup": {
                    "from": "users",
                    "localField": "user_id",
                    "foreignField": "_id",
                    "as": "user",
                }
            },
            {"$unwind": {"path": "$user", "preserveNullAndEmptyArrays": True}},
            # Project the fields we need
            {
                "$project": {
                    "_id": 1,
                    "user_id": 1,
                    "match_id": 1,
                    "predicted_home_score": 1,
                    "predicted_away_score": 1,
                    "is_scored": 1,
                    "points": 1,
                    "points_breakdown": 1,
                    "actual_home_score": 1,
                    "actual_away_score": 1,
                    "created_at": 1,
                    "updated_at": 1,
                    "scored_at": 1,
                    "user_username": "$user.username",
                    "match_home_team": "$match.home_team",
                    "match_away_team": "$match.away_team",
                    "match_scheduled_at": "$match.scheduled_at",
                    "match_status": "$match.status",
                }
            },
        ]

        results = await self.collection.aggregate(pipeline).to_list(length=limit)
        return [PredictionWithDetails.model_validate(doc) for doc in results]

    async def get_match_prediction_summary(self, match_id: ObjectId) -> dict[str, Any]:
        """
        Get aggregated prediction summary for a match.

        Args:
            match_id: Match's ObjectId

        Returns:
            Dictionary with prediction statistics for the match
        """
        pipeline = [
            {"$match": {"match_id": match_id}},
            {
                "$group": {
                    "_id": "$match_id",
                    "total_predictions": {"$sum": 1},
                    "home_win_predictions": {
                        "$sum": {
                            "$cond": [
                                {"$gt": ["$predicted_home_score", "$predicted_away_score"]},
                                1,
                                0,
                            ]
                        }
                    },
                    "draw_predictions": {
                        "$sum": {
                            "$cond": [
                                {"$eq": ["$predicted_home_score", "$predicted_away_score"]},
                                1,
                                0,
                            ]
                        }
                    },
                    "away_win_predictions": {
                        "$sum": {
                            "$cond": [
                                {"$lt": ["$predicted_home_score", "$predicted_away_score"]},
                                1,
                                0,
                            ]
                        }
                    },
                    "avg_home_score": {"$avg": "$predicted_home_score"},
                    "avg_away_score": {"$avg": "$predicted_away_score"},
                }
            },
        ]

        results = await self.collection.aggregate(pipeline).to_list(length=1)

        if not results:
            return {
                "total_predictions": 0,
                "home_win_predictions": 0,
                "draw_predictions": 0,
                "away_win_predictions": 0,
                "avg_home_score": 0,
                "avg_away_score": 0,
            }

        return results[0]

    async def get_leaderboard(
        self,
        limit: int = 10,
        min_predictions: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Get leaderboard of top predictors.

        Args:
            limit: Number of top users to return
            min_predictions: Minimum predictions required to qualify

        Returns:
            List of leaderboard entries
        """
        pipeline = [
            {"$match": {"is_scored": True}},
            {
                "$group": {
                    "_id": "$user_id",
                    "total_points": {"$sum": "$points"},
                    "total_predictions": {"$sum": 1},
                    "exact_scores": {"$sum": {"$cond": [{"$eq": ["$points", 3]}, 1, 0]}},
                    "correct_count": {"$sum": {"$cond": [{"$gt": ["$points", 0]}, 1, 0]}},
                }
            },
            # Filter by minimum predictions
            {"$match": {"total_predictions": {"$gte": min_predictions}}},
            # Calculate accuracy
            {
                "$addFields": {
                    "accuracy_percent": {
                        "$round": [
                            {
                                "$multiply": [
                                    {"$divide": ["$correct_count", "$total_predictions"]},
                                    100,
                                ]
                            },
                            2,
                        ]
                    }
                }
            },
            # Sort by total points
            {"$sort": {"total_points": -1, "accuracy_percent": -1}},
            {"$limit": limit},
            # Lookup user details
            {
                "$lookup": {
                    "from": "users",
                    "localField": "_id",
                    "foreignField": "_id",
                    "as": "user",
                }
            },
            {"$unwind": "$user"},
            # Final projection
            {
                "$project": {
                    "user_id": "$_id",
                    "username": "$user.username",
                    "total_points": 1,
                    "total_predictions": 1,
                    "exact_scores": 1,
                    "accuracy_percent": 1,
                }
            },
        ]

        results = await self.collection.aggregate(pipeline).to_list(length=limit)

        # Add rank
        for i, entry in enumerate(results, start=1):
            entry["rank"] = i

        return results

    async def count_user_predictions(self, user_id: ObjectId) -> int:
        """Count total predictions for a user."""
        return await self.collection.count_documents({"user_id": user_id})

    async def count_match_predictions(self, match_id: ObjectId) -> int:
        """Count total predictions for a match."""
        return await self.collection.count_documents({"match_id": match_id})

    async def delete_user_predictions(self, user_id: ObjectId) -> int:
        """
        Delete all predictions for a user.

        Args:
            user_id: User's ObjectId

        Returns:
            Number of deleted predictions
        """
        result = await self.collection.delete_many({"user_id": user_id})
        return result.deleted_count

    async def delete_match_predictions(self, match_id: ObjectId) -> int:
        """
        Delete all predictions for a match.

        Args:
            match_id: Match's ObjectId

        Returns:
            Number of deleted predictions
        """
        result = await self.collection.delete_many({"match_id": match_id})
        return result.deleted_count
