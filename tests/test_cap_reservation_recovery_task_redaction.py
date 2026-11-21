"""Cap Reservation recovery task must not expose exception payloads."""
import pytest

from app.scheduler_module.task_names import CAP_RESERVATION_RECOVERY_TASK_NAME
from app.scheduler_module.task_result_store import clear_task_result, get_task_result
from app.scheduler_module.tasks import cap_reservation_recovery as recovery_task_module


@pytest.mark.asyncio
async def test_recovery_task_does_not_persist_raw_exception_text(monkeypatch):
    async def fail_recovery():
        raise RuntimeError("password=secret-value mysql://user:secret@db/private")

    monkeypatch.setattr(recovery_task_module, "recover_cap_reservations", fail_recovery)
    clear_task_result(CAP_RESERVATION_RECOVERY_TASK_NAME)

    with pytest.raises(RuntimeError):
        await recovery_task_module.cap_reservation_recovery_task()

    result = get_task_result(CAP_RESERVATION_RECOVERY_TASK_NAME)
    assert result is not None
    assert "RuntimeError" in result
    assert "secret-value" not in result
    assert "mysql://" not in result
