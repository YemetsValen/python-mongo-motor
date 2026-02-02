"""
Analytics service for generating statistics, leaderboards, and reports.

Provides comprehensive analytics capabilities using MongoDB aggregation
pipelines for efficient data processing.
"""

from datetime import datetime, timedelta
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.models.analytics import (
    DailyStats,
    Leaderboard,
    LeaderboardEntry,
    LeaderboardType,
    MatchPredictionSummary,
    PredictionDistribution,
    SystemStats,
    TimePeriod,
    UserPredictionStats,
    UserTrend,
)


class AnalyticsService:
    """
    Service for generating analytics and statistics.

    Uses MongoDB aggregation pipelines for efficient computation
    of leaderboards, user statistics, and system-wide metrics.
    """

    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        """
        Initialize analytics service.

        Args:
            database: Motor database instance
        """
        self.db = database
        self.users = database["users"]
        self.matches = database["matches"]
        self.predictions = database["predictions"]
        self.user_stats = database["user_stats"]

    # =========================================================================
    # User Statistics
    # =========================================================================

    async def get_user_stats(self, user_id: ObjectId | str) -> UserPredictionStats | None:
        """
        Get comprehensive statistics for a user.

        Args:
            user_id: User's ObjectId

        Returns:
            User statistics or None if user not found
        """
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)

        # Get user info
        user = await self.users.find_one({"_id": user_id})
        if not user:
            return None

        # Aggregate prediction stats
        pipeline = [
            {"$match": {"user_id": user_id}},
            {
                "$facet": {
                    "totals": [
                        {
                            "$group": {
                                "_id": None,
                                "total_predictions": {"$sum": 1},
                                "scored_predictions": {"$sum": {"$cond": ["$is_scored", 1, 0]}},
                                "pending_predictions": {"$sum": {"$cond": ["$is_scored", 0, 1]}},
                                "total_points": {"$sum": {"$ifNull": ["$points", 0]}},
                            }
                        }
                    ],
                    "outcomes": [
                        {"$match": {"is_scored": True}},
                        {
                            "$group": {
                                "_id": "$points",
                                "count": {"$sum": 1},
                            }
                        },
                    ],
                    "dates": [
                        {
                            "$group": {
                                "_id": None,
                                "first_prediction": {"$min": "$created_at"},
                                "last_prediction": {"$max": "$created_at"},
                            }
                        }
                    ],
                    "streaks": [
                        {"$match": {"is_scored": True}},
                        {"$sort": {"scored_at": 1}},
                        {
                            "$group": {
                                "_id": None,
                                "results": {"$push": {"$cond": [{"$gt": ["$points", 0]}, 1, 0]}},
                            }
                        },
                    ],
                }
            },
        ]

        results = await self.predictions.aggregate(pipeline).to_list(length=1)

        if not results:
            return UserPredictionStats(
                user_id=user_id,
                username=user.get("username", "Unknown"),
                total_predictions=0,
                scored_predictions=0,
                pending_predictions=0,
                exact_scores=0,
                correct_diffs=0,
                correct_outcomes=0,
                incorrect=0,
                total_points=0,
            )

        data = results[0]

        # Parse totals
        totals = data["totals"][0] if data["totals"] else {}
        total_predictions = totals.get("total_predictions", 0)
        scored_predictions = totals.get("scored_predictions", 0)
        pending_predictions = totals.get("pending_predictions", 0)
        total_points = totals.get("total_points", 0)

        # Parse outcomes (points: 3=exact, 2=diff, 1=outcome, 0=incorrect)
        outcomes_map = {item["_id"]: item["count"] for item in data["outcomes"]}
        exact_scores = outcomes_map.get(3, 0)
        correct_diffs = outcomes_map.get(2, 0)
        correct_outcomes = outcomes_map.get(1, 0)
        incorrect = outcomes_map.get(0, 0)

        # Parse dates
        dates = data["dates"][0] if data["dates"] else {}
        first_prediction_at = dates.get("first_prediction")
        last_prediction_at = dates.get("last_prediction")

        # Calculate streaks
        current_streak = 0
        best_streak = 0
        worst_streak = 0

        if data["streaks"] and data["streaks"][0].get("results"):
            results_list = data["streaks"][0]["results"]
            current_streak, best_streak, worst_streak = self._calculate_streaks(results_list)

        return UserPredictionStats(
            user_id=user_id,
            username=user.get("username", "Unknown"),
            total_predictions=total_predictions,
            scored_predictions=scored_predictions,
            pending_predictions=pending_predictions,
            exact_scores=exact_scores,
            correct_diffs=correct_diffs,
            correct_outcomes=correct_outcomes,
            incorrect=incorrect,
            total_points=total_points,
            current_streak=current_streak,
            best_streak=best_streak,
            worst_streak=worst_streak,
            first_prediction_at=first_prediction_at,
            last_prediction_at=last_prediction_at,
        )

    def _calculate_streaks(self, results: list[int]) -> tuple[int, int, int]:
        """
        Calculate winning/losing streaks from a list of results.

        Args:
            results: List of 1 (correct) or 0 (incorrect)

        Returns:
            Tuple of (current_streak, best_winning_streak, worst_losing_streak)
        """
        if not results:
            return 0, 0, 0

        current_streak = 0
        best_streak = 0
        worst_streak = 0
        temp_streak = 0
        temp_losing = 0

        for result in results:
            if result == 1:
                temp_streak += 1
                temp_losing = 0
                best_streak = max(best_streak, temp_streak)
            else:
                temp_losing += 1
                temp_streak = 0
                worst_streak = max(worst_streak, temp_losing)

        # Current streak (from the end)
        current_streak = 0
        for result in reversed(results):
            if result == 1:
                current_streak += 1
            else:
                break

        return current_streak, best_streak, worst_streak

    # =========================================================================
    # Leaderboards
    # =========================================================================

    async def get_leaderboard(
        self,
        leaderboard_type: LeaderboardType = LeaderboardType.POINTS,
        period: TimePeriod = TimePeriod.ALL_TIME,
        limit: int = 20,
        min_predictions: int = 5,
    ) -> Leaderboard:
        """
        Generate a leaderboard.

        Args:
            leaderboard_type: Type of leaderboard (points, accuracy, etc.)
            period: Time period for the leaderboard
            limit: Number of entries to return
            min_predictions: Minimum predictions to qualify

        Returns:
            Leaderboard with ranked entries
        """
        # Calculate date range for period
        period_start, period_end = self._get_period_dates(period)

        # Build match stage
        match_stage: dict[str, Any] = {"is_scored": True}
        if period_start:
            match_stage["scored_at"] = {"$gte": period_start, "$lte": period_end}

        # Build sort field based on type
        sort_field = self._get_sort_field(leaderboard_type)

        pipeline = [
            {"$match": match_stage},
            {
                "$group": {
                    "_id": "$user_id",
                    "total_points": {"$sum": "$points"},
                    "total_predictions": {"$sum": 1},
                    "exact_scores": {"$sum": {"$cond": [{"$eq": ["$points", 3]}, 1, 0]}},
                    "correct_count": {"$sum": {"$cond": [{"$gt": ["$points", 0]}, 1, 0]}},
                }
            },
            {"$match": {"total_predictions": {"$gte": min_predictions}}},
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
            {"$sort": {sort_field: -1, "total_predictions": -1}},
            {"$limit": limit},
            {
                "$lookup": {
                    "from": "users",
                    "localField": "_id",
                    "foreignField": "_id",
                    "as": "user",
                }
            },
            {"$unwind": {"path": "$user", "preserveNullAndEmptyArrays": True}},
            {
                "$project": {
                    "user_id": "$_id",
                    "username": {"$ifNull": ["$user.username", "Unknown"]},
                    "total_points": 1,
                    "total_predictions": 1,
                    "accuracy_percent": 1,
                    "exact_scores": 1,
                }
            },
        ]

        results = await self.predictions.aggregate(pipeline).to_list(length=limit)

        # Count total participants
        count_pipeline = [
            {"$match": match_stage},
            {"$group": {"_id": "$user_id"}},
            {"$count": "total"},
        ]
        count_result = await self.predictions.aggregate(count_pipeline).to_list(length=1)
        total_participants = count_result[0]["total"] if count_result else 0

        # Build leaderboard entries
        entries = []
        for rank, entry in enumerate(results, start=1):
            entries.append(
                LeaderboardEntry(
                    rank=rank,
                    user_id=entry["user_id"],
                    username=entry["username"],
                    total_points=entry["total_points"],
                    total_predictions=entry["total_predictions"],
                    accuracy_percent=entry["accuracy_percent"],
                    exact_scores=entry["exact_scores"],
                    rank_change=0,  # Would need historical data
                    points_change=0,
                    is_new=False,
                )
            )

        return Leaderboard(
            type=leaderboard_type,
            period=period,
            entries=entries,
            total_participants=total_participants,
            period_start=period_start,
            period_end=period_end,
        )

    def _get_period_dates(self, period: TimePeriod) -> tuple[datetime | None, datetime | None]:
        """Get start and end dates for a time period."""
        now = datetime.utcnow()

        if period == TimePeriod.ALL_TIME:
            return None, None
        elif period == TimePeriod.DAY:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == TimePeriod.WEEK:
            start = now - timedelta(days=now.weekday())
            start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == TimePeriod.MONTH:
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif period == TimePeriod.YEAR:
            start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            return None, None

        return start, now

    def _get_sort_field(self, leaderboard_type: LeaderboardType) -> str:
        """Get the field to sort by for a leaderboard type."""
        mapping = {
            LeaderboardType.POINTS: "total_points",
            LeaderboardType.ACCURACY: "accuracy_percent",
            LeaderboardType.EXACT_SCORES: "exact_scores",
            LeaderboardType.EFFICIENCY: "accuracy_percent",
        }
        return mapping.get(leaderboard_type, "total_points")

    # =========================================================================
    # Match Analytics
    # =========================================================================

    async def get_match_prediction_summary(
        self, match_id: ObjectId | str
    ) -> MatchPredictionSummary | None:
        """
        Get prediction summary for a specific match.

        Args:
            match_id: Match's ObjectId

        Returns:
            Match prediction summary or None
        """
        if isinstance(match_id, str):
            match_id = ObjectId(match_id)

        # Get match info
        match = await self.matches.find_one({"_id": match_id})
        if not match:
            return None

        # Aggregate predictions
        pipeline = [
            {"$match": {"match_id": match_id}},
            {
                "$group": {
                    "_id": None,
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
                    "avg_home": {"$avg": "$predicted_home_score"},
                    "avg_away": {"$avg": "$predicted_away_score"},
                    "scores": {
                        "$push": {
                            "$concat": [
                                {"$toString": "$predicted_home_score"},
                                "-",
                                {"$toString": "$predicted_away_score"},
                            ]
                        }
                    },
                }
            },
        ]

        results = await self.predictions.aggregate(pipeline).to_list(length=1)

        if not results:
            return MatchPredictionSummary(
                match_id=match_id,
                home_team=match.get("home_team", ""),
                away_team=match.get("away_team", ""),
                total_predictions=0,
            )

        data = results[0]

        # Find most predicted score
        scores = data.get("scores", [])
        most_predicted_score = None
        most_predicted_count = 0
        if scores:
            from collections import Counter

            score_counts = Counter(scores)
            most_predicted_score, most_predicted_count = score_counts.most_common(1)[0]

        return MatchPredictionSummary(
            match_id=match_id,
            home_team=match.get("home_team", ""),
            away_team=match.get("away_team", ""),
            total_predictions=data.get("total_predictions", 0),
            home_win_predictions=data.get("home_win_predictions", 0),
            draw_predictions=data.get("draw_predictions", 0),
            away_win_predictions=data.get("away_win_predictions", 0),
            most_predicted_score=most_predicted_score,
            most_predicted_score_count=most_predicted_count,
            avg_predicted_home_goals=round(data.get("avg_home", 0), 2),
            avg_predicted_away_goals=round(data.get("avg_away", 0), 2),
            actual_home_score=match.get("home_score"),
            actual_away_score=match.get("away_score"),
        )

    # =========================================================================
    # System Statistics
    # =========================================================================

    async def get_system_stats(self) -> SystemStats:
        """
        Get system-wide statistics.

        Returns:
            System statistics
        """
        # Users stats
        total_users = await self.users.count_documents({})
        active_users = await self.users.count_documents({"is_active": True})

        # Match stats
        total_matches = await self.matches.count_documents({})
        finished_matches = await self.matches.count_documents({"status": "finished"})
        pending_matches = await self.matches.count_documents({"status": "pending"})

        # Prediction stats
        total_predictions = await self.predictions.count_documents({})
        scored_predictions = await self.predictions.count_documents({"is_scored": True})

        # Calculate averages
        avg_per_match = total_predictions / total_matches if total_matches > 0 else 0
        avg_per_user = total_predictions / total_users if total_users > 0 else 0

        # Global accuracy
        accuracy_pipeline = [
            {"$match": {"is_scored": True}},
            {
                "$group": {
                    "_id": None,
                    "total": {"$sum": 1},
                    "correct": {"$sum": {"$cond": [{"$gt": ["$points", 0]}, 1, 0]}},
                }
            },
        ]
        accuracy_result = await self.predictions.aggregate(accuracy_pipeline).to_list(1)
        global_accuracy = 0.0
        if accuracy_result:
            data = accuracy_result[0]
            if data["total"] > 0:
                global_accuracy = round((data["correct"] / data["total"]) * 100, 2)

        return SystemStats(
            total_users=total_users,
            active_users=active_users,
            total_matches=total_matches,
            finished_matches=finished_matches,
            pending_matches=pending_matches,
            total_predictions=total_predictions,
            scored_predictions=scored_predictions,
            avg_predictions_per_match=round(avg_per_match, 2),
            avg_predictions_per_user=round(avg_per_user, 2),
            global_accuracy_percent=global_accuracy,
        )

    # =========================================================================
    # Prediction Distribution
    # =========================================================================

    async def get_prediction_distribution(
        self, period: TimePeriod = TimePeriod.ALL_TIME
    ) -> PredictionDistribution:
        """
        Get distribution of prediction outcomes.

        Args:
            period: Time period to analyze

        Returns:
            Prediction distribution
        """
        period_start, period_end = self._get_period_dates(period)

        match_stage: dict[str, Any] = {"is_scored": True}
        if period_start:
            match_stage["scored_at"] = {"$gte": period_start, "$lte": period_end}

        pipeline = [
            {"$match": match_stage},
            {
                "$group": {
                    "_id": "$points",
                    "count": {"$sum": 1},
                }
            },
        ]

        results = await self.predictions.aggregate(pipeline).to_list(length=10)

        outcomes_map = {item["_id"]: item["count"] for item in results}
        total = sum(outcomes_map.values())

        return PredictionDistribution(
            period=period,
            exact_scores_count=outcomes_map.get(3, 0),
            correct_diffs_count=outcomes_map.get(2, 0),
            correct_outcomes_count=outcomes_map.get(1, 0),
            incorrect_count=outcomes_map.get(0, 0),
            total=total,
        )

    # =========================================================================
    # User Trends
    # =========================================================================

    async def get_user_trend(
        self,
        user_id: ObjectId | str,
        period: TimePeriod = TimePeriod.MONTH,
    ) -> UserTrend:
        """
        Get user performance trend over time.

        Args:
            user_id: User's ObjectId
            period: Time period to analyze

        Returns:
            User trend data
        """
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)

        period_start, period_end = self._get_period_dates(period)

        match_stage: dict[str, Any] = {"user_id": user_id, "is_scored": True}
        if period_start:
            match_stage["scored_at"] = {"$gte": period_start, "$lte": period_end}

        pipeline = [
            {"$match": match_stage},
            {
                "$group": {
                    "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$scored_at"}},
                    "predictions_made": {"$sum": 1},
                    "points_earned": {"$sum": "$points"},
                    "correct": {"$sum": {"$cond": [{"$gt": ["$points", 0]}, 1, 0]}},
                }
            },
            {"$sort": {"_id": 1}},
        ]

        results = await self.predictions.aggregate(pipeline).to_list(length=100)

        data_points = []
        for item in results:
            total = item["predictions_made"]
            correct = item["correct"]
            accuracy = round((correct / total) * 100, 2) if total > 0 else 0.0

            data_points.append(
                DailyStats(
                    date=datetime.strptime(item["_id"], "%Y-%m-%d"),
                    predictions_made=total,
                    matches_finished=total,  # Approximation
                    points_earned=item["points_earned"],
                    accuracy_percent=accuracy,
                )
            )

        return UserTrend(
            user_id=user_id,
            period=period,
            data_points=data_points,
        )

    # =========================================================================
    # Cache Management
    # =========================================================================

    async def refresh_user_stats_cache(self, user_id: ObjectId | str) -> None:
        """
        Refresh cached statistics for a user.

        Updates the user_stats collection with fresh calculations.

        Args:
            user_id: User's ObjectId
        """
        stats = await self.get_user_stats(user_id)
        if stats:
            await self.user_stats.update_one(
                {"user_id": stats.user_id},
                {"$set": stats.model_dump()},
                upsert=True,
            )

    async def refresh_all_user_stats(self) -> int:
        """
        Refresh cached statistics for all users.

        Returns:
            Number of users updated
        """
        # Get all users with predictions
        user_ids = await self.predictions.distinct("user_id")

        count = 0
        for user_id in user_ids:
            await self.refresh_user_stats_cache(user_id)
            count += 1

        return count
