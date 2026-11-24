"""Offer 缓存失效 Outbox 的任务注册契约。"""
from app.scheduler_module.task_config import TASK_CONFIGS
from app.scheduler_module.task_names import (
    ALL_TASK_NAMES,
    OFFER_CACHE_INVALIDATION_TASK_NAME,
    TASK_NAME_MAP,
)
from app.scheduler_module.task_registry import load_function_by_path
from app.scheduler_module.tasks.offer_cache_invalidation_task import (
    process_offer_cache_invalidation_task,
)


def test_offer_cache_invalidation_task_is_registered_and_resolvable():
    config = TASK_CONFIGS[OFFER_CACHE_INVALIDATION_TASK_NAME]

    assert OFFER_CACHE_INVALIDATION_TASK_NAME in ALL_TASK_NAMES
    assert TASK_NAME_MAP["offer_cache_invalidation_task"] == OFFER_CACHE_INVALIDATION_TASK_NAME
    assert config["task_name"] == OFFER_CACHE_INVALIDATION_TASK_NAME
    assert config["cron_expression"] == "*/1 * * * *"

    task = load_function_by_path(
        f"{config['task_module']}.{config['task_function']}"
    )
    assert task is process_offer_cache_invalidation_task

    getter = load_function_by_path(
        f"{config['result_getter_module']}.{config['result_getter_function']}"
    )
    from app.scheduler_module.task_result_store import get_task_result
    assert getter is get_task_result
