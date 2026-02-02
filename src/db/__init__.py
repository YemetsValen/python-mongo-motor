"""
Database connection and management module.

Provides async MongoDB connectivity through Motor driver.
"""

from src.db.connection import (
    Database,
    close_database,
    get_database,
    ping_database,
)
from src.db.indexes import ensure_indexes

__all__ = [
    "Database",
    "get_database",
    "close_database",
    "ping_database",
    "ensure_indexes",
]
