"""剩余管理端列表深分页预算回归测试。"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.models import User, UserRole
from app.core.query_builder import QueryBuilder
from app.services.audit_log_service import AuditLogService
from app.services.client_service import ClientService
from app.services.product_service import ProductService
from app.services.cpl.publisher_service import PublisherService
from app.services.cpl.advertiser_service import AdvertiserService
from app.services.cpl.discount_service import DiscountService
from app.services.cpl.postback_conversion_service import PostbackConversionService
from app.services.cpl.cap_service import CapService
from app.services.scheduled_task_service import ScheduledTaskService
from app.services.cpl.offer.queries.list_query import OfferListQuery
from app.services.cpl.deduction.queries.config_list_query import DeductionConfigListQuery
from app.services.cpl.deduction.queries.logs_query import DeductionLogsQuery
from app.services.session_service import SessionService
from app.api_v1.system.sessions import get_blacklist
from app.api_v1.system.countries import list_countries
from app.api_v1.system.cloak_configs import list_cloak_configs
from app.api_v1.system.sensitive_path_probes import (
    get_sensitive_path_probe_logs,
    get_blocked_ips,
)
from app.api_v1.system.third_party_reports import get_third_party_reports
from app.api_v1.system.ad_data_health import get_alerts, get_baselines
from app.services.ad_data import baseline_service
from app.api_v1.cpl.affiliate_debug.affiliate_tests import get_affiliate_tests


class _NoDB:
    def __init__(self):
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        raise AssertionError("pagination budget must reject before database access")


def _admin():
    return SimpleNamespace(id=1, role=UserRole.ADMIN)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("service_factory", "method_name", "kwargs"),
    [
        (AuditLogService, "get_audit_logs", {"page": 1002, "page_size": 100}),
        (ClientService, "list_clients", {"page": 1002, "page_size": 100}),
        (
            ProductService,
            "get_products",
            {"current_user": _admin(), "page": 1002, "page_size": 100},
        ),
        (
            PublisherService,
            "get_publishers",
            {"current_user": _admin(), "page": 1002, "page_size": 100},
        ),
        (
            AdvertiserService,
            "get_advertisers",
            {"current_user": _admin(), "page": 1002, "page_size": 100},
        ),
        (CapService, "get_caps", {"page": 1002, "page_size": 100}),
        (DiscountService, "get_discounts", {"page": 1002, "page_size": 100}),
        (
            ScheduledTaskService,
            "get_scheduled_tasks",
            {"page": 1002, "page_size": 100},
        ),
        (
            OfferListQuery,
            "fetch",
            {"current_user": _admin(), "page": 1002, "page_size": 100},
        ),
        (DeductionConfigListQuery, "fetch", {"page": 1002, "page_size": 100}),
        (DeductionLogsQuery, "fetch", {"page": 1002, "page_size": 100}),
        (
            SessionService,
            "get_my_sessions",
            {"user_id": 1, "page": 1002, "page_size": 100},
        ),
        (
            SessionService,
            "get_user_sessions",
            {"user_id": 1, "page": 1002, "page_size": 100},
        ),
    ],
)
async def test_remaining_list_services_reject_deep_pagination_before_db(
    service_factory,
    method_name,
    kwargs,
):
    db = _NoDB()
    service = service_factory(db)

    with pytest.raises(HTTPException):
        await getattr(service, method_name)(**kwargs)

    assert db.statements == []


@pytest.mark.asyncio
async def test_audit_log_rejects_zero_page_size_before_db():
    db = _NoDB()

    with pytest.raises(HTTPException):
        await AuditLogService(db).get_audit_logs(page=1, page_size=0)

    assert db.statements == []


@pytest.mark.asyncio
async def test_session_service_rejects_invalid_page_before_user_lookup():
    db = _NoDB()

    with pytest.raises(HTTPException):
        await SessionService(db).get_user_sessions(
            user_id=1,
            page=0,
            page_size=10,
        )

    assert db.statements == []


@pytest.mark.asyncio
async def test_token_blacklist_route_rejects_deep_pagination_before_db():
    db = _NoDB()

    with pytest.raises(HTTPException):
        await get_blacklist(
            request=SimpleNamespace(),
            db=db,
            current_user=_admin(),
            page=1002,
            page_size=100,
            user_id=None,
        )

    assert db.statements == []


@pytest.mark.asyncio
async def test_country_list_route_rejects_deep_pagination_before_db():
    db = _NoDB()

    with pytest.raises(HTTPException):
        await list_countries(
            page=1002,
            page_size=100,
            keyword=None,
            continent=None,
            db=db,
            _current_user=_admin(),
        )

    assert db.statements == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "kwargs"),
    [
        (list_cloak_configs, {"page": 1002, "page_size": 100}),
        (
            get_sensitive_path_probe_logs,
            {"page": 1002, "page_size": 100, "current_user": _admin()},
        ),
        (
            get_blocked_ips,
            {"page": 1002, "page_size": 100, "current_user": _admin()},
        ),
        (
            get_third_party_reports,
            {"page": 1002, "page_size": 100, "current_user": _admin()},
        ),
        (get_alerts, {"limit": 500, "offset": 100001}),
        (get_baselines, {"limit": 1000, "offset": 100001}),
    ],
)
async def test_system_list_routes_reject_excessive_offsets_before_db(handler, kwargs):
    db = _NoDB()
    with pytest.raises(HTTPException):
        await handler(db=db, **kwargs)
    assert db.statements == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("service_method", "kwargs"),
    [
        (baseline_service.list_alerts, {"limit": 500, "offset": 100001}),
        (baseline_service.list_baselines, {"limit": 1000, "offset": 100001}),
    ],
)
async def test_health_data_services_reject_excessive_offsets_before_db(
    service_method,
    kwargs,
):
    db = _NoDB()
    with pytest.raises(HTTPException):
        await service_method(db, **kwargs)
    assert db.statements == []


@pytest.mark.asyncio
async def test_affiliate_test_list_rejects_deep_pagination_before_db():
    db = _NoDB()

    with pytest.raises(HTTPException):
        await get_affiliate_tests(
            page=1002,
            page_size=100,
            db=db,
            current_user=_admin(),
        )

    assert db.statements == []


@pytest.mark.asyncio
async def test_postback_conversion_list_rejects_deep_pagination_before_db():
    db = _NoDB()

    with pytest.raises(HTTPException):
        await PostbackConversionService().get_postback_conversions(
            request=SimpleNamespace(),
            platform=None,
            product_id=None,
            client_id=None,
            conversion_or_click_id=None,
            click_id=None,
            offer_id=None,
            publisher_id=None,
            advertiser_id=None,
            conversion_status=None,
            start_date=None,
            end_date=None,
            page=102,
            page_size=1000,
            db=db,
            current_user=_admin(),
        )

    assert db.statements == []


@pytest.mark.asyncio
async def test_query_builder_rejects_deep_offset_before_db():
    db = _NoDB()

    with pytest.raises(HTTPException):
        await QueryBuilder(db, User).base().paginated(page=1002, page_size=100)

    assert db.statements == []


def test_query_builder_preserves_bounded_internal_export_page_size():
    builder = QueryBuilder(_NoDB(), User).base().paginate(page=1, page_size=10000)

    assert builder._query._limit_clause.value == 10000
    assert builder._query._offset_clause.value == 0
