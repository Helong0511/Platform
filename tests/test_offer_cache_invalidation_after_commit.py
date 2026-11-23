"""Offer CRUD 必须在业务事务提交后再次失效缓存。"""
from pathlib import Path


def test_offer_create_commits_before_post_commit_cache_invalidation():
    source = Path("app/api_v1/cpl/offers.py").read_text(encoding="utf-8")
    start = source.index("async def create_offer(")
    end = source.index("@router.get(", start)
    section = source[start:end]
    commit_pos = section.index("await commit_audit_log(db)")
    invalidate_pos = section.index("await CacheInvalidator.invalidate_offer_cache(offer.id)", commit_pos)
    reload_pos = section.index("await offer_service.get_offer_by_id", invalidate_pos)
    assert commit_pos < invalidate_pos < reload_pos


def test_offer_update_commits_before_post_commit_cache_invalidation():
    source = Path("app/api_v1/cpl/offers.py").read_text(encoding="utf-8")
    start = source.index("async def update_offer(")
    end = source.index("@router.delete(", start)
    section = source[start:end]
    commit_pos = section.index("await commit_audit_log(db)")
    invalidate_pos = section.index("await CacheInvalidator.invalidate_offer_cache(offer.id)", commit_pos)
    reload_pos = section.index("await offer_service.get_offer_by_id", invalidate_pos)
    assert commit_pos < invalidate_pos < reload_pos


def test_offer_delete_commits_before_post_commit_cache_invalidation():
    source = Path("app/api_v1/cpl/offers.py").read_text(encoding="utf-8")
    start = source.index("async def delete_offer(")
    section = source[start:]
    commit_pos = section.index("await commit_audit_log(db)")
    invalidate_pos = section.index("await CacheInvalidator.invalidate_offer_cache(offer_id)", commit_pos)
    response_pos = section.index('return ResponseBaseSchema.success(data={"message": "Offer已删除"})')
    assert commit_pos < invalidate_pos < response_pos
