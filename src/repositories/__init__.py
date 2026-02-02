"""
Repository layer for data access.

Provides abstraction over MongoDB collections with async operations
using Motor driver. Each repository handles CRUD operations and
queries for its respective domain model.
"""

from src.repositories.base import BaseRepository
from src.repositories.match_repository import MatchRepository
from src.repositories.prediction_repository import PredictionRepository
from src.repositories.user_repository import UserRepository

__all__ = [
    "BaseRepository",
    "UserRepository",
    "MatchRepository",
    "PredictionRepository",
]
