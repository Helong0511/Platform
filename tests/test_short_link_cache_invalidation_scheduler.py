"""短链接缓存失效 Outbox 的任务注册契约。"""
from app.scheduler_module.task_config import TASK_CONFIGS
from app.scheduler_module.task_names import (
    ALL_TASK_NAMES,
    SHORT_LINK_CACHE_INVALIDATION_TASK_NAME,
    TASK_NAME_MAP,
)
from app.scheduler_module.task_registry import load_function_by_path
from app.scheduler_module.tasks.short_link_cache_invalidation_task import (
    process_short_link_cache_invalidation_task,
)


def test_short_link_cache_invalidation_task_is_registered_and_resolvable():
    config = TASK_CONFIGS[SHORT_LINK_CACHE_INVALIDATION_TASK_NAME]

    assert SHORT_LINK_CACHE_INVALIDATION_TASK_NAME in ALL_TASK_NAMES
    assert TASK_NAME_MAP["short_link_cache_invalidation_task"] == SHORT_LINK_CACHE_INVALIDATION_TASK_NAME
    assert config["task_name"] == SHORT_LINK_CACHE_INVALIDATION_TASK_NAME
    assert config["cron_expression"] == "*/1 * * * *"

    task = load_function_by_path(f"{config['task_module']}.{config['task_function']}")
    assert task is process_short_link_cache_invalidation_task
