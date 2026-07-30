import pytest

from database import init_db


@pytest.fixture(scope="session", autouse=True)
def initialize_test_database() -> None:
    """Create and seed the test database before the first test runs."""
    init_db()
