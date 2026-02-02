"""
Analytics Data Transfer Objects and aggregation result models.

These models represent the results of analytics calculations,
leaderboard entries, and statistical aggregations.
"""

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, computed_field

from src.validators.custom_types import PyObjectId


class TimePeriod(StrEnum):
    """Time period for analytics aggregation."""

    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    SEASON = "season"
    YEAR = "year"
    ALL_TIME = "all_time"


class PredictionOutcome(StrEnum):
    """Possible outcomes of a prediction evaluation."""

    EXACT_SCORE = "exact_score"  # 3 points - guessed exact score
    CORRECT_DIFF = "correct_diff"  # 2 points - correct outcome + goal difference
    CORRECT_OUTCOME = "correct_outcome"  # 1 point - only correct outcome
    INCORRECT = "incorrect"  # 0 points - wrong prediction


# =============================================================================
# User Statistics Models
# =============================================================================


class UserPredictionStats(BaseModel):
    """
    Aggregated prediction statistics for a user.

    This model represents the result of analytics calculations
    for a single user's prediction history.
    """

    user_id: PyObjectId = Field(..., description="User identifier")
    username: str = Field(..., description="Username for display")

    # Prediction counts
    total_predictions: int = Field(default=0, ge=0, description="Total predictions made")
    scored_predictions: int = Field(
        default=0, ge=0, description="Predictions that have been scored"
    )
    pending_predictions: int = Field(
        default=0, ge=0, description="Predictions awaiting match results"
    )

    # Outcome breakdown
    exact_scores: int = Field(default=0, ge=0, description="Exact score predictions")
    correct_diffs: int = Field(default=0, ge=0, description="Correct difference predictions")
    correct_outcomes: int = Field(default=0, ge=0, description="Correct outcome predictions")
    incorrect: int = Field(default=0, ge=0, description="Incorrect predictions")

    # Points
    total_points: int = Field(default=0, ge=0, description="Total points earned")

    # Streaks
    current_streak: int = Field(default=0, ge=0, description="Current correct prediction streak")
    best_streak: int = Field(default=0, ge=0, description="Best correct prediction streak")
    worst_streak: int = Field(default=0, ge=0, description="Worst incorrect prediction streak")

    # Time-based stats
    first_prediction_at: datetime | None = Field(
        default=None, description="Date of first prediction"
    )
    last_prediction_at: datetime | None = Field(
        default=None, description="Date of most recent prediction"
    )
    last_updated: datetime = Field(
        default_factory=datetime.utcnow, description="When stats were last calculated"
    )

    @computed_field
    @property
    def accuracy_percent(self) -> float:
        """Calculate accuracy percentage (correct outcomes / scored predictions)."""
        if self.scored_predictions == 0:
            return 0.0
        correct = self.exact_scores + self.correct_diffs + self.correct_outcomes
        return round((correct / self.scored_predictions) * 100, 2)

    @computed_field
    @property
    def exact_score_percent(self) -> float:
        """Percentage of exact score predictions."""
        if self.scored_predictions == 0:
            return 0.0
        return round((self.exact_scores / self.scored_predictions) * 100, 2)

    @computed_field
    @property
    def avg_points_per_prediction(self) -> float:
        """Average points per scored prediction."""
        if self.scored_predictions == 0:
            return 0.0
        return round(self.total_points / self.scored_predictions, 2)

    @computed_field
    @property
    def points_efficiency(self) -> float:
        """
        Points efficiency: actual points / maximum possible points.

        Maximum possible = scored_predictions * 3 (if all were exact scores)
        """
        max_points = self.scored_predictions * 3
        if max_points == 0:
            return 0.0
        return round((self.total_points / max_points) * 100, 2)

    class Config:
        populate_by_name = True


class UserStatsDocument(UserPredictionStats):
    """
    MongoDB document model for persisted user statistics.

    Extends UserPredictionStats with document-level fields for storage.
    """

    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    schema_version: int = Field(default=1, description="Document schema version")

    class Config:
        populate_by_name = True


# =============================================================================
# Leaderboard Models
# =============================================================================


class LeaderboardEntry(BaseModel):
    """Single entry in a leaderboard."""

    rank: int = Field(..., ge=1, description="Position in leaderboard")
    user_id: PyObjectId = Field(..., description="User identifier")
    username: str = Field(..., description="Username for display")
    total_points: int = Field(default=0, ge=0, description="Total points")
    total_predictions: int = Field(default=0, ge=0, description="Total predictions")
    accuracy_percent: float = Field(default=0.0, ge=0, le=100, description="Accuracy %")
    exact_scores: int = Field(default=0, ge=0, description="Exact score count")

    # Movement indicators (compared to previous period)
    rank_change: int = Field(
        default=0, description="Rank change (+positive = improved, -negative = dropped)"
    )
    points_change: int = Field(default=0, description="Points change since last period")
    is_new: bool = Field(default=False, description="Is this user new to the leaderboard")


class LeaderboardType(StrEnum):
    """Types of leaderboards available."""

    POINTS = "points"  # Ranked by total points
    ACCURACY = "accuracy"  # Ranked by accuracy percentage
    EXACT_SCORES = "exact_scores"  # Ranked by exact score predictions
    STREAK = "streak"  # Ranked by current winning streak
    EFFICIENCY = "efficiency"  # Ranked by points efficiency


class Leaderboard(BaseModel):
    """Complete leaderboard with metadata."""

    type: LeaderboardType = Field(..., description="Type of leaderboard")
    period: TimePeriod = Field(default=TimePeriod.ALL_TIME, description="Time period")
    entries: list[LeaderboardEntry] = Field(default_factory=list, description="Leaderboard entries")
    total_participants: int = Field(default=0, ge=0, description="Total users in ranking")
    generated_at: datetime = Field(
        default_factory=datetime.utcnow, description="When leaderboard was generated"
    )
    period_start: datetime | None = Field(default=None, description="Period start date")
    period_end: datetime | None = Field(default=None, description="Period end date")

    @computed_field
    @property
    def top_score(self) -> int:
        """Get the top score in this leaderboard."""
        if not self.entries:
            return 0
        return self.entries[0].total_points


# =============================================================================
# Match Analytics Models
# =============================================================================


class MatchPredictionSummary(BaseModel):
    """Summary of all predictions for a single match."""

    match_id: PyObjectId = Field(..., description="Match identifier")
    home_team: str = Field(..., description="Home team name")
    away_team: str = Field(..., description="Away team name")

    # Prediction counts
    total_predictions: int = Field(default=0, ge=0)
    home_win_predictions: int = Field(default=0, ge=0)
    draw_predictions: int = Field(default=0, ge=0)
    away_win_predictions: int = Field(default=0, ge=0)

    # Most predicted scores
    most_predicted_score: str | None = Field(
        default=None, description="Most predicted score (e.g., '2-1')"
    )
    most_predicted_score_count: int = Field(default=0, ge=0)

    # Average predicted scores
    avg_predicted_home_goals: float = Field(default=0.0, ge=0)
    avg_predicted_away_goals: float = Field(default=0.0, ge=0)

    # Actual result (if match finished)
    actual_home_score: int | None = Field(default=None, ge=0)
    actual_away_score: int | None = Field(default=None, ge=0)

    @computed_field
    @property
    def home_win_percent(self) -> float:
        """Percentage predicting home win."""
        if self.total_predictions == 0:
            return 0.0
        return round((self.home_win_predictions / self.total_predictions) * 100, 2)

    @computed_field
    @property
    def draw_percent(self) -> float:
        """Percentage predicting draw."""
        if self.total_predictions == 0:
            return 0.0
        return round((self.draw_predictions / self.total_predictions) * 100, 2)

    @computed_field
    @property
    def away_win_percent(self) -> float:
        """Percentage predicting away win."""
        if self.total_predictions == 0:
            return 0.0
        return round((self.away_win_predictions / self.total_predictions) * 100, 2)


# =============================================================================
# Trend and Time-Series Models
# =============================================================================


class DailyStats(BaseModel):
    """Statistics for a single day."""

    date: datetime = Field(..., description="Date")
    predictions_made: int = Field(default=0, ge=0)
    matches_finished: int = Field(default=0, ge=0)
    points_earned: int = Field(default=0, ge=0)
    accuracy_percent: float = Field(default=0.0, ge=0, le=100)


class UserTrend(BaseModel):
    """User performance trend over time."""

    user_id: PyObjectId = Field(..., description="User identifier")
    period: TimePeriod = Field(..., description="Aggregation period")
    data_points: list[DailyStats] = Field(default_factory=list)

    @computed_field
    @property
    def total_points_in_period(self) -> int:
        """Sum of points in the period."""
        return sum(dp.points_earned for dp in self.data_points)

    @computed_field
    @property
    def avg_daily_accuracy(self) -> float:
        """Average daily accuracy."""
        accuracies = [dp.accuracy_percent for dp in self.data_points if dp.predictions_made > 0]
        if not accuracies:
            return 0.0
        return round(sum(accuracies) / len(accuracies), 2)

    @computed_field
    @property
    def trend_direction(self) -> str:
        """Determine if user is improving, declining, or stable."""
        if len(self.data_points) < 2:
            return "stable"

        recent = self.data_points[-3:] if len(self.data_points) >= 3 else self.data_points
        older = self.data_points[:3]

        recent_avg = sum(dp.accuracy_percent for dp in recent) / len(recent)
        older_avg = sum(dp.accuracy_percent for dp in older) / len(older)

        diff = recent_avg - older_avg
        if diff > 5:
            return "improving"
        elif diff < -5:
            return "declining"
        return "stable"


# =============================================================================
# System-Wide Analytics
# =============================================================================


class SystemStats(BaseModel):
    """System-wide statistics."""

    total_users: int = Field(default=0, ge=0)
    active_users: int = Field(default=0, ge=0, description="Users with predictions in last 30 days")
    total_matches: int = Field(default=0, ge=0)
    finished_matches: int = Field(default=0, ge=0)
    pending_matches: int = Field(default=0, ge=0)
    total_predictions: int = Field(default=0, ge=0)
    scored_predictions: int = Field(default=0, ge=0)
    avg_predictions_per_match: float = Field(default=0.0, ge=0)
    avg_predictions_per_user: float = Field(default=0.0, ge=0)
    global_accuracy_percent: float = Field(default=0.0, ge=0, le=100)
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class PredictionDistribution(BaseModel):
    """Distribution of prediction outcomes across the system."""

    period: TimePeriod = Field(default=TimePeriod.ALL_TIME)
    exact_scores_count: int = Field(default=0, ge=0)
    correct_diffs_count: int = Field(default=0, ge=0)
    correct_outcomes_count: int = Field(default=0, ge=0)
    incorrect_count: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)

    @computed_field
    @property
    def exact_scores_percent(self) -> float:
        if self.total == 0:
            return 0.0
        return round((self.exact_scores_count / self.total) * 100, 2)

    @computed_field
    @property
    def correct_diffs_percent(self) -> float:
        if self.total == 0:
            return 0.0
        return round((self.correct_diffs_count / self.total) * 100, 2)

    @computed_field
    @property
    def correct_outcomes_percent(self) -> float:
        if self.total == 0:
            return 0.0
        return round((self.correct_outcomes_count / self.total) * 100, 2)

    @computed_field
    @property
    def incorrect_percent(self) -> float:
        if self.total == 0:
            return 0.0
        return round((self.incorrect_count / self.total) * 100, 2)


# Type aliases for common analytics results
UserStatsDict = dict[str, UserPredictionStats]
LeaderboardDict = dict[LeaderboardType, Leaderboard]
