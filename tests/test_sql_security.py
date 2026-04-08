import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agent.text2sql.database import db_service as db_service_module
from agent.text2sql.database.db_service import DatabaseService
from common.datasource_util import ConnectType
from common.sql_security import validate_read_only_sql
from services import text2_sql_service as text2_sql_service_module


def build_service():
    service = object.__new__(DatabaseService)
    service._engine = None
    service._datasource_id = None
    service._datasource_type = None
    service._datasource_config = None
    return service


class FakeResult:
    def fetchall(self):
        return [(1,)]

    def keys(self):
        return ["value"]


class FakeConnection:
    def __init__(self, result=None):
        self.result = result or FakeResult()
        self.execute_calls = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, _sql):
        self.execute_calls += 1
        return self.result


class FakeEngine:
    def __init__(self, connection=None):
        self.connection = connection or FakeConnection()
        self.connect_calls = 0

    def connect(self):
        self.connect_calls += 1
        return self.connection


@pytest.mark.parametrize(
    ("sql", "dialect"),
    [
        ("SELECT 1", None),
        ("WITH a AS (SELECT 1) SELECT * FROM a", "postgres"),
        ("SELECT 1 UNION SELECT 2", "postgres"),
        ("SELECT 1;", None),
    ],
)
def test_validate_read_only_sql_allows_queries(sql, dialect):
    is_allowed, reason = validate_read_only_sql(sql, dialect=dialect)

    assert is_allowed is True
    assert reason is None


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE t",
        "INSERT INTO t VALUES (1)",
        "COPY t FROM PROGRAM 'id'",
        "SELECT * INTO audit_log FROM sensitive_data",
        "SELECT 1; DROP TABLE t",
        "",
        "NOT VALID SQL",
    ],
)
def test_validate_read_only_sql_rejects_dangerous_or_invalid_sql(sql):
    is_allowed, reason = validate_read_only_sql(sql, dialect="postgres")

    assert is_allowed is False
    assert reason


def test_execute_sql_blocks_dangerous_sql_before_sqlalchemy_execution():
    service = build_service()
    engine = FakeEngine()
    service._engine = engine

    state = {"generated_sql": "DROP TABLE sensitive_data"}

    result_state = service.execute_sql(state)

    assert result_state["execution_result"].success is False
    assert "Security check failed" in result_state["execution_result"].error
    assert engine.connect_calls == 0


def test_execute_sql_blocks_dangerous_sql_before_native_driver_execution(monkeypatch):
    service = build_service()
    service._datasource_id = 1
    service._datasource_type = "doris"
    service._datasource_config = "encrypted-config"

    execute_called = False

    def fake_execute_query(*args, **kwargs):
        nonlocal execute_called
        execute_called = True
        raise AssertionError("native driver execution should not be called")

    monkeypatch.setattr(
        db_service_module.DB,
        "get_db",
        lambda *args, **kwargs: SimpleNamespace(connect_type=ConnectType.py_driver),
    )
    monkeypatch.setattr(
        db_service_module.DatasourceConnectionUtil,
        "execute_query",
        fake_execute_query,
    )

    state = {"generated_sql": "COPY t FROM PROGRAM 'id'"}
    result_state = service.execute_sql(state)

    assert result_state["execution_result"].success is False
    assert "Security check failed" in result_state["execution_result"].error
    assert execute_called is False


def test_execute_sql_allows_safe_read_only_query():
    service = build_service()
    engine = FakeEngine()
    service._engine = engine

    state = {"generated_sql": "SELECT 1"}
    result_state = service.execute_sql(state)

    assert result_state["execution_result"].success is True
    assert result_state["execution_result"].data == [{"value": 1}]
    assert engine.connect_calls == 1
    assert engine.connection.execute_calls == 1


def test_query_ex_blocks_dangerous_sql_before_session_execution(monkeypatch):
    class GuardPool:
        def get_session(self):
            raise AssertionError("database session should not be opened")

    monkeypatch.setattr(text2_sql_service_module, "pool", GuardPool())

    with pytest.raises(ValueError, match="Security check failed"):
        text2_sql_service_module.query_ex("DROP TABLE sensitive_data")
