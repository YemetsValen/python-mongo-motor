"""
Pydantic models for the Match Predictions System.

This module exports all domain models used throughout the application:
- User: User account model
- Match: Sports match model
- Prediction: User prediction model
- Analytics models: DTOs for analytics results
"""

from src.models.analytics import (
    AccuracyReport,
    LeaderboardEntry,
    PredictionAnalytics,
    UserStats,
)
from src.models.base import BaseDocument, TimestampMixin
from src.models.match import Match, MatchCreate, MatchStatus, MatchUpdate
from src.models.prediction import Prediction, PredictionCreate, PredictionResult
from src.models.user import User, UserCreate, UserInDB, UserUpdate

__all__ = [
    # Base
    "BaseDocument",
    "TimestampMixin",
    # User
    "User",
    "UserCreate",
    "UserUpdate",
    "UserInDB",
    # Match
    "Match",
    "MatchCreate",
    "MatchUpdate",
    "MatchStatus",
    # Prediction
    "Prediction",
    "PredictionCreate",
    "PredictionResult",
    # Analytics
    "UserStats",
    "LeaderboardEntry",
    "AccuracyReport",
    "PredictionAnalytics",
]
