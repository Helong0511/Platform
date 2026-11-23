"""广告主缓存失效必须发生在数据库事务提交之后。"""
from pathlib import Path


def test_advertiser_update_reinvalidates_cache_after_commit():
    source = Path("app/services/cpl/advertiser_service.py").read_text(encoding="utf-8")
    update_start = source.index("async def update_advertiser")
    update_end = source.index("async def delete_advertiser", update_start)
    update_source = source[update_start:update_end]
    commit_pos = update_source.index("await commit_audit_log(self.db)")
    invalidate_pos = update_source.index(
        "await CacheInvalidator.invalidate_advertiser_cache(advertiser_id)",
        commit_pos,
    )
    assert invalidate_pos > commit_pos


def test_advertiser_delete_commits_then_invalidates_cache():
    source = Path("app/services/cpl/advertiser_service.py").read_text(encoding="utf-8")
    delete_start = source.index("async def delete_advertiser")
    delete_source = source[delete_start:]
    flush_pos = delete_source.index("await self.db.flush()")
    commit_pos = delete_source.index("await commit_audit_log(self.db)", flush_pos)
    invalidate_pos = delete_source.index(
        "await CacheInvalidator.invalidate_advertiser_cache(advertiser_id)",
        commit_pos,
    )
    assert flush_pos < commit_pos < invalidate_pos
