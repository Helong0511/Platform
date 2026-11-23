"""敏感路径日志模型的索引定义应与 SQL 基线保持一致，避免重复单列索引。"""
from app.models.security import SensitivePathProbeLog


def test_sensitive_probe_created_at_has_one_explicit_index():
    created_at_indexes = [
        index
        for index in SensitivePathProbeLog.__table__.indexes
        if [column.name for column in index.columns] == ["created_at"]
    ]

    assert len(created_at_indexes) == 1
    assert created_at_indexes[0].name == "idx_sensitive_probe_created_at"
