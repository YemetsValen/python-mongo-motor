"""
User repository for database operations.

Provides async CRUD operations and queries for User documents.
"""

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase

from src.models.user import User, UserCreate, UserUpdate
from src.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """
    Repository for User document operations.

    Provides specialized methods for user-related queries
    in addition to base CRUD operations.
    """

    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        """
        Initialize user repository.

        Args:
            database: Motor database instance
        """
        super().__init__(database, "users", User)

    async def create_user(self, data: UserCreate) -> User:
        """
        Create a new user.

        Args:
            data: User creation data

        Returns:
            Created User instance

        Raises:
            ValueError: If username or email already exists
        """
        # Check for existing username
        existing = await self.collection.find_one({"username": data.username})
        if existing:
            raise ValueError(f"Username '{data.username}' already exists")

        # Check for existing email
        existing = await self.collection.find_one({"email": data.email})
        if existing:
            raise ValueError(f"Email '{data.email}' already registered")

        # Create user document
        user = User.from_create(data)
        return await self.create(user)

    async def find_by_username(self, username: str) -> User | None:
        """
        Find user by username.

        Args:
            username: Username to search for

        Returns:
            User if found, None otherwise
        """
        return await self.find_one({"username": username})

    async def find_by_email(self, email: str) -> User | None:
        """
        Find user by email address.

        Args:
            email: Email to search for (case-insensitive)

        Returns:
            User if found, None otherwise
        """
        return await self.find_one({"email": email.lower()})

    async def update_user(
        self,
        user_id: ObjectId | str,
        data: UserUpdate,
    ) -> User | None:
        """
        Update user fields.

        Args:
            user_id: User's ObjectId
            data: Fields to update

        Returns:
            Updated User if found, None otherwise
        """
        update_data = data.model_dump(exclude_none=True, exclude_unset=True)
        if not update_data:
            # No fields to update
            return await self.find_by_id(user_id)

        update_data["updated_at"] = datetime.now(timezone.utc)

        return await self.update_by_id(user_id, {"$set": update_data})

    async def find_active_users(
        self,
        skip: int = 0,
        limit: int = 20,
    ) -> list[User]:
        """
        Get list of active users.

        Args:
            skip: Number of documents to skip
            limit: Maximum documents to return

        Returns:
            List of active users sorted by creation date
        """
        return await self.find_many(
            filter={"is_active": True},
            skip=skip,
            limit=limit,
            sort=[("created_at", -1)],
        )

    async def deactivate_user(self, user_id: ObjectId | str) -> User | None:
        """
        Deactivate a user account.

        Args:
            user_id: User's ObjectId

        Returns:
            Updated User if found, None otherwise
        """
        return await self.update_by_id(
            user_id,
            {
                "$set": {
                    "is_active": False,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )

    async def activate_user(self, user_id: ObjectId | str) -> User | None:
        """
        Activate a user account.

        Args:
            user_id: User's ObjectId

        Returns:
            Updated User if found, None otherwise
        """
        return await self.update_by_id(
            user_id,
            {
                "$set": {
                    "is_active": True,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )

    async def update_login(self, user_id: ObjectId | str) -> User | None:
        """
        Update user's last login timestamp.

        Args:
            user_id: User's ObjectId

        Returns:
            Updated User if found, None otherwise
        """
        return await self.update_by_id(
            user_id,
            {
                "$set": {
                    "last_login_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )

    async def increment_stats(
        self,
        user_id: ObjectId | str,
        predictions_delta: int = 0,
        points_delta: int = 0,
    ) -> User | None:
        """
        Increment user statistics.

        Args:
            user_id: User's ObjectId
            predictions_delta: Amount to add to total_predictions
            points_delta: Amount to add to total_points

        Returns:
            Updated User if found, None otherwise
        """
        update: dict[str, Any] = {
            "$set": {"updated_at": datetime.now(timezone.utc)},
            "$inc": {},
        }

        if predictions_delta != 0:
            update["$inc"]["total_predictions"] = predictions_delta
        if points_delta != 0:
            update["$inc"]["total_points"] = points_delta

        if not update["$inc"]:
            del update["$inc"]

        return await self.update_by_id(user_id, update)

    async def search_users(
        self,
        query: str,
        skip: int = 0,
        limit: int = 20,
        active_only: bool = True,
    ) -> list[User]:
        """
        Search users by username or email.

        Args:
            query: Search query string
            skip: Number of documents to skip
            limit: Maximum documents to return
            active_only: Only return active users

        Returns:
            List of matching users
        """
        filter_query: dict[str, Any] = {
            "$or": [
                {"username": {"$regex": query, "$options": "i"}},
                {"email": {"$regex": query, "$options": "i"}},
            ]
        }

        if active_only:
            filter_query["is_active"] = True

        return await self.find_many(
            filter=filter_query,
            skip=skip,
            limit=limit,
            sort=[("username", 1)],
        )

    async def get_top_users_by_points(
        self,
        limit: int = 10,
        active_only: bool = True,
    ) -> list[User]:
        """
        Get users with the most points.

        Args:
            limit: Maximum number of users to return
            active_only: Only return active users

        Returns:
            List of users sorted by total_points descending
        """
        filter_query: dict[str, Any] = {}
        if active_only:
            filter_query["is_active"] = True

        return await self.find_many(
            filter=filter_query,
            skip=0,
            limit=limit,
            sort=[("total_points", -1)],
        )

    async def get_user_count(self, active_only: bool = False) -> int:
        """
        Get total count of users.

        Args:
            active_only: Only count active users

        Returns:
            Number of users
        """
        filter_query: dict[str, Any] = {}
        if active_only:
            filter_query["is_active"] = True

        return await self.count(filter_query)

    async def get_users_with_predictions_in_period(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> list[User]:
        """
        Get users who made predictions within a time period.

        This requires a join with predictions collection.

        Args:
            start_date: Period start
            end_date: Period end

        Returns:
            List of users with predictions in the period
        """
        pipeline = [
            {
                "$lookup": {
                    "from": "predictions",
                    "localField": "_id",
                    "foreignField": "user_id",
                    "as": "recent_predictions",
                    "pipeline": [
                        {
                            "$match": {
                                "created_at": {
                                    "$gte": start_date,
                                    "$lte": end_date,
                                }
                            }
                        },
                        {"$limit": 1},  # We only need to know if there's at least one
                    ],
                }
            },
            {"$match": {"recent_predictions": {"$ne": []}}},
            {"$project": {"recent_predictions": 0}},
            {"$sort": {"total_points": -1}},
        ]

        cursor = self.collection.aggregate(pipeline)
        documents = await cursor.to_list(length=None)
        return [User.model_validate(doc) for doc in documents]

    async def recalculate_user_stats(self, user_id: ObjectId | str) -> User | None:
        """
        Recalculate user statistics from predictions collection.

        This aggregates all the user's predictions to update their stats.

        Args:
            user_id: User's ObjectId

        Returns:
            Updated User if found, None otherwise
        """
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)

        # Aggregate predictions for this user
        pipeline = [
            {"$match": {"user_id": user_id, "is_scored": True}},
            {
                "$group": {
                    "_id": "$user_id",
                    "total_predictions": {"$sum": 1},
                    "total_points": {"$sum": "$points"},
                }
            },
        ]

        cursor = self.database["predictions"].aggregate(pipeline)
        results = await cursor.to_list(length=1)

        if results:
            stats = results[0]
            return await self.update_by_id(
                user_id,
                {
                    "$set": {
                        "total_predictions": stats["total_predictions"],
                        "total_points": stats["total_points"],
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )
        else:
            # No scored predictions, reset stats
            return await self.update_by_id(
                user_id,
                {
                    "$set": {
                        "total_predictions": 0,
                        "total_points": 0,
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )
