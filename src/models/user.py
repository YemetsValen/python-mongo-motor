"""
User model for the predictions system.

Defines the User document structure with Pydantic validation.
"""

from datetime import datetime
from typing import Annotated

from pydantic import EmailStr, Field, field_validator, model_validator

from src.models.base import BaseDocument, MongoDocument
from src.validators.custom_types import validate_username


class UserCreate(MongoDocument):
    """
    Schema for creating a new user.

    Used for input validation when registering new users.
    """

    username: Annotated[
        str,
        Field(
            min_length=3,
            max_length=30,
            description="Unique username (3-30 characters)",
            examples=["john_doe", "pro-predictor"],
        ),
    ]
    email: Annotated[
        EmailStr,
        Field(
            description="User's email address",
            examples=["user@example.com"],
        ),
    ]
    display_name: Annotated[
        str | None,
        Field(
            default=None,
            max_length=50,
            description="Display name shown in leaderboards",
            examples=["John Doe"],
        ),
    ] = None

    @field_validator("username")
    @classmethod
    def validate_username_format(cls, v: str) -> str:
        """Validate username format."""
        return validate_username(v)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        """Normalize email to lowercase."""
        return v.lower().strip()


class UserUpdate(MongoDocument):
    """
    Schema for updating user data.

    All fields are optional - only provided fields will be updated.
    """

    display_name: Annotated[
        str | None,
        Field(
            default=None,
            max_length=50,
            description="Display name shown in leaderboards",
        ),
    ] = None
    email: Annotated[
        EmailStr | None,
        Field(
            default=None,
            description="User's email address",
        ),
    ] = None
    is_active: Annotated[
        bool | None,
        Field(
            default=None,
            description="Whether the user account is active",
        ),
    ] = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str | None) -> str | None:
        """Normalize email to lowercase."""
        if v is not None:
            return v.lower().strip()
        return v


class User(BaseDocument):
    """
    User document model.

    Represents a registered user in the system who can make predictions.

    Indexes:
        - username: unique
        - email: unique
        - (is_active, created_at): for listing active users

    Example:
        >>> user = User(
        ...     username="john_doe",
        ...     email="john@example.com",
        ...     display_name="John Doe"
        ... )
        >>> user.model_dump(by_alias=True)
        {'_id': ObjectId(...), 'username': 'john_doe', ...}
    """

    username: Annotated[
        str,
        Field(
            min_length=3,
            max_length=30,
            description="Unique username",
            examples=["john_doe"],
        ),
    ]
    email: Annotated[
        EmailStr,
        Field(
            description="User's email address (unique)",
            examples=["user@example.com"],
        ),
    ]
    display_name: Annotated[
        str | None,
        Field(
            default=None,
            max_length=50,
            description="Display name shown in leaderboards",
        ),
    ] = None
    is_active: Annotated[
        bool,
        Field(
            default=True,
            description="Whether the user account is active",
        ),
    ] = True
    last_login_at: Annotated[
        datetime | None,
        Field(
            default=None,
            description="Last login timestamp",
        ),
    ] = None

    # Denormalized stats (updated periodically for performance)
    total_predictions: Annotated[
        int,
        Field(
            default=0,
            ge=0,
            description="Total number of predictions made",
        ),
    ] = 0
    total_points: Annotated[
        int,
        Field(
            default=0,
            ge=0,
            description="Total points earned",
        ),
    ] = 0

    @field_validator("username")
    @classmethod
    def validate_username_format(cls, v: str) -> str:
        """Validate username format."""
        return validate_username(v)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        """Normalize email to lowercase."""
        return v.lower().strip()

    @property
    def effective_display_name(self) -> str:
        """Get display name, falling back to username if not set."""
        return self.display_name or self.username

    @property
    def average_points(self) -> float:
        """Calculate average points per prediction."""
        if self.total_predictions == 0:
            return 0.0
        return self.total_points / self.total_predictions

    @classmethod
    def from_create(cls, data: UserCreate) -> "User":
        """Create a User instance from UserCreate data."""
        return cls(
            username=data.username,
            email=data.email,
            display_name=data.display_name,
        )


class UserInDB(User):
    """
    User model as stored in database.

    Includes all fields that are stored but not exposed in API responses.
    This can include sensitive fields or internal tracking fields.
    """

    password_hash: Annotated[
        str | None,
        Field(
            default=None,
            description="Hashed password (if using password auth)",
            exclude=True,  # Exclude from serialization
        ),
    ] = None
    failed_login_attempts: Annotated[
        int,
        Field(
            default=0,
            ge=0,
            description="Number of consecutive failed login attempts",
        ),
    ] = 0
    locked_until: Annotated[
        datetime | None,
        Field(
            default=None,
            description="Account locked until this timestamp",
        ),
    ] = None

    @property
    def is_locked(self) -> bool:
        """Check if the account is currently locked."""
        if self.locked_until is None:
            return False
        return datetime.utcnow() < self.locked_until


class UserResponse(MongoDocument):
    """
    User data for API responses.

    Excludes sensitive fields and includes computed properties.
    """

    id: str = Field(description="User ID")
    username: str
    email: EmailStr
    display_name: str | None = None
    is_active: bool = True
    created_at: datetime
    total_predictions: int = 0
    total_points: int = 0
    average_points: float = 0.0

    @classmethod
    def from_user(cls, user: User) -> "UserResponse":
        """Create response from User model."""
        return cls(
            id=str(user.id),
            username=user.username,
            email=user.email,
            display_name=user.display_name,
            is_active=user.is_active,
            created_at=user.created_at,
            total_predictions=user.total_predictions,
            total_points=user.total_points,
            average_points=user.average_points,
        )
