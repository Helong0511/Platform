"""CPL 扣量配置缓存必须由数据库 Generation 隔离。"""
from pathlib import Path


def test_every_deduction_config_mutation_advances_generation_in_business_session():
    source = Path("app/services/cpl/conversion_deduction_service.py").read_text(encoding="utf-8")
    methods = (
        "create_deduction_config",
        "update_deduction_config",
        "update_deduction_config_status",
        "delete_deduction_config",
        "batch_update_status",
        "batch_delete",
    )
    for index, name in enumerate(methods):
        start = source.index(f"async def {name}(")
        later = [
            source.find(f"async def {other}(", start + 1)
            for other in methods[index + 1 :]
        ]
        end = min((position for position in later if position >= 0), default=len(source))
        section = source[start:end]
        assert 'advance_cache_generation(self.db, namespace="cpl:deduction_config")' in section
        assert "invalidate_config_cache(" not in section


def test_deduction_cache_generation_is_reused_for_cache_fill():
    source = Path("app/core/deduction/deduction_cache.py").read_text(encoding="utf-8")
    assert 'get_cache_generation(self.db, namespace="cpl:deduction_config")' in source
    assert "await self._save_to_cache(level, target_id, config, generation)" in source
    assert "generation: int," in source


def test_generic_invalidation_worker_accepts_deduction_namespace():
    source = Path("app/services/cache_invalidation_outbox_worker.py").read_text(encoding="utf-8")
    assert '"cpl:deduction_config"' in source
