from scripts.clickhouse_bootstrap import _statements


def test_statements_keep_sql_after_leading_comments():
    sql = "-- comment about database\nCREATE DATABASE IF NOT EXISTS geoint;\n"
    assert _statements(sql) == ["CREATE DATABASE IF NOT EXISTS geoint"]
