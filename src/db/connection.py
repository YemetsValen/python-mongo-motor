"""
MongoDB async connection module using Motor.

Provides connection management, health checks, and database access.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from src.config.settings import get_settings

logger = structlog.get_logger(__name__)


class DatabaseConnection:
    """
    Manages MongoDB connection lifecycle using Motor async driver.

    Usage:
        db_conn = DatabaseConnection()
        await db_conn.connect()
        db = db_conn.database
        # ... use db
        await db_conn.disconnect()

    Or as context manager:
        async with DatabaseConnection() as db:
            # ... use db
    """

    _client: AsyncIOMotorClient | None = None
    _database: AsyncIOMotorDatabase | None = None

    def __init__(self) -> None:
        self.settings = get_settings()
        self._lock = asyncio.Lock()

    @property
    def client(self) -> AsyncIOMotorClient:
        """Get the Motor client instance."""
        if self._client is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._client

    @property
    def database(self) -> AsyncIOMotorDatabase:
        """Get the database instance."""
        if self._database is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._database

    async def connect(self) -> None:
        """
        Establish connection to MongoDB.

        Thread-safe: uses lock to prevent multiple simultaneous connections.
        """
        async with self._lock:
            if self._client is not None:
                logger.debug("Already connected to MongoDB")
                return

            mongo_settings = self.settings.mongo

            logger.info(
                "Connecting to MongoDB",
                host=mongo_settings.host,
                port=mongo_settings.port,
                database=mongo_settings.db_name,
            )

            try:
                self._client = AsyncIOMotorClient(
                    mongo_settings.uri,
                    minPoolSize=mongo_settings.min_pool_size,
                    maxPoolSize=mongo_settings.max_pool_size,
                    maxIdleTimeMS=mongo_settings.max_idle_time_ms,
                    connectTimeoutMS=mongo_settings.connect_timeout_ms,
                    serverSelectionTimeoutMS=mongo_settings.server_selection_timeout_ms,
                )

                # Verify connection with ping
                await self._client.admin.command("ping")

                self._database = self._client[mongo_settings.db_name]

                logger.info(
                    "Successfully connected to MongoDB",
                    database=mongo_settings.db_name,
                )

            except Exception as e:
                logger.error("Failed to connect to MongoDB", error=str(e))
                self._client = None
                self._database = None
                raise

    async def disconnect(self) -> None:
        """Close the MongoDB connection."""
        async with self._lock:
            if self._client is None:
                logger.debug("No active MongoDB connection to close")
                return

            logger.info("Disconnecting from MongoDB")
            self._client.close()
            self._client = None
            self._database = None
            logger.info("Disconnected from MongoDB")

    async def health_check(self) -> dict:
        """
        Perform a health check on the database connection.

        Returns:
            dict with status and latency information
        """
        try:
            if self._client is None:
                return {
                    "status": "disconnected",
                    "healthy": False,
                    "error": "No active connection",
                }

            start = asyncio.get_event_loop().time()
            await self._client.admin.command("ping")
            latency_ms = (asyncio.get_event_loop().time() - start) * 1000

            # Get server info
            server_info = await self._client.server_info()

            return {
                "status": "connected",
                "healthy": True,
                "latency_ms": round(latency_ms, 2),
                "server_version": server_info.get("version", "unknown"),
            }

        except Exception as e:
            logger.error("Health check failed", error=str(e))
            return {
                "status": "error",
                "healthy": False,
                "error": str(e),
            }

    async def __aenter__(self) -> AsyncIOMotorDatabase:
        """Async context manager entry."""
        await self.connect()
        return self.database

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect()


# Global connection instance (singleton pattern)
_db_connection: DatabaseConnection | None = None


async def get_database() -> AsyncIOMotorDatabase:
    """
    Get the database instance, connecting if necessary.

    This is the primary way to access the database throughout the application.

    Returns:
        AsyncIOMotorDatabase instance

    Example:
        db = await get_database()
        users = db.users
        await users.insert_one({"name": "John"})
    """
    global _db_connection

    if _db_connection is None:
        _db_connection = DatabaseConnection()

    if _db_connection._client is None:
        await _db_connection.connect()

    return _db_connection.database


async def get_connection() -> DatabaseConnection:
    """
    Get the DatabaseConnection instance.

    Useful when you need access to connection management methods
    like health_check() or disconnect().
    """
    global _db_connection

    if _db_connection is None:
        _db_connection = DatabaseConnection()

    return _db_connection


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncIOMotorDatabase, None]:
    """
    Context manager for database sessions.

    Provides a clean way to work with the database in a scoped manner.
    Note: MongoDB doesn't have traditional sessions like SQL databases,
    but this provides consistent access patterns.

    Example:
        async with get_db_session() as db:
            await db.users.find_one({"username": "john"})
    """
    db = await get_database()
    try:
        yield db
    finally:
        # Connection pooling handles cleanup
        pass


async def close_database() -> None:
    """
    Close the global database connection.

    Should be called during application shutdown.
    """
    global _db_connection

    if _db_connection is not None:
        await _db_connection.disconnect()
        _db_connection = None
