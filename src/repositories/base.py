"""
Base repository pattern implementation for MongoDB with Motor.

Provides generic CRUD operations and common query patterns that can be
inherited by specific repository implementations.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Generic, TypeVar

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from pydantic import BaseModel

from src.validators.custom_types import PyObjectId

# Type variables for generic repository
ModelType = TypeVar("ModelType", bound=BaseModel)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)


class BaseRepository(Generic[ModelType, CreateSchemaType, UpdateSchemaType], ABC):
    """
    Abstract base repository with common CRUD operations.

    Provides a consistent interface for database operations across all
    document types. Subclasses must implement the abstract properties
    and can override methods for custom behavior.

    Type Parameters:
        ModelType: The Pydantic model representing the document
        CreateSchemaType: Schema for creating new documents
        UpdateSchemaType: Schema for updating existing documents

    Usage:
        class UserRepository(BaseRepository[User, UserCreate, UserUpdate]):
            collection_name = "users"
            model_class = User

            async def find_by_email(self, email: str) -> User | None:
                return await self.find_one({"email": email})
    """

    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        """
        Initialize repository with database connection.

        Args:
            database: Motor database instance
        """
        self._database = database
        self._collection: AsyncIOMotorCollection = database[self.collection_name]

    @property
    @abstractmethod
    def collection_name(self) -> str:
        """Name of the MongoDB collection."""
        ...

    @property
    @abstractmethod
    def model_class(self) -> type[ModelType]:
        """Pydantic model class for this repository."""
        ...

    @property
    def collection(self) -> AsyncIOMotorCollection:
        """Get the Motor collection instance."""
        return self._collection

    @property
    def database(self) -> AsyncIOMotorDatabase:
        """Get the Motor database instance."""
        return self._database

    # =========================================================================
    # Create Operations
    # =========================================================================

    async def create(self, data: CreateSchemaType) -> ModelType:
        """
        Create a new document.

        Args:
            data: Creation schema with document data

        Returns:
            Created document as model instance
        """
        document = data.model_dump(by_alias=True, exclude_unset=True)

        # Ensure _id is set
        if "_id" not in document:
            document["_id"] = ObjectId()

        # Add timestamps if not present
        now = datetime.utcnow()
        if "created_at" not in document:
            document["created_at"] = now
        if "updated_at" not in document:
            document["updated_at"] = now

        result = await self._collection.insert_one(document)
        document["_id"] = result.inserted_id

        return self.model_class.model_validate(document)

    async def create_many(self, items: list[CreateSchemaType]) -> list[ModelType]:
        """
        Create multiple documents at once.

        Args:
            items: List of creation schemas

        Returns:
            List of created documents as model instances
        """
        if not items:
            return []

        documents = []
        now = datetime.utcnow()

        for item in items:
            doc = item.model_dump(by_alias=True, exclude_unset=True)
            if "_id" not in doc:
                doc["_id"] = ObjectId()
            if "created_at" not in doc:
                doc["created_at"] = now
            if "updated_at" not in doc:
                doc["updated_at"] = now
            documents.append(doc)

        result = await self._collection.insert_many(documents)

        # Update documents with inserted IDs
        for doc, inserted_id in zip(documents, result.inserted_ids):
            doc["_id"] = inserted_id

        return [self.model_class.model_validate(doc) for doc in documents]

    # =========================================================================
    # Read Operations
    # =========================================================================

    async def get_by_id(self, id: str | ObjectId | PyObjectId) -> ModelType | None:
        """
        Get a document by its ID.

        Args:
            id: Document ID (string or ObjectId)

        Returns:
            Model instance or None if not found
        """
        object_id = ObjectId(id) if isinstance(id, str) else id
        document = await self._collection.find_one({"_id": object_id})

        if document is None:
            return None

        return self.model_class.model_validate(document)

    async def find_one(self, filter: dict[str, Any]) -> ModelType | None:
        """
        Find a single document matching the filter.

        Args:
            filter: MongoDB query filter

        Returns:
            Model instance or None if not found
        """
        document = await self._collection.find_one(filter)

        if document is None:
            return None

        return self.model_class.model_validate(document)

    async def find_many(
        self,
        filter: dict[str, Any] | None = None,
        *,
        skip: int = 0,
        limit: int = 100,
        sort: list[tuple[str, int]] | None = None,
        projection: dict[str, Any] | None = None,
    ) -> list[ModelType]:
        """
        Find multiple documents matching the filter.

        Args:
            filter: MongoDB query filter (default: all documents)
            skip: Number of documents to skip (for pagination)
            limit: Maximum number of documents to return
            sort: List of (field, direction) tuples for sorting
            projection: Fields to include/exclude

        Returns:
            List of model instances
        """
        filter = filter or {}

        cursor = self._collection.find(filter, projection)

        if sort:
            cursor = cursor.sort(sort)

        cursor = cursor.skip(skip).limit(limit)

        documents = await cursor.to_list(length=limit)
        return [self.model_class.model_validate(doc) for doc in documents]

    async def count(self, filter: dict[str, Any] | None = None) -> int:
        """
        Count documents matching the filter.

        Args:
            filter: MongoDB query filter (default: all documents)

        Returns:
            Number of matching documents
        """
        filter = filter or {}
        return await self._collection.count_documents(filter)

    async def exists(self, filter: dict[str, Any]) -> bool:
        """
        Check if any document matches the filter.

        Args:
            filter: MongoDB query filter

        Returns:
            True if at least one document matches
        """
        count = await self._collection.count_documents(filter, limit=1)
        return count > 0

    # =========================================================================
    # Update Operations
    # =========================================================================

    async def update_by_id(
        self,
        id: str | ObjectId | PyObjectId,
        data: UpdateSchemaType,
    ) -> ModelType | None:
        """
        Update a document by its ID.

        Args:
            id: Document ID
            data: Update schema with fields to update

        Returns:
            Updated model instance or None if not found
        """
        object_id = ObjectId(id) if isinstance(id, str) else id

        # Get update data, excluding None values and unset fields
        update_data = data.model_dump(exclude_unset=True, exclude_none=True)

        if not update_data:
            # Nothing to update, return current document
            return await self.get_by_id(id)

        # Always update the updated_at timestamp
        update_data["updated_at"] = datetime.utcnow()

        result = await self._collection.find_one_and_update(
            {"_id": object_id},
            {"$set": update_data},
            return_document=True,
        )

        if result is None:
            return None

        return self.model_class.model_validate(result)

    async def update_one(
        self,
        filter: dict[str, Any],
        update: dict[str, Any],
        *,
        upsert: bool = False,
    ) -> bool:
        """
        Update a single document matching the filter.

        Args:
            filter: MongoDB query filter
            update: Update operations (e.g., {"$set": {...}})
            upsert: Create document if not found

        Returns:
            True if a document was modified
        """
        # Ensure updated_at is set
        if "$set" in update:
            update["$set"]["updated_at"] = datetime.utcnow()
        else:
            update["$set"] = {"updated_at": datetime.utcnow()}

        result = await self._collection.update_one(filter, update, upsert=upsert)
        return result.modified_count > 0 or (upsert and result.upserted_id is not None)

    async def update_many(
        self,
        filter: dict[str, Any],
        update: dict[str, Any],
    ) -> int:
        """
        Update multiple documents matching the filter.

        Args:
            filter: MongoDB query filter
            update: Update operations

        Returns:
            Number of documents modified
        """
        # Ensure updated_at is set
        if "$set" in update:
            update["$set"]["updated_at"] = datetime.utcnow()
        else:
            update["$set"] = {"updated_at": datetime.utcnow()}

        result = await self._collection.update_many(filter, update)
        return result.modified_count

    async def increment(
        self,
        id: str | ObjectId | PyObjectId,
        field: str,
        amount: int = 1,
    ) -> ModelType | None:
        """
        Increment a numeric field atomically.

        Args:
            id: Document ID
            field: Field name to increment
            amount: Amount to increment by (can be negative)

        Returns:
            Updated model instance or None if not found
        """
        object_id = ObjectId(id) if isinstance(id, str) else id

        result = await self._collection.find_one_and_update(
            {"_id": object_id},
            {
                "$inc": {field: amount},
                "$set": {"updated_at": datetime.utcnow()},
            },
            return_document=True,
        )

        if result is None:
            return None

        return self.model_class.model_validate(result)

    # =========================================================================
    # Delete Operations
    # =========================================================================

    async def delete_by_id(self, id: str | ObjectId | PyObjectId) -> bool:
        """
        Delete a document by its ID.

        Args:
            id: Document ID

        Returns:
            True if document was deleted
        """
        object_id = ObjectId(id) if isinstance(id, str) else id
        result = await self._collection.delete_one({"_id": object_id})
        return result.deleted_count > 0

    async def delete_one(self, filter: dict[str, Any]) -> bool:
        """
        Delete a single document matching the filter.

        Args:
            filter: MongoDB query filter

        Returns:
            True if a document was deleted
        """
        result = await self._collection.delete_one(filter)
        return result.deleted_count > 0

    async def delete_many(self, filter: dict[str, Any]) -> int:
        """
        Delete multiple documents matching the filter.

        Args:
            filter: MongoDB query filter

        Returns:
            Number of documents deleted
        """
        result = await self._collection.delete_many(filter)
        return result.deleted_count

    # =========================================================================
    # Soft Delete Operations (if model supports it)
    # =========================================================================

    async def soft_delete(self, id: str | ObjectId | PyObjectId) -> ModelType | None:
        """
        Soft delete a document by setting is_deleted flag.

        Args:
            id: Document ID

        Returns:
            Updated model instance or None if not found
        """
        object_id = ObjectId(id) if isinstance(id, str) else id

        result = await self._collection.find_one_and_update(
            {"_id": object_id},
            {
                "$set": {
                    "is_deleted": True,
                    "deleted_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                }
            },
            return_document=True,
        )

        if result is None:
            return None

        return self.model_class.model_validate(result)

    async def restore(self, id: str | ObjectId | PyObjectId) -> ModelType | None:
        """
        Restore a soft-deleted document.

        Args:
            id: Document ID

        Returns:
            Updated model instance or None if not found
        """
        object_id = ObjectId(id) if isinstance(id, str) else id

        result = await self._collection.find_one_and_update(
            {"_id": object_id},
            {
                "$set": {
                    "is_deleted": False,
                    "updated_at": datetime.utcnow(),
                },
                "$unset": {"deleted_at": ""},
            },
            return_document=True,
        )

        if result is None:
            return None

        return self.model_class.model_validate(result)

    # =========================================================================
    # Aggregation Operations
    # =========================================================================

    async def aggregate(
        self,
        pipeline: list[dict[str, Any]],
        *,
        allow_disk_use: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Execute an aggregation pipeline.

        Args:
            pipeline: List of aggregation stages
            allow_disk_use: Allow using disk for large operations

        Returns:
            List of aggregation results
        """
        cursor = self._collection.aggregate(pipeline, allowDiskUse=allow_disk_use)
        return await cursor.to_list(length=None)

    async def distinct(
        self,
        field: str,
        filter: dict[str, Any] | None = None,
    ) -> list[Any]:
        """
        Get distinct values for a field.

        Args:
            field: Field name
            filter: Optional filter

        Returns:
            List of distinct values
        """
        return await self._collection.distinct(field, filter or {})

    # =========================================================================
    # Utility Methods
    # =========================================================================

    async def bulk_write(self, operations: list) -> dict[str, int]:
        """
        Execute bulk write operations.

        Args:
            operations: List of pymongo operations

        Returns:
            Summary of operations performed
        """
        if not operations:
            return {"inserted": 0, "modified": 0, "deleted": 0}

        result = await self._collection.bulk_write(operations)

        return {
            "inserted": result.inserted_count,
            "modified": result.modified_count,
            "deleted": result.deleted_count,
        }

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(collection='{self.collection_name}')>"
