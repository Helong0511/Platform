"""Ambiguous JSON responses must never mark a downstream postback as successful."""
import json

import pytest

from app.core.postback.forwarding.success_checker import SuccessChecker


@pytest.mark.parametrize(
    "body",
    [
        '"error"',
        "[]",
        "[{\"status\":\"failed\"}]",
        "0",
        "404",
        "false",
        "{\"status\":\"failed\"}",
    ],
)
def test_json_check_fails_closed_without_expected_value(body):
    ok, _ = SuccessChecker.check(
        status_code=200,
        response_content=body,
        success_check_config=json.dumps({"type": "json"}),
    )
    assert ok is False


def test_json_check_requires_configured_path_and_expected_value():
    ok, _ = SuccessChecker.check(
        status_code=200,
        response_content='{"status":"failed"}',
        success_check_config=json.dumps(
            {"type": "json", "path": "status", "expected": "success"}
        ),
    )
    assert ok is False


def test_json_check_accepts_matching_nested_value():
    ok, _ = SuccessChecker.check(
        status_code=200,
        response_content='{"data":{"result":"success"}}',
        success_check_config=json.dumps(
            {"type": "json", "path": "data.result", "expected": "success"}
        ),
    )
    assert ok is True


def test_json_check_accepts_explicit_legacy_success_indicator():
    ok, _ = SuccessChecker.check(
        status_code=200,
        response_content="success",
        success_check_config=json.dumps({"type": "json"}),
    )
    assert ok is True


def test_invalid_success_check_config_falls_back_to_status_range():
    ok, _ = SuccessChecker.check(
        status_code=503,
        response_content="temporarily unavailable",
        success_check_config="{invalid",
    )
    assert ok is False
