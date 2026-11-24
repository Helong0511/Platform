"""短链接变更必须与持久化缓存失效事件处于同一事务。"""
from pathlib import Path


def test_short_link_update_enqueues_durable_invalidation_in_service_transaction():
    source = Path("app/services/short_link_service.py").read_text(encoding="utf-8")
    start = source.index("async def update_short_link(")
    end = source.index("async def delete_short_link(", start)
    section = source[start:end]
    assert "await enqueue_short_link_cache_invalidation(self.db, short_link.short_code)" in section


def test_short_link_delete_enqueues_durable_invalidation_in_service_transaction():
    source = Path("app/services/short_link_service.py").read_text(encoding="utf-8")
    start = source.index("async def delete_short_link(")
    section = source[start:]
    assert "await enqueue_short_link_cache_invalidation(self.db, short_code)" in section


def test_short_link_api_commits_business_transaction_before_immediate_cache_delete():
    source = Path("app/api_v1/tracking/short_links.py").read_text(encoding="utf-8")
    update_start = source.index("async def update_short_link(")
    delete_start = source.index("async def delete_short_link(", update_start)
    update_section = source[update_start:delete_start]
    update_commit = update_section.index("await commit_audit_log(db)")
    update_delete = update_section.index("await invalidate_short_link_cache(", update_commit)
    assert update_commit < update_delete

    delete_section = source[delete_start:]
    delete_commit = delete_section.index("await commit_audit_log(db)")
    delete_cache = delete_section.index("await invalidate_short_link_cache(", delete_commit)
    assert delete_commit < delete_cache


def test_scheduled_short_link_reactivation_enqueues_invalidation_in_same_transaction():
    source = Path("app/scheduler_module/tasks/short_link_tasks.py").read_text(encoding="utf-8")
    start = source.index("async def open_closed_short_links_task(")
    section = source[start:]
    assert "ShortLink.short_code" in section
    assert "await enqueue_short_link_cache_invalidation(db, short_code, flush=False)" in section
    assert section.index("await enqueue_short_link_cache_invalidation(db, short_code, flush=False)") < section.index("await db.flush()") < section.index("await db.commit()")
