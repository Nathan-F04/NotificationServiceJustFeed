"""Conftest file"""

import pytest
from fastapi.testclient import TestClient
from notification_service.notification import app

@pytest.fixture
def client():
    """Client for testing"""
    with TestClient(app) as c:
        yield c
