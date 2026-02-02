"""
User service with business logic for user management.

Provides high-level operations for user registration, authentication,
profile management, and statistics calculation.
"""

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.models.user import User, UserCreate, UserResponse, UserUpdate
from src.repositories.user_repository import UserRepository


class UserServiceError(Exception):
    """Base exception for user service errors."""

    pass


class UserNotFoundError(UserServiceError):
    """Raised when user is not found."""

    pass


class UserAlreadyExistsError(UserServiceError):
    """Raised when trying to create a user that already exists."""

    pass


class UserInactiveError(UserServiceError):
    """Raised when trying to perform action on inactive user."""

    pass


class UserService:
    """
    Service layer for user operations.

    Handles business logic, validation, and orchestration of user-related
    operations. Uses UserRepository for database access.

    Usage:
        db = await get_database()
        user_service = UserService(db)
        user = await user_service.register_user(username="john", email="john@example.com")
    """

    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        """
        Initialize user service.

        Args:
            database: Motor database instance
        """
        self.db = database
        self.repository = UserRepository(database)

    # =========================================================================
    # User Registration and Management
    # =========================================================================

    async def register_user(
        self,
        username: str,
        email: str,
        display_name: str | None = None,
    ) -> User:
        """
        Register a new user.

        Args:
            username: Unique username (3-30 characters)
            email: User's email address
            display_name: Optional display name

        Returns:
            Created User instance

        Raises:
            UserAlreadyExistsError: If username or email already exists
        """
        # Check for existing username
        existing = await self.repository.find_by_username(username)
        if existing:
            raise UserAlreadyExistsError(f"Username '{username}' is already taken")

        # Check for existing email
        existing = await self.repository.find_by_email(email)
        if existing:
            raise UserAlreadyExistsError(f"Email '{email}' is already registered")

        # Create user
        user_data = UserCreate(
            username=username,
            email=email,
            display_name=display_name,
        )

        return await self.repository.create_user(user_data)

    async def get_user(self, user_id: str | ObjectId) -> User:
        """
        Get user by ID.

        Args:
            user_id: User's ObjectId or string ID

        Returns:
            User instance

        Raises:
            UserNotFoundError: If user not found
        """
        user = await self.repository.find_by_id(user_id)
        if user is None:
            raise UserNotFoundError(f"User with ID '{user_id}' not found")
        return user

    async def get_user_by_username(self, username: str) -> User:
        """
        Get user by username.

        Args:
            username: User's username

        Returns:
            User instance

        Raises:
            UserNotFoundError: If user not found
        """
        user = await self.repository.find_by_username(username)
        if user is None:
            raise UserNotFoundError(f"User '{username}' not found")
        return user

    async def get_user_by_email(self, email: str) -> User:
        """
        Get user by email.

        Args:
            email: User's email address

        Returns:
            User instance

        Raises:
            UserNotFoundError: If user not found
        """
        user = await self.repository.find_by_email(email)
        if user is None:
            raise UserNotFoundError(f"User with email '{email}' not found")
        return user

    async def update_user(
        self,
        user_id: str | ObjectId,
        display_name: str | None = None,
        email: str | None = None,
    ) -> User:
        """
        Update user profile.

        Args:
            user_id: User's ObjectId
            display_name: New display name (optional)
            email: New email address (optional)

        Returns:
            Updated User instance

        Raises:
            UserNotFoundError: If user not found
            UserAlreadyExistsError: If new email is already in use
        """
        # Verify user exists
        user = await self.get_user(user_id)

        # Check email uniqueness if changing
        if email and email.lower() != user.email.lower():
            existing = await self.repository.find_by_email(email)
            if existing:
                raise UserAlreadyExistsError(f"Email '{email}' is already in use")

        update_data = UserUpdate(
            display_name=display_name,
            email=email,
        )

        updated = await self.repository.update_user(user_id, update_data)
        if updated is None:
            raise UserNotFoundError(f"User with ID '{user_id}' not found")

        return updated

    async def deactivate_user(self, user_id: str | ObjectId) -> User:
        """
        Deactivate a user account.

        Args:
            user_id: User's ObjectId

        Returns:
            Updated User instance

        Raises:
            UserNotFoundError: If user not found
        """
        user = await self.repository.deactivate_user(user_id)
        if user is None:
            raise UserNotFoundError(f"User with ID '{user_id}' not found")
        return user

    async def activate_user(self, user_id: str | ObjectId) -> User:
        """
        Activate a user account.

        Args:
            user_id: User's ObjectId

        Returns:
            Updated User instance

        Raises:
            UserNotFoundError: If user not found
        """
        user = await self.repository.activate_user(user_id)
        if user is None:
            raise UserNotFoundError(f"User with ID '{user_id}' not found")
        return user

    async def delete_user(self, user_id: str | ObjectId, hard_delete: bool = False) -> bool:
        """
        Delete a user.

        Args:
            user_id: User's ObjectId
            hard_delete: If True, permanently delete. If False, just deactivate.

        Returns:
            True if user was deleted/deactivated

        Raises:
            UserNotFoundError: If user not found
        """
        # Verify user exists
        await self.get_user(user_id)

        if hard_delete:
            # Also delete user's predictions
            predictions_collection = self.db["predictions"]
            object_id = ObjectId(user_id) if isinstance(user_id, str) else user_id
            await predictions_collection.delete_many({"user_id": object_id})
            return await self.repository.delete_by_id(user_id)
        else:
            await self.deactivate_user(user_id)
            return True

    # =========================================================================
    # User Listing and Search
    # =========================================================================

    async def list_users(
        self,
        skip: int = 0,
        limit: int = 20,
        active_only: bool = True,
    ) -> list[User]:
        """
        List users with pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            active_only: If True, only return active users

        Returns:
            List of users
        """
        if active_only:
            return await self.repository.find_active_users(skip=skip, limit=limit)
        else:
            return await self.repository.find_many(skip=skip, limit=limit)

    async def search_users(
        self,
        query: str,
        skip: int = 0,
        limit: int = 20,
    ) -> list[User]:
        """
        Search users by username or email.

        Args:
            query: Search query
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of matching users
        """
        return await self.repository.search_users(
            query=query,
            skip=skip,
            limit=limit,
        )

    async def get_user_count(self, active_only: bool = True) -> int:
        """
        Get total number of users.

        Args:
            active_only: If True, only count active users

        Returns:
            Number of users
        """
        return await self.repository.get_user_count(active_only=active_only)

    # =========================================================================
    # User Statistics
    # =========================================================================

    async def get_user_stats(self, user_id: str | ObjectId) -> dict[str, Any]:
        """
        Get comprehensive statistics for a user.

        Args:
            user_id: User's ObjectId

        Returns:
            Dictionary with user statistics

        Raises:
            UserNotFoundError: If user not found
        """
        user = await self.get_user(user_id)
        object_id = ObjectId(user_id) if isinstance(user_id, str) else user_id

        # Get prediction stats from predictions collection
        predictions = self.db["predictions"]

        pipeline = [
            {"$match": {"user_id": object_id}},
            {
                "$group": {
                    "_id": "$user_id",
                    "total_predictions": {"$sum": 1},
                    "scored_predictions": {"$sum": {"$cond": ["$is_scored", 1, 0]}},
                    "pending_predictions": {"$sum": {"$cond": ["$is_scored", 0, 1]}},
                    "total_points": {"$sum": {"$ifNull": ["$points", 0]}},
                    "exact_scores": {"$sum": {"$cond": [{"$eq": ["$points", 3]}, 1, 0]}},
                    "correct_diffs": {"$sum": {"$cond": [{"$eq": ["$points", 2]}, 1, 0]}},
                    "correct_outcomes": {"$sum": {"$cond": [{"$eq": ["$points", 1]}, 1, 0]}},
                    "incorrect": {
                        "$sum": {
                            "$cond": [
                                {"$and": ["$is_scored", {"$eq": ["$points", 0]}]},
                                1,
                                0,
                            ]
                        }
                    },
                    "first_prediction": {"$min": "$created_at"},
                    "last_prediction": {"$max": "$created_at"},
                }
            },
        ]

        cursor = predictions.aggregate(pipeline)
        results = await cursor.to_list(length=1)

        if results:
            stats = results[0]
            scored = stats["scored_predictions"]
            correct = stats["exact_scores"] + stats["correct_diffs"] + stats["correct_outcomes"]

            accuracy = (correct / scored * 100) if scored > 0 else 0.0
            avg_points = stats["total_points"] / scored if scored > 0 else 0.0

            return {
                "user_id": str(user.id),
                "username": user.username,
                "display_name": user.effective_display_name,
                "total_predictions": stats["total_predictions"],
                "scored_predictions": stats["scored_predictions"],
                "pending_predictions": stats["pending_predictions"],
                "total_points": stats["total_points"],
                "exact_scores": stats["exact_scores"],
                "correct_differences": stats["correct_diffs"],
                "correct_outcomes": stats["correct_outcomes"],
                "incorrect": stats["incorrect"],
                "accuracy_percent": round(accuracy, 2),
                "avg_points_per_prediction": round(avg_points, 2),
                "first_prediction_at": stats["first_prediction"],
                "last_prediction_at": stats["last_prediction"],
                "member_since": user.created_at,
            }
        else:
            # No predictions yet
            return {
                "user_id": str(user.id),
                "username": user.username,
                "display_name": user.effective_display_name,
                "total_predictions": 0,
                "scored_predictions": 0,
                "pending_predictions": 0,
                "total_points": 0,
                "exact_scores": 0,
                "correct_differences": 0,
                "correct_outcomes": 0,
                "incorrect": 0,
                "accuracy_percent": 0.0,
                "avg_points_per_prediction": 0.0,
                "first_prediction_at": None,
                "last_prediction_at": None,
                "member_since": user.created_at,
            }

    async def get_top_users(self, limit: int = 10) -> list[dict[str, Any]]:
        """
        Get top users by total points.

        Args:
            limit: Number of top users to return

        Returns:
            List of top users with their stats
        """
        users = await self.repository.get_top_users_by_points(limit=limit)

        result = []
        for rank, user in enumerate(users, start=1):
            result.append(
                {
                    "rank": rank,
                    "user_id": str(user.id),
                    "username": user.username,
                    "display_name": user.effective_display_name,
                    "total_points": user.total_points,
                    "total_predictions": user.total_predictions,
                    "avg_points": user.average_points,
                }
            )

        return result

    async def update_login_timestamp(self, user_id: str | ObjectId) -> User:
        """
        Update user's last login timestamp.

        Args:
            user_id: User's ObjectId

        Returns:
            Updated user

        Raises:
            UserNotFoundError: If user not found
        """
        user = await self.repository.update_login(user_id)
        if user is None:
            raise UserNotFoundError(f"User with ID '{user_id}' not found")
        return user

    async def recalculate_stats(self, user_id: str | ObjectId) -> User:
        """
        Recalculate and update user's denormalized statistics.

        This syncs the user's total_predictions and total_points
        with the actual data in the predictions collection.

        Args:
            user_id: User's ObjectId

        Returns:
            Updated user with recalculated stats

        Raises:
            UserNotFoundError: If user not found
        """
        user = await self.repository.recalculate_user_stats(user_id)
        if user is None:
            raise UserNotFoundError(f"User with ID '{user_id}' not found")
        return user

    # =========================================================================
    # Utility Methods
    # =========================================================================

    async def ensure_active(self, user_id: str | ObjectId) -> User:
        """
        Ensure user exists and is active.

        Args:
            user_id: User's ObjectId

        Returns:
            User instance

        Raises:
            UserNotFoundError: If user not found
            UserInactiveError: If user is not active
        """
        user = await self.get_user(user_id)

        if not user.is_active:
            raise UserInactiveError(f"User '{user.username}' is not active")

        return user

    async def to_response(self, user: User) -> UserResponse:
        """
        Convert User model to API response format.

        Args:
            user: User instance

        Returns:
            UserResponse DTO
        """
        return UserResponse.from_user(user)
