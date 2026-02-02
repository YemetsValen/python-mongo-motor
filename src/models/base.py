"""
Base model classes for MongoDB document integration with Pydantic v2.

Provides foundational classes that handle:
- ObjectId serialization/deserialization
- Common fields (id, created_at, updated_at)
- Document conversion utilities
- Schema versioning support
"""

from datetime import datetime, timezone
from typing import Any, ClassVar, Self

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.validators.custom_types import PyObjectId


def utc_now() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(timezone.utc)


class MongoBaseModel(BaseModel):
    """
    Base model for all MongoDB documents.

    Provides:
    - Automatic ObjectId handling with alias '_id'
    - JSON serialization with string IDs
    - Conversion to/from MongoDB documents
    - Common configuration for all models

    Usage:
        class User(MongoBaseModel):
            username: str
            email: str
    """

    model_config = ConfigDict(
        # Allow population by field name or alias
        populate_by_name=True,
        # Use enum values for serialization
        use_enum_values=True,
        # Validate on assignment
        validate_assignment=True,
        # Allow arbitrary types (for ObjectId)
        arbitrary_types_allowed=True,
        # JSON serialization settings
        json_encoders={
            ObjectId: str,
            datetime: lambda v: v.isoformat(),
        },
        # Strip whitespace from strings
        str_strip_whitespace=True,
    )

    # MongoDB document ID
    id: PyObjectId = Field(
        default_factory=ObjectId,
        alias="_id",
        description="MongoDB document ID",
    )

    @classmethod
    def from_mongo(cls, document: dict[str, Any] | None) -> Self | None:
        """
        Create model instance from MongoDB document.

        Args:
            document: Raw MongoDB document dict

        Returns:
            Model instance or None if document is None
        """
        if document is None:
            return None
        return cls.model_validate(document)

    @classmethod
    def from_mongo_list(cls, documents: list[dict[str, Any]]) -> list[Self]:
        """
        Create list of model instances from MongoDB documents.

        Args:
            documents: List of raw MongoDB document dicts

        Returns:
            List of model instances
        """
        return [cls.model_validate(doc) for doc in documents]

    def to_mongo(self, exclude_none: bool = False, by_alias: bool = True) -> dict[str, Any]:
        """
        Convert model to MongoDB document format.

        Args:
            exclude_none: Whether to exclude None values
            by_alias: Whether to use field aliases (e.g., '_id' instead of 'id')

        Returns:
            Dictionary suitable for MongoDB insertion/update
        """
        data = self.model_dump(
            exclude_none=exclude_none,
            by_alias=by_alias,
        )
        return data

    def to_json_dict(self, exclude_none: bool = False) -> dict[str, Any]:
        """
        Convert model to JSON-serializable dictionary.

        ObjectIds are converted to strings for JSON compatibility.

        Args:
            exclude_none: Whether to exclude None values

        Returns:
            JSON-serializable dictionary
        """
        data = self.model_dump(
            exclude_none=exclude_none,
            by_alias=False,
            mode="json",
        )
        return data


class TimestampedModel(MongoBaseModel):
    """
    Base model with automatic timestamp tracking.

    Adds:
    - created_at: Set on document creation
    - updated_at: Updated on every modification
    """

    created_at: datetime = Field(
        default_factory=utc_now,
        description="Document creation timestamp (UTC)",
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        description="Last update timestamp (UTC)",
    )

    @model_validator(mode="before")
    @classmethod
    def set_updated_at(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Ensure updated_at is set to current time on updates."""
        # Only update if this is an existing document being modified
        if "_id" in values or "id" in values:
            values["updated_at"] = utc_now()
        return values

    def touch(self) -> None:
        """Update the updated_at timestamp to current time."""
        self.updated_at = utc_now()


class VersionedModel(TimestampedModel):
    """
    Base model with schema versioning support.

    Adds:
    - schema_version: For tracking document schema versions
    - Migration support between schema versions

    Useful for evolving document schemas over time.
    """

    # Class variable for current schema version
    SCHEMA_VERSION: ClassVar[int] = 1

    schema_version: int = Field(
        default=1,
        ge=1,
        description="Document schema version for migrations",
    )

    @model_validator(mode="before")
    @classmethod
    def set_schema_version(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Set schema version to current version on new documents."""
        if "schema_version" not in values:
            values["schema_version"] = cls.SCHEMA_VERSION
        return values

    @classmethod
    def migrate(cls, document: dict[str, Any]) -> dict[str, Any]:
        """
        Migrate document to current schema version.

        Override this method to implement custom migration logic.

        Args:
            document: Raw MongoDB document

        Returns:
            Migrated document dict
        """
        doc_version = document.get("schema_version", 1)

        if doc_version < cls.SCHEMA_VERSION:
            # Apply migrations sequentially
            for version in range(doc_version, cls.SCHEMA_VERSION):
                migration_method = getattr(cls, f"_migrate_v{version}_to_v{version + 1}", None)
                if migration_method:
                    document = migration_method(document)

            document["schema_version"] = cls.SCHEMA_VERSION

        return document

    @classmethod
    def from_mongo(cls, document: dict[str, Any] | None) -> Self | None:
        """
        Create model instance from MongoDB document with migration.

        Args:
            document: Raw MongoDB document dict

        Returns:
            Model instance or None if document is None
        """
        if document is None:
            return None

        # Apply migrations if needed
        migrated = cls.migrate(document)
        return cls.model_validate(migrated)


class SoftDeleteModel(TimestampedModel):
    """
    Base model with soft delete support.

    Instead of permanently deleting documents, marks them as deleted.
    Useful for audit trails and data recovery.
    """

    is_deleted: bool = Field(
        default=False,
        description="Whether document is soft-deleted",
    )
    deleted_at: datetime | None = Field(
        default=None,
        description="Soft deletion timestamp (UTC)",
    )

    def soft_delete(self) -> None:
        """Mark document as deleted."""
        self.is_deleted = True
        self.deleted_at = utc_now()
        self.touch()

    def restore(self) -> None:
        """Restore soft-deleted document."""
        self.is_deleted = False
        self.deleted_at = None
        self.touch()


class EmbeddedModel(BaseModel):
    """
    Base model for embedded documents (subdocuments).

    Does not include _id field - used for nested objects within documents.

    Usage:
        class Address(EmbeddedModel):
            street: str
            city: str
            country: str

        class User(MongoBaseModel):
            name: str
            address: Address
    """

    model_config = ConfigDict(
        populate_by_name=True,
        use_enum_values=True,
        validate_assignment=True,
        arbitrary_types_allowed=True,
        str_strip_whitespace=True,
    )

    def to_dict(self, exclude_none: bool = False) -> dict[str, Any]:
        """Convert embedded model to dictionary."""
        return self.model_dump(exclude_none=exclude_none)
