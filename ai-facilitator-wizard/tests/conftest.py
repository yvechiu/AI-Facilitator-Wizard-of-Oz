import pytest
from unittest.mock import Mock
from src.database import Database
from src.session_service import SessionService
from src.message_service import load_messages

@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.sqlite3")

@pytest.fixture
def session(db):
    service = SessionService(db)
    sid = service.create("測試", "前測", "WOZ", "123456789012345678")
    service.start(sid)
    return sid

@pytest.fixture
def template():
    return load_messages()[0]

@pytest.fixture
def client():
    obj = Mock()
    obj.token = "private-test-token"
    return obj
