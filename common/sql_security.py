from __future__ import annotations

from typing import Optional

import sqlglot
from sqlglot import exp


_DIALECT_ALIASES = {
    "pg": "postgres",
    "postgresql": "postgres",
    "kingbase": "postgres",
    "redshift": "redshift",
    "mysql": "mysql",
    "doris": "mysql",
    "starrocks": "mysql",
    "elasticsearch": "mysql",
    "es": "mysql",
    "oracle": "oracle",
    "dm": "oracle",
    "sqlserver": "tsql",
    "sql_server": "tsql",
    "sqlserverlegacy": "tsql",
    "sqlserver_legacy": "tsql",
    "sqlservercompat": "tsql",
    "sqlserver_compat": "tsql",
    "ck": "clickhouse",
    "clickhouse": "clickhouse",
}

_FORBIDDEN_EXPRESSIONS = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
    exp.Create,
    exp.Copy,
    exp.Grant,
    exp.Revoke,
    exp.Merge,
    exp.Command,
    exp.Into,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
    exp.Set,
    exp.Use,
)


def _normalize_dialect(dialect: Optional[str]) -> Optional[str]:
    if not dialect:
        return None

    normalized = dialect.strip().lower()
    return _DIALECT_ALIASES.get(normalized, normalized or None)


def validate_read_only_sql(
    sql: str,
    dialect: str | None = None,
) -> tuple[bool, str | None]:
    """
    Validate that SQL is a single read-only query.

    Only SELECT-style query roots are allowed. Anything else fails closed.
    """
    if not sql or not sql.strip():
        return False, "Security check failed: SQL is empty"

    parse_kwargs = {}
    normalized_dialect = _normalize_dialect(dialect)
    if normalized_dialect:
        parse_kwargs["read"] = normalized_dialect

    try:
        statements = sqlglot.parse(sql.strip(), **parse_kwargs)
    except Exception:
        return False, "Security check failed: unable to parse SQL as a read-only query"

    if len(statements) != 1:
        return False, "Security check failed: only a single read-only query is allowed"

    statement = statements[0]
    if not isinstance(statement, exp.Query):
        return False, "Security check failed: only read-only SELECT queries are allowed"

    for node in statement.find_all(*_FORBIDDEN_EXPRESSIONS):
        node_name = type(node).__name__.upper()
        return False, f"Security check failed: {node_name} operations are not allowed"

    return True, None
