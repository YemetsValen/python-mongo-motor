"""
Tests for Pydantic models.

Tests validation, serialization, and business logic for all domain models.
"""

from datetime import datetime, timezone

import pytest
from bson import ObjectId

from src.models.match import Match, MatchCreate, MatchOutcome, MatchStatus, Sport
from src.models.prediction import Prediction, PredictionCreate, PredictionPoints
from src.models.user import User, UserCreate, UserResponse, UserUpdate
from src.validators.custom_types import PyObjectId, validate_username

# =============================================================================
# PyObjectId Tests
# =============================================================================


class TestPyObjectId:
    """Tests for PyObjectId custom type."""

    def test_valid_objectid_string(self):
        """Test validation of valid ObjectId string."""
        valid_id = "507f1f77bcf86cd799439011"
        result = PyObjectId.validate(valid_id)
        assert isinstance(result, ObjectId)
        assert str(result) == valid_id

    def test_valid_objectid_instance(self):
        """Test that ObjectId instances pass through."""
        oid = ObjectId()
        result = PyObjectId.validate(oid)
        assert result == oid

    def test_invalid_objectid_string(self):
        """Test rejection of invalid ObjectId string."""
        with pytest.raises(Exception):
            PyObjectId.validate("invalid-id")

    def test_empty_string(self):
        """Test rejection of empty string."""
        with pytest.raises(Exception):
            PyObjectId.validate("")

    def test_serialize(self):
        """Test ObjectId serialization to string."""
        oid = ObjectId()
        result = PyObjectId.serialize(oid)
        assert isinstance(result, str)
        assert result == str(oid)


# =============================================================================
# Username Validation Tests
# =============================================================================


class TestUsernameValidation:
    """Tests for username validation."""

    def test_valid_username(self):
        """Test valid usernames pass validation."""
        valid_usernames = ["john_doe", "user123", "Pro-Predictor", "abc"]
        for username in valid_usernames:
            result = validate_username(username)
            assert result == username

    def test_too_short(self):
        """Test rejection of usernames shorter than 3 characters."""
        with pytest.raises(ValueError, match="at least 3 characters"):
            validate_username("ab")

    def test_too_long(self):
        """Test rejection of usernames longer than 30 characters."""
        with pytest.raises(ValueError, match="cannot exceed 30"):
            validate_username("a" * 31)

    def test_starts_with_number(self):
        """Test rejection of usernames starting with a number."""
        with pytest.raises(ValueError, match="must start with a letter"):
            validate_username("123user")

    def test_invalid_characters(self):
        """Test rejection of usernames with invalid characters."""
        with pytest.raises(ValueError):
            validate_username("user@name")


# =============================================================================
# User Model Tests
# =============================================================================


class TestUserCreate:
    """Tests for UserCreate model."""

    def test_valid_user_create(self):
        """Test creation with valid data."""
        user = UserCreate(
            username="john_doe",
            email="john@example.com",
            display_name="John Doe",
        )
        assert user.username == "john_doe"
        assert user.email == "john@example.com"
        assert user.display_name == "John Doe"

    def test_email_normalization(self):
        """Test that email is normalized to lowercase."""
        user = UserCreate(
            username="john_doe",
            email="JOHN@EXAMPLE.COM",
        )
        assert user.email == "john@example.com"

    def test_invalid_email(self):
        """Test rejection of invalid email."""
        with pytest.raises(Exception):
            UserCreate(
                username="john_doe",
                email="invalid-email",
            )

    def test_invalid_username(self):
        """Test rejection of invalid username."""
        with pytest.raises(Exception):
            UserCreate(
                username="ab",  # too short
                email="john@example.com",
            )


class TestUser:
    """Tests for User model."""

    def test_user_creation(self):
        """Test User model creation."""
        user = User(
            username="john_doe",
            email="john@example.com",
        )
        assert user.id is not None
        assert isinstance(user.id, ObjectId)
        assert user.is_active is True
        assert user.total_predictions == 0
        assert user.total_points == 0

    def test_effective_display_name_with_display_name(self):
        """Test effective_display_name returns display_name when set."""
        user = User(
            username="john_doe",
            email="john@example.com",
            display_name="John Doe",
        )
        assert user.effective_display_name == "John Doe"

    def test_effective_display_name_fallback(self):
        """Test effective_display_name falls back to username."""
        user = User(
            username="john_doe",
            email="john@example.com",
        )
        assert user.effective_display_name == "john_doe"

    def test_average_points_zero_predictions(self):
        """Test average_points returns 0 when no predictions."""
        user = User(
            username="john_doe",
            email="john@example.com",
            total_predictions=0,
            total_points=0,
        )
        assert user.average_points == 0.0

    def test_average_points_with_predictions(self):
        """Test average_points calculation."""
        user = User(
            username="john_doe",
            email="john@example.com",
            total_predictions=10,
            total_points=15,
        )
        assert user.average_points == 1.5

    def test_from_create(self):
        """Test creating User from UserCreate."""
        create_data = UserCreate(
            username="john_doe",
            email="john@example.com",
            display_name="John Doe",
        )
        user = User.from_create(create_data)
        assert user.username == "john_doe"
        assert user.email == "john@example.com"
        assert user.display_name == "John Doe"


# =============================================================================
# Match Model Tests
# =============================================================================


class TestMatchCreate:
    """Tests for MatchCreate model."""

    def test_valid_match_create(self):
        """Test creation with valid data."""
        match = MatchCreate(
            home_team="Manchester United",
            away_team="Liverpool",
            scheduled_at=datetime.now(timezone.utc),
            sport=Sport.FOOTBALL,
            league="Premier League",
        )
        assert match.home_team == "Manchester United"
        assert match.away_team == "Liverpool"

    def test_same_teams_rejected(self):
        """Test that same home and away teams are rejected."""
        with pytest.raises(ValueError, match="must be different"):
            MatchCreate(
                home_team="Manchester United",
                away_team="Manchester United",
                scheduled_at=datetime.now(timezone.utc),
            )

    def test_case_insensitive_team_check(self):
        """Test that team comparison is case-insensitive."""
        with pytest.raises(ValueError, match="must be different"):
            MatchCreate(
                home_team="manchester united",
                away_team="MANCHESTER UNITED",
                scheduled_at=datetime.now(timezone.utc),
            )


class TestMatch:
    """Tests for Match model."""

    def test_match_creation(self):
        """Test Match model creation with defaults."""
        match = Match(
            home_team="Manchester United",
            away_team="Liverpool",
            scheduled_at=datetime.now(timezone.utc),
        )
        assert match.status == MatchStatus.PENDING
        assert match.home_score is None
        assert match.away_score is None
        assert match.predictions_locked is False

    def test_outcome_home_win(self):
        """Test outcome property for home win."""
        match = Match(
            home_team="Manchester United",
            away_team="Liverpool",
            scheduled_at=datetime.now(timezone.utc),
            home_score=2,
            away_score=1,
        )
        assert match.outcome == MatchOutcome.HOME_WIN

    def test_outcome_away_win(self):
        """Test outcome property for away win."""
        match = Match(
            home_team="Manchester United",
            away_team="Liverpool",
            scheduled_at=datetime.now(timezone.utc),
            home_score=1,
            away_score=3,
        )
        assert match.outcome == MatchOutcome.AWAY_WIN

    def test_outcome_draw(self):
        """Test outcome property for draw."""
        match = Match(
            home_team="Manchester United",
            away_team="Liverpool",
            scheduled_at=datetime.now(timezone.utc),
            home_score=2,
            away_score=2,
        )
        assert match.outcome == MatchOutcome.DRAW

    def test_outcome_no_score(self):
        """Test outcome is None when scores not set."""
        match = Match(
            home_team="Manchester United",
            away_team="Liverpool",
            scheduled_at=datetime.now(timezone.utc),
        )
        assert match.outcome is None

    def test_goal_difference(self):
        """Test goal difference calculation."""
        match = Match(
            home_team="Manchester United",
            away_team="Liverpool",
            scheduled_at=datetime.now(timezone.utc),
            home_score=3,
            away_score=1,
        )
        assert match.goal_difference == 2

    def test_total_goals(self):
        """Test total goals calculation."""
        match = Match(
            home_team="Manchester United",
            away_team="Liverpool",
            scheduled_at=datetime.now(timezone.utc),
            home_score=3,
            away_score=2,
        )
        assert match.total_goals == 5

    def test_is_completed_finished(self):
        """Test is_completed for finished match."""
        match = Match(
            home_team="Manchester United",
            away_team="Liverpool",
            scheduled_at=datetime.now(timezone.utc),
            status=MatchStatus.FINISHED,
            home_score=1,
            away_score=0,
        )
        assert match.is_completed is True

    def test_is_completed_pending(self):
        """Test is_completed for pending match."""
        match = Match(
            home_team="Manchester United",
            away_team="Liverpool",
            scheduled_at=datetime.now(timezone.utc),
            status=MatchStatus.PENDING,
        )
        assert match.is_completed is False

    def test_display_score_with_scores(self):
        """Test display_score with scores set."""
        match = Match(
            home_team="Manchester United",
            away_team="Liverpool",
            scheduled_at=datetime.now(timezone.utc),
            home_score=2,
            away_score=1,
        )
        assert match.display_score == "2 : 1"

    def test_display_score_no_scores(self):
        """Test display_score without scores."""
        match = Match(
            home_team="Manchester United",
            away_team="Liverpool",
            scheduled_at=datetime.now(timezone.utc),
        )
        assert match.display_score == "- : -"


# =============================================================================
# Prediction Model Tests
# =============================================================================


class TestPrediction:
    """Tests for Prediction model."""

    def test_prediction_creation(self):
        """Test Prediction model creation."""
        prediction = Prediction(
            user_id=ObjectId(),
            match_id=ObjectId(),
            predicted_home_score=2,
            predicted_away_score=1,
        )
        assert prediction.is_scored is False
        assert prediction.points is None

    def test_predicted_outcome_home_win(self):
        """Test predicted_outcome for home win prediction."""
        prediction = Prediction(
            user_id=ObjectId(),
            match_id=ObjectId(),
            predicted_home_score=3,
            predicted_away_score=1,
        )
        assert prediction.predicted_outcome == "home_win"

    def test_predicted_outcome_away_win(self):
        """Test predicted_outcome for away win prediction."""
        prediction = Prediction(
            user_id=ObjectId(),
            match_id=ObjectId(),
            predicted_home_score=0,
            predicted_away_score=2,
        )
        assert prediction.predicted_outcome == "away_win"

    def test_predicted_outcome_draw(self):
        """Test predicted_outcome for draw prediction."""
        prediction = Prediction(
            user_id=ObjectId(),
            match_id=ObjectId(),
            predicted_home_score=1,
            predicted_away_score=1,
        )
        assert prediction.predicted_outcome == "draw"

    def test_predicted_goal_difference(self):
        """Test predicted_goal_difference calculation."""
        prediction = Prediction(
            user_id=ObjectId(),
            match_id=ObjectId(),
            predicted_home_score=3,
            predicted_away_score=1,
        )
        assert prediction.predicted_goal_difference == 2


class TestPredictionScoring:
    """Tests for prediction scoring logic."""

    def test_exact_score(self):
        """Test scoring for exact score match."""
        prediction = Prediction(
            user_id=ObjectId(),
            match_id=ObjectId(),
            predicted_home_score=2,
            predicted_away_score=1,
        )
        points, breakdown = prediction.calculate_points(2, 1)
        assert points == PredictionPoints.EXACT_SCORE
        assert "Exact score" in breakdown

    def test_correct_difference(self):
        """Test scoring for correct outcome and goal difference."""
        prediction = Prediction(
            user_id=ObjectId(),
            match_id=ObjectId(),
            predicted_home_score=3,
            predicted_away_score=1,  # diff = +2
        )
        points, breakdown = prediction.calculate_points(4, 2)  # diff = +2
        assert points == PredictionPoints.CORRECT_DIFFERENCE
        assert "goal difference" in breakdown

    def test_correct_outcome_only(self):
        """Test scoring for correct outcome but wrong details."""
        prediction = Prediction(
            user_id=ObjectId(),
            match_id=ObjectId(),
            predicted_home_score=2,
            predicted_away_score=1,  # home win, diff = +1
        )
        points, breakdown = prediction.calculate_points(3, 0)  # home win, diff = +3
        assert points == PredictionPoints.CORRECT_OUTCOME
        assert "Correct outcome" in breakdown

    def test_incorrect_prediction(self):
        """Test scoring for completely wrong prediction."""
        prediction = Prediction(
            user_id=ObjectId(),
            match_id=ObjectId(),
            predicted_home_score=2,
            predicted_away_score=0,  # home win
        )
        points, breakdown = prediction.calculate_points(0, 3)  # away win
        assert points == PredictionPoints.INCORRECT
        assert "Incorrect" in breakdown

    def test_draw_exact(self):
        """Test exact draw prediction."""
        prediction = Prediction(
            user_id=ObjectId(),
            match_id=ObjectId(),
            predicted_home_score=1,
            predicted_away_score=1,
        )
        points, _ = prediction.calculate_points(1, 1)
        assert points == PredictionPoints.EXACT_SCORE

    def test_draw_correct_outcome(self):
        """Test draw prediction with different score."""
        prediction = Prediction(
            user_id=ObjectId(),
            match_id=ObjectId(),
            predicted_home_score=0,
            predicted_away_score=0,
        )
        points, _ = prediction.calculate_points(2, 2)
        assert points == PredictionPoints.CORRECT_DIFFERENCE  # draw, diff = 0

    def test_score_prediction_method(self):
        """Test score_prediction returns updated instance."""
        prediction = Prediction(
            user_id=ObjectId(),
            match_id=ObjectId(),
            predicted_home_score=2,
            predicted_away_score=1,
        )
        scored = prediction.score_prediction(2, 1)

        assert scored.is_scored is True
        assert scored.points == PredictionPoints.EXACT_SCORE
        assert scored.actual_home_score == 2
        assert scored.actual_away_score == 1
        assert scored.scored_at is not None


# =============================================================================
# Model Serialization Tests
# =============================================================================


class TestModelSerialization:
    """Tests for model serialization and deserialization."""

    def test_user_to_dict(self):
        """Test User serialization to dictionary."""
        user = User(
            username="john_doe",
            email="john@example.com",
        )
        data = user.model_dump(by_alias=True)

        assert "_id" in data
        assert data["username"] == "john_doe"
        assert data["email"] == "john@example.com"

    def test_user_to_json(self):
        """Test User JSON serialization."""
        user = User(
            username="john_doe",
            email="john@example.com",
        )
        json_data = user.model_dump(mode="json")

        # ObjectId should be serialized to string
        assert isinstance(json_data["id"], str)

    def test_user_from_dict(self):
        """Test User creation from dictionary (like MongoDB document)."""
        data = {
            "_id": ObjectId(),
            "username": "john_doe",
            "email": "john@example.com",
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        user = User.model_validate(data)

        assert user.username == "john_doe"
        assert user.email == "john@example.com"

    def test_match_to_mongo(self):
        """Test Match serialization for MongoDB."""
        match = Match(
            home_team="Manchester United",
            away_team="Liverpool",
            scheduled_at=datetime.now(timezone.utc),
            sport=Sport.FOOTBALL,
        )
        data = match.model_dump(by_alias=True)

        assert "_id" in data
        assert data["home_team"] == "Manchester United"
        assert data["sport"] == "football"  # enum value


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
