"""
Pytest configuration and fixtures for testing.

Provides database fixtures, mock data factories, and test utilities
for testing the Match Predictions System.
"""

import asyncio
from datetime import datetime, timedelta
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from src.models.match import Match, MatchCreate, MatchStatus, Sport
from src.models.prediction import Prediction, PredictionCreate
from src.models.user import User, UserCreate
from src.repositories.match_repository import MatchRepository
from src.repositories.prediction_repository import PredictionRepository
from src.repositories.user_repository import UserRepository
from src.services.analytics_service import AnalyticsService
from src.services.match_service import MatchService
from src.services.prediction_service import PredictionService
from src.services.user_service import UserService

# =============================================================================
# Event Loop Configuration
# =============================================================================


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# Database Fixtures
# =============================================================================


@pytest_asyncio.fixture(scope="function")
async def mongo_client() -> AsyncGenerator[AsyncIOMotorClient, None]:
    """
    Create a MongoDB client for testing.

    Uses a test database that gets cleaned up after each test.
    """
    # Use environment variable or default test URI
    import os

    mongo_uri = os.getenv(
        "TEST_MONGO_URI", "mongodb://admin:secret@localhost:27017/?authSource=admin"
    )

    client = AsyncIOMotorClient(mongo_uri)

    try:
        # Verify connection
        await client.admin.command("ping")
        yield client
    finally:
        client.close()


@pytest_asyncio.fixture(scope="function")
async def test_db(mongo_client: AsyncIOMotorClient) -> AsyncGenerator[AsyncIOMotorDatabase, None]:
    """
    Create a test database that gets cleaned up after each test.
    """
    db_name = f"test_predictions_{ObjectId()}"
    db = mongo_client[db_name]

    yield db

    # Cleanup: drop the test database
    await mongo_client.drop_database(db_name)


@pytest_asyncio.fixture(scope="function")
async def mock_db() -> AsyncIOMotorDatabase:
    """
    Create a mock database for unit tests that don't need real MongoDB.
    """
    mock = MagicMock(spec=AsyncIOMotorDatabase)
    mock.__getitem__ = MagicMock(return_value=MagicMock())
    return mock


# =============================================================================
# Repository Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def user_repository(test_db: AsyncIOMotorDatabase) -> UserRepository:
    """Create a UserRepository instance with test database."""
    return UserRepository(test_db)


@pytest_asyncio.fixture
async def match_repository(test_db: AsyncIOMotorDatabase) -> MatchRepository:
    """Create a MatchRepository instance with test database."""
    return MatchRepository(test_db)


@pytest_asyncio.fixture
async def prediction_repository(test_db: AsyncIOMotorDatabase) -> PredictionRepository:
    """Create a PredictionRepository instance with test database."""
    return PredictionRepository(test_db)


# =============================================================================
# Service Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def user_service(test_db: AsyncIOMotorDatabase) -> UserService:
    """Create a UserService instance with test database."""
    return UserService(test_db)


@pytest_asyncio.fixture
async def match_service(test_db: AsyncIOMotorDatabase) -> MatchService:
    """Create a MatchService instance with test database."""
    return MatchService(test_db)


@pytest_asyncio.fixture
async def prediction_service(test_db: AsyncIOMotorDatabase) -> PredictionService:
    """Create a PredictionService instance with test database."""
    return PredictionService(test_db)


@pytest_asyncio.fixture
async def analytics_service(test_db: AsyncIOMotorDatabase) -> AnalyticsService:
    """Create an AnalyticsService instance with test database."""
    return AnalyticsService(test_db)


# =============================================================================
# Factory Fixtures
# =============================================================================


class UserFactory:
    """Factory for creating test User objects."""

    _counter = 0

    @classmethod
    def create(
        cls,
        username: str | None = None,
        email: str | None = None,
        display_name: str | None = None,
        is_active: bool = True,
    ) -> User:
        """Create a User instance with default or provided values."""
        cls._counter += 1

        return User(
            id=ObjectId(),
            username=username or f"testuser_{cls._counter}",
            email=email or f"testuser_{cls._counter}@example.com",
            display_name=display_name,
            is_active=is_active,
            total_predictions=0,
            total_points=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

    @classmethod
    def create_data(
        cls,
        username: str | None = None,
        email: str | None = None,
        display_name: str | None = None,
    ) -> UserCreate:
        """Create UserCreate data for registration."""
        cls._counter += 1

        return UserCreate(
            username=username or f"testuser_{cls._counter}",
            email=email or f"testuser_{cls._counter}@example.com",
            display_name=display_name,
        )


class MatchFactory:
    """Factory for creating test Match objects."""

    _counter = 0

    @classmethod
    def create(
        cls,
        home_team: str | None = None,
        away_team: str | None = None,
        scheduled_at: datetime | None = None,
        status: MatchStatus = MatchStatus.PENDING,
        sport: Sport = Sport.FOOTBALL,
        league: str | None = None,
        home_score: int | None = None,
        away_score: int | None = None,
    ) -> Match:
        """Create a Match instance with default or provided values."""
        cls._counter += 1

        return Match(
            id=ObjectId(),
            home_team=home_team or f"Home Team {cls._counter}",
            away_team=away_team or f"Away Team {cls._counter}",
            scheduled_at=scheduled_at or (datetime.utcnow() + timedelta(days=1)),
            status=status,
            sport=sport,
            league=league or "Test League",
            season="2024-25",
            home_score=home_score,
            away_score=away_score,
            predictions_locked=status not in (MatchStatus.PENDING, MatchStatus.POSTPONED),
            total_predictions=0,
        )

    @classmethod
    def create_data(
        cls,
        home_team: str | None = None,
        away_team: str | None = None,
        scheduled_at: datetime | None = None,
        sport: Sport = Sport.FOOTBALL,
        league: str | None = None,
    ) -> MatchCreate:
        """Create MatchCreate data."""
        cls._counter += 1

        return MatchCreate(
            home_team=home_team or f"Home Team {cls._counter}",
            away_team=away_team or f"Away Team {cls._counter}",
            scheduled_at=scheduled_at or (datetime.utcnow() + timedelta(days=1)),
            sport=sport,
            league=league or "Test League",
            season="2024-25",
        )


class PredictionFactory:
    """Factory for creating test Prediction objects."""

    @classmethod
    def create(
        cls,
        user_id: ObjectId | None = None,
        match_id: ObjectId | None = None,
        predicted_home_score: int = 2,
        predicted_away_score: int = 1,
        is_scored: bool = False,
        points: int | None = None,
    ) -> Prediction:
        """Create a Prediction instance with default or provided values."""
        return Prediction(
            id=ObjectId(),
            user_id=user_id or ObjectId(),
            match_id=match_id or ObjectId(),
            predicted_home_score=predicted_home_score,
            predicted_away_score=predicted_away_score,
            is_scored=is_scored,
            points=points,
            created_at=datetime.utcnow(),
        )

    @classmethod
    def create_data(
        cls,
        user_id: ObjectId,
        match_id: ObjectId,
        predicted_home_score: int = 2,
        predicted_away_score: int = 1,
    ) -> PredictionCreate:
        """Create PredictionCreate data."""
        return PredictionCreate(
            user_id=user_id,
            match_id=match_id,
            predicted_home_score=predicted_home_score,
            predicted_away_score=predicted_away_score,
        )


@pytest.fixture
def user_factory() -> type[UserFactory]:
    """Provide UserFactory class."""
    UserFactory._counter = 0
    return UserFactory


@pytest.fixture
def match_factory() -> type[MatchFactory]:
    """Provide MatchFactory class."""
    MatchFactory._counter = 0
    return MatchFactory


@pytest.fixture
def prediction_factory() -> type[PredictionFactory]:
    """Provide PredictionFactory class."""
    return PredictionFactory


# =============================================================================
# Test Data Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def sample_user(user_service: UserService) -> User:
    """Create and return a sample user in the database."""
    return await user_service.register_user(
        username="sample_user",
        email="sample@example.com",
        display_name="Sample User",
    )


@pytest_asyncio.fixture
async def sample_match(match_service: MatchService) -> Match:
    """Create and return a sample match in the database."""
    data = MatchCreate(
        home_team="Manchester United",
        away_team="Liverpool",
        scheduled_at=datetime.utcnow() + timedelta(days=1),
        sport=Sport.FOOTBALL,
        league="Premier League",
        season="2024-25",
    )
    return await match_service.create_match(data)


@pytest_asyncio.fixture
async def sample_prediction(
    prediction_service: PredictionService,
    sample_user: User,
    sample_match: Match,
) -> Prediction:
    """Create and return a sample prediction in the database."""
    return await prediction_service.create_prediction(
        user_id=sample_user.id,
        match_id=sample_match.id,
        home_score=2,
        away_score=1,
    )


# =============================================================================
# Helper Fixtures
# =============================================================================


@pytest.fixture
def mock_datetime(monkeypatch):
    """
    Fixture to mock datetime.utcnow() for deterministic testing.

    Usage:
        def test_something(mock_datetime):
            fixed_time = datetime(2024, 1, 1, 12, 0, 0)
            mock_datetime(fixed_time)
            # datetime.utcnow() will now return fixed_time
    """

    def _mock_datetime(fixed_time: datetime):
        class MockDateTime:
            @classmethod
            def utcnow(cls):
                return fixed_time

            @classmethod
            def now(cls, tz=None):
                return fixed_time

        monkeypatch.setattr("datetime.datetime", MockDateTime)
        return MockDateTime

    return _mock_datetime


@pytest.fixture
def assert_raises_with_message():
    """
    Fixture for asserting exceptions with specific messages.

    Usage:
        def test_something(assert_raises_with_message):
            with assert_raises_with_message(ValueError, "expected message"):
                raise ValueError("expected message")
    """
    from contextlib import contextmanager

    @contextmanager
    def _assert_raises(exception_type: type, message_contains: str):
        with pytest.raises(exception_type) as exc_info:
            yield

        assert message_contains in str(exc_info.value), (
            f"Expected message to contain '{message_contains}', but got '{str(exc_info.value)}'"
        )

    return _assert_raises
