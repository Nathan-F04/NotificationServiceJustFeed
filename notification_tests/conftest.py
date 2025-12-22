# tests/conftest.py
import pytest
from fastapi.testclient import TestClient
from notification_service.order_success_worker import app

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c