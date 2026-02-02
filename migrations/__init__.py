"""
Database migrations module.

Provides utilities for managing MongoDB schema migrations,
including version tracking, forward/backward migrations,
and index management.
"""

from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "versions"

__all__ = ["MIGRATIONS_DIR"]
