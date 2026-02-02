"""
Prediction model for match predictions.

Handles user predictions on match outcomes with scoring logic.
"""

from datetime import datetime
from enum import IntEnum
from typing import Annotated, Any, Self

from bson import ObjectId
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from src.validators.custom_types import PyObjectId


class PredictionPoints(IntEnum):
    """Points awarded for different prediction outcomes."""

    EXACT_SCORE = 3  # Guessed exact score
    CORRECT_DIFFERENCE = 2  # Correct outcome + goal difference
    CORRECT_OUTCOME = 1  # Only correct outcome (win/draw/loss)
    INCORRECT = 0  # Wrong prediction


class PredictionOutcome(str):
    """Prediction outcome categories."""

    HOME_WIN = "home_win"
    AWAY_WIN = "away_win"
    DRAW = "draw"


class PredictionBase(BaseModel):
    """Base prediction fields shared across create/update operations."""

    predicted_home_score: Annotated[
        int,
        Field(ge=0, le=99, description="Predicted goals for home team"),
    ]
    predicted_away_score: Annotated[
        int,
        Field(ge=0, le=99, description="Predicted goals for away team"),
    ]

    @field_validator("predicted_home_score", "predicted_away_score")
    @classmethod
    def validate_score(cls, v: int) -> int:
        """Validate score is within reasonable range."""
        if v < 0:
            raise ValueError("Score cannot be negative")
        if v > 99:
            raise ValueError("Score cannot exceed 99")
        return v


class PredictionCreate(PredictionBase):
    """Schema for creating a new prediction."""

    user_id: PyObjectId = Field(..., description="User making the prediction")
    match_id: PyObjectId = Field(..., description="Match being predicted")


class PredictionUpdate(BaseModel):
    """Schema for updating a prediction (before match starts)."""

    predicted_home_score: Annotated[
        int | None,
        Field(ge=0, le=99, description="Updated home score prediction"),
    ] = None
    predicted_away_score: Annotated[
        int | None,
        Field(ge=0, le=99, description="Updated away score prediction"),
    ] = None


class Prediction(PredictionBase):
    """
    Full prediction document model.

    Represents a user's prediction for a specific match outcome.
    One user can have only one prediction per match.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str, datetime: lambda v: v.isoformat()},
        json_schema_extra={
            "example": {
                "_id": "507f1f77bcf86cd799439011",
                "user_id": "507f1f77bcf86cd799439012",
                "match_id": "507f1f77bcf86cd799439013",
                "predicted_home_score": 2,
                "predicted_away_score": 1,
                "is_scored": False,
                "points": None,
                "created_at": "2024-03-01T10:00:00Z",
            }
        },
    )

    id: PyObjectId = Field(default_factory=ObjectId, alias="_id")
    user_id: PyObjectId = Field(..., description="Reference to user document")
    match_id: PyObjectId = Field(..., description="Reference to match document")

    # Scoring status
    is_scored: bool = Field(
        default=False,
        description="Whether this prediction has been scored",
    )
    points: int | None = Field(
        default=None,
        description="Points awarded (null if not yet scored)",
    )
    points_breakdown: str | None = Field(
        default=None,
        description="Explanation of how points were calculated",
    )

    # Actual match result (populated when scored)
    actual_home_score: int | None = Field(
        default=None,
        description="Actual home team score (set when match finishes)",
    )
    actual_away_score: int | None = Field(
        default=None,
        description="Actual away team score (set when match finishes)",
    )

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime | None = Field(default=None)
    scored_at: datetime | None = Field(default=None)

    @computed_field
    @property
    def predicted_outcome(self) -> str:
        """Get the predicted outcome (home_win/away_win/draw)."""
        if self.predicted_home_score > self.predicted_away_score:
            return PredictionOutcome.HOME_WIN
        elif self.predicted_home_score < self.predicted_away_score:
            return PredictionOutcome.AWAY_WIN
        else:
            return PredictionOutcome.DRAW

    @computed_field
    @property
    def predicted_goal_difference(self) -> int:
        """Get the predicted goal difference (home - away)."""
        return self.predicted_home_score - self.predicted_away_score

    def calculate_points(
        self,
        actual_home: int,
        actual_away: int,
    ) -> tuple[int, str]:
        """
        Calculate points based on actual match result.

        Returns:
            Tuple of (points, breakdown explanation)
        """
        # Determine actual outcome
        if actual_home > actual_away:
            actual_outcome = PredictionOutcome.HOME_WIN
        elif actual_home < actual_away:
            actual_outcome = PredictionOutcome.AWAY_WIN
        else:
            actual_outcome = PredictionOutcome.DRAW

        actual_diff = actual_home - actual_away

        # Exact score match
        if self.predicted_home_score == actual_home and self.predicted_away_score == actual_away:
            return (
                PredictionPoints.EXACT_SCORE,
                f"Exact score! Predicted {self.predicted_home_score}-{self.predicted_away_score}, "
                f"actual {actual_home}-{actual_away}",
            )

        # Correct outcome and goal difference
        if (
            self.predicted_outcome == actual_outcome
            and self.predicted_goal_difference == actual_diff
        ):
            return (
                PredictionPoints.CORRECT_DIFFERENCE,
                f"Correct outcome and goal difference! "
                f"Predicted {self.predicted_home_score}-{self.predicted_away_score} "
                f"(diff: {self.predicted_goal_difference}), "
                f"actual {actual_home}-{actual_away} (diff: {actual_diff})",
            )

        # Only correct outcome
        if self.predicted_outcome == actual_outcome:
            return (
                PredictionPoints.CORRECT_OUTCOME,
                f"Correct outcome ({actual_outcome})! "
                f"Predicted {self.predicted_home_score}-{self.predicted_away_score}, "
                f"actual {actual_home}-{actual_away}",
            )

        # Incorrect
        return (
            PredictionPoints.INCORRECT,
            f"Incorrect. Predicted {self.predicted_home_score}-{self.predicted_away_score} "
            f"({self.predicted_outcome}), actual {actual_home}-{actual_away} ({actual_outcome})",
        )

    def score_prediction(
        self,
        actual_home: int,
        actual_away: int,
    ) -> Self:
        """
        Score this prediction and return updated instance.

        Args:
            actual_home: Actual home team score
            actual_away: Actual away team score

        Returns:
            Updated prediction with points calculated
        """
        points, breakdown = self.calculate_points(actual_home, actual_away)

        return self.model_copy(
            update={
                "is_scored": True,
                "points": points,
                "points_breakdown": breakdown,
                "actual_home_score": actual_home,
                "actual_away_score": actual_away,
                "scored_at": datetime.utcnow(),
            }
        )

    def to_document(self) -> dict[str, Any]:
        """Convert model to MongoDB document."""
        doc = self.model_dump(by_alias=True, exclude_none=False)
        # Ensure ObjectIds are properly typed
        doc["_id"] = ObjectId(doc["_id"]) if isinstance(doc["_id"], str) else doc["_id"]
        doc["user_id"] = (
            ObjectId(doc["user_id"]) if isinstance(doc["user_id"], str) else doc["user_id"]
        )
        doc["match_id"] = (
            ObjectId(doc["match_id"]) if isinstance(doc["match_id"], str) else doc["match_id"]
        )
        return doc

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> Self:
        """Create model instance from MongoDB document."""
        return cls.model_validate(doc)


class PredictionWithDetails(Prediction):
    """
    Prediction with embedded match and user details.

    Used for displaying predictions with full context.
    """

    # Embedded user info (from aggregation)
    user_username: str | None = Field(default=None, description="User's username")

    # Embedded match info (from aggregation)
    match_home_team: str | None = Field(default=None, description="Home team name")
    match_away_team: str | None = Field(default=None, description="Away team name")
    match_scheduled_at: datetime | None = Field(default=None, description="Match scheduled time")
    match_status: str | None = Field(default=None, description="Current match status")


class UserPredictionStats(BaseModel):
    """Statistics for a user's predictions."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": "507f1f77bcf86cd799439011",
                "total_predictions": 50,
                "scored_predictions": 45,
                "total_points": 67,
                "exact_scores": 5,
                "correct_differences": 12,
                "correct_outcomes": 18,
                "incorrect": 10,
                "accuracy_percent": 77.78,
                "avg_points_per_prediction": 1.49,
            }
        },
    )

    user_id: PyObjectId
    total_predictions: int = Field(ge=0)
    scored_predictions: int = Field(ge=0)
    total_points: int = Field(ge=0)

    # Breakdown by result type
    exact_scores: int = Field(ge=0, description="Count of exact score predictions")
    correct_differences: int = Field(ge=0, description="Count of correct outcome + difference")
    correct_outcomes: int = Field(ge=0, description="Count of correct outcome only predictions")
    incorrect: int = Field(ge=0, description="Count of incorrect predictions")

    @computed_field
    @property
    def accuracy_percent(self) -> float:
        """Percentage of predictions with at least correct outcome."""
        if self.scored_predictions == 0:
            return 0.0
        correct = self.exact_scores + self.correct_differences + self.correct_outcomes
        return round((correct / self.scored_predictions) * 100, 2)

    @computed_field
    @property
    def avg_points_per_prediction(self) -> float:
        """Average points per scored prediction."""
        if self.scored_predictions == 0:
            return 0.0
        return round(self.total_points / self.scored_predictions, 2)

    @computed_field
    @property
    def exact_score_rate(self) -> float:
        """Percentage of exact score predictions."""
        if self.scored_predictions == 0:
            return 0.0
        return round((self.exact_scores / self.scored_predictions) * 100, 2)
