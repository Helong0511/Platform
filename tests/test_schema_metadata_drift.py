"""应用启动 schema drift 检查的隔离单元测试。"""

from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine

from app.bootstrap.lifespan import _schema_metadata_drift


def test_schema_metadata_drift_reports_missing_tables_and_columns():
    metadata = MetaData()
    Table(
        "required_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("required_value", String(64), nullable=False),
    )
    Table(
        "another_required_table",
        metadata,
        Column("id", Integer, primary_key=True),
    )

    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE required_table (id INTEGER PRIMARY KEY)"
            )

        with engine.connect() as connection:
            drift = _schema_metadata_drift(connection, metadata)

        assert drift == {
            "missing_tables": ["another_required_table"],
            "missing_columns": {"required_table": ["required_value"]},
        }
    finally:
        engine.dispose()


def test_schema_metadata_drift_accepts_complete_existing_schema():
    metadata = MetaData()
    Table(
        "required_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("required_value", String(64), nullable=False),
    )

    engine = create_engine("sqlite:///:memory:")
    try:
        metadata.create_all(engine)
        with engine.connect() as connection:
            drift = _schema_metadata_drift(connection, metadata)

        assert drift == {"missing_tables": [], "missing_columns": {}}
    finally:
        engine.dispose()
