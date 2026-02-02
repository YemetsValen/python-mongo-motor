"""
Match service with business logic for match operations.

Provides high-level operations for managing matches,
including validation, status transitions, and result processing.
"""

from datetime import datetime, timedelta
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.models.match import (
    Match,
    MatchCreate,
    MatchFilter,
    MatchResult,
    MatchStatus,
    MatchUpdate,
    MatchWithPredictionCount,
)
from src.repositories.match_repository import MatchRepository
from src.repositories.prediction_repository import PredictionRepository


class MatchServiceError(Exception):
    """Base exception for match service errors."""

    pass


class MatchNotFoundError(MatchServiceError):
    """Raised when a match is not found."""

    pass


class InvalidMatchStateError(MatchServiceError):
    """Raised when an operation is invalid for the current match state."""

    pass


class PredictionsLockedError(MatchServiceError):
    """Raised when trying to modify a match with locked predictions."""

    pass


class MatchService:
    """
    Service layer for match operations.

    Handles business logic, validation, and orchestration
    between match and prediction repositories.
    """

    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        """
        Initialize match service.

        Args:
            database: Motor database instance
        """
        self._db = database
        self._match_repo = MatchRepository(database)
        self._prediction_repo = PredictionRepository(database)

    # =========================================================================
    # Create Operations
    # =========================================================================

    async def create_match(self, data: MatchCreate) -> Match:
        """
        Create a new match.

        Args:
            data: Match creation data

        Returns:
            Created match

        Raises:
            MatchServiceError: If validation fails
        """
        # Validate scheduled time is in the future
        if data.scheduled_at <= datetime.utcnow():
            raise MatchServiceError("Match must be scheduled in the future")

        # Create match document
        match = Match(
            home_team=data.home_team,
            away_team=data.away_team,
            scheduled_at=data.scheduled_at,
            sport=data.sport,
            league=data.league,
            season=data.season,
            status=MatchStatus.PENDING,
            predictions_locked=False,
        )

        return await self._match_repo.create(match)

    async def create_matches_batch(
        self,
        matches: list[MatchCreate],
    ) -> list[Match]:
        """
        Create multiple matches at once.

        Args:
            matches: List of match creation data

        Returns:
            List of created matches
        """
        created = []
        for match_data in matches:
            try:
                match = await self.create_match(match_data)
                created.append(match)
            except MatchServiceError:
                # Skip invalid matches, could also collect errors
                continue

        return created

    # =========================================================================
    # Read Operations
    # =========================================================================

    async def get_match(self, match_id: str | ObjectId) -> Match:
        """
        Get a match by ID.

        Args:
            match_id: Match document ID

        Returns:
            Match document

        Raises:
            MatchNotFoundError: If match doesn't exist
        """
        match = await self._match_repo.get_by_id(match_id)

        if match is None:
            raise MatchNotFoundError(f"Match {match_id} not found")

        return match

    async def get_matches(
        self,
        filter_params: MatchFilter | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[Match], int]:
        """
        Get matches with optional filtering.

        Args:
            filter_params: Optional filter parameters
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            Tuple of (matches list, total count)
        """
        if filter_params is None:
            filter_params = MatchFilter()

        matches = await self._match_repo.find_with_filter(
            filter_params,
            skip=skip,
            limit=limit,
        )

        total = await self._match_repo.count_by_filter(filter_params)

        return matches, total

    async def get_upcoming_matches(
        self,
        days_ahead: int = 7,
        limit: int = 20,
    ) -> list[Match]:
        """
        Get upcoming matches within specified days.

        Args:
            days_ahead: Number of days to look ahead
            limit: Maximum number of matches to return

        Returns:
            List of upcoming matches
        """
        end_date = datetime.utcnow() + timedelta(days=days_ahead)

        filter_params = MatchFilter(
            status=[MatchStatus.PENDING, MatchStatus.POSTPONED],
            scheduled_from=datetime.utcnow(),
            scheduled_to=end_date,
        )

        matches, _ = await self.get_matches(filter_params, limit=limit)
        return matches

    async def get_predictable_matches(self, limit: int = 20) -> list[Match]:
        """
        Get matches that are open for predictions.

        Args:
            limit: Maximum number of matches to return

        Returns:
            List of predictable matches
        """
        return await self._match_repo.find_predictable(limit=limit)

    async def get_matches_with_predictions(
        self,
        status: MatchStatus | None = None,
        limit: int = 20,
    ) -> list[MatchWithPredictionCount]:
        """
        Get matches with prediction statistics.

        Args:
            status: Optional status filter
            limit: Maximum number of matches to return

        Returns:
            List of matches with prediction counts
        """
        return await self._match_repo.get_with_prediction_counts(
            status=status,
            limit=limit,
        )

    async def search_by_team(
        self,
        team_name: str,
        limit: int = 20,
    ) -> list[Match]:
        """
        Search matches by team name.

        Args:
            team_name: Team name to search for
            limit: Maximum number of matches to return

        Returns:
            List of matches involving the team
        """
        return await self._match_repo.find_by_teams(team_name, limit=limit)

    # =========================================================================
    # Update Operations
    # =========================================================================

    async def update_match(
        self,
        match_id: str | ObjectId,
        data: MatchUpdate,
    ) -> Match:
        """
        Update match details.

        Args:
            match_id: Match document ID
            data: Fields to update

        Returns:
            Updated match

        Raises:
            MatchNotFoundError: If match doesn't exist
            InvalidMatchStateError: If match cannot be updated
        """
        match = await self.get_match(match_id)

        # Can't update finished or cancelled matches
        if match.status in (MatchStatus.FINISHED, MatchStatus.CANCELLED):
            raise InvalidMatchStateError(f"Cannot update match in {match.status} state")

        # Validate new scheduled time if provided
        if data.scheduled_at and data.scheduled_at <= datetime.utcnow():
            raise MatchServiceError("Match must be scheduled in the future")

        updated = await self._match_repo.update_by_id(match_id, data)

        if updated is None:
            raise MatchNotFoundError(f"Match {match_id} not found")

        return updated

    async def reschedule_match(
        self,
        match_id: str | ObjectId,
        new_scheduled_at: datetime,
    ) -> Match:
        """
        Reschedule a match to a new time.

        Args:
            match_id: Match document ID
            new_scheduled_at: New scheduled time

        Returns:
            Updated match

        Raises:
            MatchNotFoundError: If match doesn't exist
            MatchServiceError: If validation fails
        """
        if new_scheduled_at <= datetime.utcnow():
            raise MatchServiceError("New schedule must be in the future")

        match = await self.get_match(match_id)

        if match.status == MatchStatus.FINISHED:
            raise InvalidMatchStateError("Cannot reschedule a finished match")

        if match.status == MatchStatus.LIVE:
            raise InvalidMatchStateError("Cannot reschedule a live match")

        update_data = MatchUpdate(
            scheduled_at=new_scheduled_at,
            status=MatchStatus.PENDING,
            predictions_locked=False,  # Reopen predictions
        )

        return await self.update_match(match_id, update_data)

    # =========================================================================
    # Status Transitions
    # =========================================================================

    async def start_match(self, match_id: str | ObjectId) -> Match:
        """
        Mark a match as started (live).

        This also locks predictions for the match.

        Args:
            match_id: Match document ID

        Returns:
            Updated match

        Raises:
            MatchNotFoundError: If match doesn't exist
            InvalidMatchStateError: If match cannot be started
        """
        match = await self.get_match(match_id)

        if match.status not in (MatchStatus.PENDING, MatchStatus.POSTPONED):
            raise InvalidMatchStateError(f"Cannot start match in {match.status} state")

        result = await self._match_repo.start_match(match_id)

        if result is None:
            raise MatchNotFoundError(f"Match {match_id} not found")

        return result

    async def finish_match(
        self,
        match_id: str | ObjectId,
        result: MatchResult,
        score_predictions: bool = True,
    ) -> tuple[Match, int]:
        """
        Finish a match and set the final result.

        Optionally scores all predictions for this match.

        Args:
            match_id: Match document ID
            result: Final match result with scores
            score_predictions: Whether to score predictions automatically

        Returns:
            Tuple of (updated match, number of predictions scored)

        Raises:
            MatchNotFoundError: If match doesn't exist
            InvalidMatchStateError: If match cannot be finished
        """
        match = await self.get_match(match_id)

        if match.status == MatchStatus.FINISHED:
            raise InvalidMatchStateError("Match is already finished")

        if match.status == MatchStatus.CANCELLED:
            raise InvalidMatchStateError("Cannot finish a cancelled match")

        # Set the result
        updated_match = await self._match_repo.set_result(match_id, result)

        if updated_match is None:
            raise MatchNotFoundError(f"Match {match_id} not found")

        # Score predictions if requested
        scored_count = 0
        if score_predictions:
            scored_count = await self._score_predictions(
                ObjectId(match_id) if isinstance(match_id, str) else match_id,
                result.home_score,
                result.away_score,
            )

        return updated_match, scored_count

    async def cancel_match(
        self,
        match_id: str | ObjectId,
        reason: str | None = None,
    ) -> Match:
        """
        Cancel a match.

        Args:
            match_id: Match document ID
            reason: Optional cancellation reason

        Returns:
            Updated match

        Raises:
            MatchNotFoundError: If match doesn't exist
            InvalidMatchStateError: If match cannot be cancelled
        """
        match = await self.get_match(match_id)

        if match.status == MatchStatus.FINISHED:
            raise InvalidMatchStateError("Cannot cancel a finished match")

        result = await self._match_repo.cancel_match(match_id, reason)

        if result is None:
            raise MatchNotFoundError(f"Match {match_id} not found")

        return result

    async def postpone_match(
        self,
        match_id: str | ObjectId,
        new_scheduled_at: datetime | None = None,
    ) -> Match:
        """
        Postpone a match.

        Args:
            match_id: Match document ID
            new_scheduled_at: Optional new scheduled time

        Returns:
            Updated match

        Raises:
            MatchNotFoundError: If match doesn't exist
            InvalidMatchStateError: If match cannot be postponed
        """
        match = await self.get_match(match_id)

        if match.status in (MatchStatus.FINISHED, MatchStatus.CANCELLED):
            raise InvalidMatchStateError(f"Cannot postpone match in {match.status} state")

        result = await self._match_repo.postpone_match(match_id, new_scheduled_at)

        if result is None:
            raise MatchNotFoundError(f"Match {match_id} not found")

        return result

    # =========================================================================
    # Prediction Lock Management
    # =========================================================================

    async def lock_predictions(self, match_id: str | ObjectId) -> bool:
        """
        Lock predictions for a match.

        Args:
            match_id: Match document ID

        Returns:
            True if predictions were locked
        """
        return await self._match_repo.lock_predictions(match_id)

    async def unlock_predictions(self, match_id: str | ObjectId) -> bool:
        """
        Unlock predictions for a match.

        Only works for pending/postponed matches.

        Args:
            match_id: Match document ID

        Returns:
            True if predictions were unlocked

        Raises:
            InvalidMatchStateError: If match is not in valid state
        """
        match = await self.get_match(match_id)

        if match.status not in (MatchStatus.PENDING, MatchStatus.POSTPONED):
            raise InvalidMatchStateError(
                f"Cannot unlock predictions for match in {match.status} state"
            )

        return await self._match_repo.unlock_predictions(match_id)

    async def auto_lock_starting_matches(
        self,
        minutes_before: int = 30,
    ) -> int:
        """
        Automatically lock predictions for matches starting soon.

        This should be called periodically (e.g., via a cron job).

        Args:
            minutes_before: Minutes before match start to lock

        Returns:
            Number of matches locked
        """
        return await self._match_repo.lock_all_starting_soon(minutes_before)

    # =========================================================================
    # Statistics
    # =========================================================================

    async def get_match_stats(self, match_id: str | ObjectId) -> dict[str, Any]:
        """
        Get statistics for a match.

        Args:
            match_id: Match document ID

        Returns:
            Dictionary with match statistics
        """
        match = await self.get_match(match_id)
        object_id = ObjectId(match_id) if isinstance(match_id, str) else match_id

        prediction_summary = await self._prediction_repo.get_match_prediction_summary(object_id)

        return {
            "match_id": str(match.id),
            "home_team": match.home_team,
            "away_team": match.away_team,
            "status": match.status,
            "scheduled_at": match.scheduled_at,
            "result": {
                "home_score": match.home_score,
                "away_score": match.away_score,
            }
            if match.is_completed
            else None,
            "predictions": prediction_summary,
        }

    async def get_league_stats(
        self,
        league: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get statistics grouped by league.

        Args:
            league: Optional league to filter by

        Returns:
            List of league statistics
        """
        return await self._match_repo.get_stats_by_league(league)

    # =========================================================================
    # Private Methods
    # =========================================================================

    async def _score_predictions(
        self,
        match_id: ObjectId,
        home_score: int,
        away_score: int,
    ) -> int:
        """
        Score all predictions for a match.

        Args:
            match_id: Match ObjectId
            home_score: Actual home score
            away_score: Actual away score

        Returns:
            Number of predictions scored
        """
        return await self._prediction_repo.score_predictions_for_match(
            match_id,
            home_score,
            away_score,
        )
