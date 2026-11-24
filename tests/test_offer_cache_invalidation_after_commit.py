"""Offer CRUD 必须在业务事务内登记 Outbox，并在提交后立即尝试清理热点键。"""
from pathlib import Path


def test_offer_create_enqueues_durable_invalidation_in_service_transaction():
    source = Path("app/services/cpl/offer_service.py").read_text(encoding="utf-8")
    start = source.index("async def create_offer(")
    end = source.index("async def update_offer(", start)
    section = source[start:end]
    assert "await enqueue_offer_cache_invalidation(self.db, offer.id)" in section
    assert "CacheInvalidator.invalidate_offer_cache" not in section


def test_offer_update_enqueues_durable_invalidation_in_service_transaction():
    source = Path("app/services/cpl/offer_service.py").read_text(encoding="utf-8")
    start = source.index("async def update_offer(")
    end = source.index("async def delete_offer(", start)
    section = source[start:end]
    assert "await enqueue_offer_cache_invalidation(self.db, offer.id)" in section
    assert "CacheInvalidator.invalidate_offer_cache" not in section


def test_offer_delete_enqueues_durable_invalidation_in_service_transaction():
    source = Path("app/services/cpl/offer_service.py").read_text(encoding="utf-8")
    start = source.index("async def delete_offer(")
    section = source[start:]
    assert "await enqueue_offer_cache_invalidation(self.db, offer_id)" in section
    assert "CacheInvalidator.invalidate_offer_cache" not in section


def test_offer_create_commits_before_immediate_hot_key_invalidation():
    source = Path("app/api_v1/cpl/offers.py").read_text(encoding="utf-8")
    start = source.index("async def create_offer(")
    end = source.index("@router.get(", start)
    section = source[start:end]
    commit_pos = section.index("await commit_audit_log(db)")
    invalidate_pos = section.index("await invalidate_hot_offer_cache(offer.id)", commit_pos)
    assert commit_pos < invalidate_pos


def test_offer_update_commits_before_immediate_hot_key_invalidation():
    source = Path("app/api_v1/cpl/offers.py").read_text(encoding="utf-8")
    start = source.index("async def update_offer(")
    end = source.index("@router.delete(", start)
    section = source[start:end]
    commit_pos = section.index("await commit_audit_log(db)")
    invalidate_pos = section.index("await invalidate_hot_offer_cache(offer.id)", commit_pos)
    assert commit_pos < invalidate_pos


def test_offer_delete_commits_before_immediate_hot_key_invalidation():
    source = Path("app/api_v1/cpl/offers.py").read_text(encoding="utf-8")
    start = source.index("async def delete_offer(")
    section = source[start:]
    commit_pos = section.index("await commit_audit_log(db)")
    invalidate_pos = section.index("await invalidate_hot_offer_cache(offer_id)", commit_pos)
    response_pos = section.index('return ResponseBaseSchema.success(data={"message": "Offer已删除"})')
    assert commit_pos < invalidate_pos < response_pos
