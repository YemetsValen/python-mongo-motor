"""
Match model for sports matches.

Represents a match between two teams with status tracking,
scheduling, and result management.
"""

from datetime import datetime
from enum import Enum
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from src.models.base import MongoBaseModel
from src.validators.custom_types import PyObjectId


class MatchStatus(str, Enum):
    """Possible states of a match."""

    PENDING = "pending"  # Match scheduled but not started
    LIVE = "live"  # Match currently in progress
    FINISHED = "finished"  # Match completed with final score
    CANCELLED = "cancelled"  # Match was cancelled
    POSTPONED = "postponed"  # Match postponed to later date


class MatchOutcome(str, Enum):
    """Possible outcomes of a finished match."""

    HOME_WIN = "home_win"
    AWAY_WIN = "away_win"
    DRAW = "draw"


class Sport(str, Enum):
    """Supported sports types."""

    FOOTBALL = "football"
    HOCKEY = "hockey"
    BASKETBALL = "basketball"
    TENNIS = "tennis"


# Type aliases for clarity
TeamName = Annotated[str, Field(min_length=1, max_length=100)]
Score = Annotated[int, Field(ge=0, le=99)]


class MatchBase(BaseModel):
    """Base match fields for creation and updates."""

    home_team: TeamName = Field(
        ...,
        description="Name of the home team",
        examples=["Manchester United", "Real Madrid"],
    )
    away_team: TeamName = Field(
        ...,
        description="Name of the away team",
        examples=["Liverpool", "Barcelona"],
    )
    scheduled_at: datetime = Field(
        ...,
        description="Scheduled start time of the match (UTC)",
    )
    sport: Sport = Field(
        default=Sport.FOOTBALL,
        description="Type of sport",
    )
    league: str | None = Field(
        default=None,
        max_length=100,
        description="League or competition name",
        examples=["Premier League", "La Liga", "Champions League"],
    )
    season: str | None = Field(
        default=None,
        max_length=20,
        description="Season identifier",
        examples=["2023-24", "2024"],
    )

    @field_validator("home_team", "away_team")
    @classmethod
    def normalize_team_name(cls, v: str) -> str:
        """Normalize team name: strip whitespace, title case."""
        return v.strip()

    @model_validator(mode="after")
    def teams_must_be_different(self) -> Self:
        """Ensure home and away teams are different."""
        if self.home_team.lower() == self.away_team.lower():
            raise ValueError("Home and away teams must be different")
        return self


class Match(MongoBaseModel, MatchBase):
    """
    Complete match model with status and results.

    Includes all fields stored in MongoDB and computed properties.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        use_enum_values=True,
    )

    # Status tracking
    status: MatchStatus = Field(
        default=MatchStatus.PENDING,
        description="Current status of the match",
    )

    # Results (only set when match is finished)
    home_score: Score | None = Field(
        default=None,
        description="Final score for home team",
    )
    away_score: Score | None = Field(
        default=None,
        description="Final score for away team",
    )

    # Timestamps
    started_at: datetime | None = Field(
        default=None,
        description="Actual start time of the match",
    )
    finished_at: datetime | None = Field(
        default=None,
        description="Time when match was completed",
    )
    cancelled_at: datetime | None = Field(
        default=None,
        description="Time when match was cancelled",
    )

    # Metadata
    predictions_locked: bool = Field(
        default=False,
        description="Whether predictions are locked for this match",
    )
    total_predictions: int = Field(
        default=0,
        ge=0,
        description="Number of predictions made for this match",
    )

    @property
    def outcome(self) -> MatchOutcome | None:
        """
        Get the match outcome based on final scores.

        Returns None if match is not finished or scores not set.
        """
        if self.home_score is None or self.away_score is None:
            return None

        if self.home_score > self.away_score:
            return MatchOutcome.HOME_WIN
        elif self.away_score > self.home_score:
            return MatchOutcome.AWAY_WIN
        else:
            return MatchOutcome.DRAW

    @property
    def goal_difference(self) -> int | None:
        """Get the goal difference (home - away)."""
        if self.home_score is None or self.away_score is None:
            return None
        return self.home_score - self.away_score

    @property
    def total_goals(self) -> int | None:
        """Get total goals scored in the match."""
        if self.home_score is None or self.away_score is None:
            return None
        return self.home_score + self.away_score

    @property
    def is_completed(self) -> bool:
        """Check if match has a final result."""
        return self.status == MatchStatus.FINISHED

    @property
    def is_predictable(self) -> bool:
        """Check if predictions can still be made."""
        if self.predictions_locked:
            return False
        if self.status not in (MatchStatus.PENDING, MatchStatus.POSTPONED):
            return False
        return True

    @property
    def display_score(self) -> str:
        """Get formatted score string."""
        if self.home_score is None or self.away_score is None:
            return "- : -"
        return f"{self.home_score} : {self.away_score}"

    @model_validator(mode="after")
    def validate_status_consistency(self) -> Self:
        """Ensure status and related fields are consistent."""
        if self.status == MatchStatus.FINISHED:
            if self.home_score is None or self.away_score is None:
                raise ValueError("Finished match must have scores")
            if self.finished_at is None:
                # Auto-set finished_at if not provided
                object.__setattr__(self, "finished_at", datetime.utcnow())

        if self.status == MatchStatus.CANCELLED:
            if self.cancelled_at is None:
                object.__setattr__(self, "cancelled_at", datetime.utcnow())

        if self.status == MatchStatus.LIVE:
            if self.started_at is None:
                object.__setattr__(self, "started_at", datetime.utcnow())
            # Lock predictions when match starts
            object.__setattr__(self, "predictions_locked", True)

        return self


class MatchCreate(MatchBase):
    """Schema for creating a new match."""

    pass


class MatchUpdate(BaseModel):
    """Schema for updating match fields."""

    model_config = ConfigDict(use_enum_values=True)

    home_team: TeamName | None = None
    away_team: TeamName | None = None
    scheduled_at: datetime | None = None
    sport: Sport | None = None
    league: str | None = None
    season: str | None = None
    status: MatchStatus | None = None
    home_score: Score | None = None
    away_score: Score | None = None
    predictions_locked: bool | None = None

    @model_validator(mode="after")
    def validate_teams_if_both_provided(self) -> Self:
        """If both teams are updated, ensure they're different."""
        if (
            self.home_team is not None
            and self.away_team is not None
            and self.home_team.lower() == self.away_team.lower()
        ):
            raise ValueError("Home and away teams must be different")
        return self


class MatchResult(BaseModel):
    """Schema for setting match result."""

    home_score: Score = Field(..., description="Final home team score")
    away_score: Score = Field(..., description="Final away team score")
    finished_at: datetime | None = Field(
        default=None,
        description="Time when match finished (defaults to now)",
    )


class MatchFilter(BaseModel):
    """Filter options for querying matches."""

    status: MatchStatus | list[MatchStatus] | None = None
    sport: Sport | None = None
    league: str | None = None
    season: str | None = None
    team: str | None = Field(
        default=None,
        description="Filter by team name (home or away)",
    )
    scheduled_from: datetime | None = Field(
        default=None,
        description="Match scheduled on or after this time",
    )
    scheduled_to: datetime | None = Field(
        default=None,
        description="Match scheduled on or before this time",
    )
    is_predictable: bool | None = Field(
        default=None,
        description="Filter by whether predictions are open",
    )

    def to_query(self) -> dict:
        """Convert filter to MongoDB query dict."""
        query: dict = {}

        if self.status is not None:
            if isinstance(self.status, list):
                query["status"] = {"$in": [s.value for s in self.status]}
            else:
                query["status"] = self.status.value

        if self.sport is not None:
            query["sport"] = self.sport.value

        if self.league is not None:
            query["league"] = {"$regex": self.league, "$options": "i"}

        if self.season is not None:
            query["season"] = self.season

        if self.team is not None:
            query["$or"] = [
                {"home_team": {"$regex": self.team, "$options": "i"}},
                {"away_team": {"$regex": self.team, "$options": "i"}},
            ]

        if self.scheduled_from is not None or self.scheduled_to is not None:
            query["scheduled_at"] = {}
            if self.scheduled_from is not None:
                query["scheduled_at"]["$gte"] = self.scheduled_from
            if self.scheduled_to is not None:
                query["scheduled_at"]["$lte"] = self.scheduled_to

        if self.is_predictable is not None:
            if self.is_predictable:
                query["predictions_locked"] = False
                query["status"] = {"$in": ["pending", "postponed"]}
            else:
                query["$or"] = [
                    {"predictions_locked": True},
                    {"status": {"$nin": ["pending", "postponed"]}},
                ]

        return query


class MatchWithPredictionCount(Match):
    """Match model enriched with prediction statistics."""

    prediction_count: int = Field(
        default=0,
        ge=0,
        description="Number of predictions for this match",
    )
    home_win_predictions: int = Field(
        default=0,
        ge=0,
        description="Predictions for home win",
    )
    away_win_predictions: int = Field(
        default=0,
        ge=0,
        description="Predictions for away win",
    )
    draw_predictions: int = Field(
        default=0,
        ge=0,
        description="Predictions for draw",
    )
