"""
Prediction service for business logic.

Handles prediction creation, updates, scoring, and analytics.
Coordinates between repositories and enforces business rules.
"""

from datetime import datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.models.match import MatchStatus
from src.models.prediction import (
    Prediction,
    PredictionCreate,
    PredictionUpdate,
    PredictionWithDetails,
    UserPredictionStats,
)
from src.repositories.match_repository import MatchRepository
from src.repositories.prediction_repository import PredictionRepository
from src.repositories.user_repository import UserRepository


class PredictionServiceError(Exception):
    """Base exception for prediction service errors."""

    pass


class PredictionNotAllowedError(PredictionServiceError):
    """Raised when prediction is not allowed."""

    pass


class PredictionNotFoundError(PredictionServiceError):
    """Raised when prediction is not found."""

    pass


class DuplicatePredictionError(PredictionServiceError):
    """Raised when user already has prediction for match."""

    pass


class PredictionService:
    """
    Service layer for prediction operations.

    Encapsulates business logic for creating, updating, and scoring
    predictions. Coordinates between multiple repositories.
    """

    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        """
        Initialize prediction service.

        Args:
            database: Motor database instance
        """
        self.db = database
        self.prediction_repo = PredictionRepository(database)
        self.match_repo = MatchRepository(database)
        self.user_repo = UserRepository(database)

    async def create_prediction(
        self,
        user_id: str | ObjectId,
        match_id: str | ObjectId,
        home_score: int,
        away_score: int,
    ) -> Prediction:
        """
        Create a new prediction for a match.

        Validates that:
        - User exists and is active
        - Match exists and accepts predictions
        - User doesn't already have prediction for this match

        Args:
            user_id: User making the prediction
            match_id: Match to predict
            home_score: Predicted home team score
            away_score: Predicted away team score

        Returns:
            Created prediction

        Raises:
            PredictionNotAllowedError: If prediction not allowed
            DuplicatePredictionError: If user already predicted this match
        """
        # Convert to ObjectId
        user_oid = ObjectId(user_id) if isinstance(user_id, str) else user_id
        match_oid = ObjectId(match_id) if isinstance(match_id, str) else match_id

        # Validate user exists and is active
        user = await self.user_repo.find_by_id(user_oid)
        if user is None:
            raise PredictionNotAllowedError(f"User not found: {user_id}")
        if not user.is_active:
            raise PredictionNotAllowedError("User account is not active")

        # Validate match exists and is predictable
        match = await self.match_repo.find_by_id(match_oid)
        if match is None:
            raise PredictionNotAllowedError(f"Match not found: {match_id}")

        if match.predictions_locked:
            raise PredictionNotAllowedError("Predictions are locked for this match")

        if match.status not in (MatchStatus.PENDING, MatchStatus.POSTPONED):
            raise PredictionNotAllowedError(f"Cannot predict match with status: {match.status}")

        # Check for existing prediction
        existing = await self.prediction_repo.get_by_user_and_match(user_oid, match_oid)
        if existing is not None:
            raise DuplicatePredictionError(f"User already has prediction for match {match_id}")

        # Validate scores
        if home_score < 0 or away_score < 0:
            raise PredictionNotAllowedError("Scores cannot be negative")
        if home_score > 99 or away_score > 99:
            raise PredictionNotAllowedError("Scores cannot exceed 99")

        # Create prediction
        prediction_data = PredictionCreate(
            user_id=user_oid,
            match_id=match_oid,
            predicted_home_score=home_score,
            predicted_away_score=away_score,
        )

        prediction = await self.prediction_repo.create_prediction(prediction_data)

        # Update match prediction count
        await self.match_repo.increment_prediction_count(match_oid)

        # Update user stats
        await self.user_repo.increment_stats(user_oid, predictions_delta=1)

        return prediction

    async def update_prediction(
        self,
        prediction_id: str | ObjectId,
        user_id: str | ObjectId,
        home_score: int | None = None,
        away_score: int | None = None,
    ) -> Prediction:
        """
        Update an existing prediction.

        Only allowed if:
        - Prediction exists and belongs to user
        - Prediction hasn't been scored yet
        - Match still accepts predictions

        Args:
            prediction_id: Prediction to update
            user_id: User making the update (for authorization)
            home_score: New home score prediction (optional)
            away_score: New away score prediction (optional)

        Returns:
            Updated prediction

        Raises:
            PredictionNotFoundError: If prediction not found
            PredictionNotAllowedError: If update not allowed
        """
        pred_oid = ObjectId(prediction_id) if isinstance(prediction_id, str) else prediction_id
        user_oid = ObjectId(user_id) if isinstance(user_id, str) else user_id

        # Get existing prediction
        prediction = await self.prediction_repo.find_by_id(pred_oid)
        if prediction is None:
            raise PredictionNotFoundError(f"Prediction not found: {prediction_id}")

        # Verify ownership
        if prediction.user_id != user_oid:
            raise PredictionNotAllowedError("Cannot update another user's prediction")

        # Check if already scored
        if prediction.is_scored:
            raise PredictionNotAllowedError("Cannot update scored prediction")

        # Check if match still accepts predictions
        match = await self.match_repo.find_by_id(prediction.match_id)
        if match and match.predictions_locked:
            raise PredictionNotAllowedError("Predictions are locked for this match")

        # Build update data
        update_data = PredictionUpdate()
        if home_score is not None:
            if home_score < 0 or home_score > 99:
                raise PredictionNotAllowedError("Invalid home score")
            update_data.predicted_home_score = home_score
        if away_score is not None:
            if away_score < 0 or away_score > 99:
                raise PredictionNotAllowedError("Invalid away score")
            update_data.predicted_away_score = away_score

        # Perform update
        updated = await self.prediction_repo.update_prediction(pred_oid, update_data)
        if updated is None:
            raise PredictionNotFoundError("Failed to update prediction")

        return updated

    async def delete_prediction(
        self,
        prediction_id: str | ObjectId,
        user_id: str | ObjectId,
    ) -> bool:
        """
        Delete a prediction.

        Only allowed if prediction hasn't been scored.

        Args:
            prediction_id: Prediction to delete
            user_id: User making the deletion (for authorization)

        Returns:
            True if deleted

        Raises:
            PredictionNotFoundError: If prediction not found
            PredictionNotAllowedError: If deletion not allowed
        """
        pred_oid = ObjectId(prediction_id) if isinstance(prediction_id, str) else prediction_id
        user_oid = ObjectId(user_id) if isinstance(user_id, str) else user_id

        # Get prediction
        prediction = await self.prediction_repo.find_by_id(pred_oid)
        if prediction is None:
            raise PredictionNotFoundError(f"Prediction not found: {prediction_id}")

        # Verify ownership
        if prediction.user_id != user_oid:
            raise PredictionNotAllowedError("Cannot delete another user's prediction")

        # Check if scored
        if prediction.is_scored:
            raise PredictionNotAllowedError("Cannot delete scored prediction")

        # Delete prediction
        deleted = await self.prediction_repo.delete_by_id(pred_oid)

        if deleted:
            # Update counters
            await self.match_repo.decrement_prediction_count(prediction.match_id)
            await self.user_repo.increment_stats(user_oid, predictions_delta=-1)

        return deleted

    async def get_user_prediction(
        self,
        user_id: str | ObjectId,
        match_id: str | ObjectId,
    ) -> Prediction | None:
        """
        Get a user's prediction for a specific match.

        Args:
            user_id: User ID
            match_id: Match ID

        Returns:
            Prediction if found, None otherwise
        """
        user_oid = ObjectId(user_id) if isinstance(user_id, str) else user_id
        match_oid = ObjectId(match_id) if isinstance(match_id, str) else match_id

        return await self.prediction_repo.get_by_user_and_match(user_oid, match_oid)

    async def get_user_predictions(
        self,
        user_id: str | ObjectId,
        skip: int = 0,
        limit: int = 20,
        scored_only: bool = False,
        with_details: bool = False,
    ) -> list[Prediction] | list[PredictionWithDetails]:
        """
        Get all predictions for a user.

        Args:
            user_id: User ID
            skip: Number to skip (pagination)
            limit: Maximum number to return
            scored_only: Only return scored predictions
            with_details: Include match and user details

        Returns:
            List of predictions
        """
        user_oid = ObjectId(user_id) if isinstance(user_id, str) else user_id

        if with_details:
            return await self.prediction_repo.get_predictions_with_details(
                user_oid, skip=skip, limit=limit
            )
        else:
            return await self.prediction_repo.get_user_predictions(
                user_oid, skip=skip, limit=limit, scored_only=scored_only
            )

    async def get_match_predictions(
        self,
        match_id: str | ObjectId,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Prediction]:
        """
        Get all predictions for a match.

        Args:
            match_id: Match ID
            skip: Number to skip (pagination)
            limit: Maximum number to return

        Returns:
            List of predictions
        """
        match_oid = ObjectId(match_id) if isinstance(match_id, str) else match_id
        return await self.prediction_repo.get_match_predictions(match_oid, skip=skip, limit=limit)

    async def score_match_predictions(
        self,
        match_id: str | ObjectId,
    ) -> int:
        """
        Score all predictions for a finished match.

        Gets the match result and scores all pending predictions.
        Also updates user statistics.

        Args:
            match_id: Match ID

        Returns:
            Number of predictions scored

        Raises:
            PredictionServiceError: If match not finished or scores not set
        """
        match_oid = ObjectId(match_id) if isinstance(match_id, str) else match_id

        # Get match
        match = await self.match_repo.find_by_id(match_oid)
        if match is None:
            raise PredictionServiceError(f"Match not found: {match_id}")

        if match.status != MatchStatus.FINISHED:
            raise PredictionServiceError(f"Match not finished: {match.status}")

        if match.home_score is None or match.away_score is None:
            raise PredictionServiceError("Match scores not set")

        # Score predictions
        scored_count = await self.prediction_repo.score_predictions_for_match(
            match_oid, match.home_score, match.away_score
        )

        # Update user statistics for affected users
        if scored_count > 0:
            # Get all predictions for this match to update user stats
            predictions = await self.prediction_repo.get_match_predictions(match_oid, limit=1000)

            for pred in predictions:
                if pred.is_scored and pred.points is not None:
                    await self.user_repo.increment_stats(pred.user_id, points_delta=pred.points)

        return scored_count

    async def get_user_stats(
        self,
        user_id: str | ObjectId,
    ) -> UserPredictionStats:
        """
        Get prediction statistics for a user.

        Args:
            user_id: User ID

        Returns:
            User prediction statistics
        """
        user_oid = ObjectId(user_id) if isinstance(user_id, str) else user_id
        return await self.prediction_repo.get_user_stats(user_oid)

    async def get_match_summary(
        self,
        match_id: str | ObjectId,
    ) -> dict[str, Any]:
        """
        Get prediction summary for a match.

        Includes prediction counts and distribution.

        Args:
            match_id: Match ID

        Returns:
            Match prediction summary
        """
        match_oid = ObjectId(match_id) if isinstance(match_id, str) else match_id
        return await self.prediction_repo.get_match_prediction_summary(match_oid)

    async def get_leaderboard(
        self,
        limit: int = 10,
        min_predictions: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Get the predictions leaderboard.

        Ranks users by total points.

        Args:
            limit: Number of top users to return
            min_predictions: Minimum predictions required to qualify

        Returns:
            List of leaderboard entries with rank
        """
        return await self.prediction_repo.get_leaderboard(
            limit=limit, min_predictions=min_predictions
        )

    async def score_all_pending_matches(self) -> dict[str, int]:
        """
        Score predictions for all finished but unscored matches.

        Useful for batch processing.

        Returns:
            Dictionary with match_id: scored_count mappings
        """
        # Find finished matches that might have unscored predictions
        finished_matches = await self.match_repo.find_finished_unscored(limit=100)

        results: dict[str, int] = {}

        for match in finished_matches:
            if match.home_score is not None and match.away_score is not None:
                try:
                    scored = await self.score_match_predictions(match.id)
                    if scored > 0:
                        results[str(match.id)] = scored
                except PredictionServiceError:
                    # Skip matches that can't be scored
                    continue

        return results

    async def can_user_predict(
        self,
        user_id: str | ObjectId,
        match_id: str | ObjectId,
    ) -> tuple[bool, str]:
        """
        Check if a user can make a prediction for a match.

        Returns a tuple of (can_predict, reason).

        Args:
            user_id: User ID
            match_id: Match ID

        Returns:
            Tuple of (bool, str) - whether user can predict and reason
        """
        user_oid = ObjectId(user_id) if isinstance(user_id, str) else user_id
        match_oid = ObjectId(match_id) if isinstance(match_id, str) else match_id

        # Check user
        user = await self.user_repo.find_by_id(user_oid)
        if user is None:
            return False, "User not found"
        if not user.is_active:
            return False, "User account is not active"

        # Check match
        match = await self.match_repo.find_by_id(match_oid)
        if match is None:
            return False, "Match not found"
        if match.predictions_locked:
            return False, "Predictions are locked for this match"
        if match.status not in (MatchStatus.PENDING, MatchStatus.POSTPONED):
            return False, f"Match status is {match.status}"

        # Check for existing prediction
        existing = await self.prediction_repo.get_by_user_and_match(user_oid, match_oid)
        if existing is not None:
            return False, "User already has prediction for this match"

        return True, "OK"
