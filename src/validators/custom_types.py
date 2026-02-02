"""
Custom Pydantic types and validators for MongoDB integration.

Provides PyObjectId type and other custom validators for seamless
MongoDB document handling with Pydantic v2.
"""

from typing import Annotated, Any, Callable

from bson import ObjectId
from bson.errors import InvalidId
from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema, PydanticCustomError, core_schema


class PyObjectId(ObjectId):
    """
    Custom ObjectId type for Pydantic v2 integration.

    Handles serialization/deserialization of MongoDB ObjectId fields.
    Can accept ObjectId instances, valid hex strings, or None.

    Usage:
        class MyModel(BaseModel):
            id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    """

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        _source_type: Any,
        _handler: GetCoreSchemaHandler,
    ) -> CoreSchema:
        """Define how Pydantic should validate this type."""
        return core_schema.union_schema(
            [
                # If it's already an ObjectId, use it directly
                core_schema.is_instance_schema(ObjectId),
                # If it's a string, validate and convert
                core_schema.no_info_plain_validator_function(cls.validate),
            ],
            serialization=core_schema.plain_serializer_function_ser_schema(
                cls.serialize,
                info_arg=False,
                return_schema=core_schema.str_schema(),
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        _core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        """Define JSON schema representation."""
        return {
            "type": "string",
            "pattern": "^[0-9a-fA-F]{24}$",
            "description": "MongoDB ObjectId as 24-character hex string",
            "example": "507f1f77bcf86cd799439011",
        }

    @classmethod
    def validate(cls, value: Any) -> ObjectId:
        """Validate and convert value to ObjectId."""
        if isinstance(value, ObjectId):
            return value

        if isinstance(value, str):
            if not value:
                raise PydanticCustomError(
                    "objectid_empty",
                    "ObjectId cannot be empty string",
                )
            try:
                return ObjectId(value)
            except InvalidId as e:
                raise PydanticCustomError(
                    "objectid_invalid",
                    "Invalid ObjectId format: {value}",
                    {"value": value},
                ) from e

        raise PydanticCustomError(
            "objectid_type",
            "ObjectId must be ObjectId instance or 24-character hex string, got {type}",
            {"type": type(value).__name__},
        )

    @classmethod
    def serialize(cls, value: ObjectId) -> str:
        """Serialize ObjectId to string."""
        return str(value)


# Annotated type for optional ObjectId fields
OptionalPyObjectId = Annotated[PyObjectId | None, "Optional MongoDB ObjectId"]


def objectid_validator(value: Any) -> ObjectId:
    """
    Standalone validator function for ObjectId.

    Can be used with Annotated types or field validators.
    """
    if isinstance(value, ObjectId):
        return value
    if isinstance(value, str):
        try:
            return ObjectId(value)
        except InvalidId as e:
            raise ValueError(f"Invalid ObjectId: {value}") from e
    raise TypeError(f"Expected ObjectId or str, got {type(value).__name__}")


def create_objectid_field(
    default_factory: Callable[[], ObjectId] | None = None,
    alias: str = "_id",
    description: str = "MongoDB document ID",
) -> dict[str, Any]:
    """
    Create field kwargs for ObjectId fields.

    Usage:
        class MyModel(BaseModel):
            id: PyObjectId = Field(**create_objectid_field())
    """
    from pydantic import Field

    kwargs: dict[str, Any] = {
        "alias": alias,
        "description": description,
    }

    if default_factory:
        kwargs["default_factory"] = default_factory
    else:
        kwargs["default_factory"] = ObjectId

    return kwargs


# Type aliases for common use cases
DocumentId = Annotated[PyObjectId, "Primary document identifier"]
ReferenceId = Annotated[PyObjectId, "Reference to another document"]


class BsonBytes:
    """
    Custom type for handling BSON Binary data in Pydantic.
    """

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        _source_type: Any,
        _handler: GetCoreSchemaHandler,
    ) -> CoreSchema:
        return core_schema.bytes_schema()


# Score validation (for predictions)
Score = Annotated[int, "Match score (non-negative integer)"]


def validate_score(value: int) -> int:
    """Validate that a score is non-negative."""
    if value < 0:
        raise ValueError("Score cannot be negative")
    if value > 99:  # Reasonable upper limit
        raise ValueError("Score seems unrealistic (max 99)")
    return value


# Username validation
def validate_username(value: str) -> str:
    """
    Validate username format.

    Rules:
    - 3-30 characters
    - Alphanumeric, underscores, hyphens allowed
    - Must start with a letter
    """
    import re

    if not value:
        raise ValueError("Username cannot be empty")

    if len(value) < 3:
        raise ValueError("Username must be at least 3 characters")

    if len(value) > 30:
        raise ValueError("Username cannot exceed 30 characters")

    if not re.match(r"^[a-zA-Z][a-zA-Z0-9_-]*$", value):
        raise ValueError(
            "Username must start with a letter and contain only "
            "letters, numbers, underscores, and hyphens"
        )

    return value


# Email validation is built into Pydantic, but we can add custom rules
def validate_email_domain(email: str, allowed_domains: list[str] | None = None) -> str:
    """
    Validate email and optionally check domain.

    Args:
        email: Email address to validate
        allowed_domains: Optional list of allowed domains
    """
    if allowed_domains:
        domain = email.split("@")[-1].lower()
        if domain not in [d.lower() for d in allowed_domains]:
            raise ValueError(f"Email domain not allowed: {domain}")
    return email
