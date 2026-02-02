"""
Test suite for the Match Predictions System.

This package contains unit tests, integration tests, and fixtures
for testing the predictions system components.

Test Structure:
    - conftest.py: Shared fixtures and configuration
    - test_models.py: Tests for Pydantic models
    - test_repositories.py: Tests for database repositories
    - test_services.py: Tests for business logic services

Running Tests:
    pytest                          # Run all tests
    pytest -v                       # Verbose output
    pytest --cov=src               # With coverage
    pytest tests/test_models.py    # Run specific test file
"""

import pytest

# Mark all tests in this package as asyncio tests by default
pytestmark = pytest.mark.asyncio
