"""url_params 读取规范化。"""
import os
import sys

os.environ.setdefault("UNIT_TEST", "1")
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def test_normalize_list_dp_to_scalar():
    from app.core.url.url_params_util import normalize_url_params

    raw = {
        "dp": ["149"],
        "fbclid": ["abc", "ignored_second"],
        "cloak_visit": True,
        "cloak_dp_effective": "149",
        "cloak_dp_query": "149",
    }
    out = normalize_url_params(raw)
    assert out["dp"] == "149"
    assert out["fbclid"] == "abc"
    assert out["cloak_visit"] is True
    assert out["cloak_dp_effective"] == "149"


def test_resolve_dp_prefers_cloak_dp_effective():
    from app.core.url.url_params_util import resolve_dp_from_url_params

    assert resolve_dp_from_url_params({"dp": ["master"], "cloak_dp_effective": "149"}) == "149"
    assert resolve_dp_from_url_params({"dp": ["149"]}) == "149"
    assert resolve_dp_from_url_params({"dp": "master"}) == "master"
    assert resolve_dp_from_url_params({}) is None


def test_scalar_query_value_skips_bool():
    from app.core.url.url_params_util import scalar_query_value

    assert scalar_query_value(True) is None
    assert scalar_query_value(["x"]) == "x"


def test_pack_query_params_for_storage():
    from app.core.url.url_params_util import pack_query_params_for_storage

    packed = pack_query_params_for_storage({"dp": "149", "fbclid": "abc"})
    assert packed == {"dp": ["149"], "fbclid": ["abc"]}


def test_build_click_association_payload_normalizes_list():
    from app.core.url.url_params_util import build_click_association_payload

    payload = build_click_association_payload(
        {
            "click_id": "tok1",
            "offer_id": 10,
            "url_params": {"dp": ["149"], "fbclid": ["x"]},
        }
    )
    assert payload["url_params"]["dp"] == "149"
    assert payload["url_params"]["fbclid"] == "x"
    assert payload["click_id"] == "tok1"


def test_canonicalize_scalar_to_multi_idempotent():
    from app.core.url.url_params_util import (
        canonicalize_url_params_for_storage,
        canonicalize_url_params_json_text,
        needs_storage_canonicalization,
    )

    scalar = '{"dp":"149","fbclid":"x","cloak_visit":true,"cloak_dp_effective":"149"}'
    assert needs_storage_canonicalization({"dp": "149"}) is True
    assert needs_storage_canonicalization({"dp": ["149"]}) is False

    canon = canonicalize_url_params_for_storage(
        {"dp": "149", "cloak_visit": True, "cloak_dp_effective": "149"}
    )
    assert canon["dp"] == ["149"]
    assert canon["cloak_visit"] is True
    assert canon["cloak_dp_effective"] == "149"

    new_text = canonicalize_url_params_json_text(scalar)
    assert new_text is not None
    assert canonicalize_url_params_json_text(new_text) is None


def test_click_persist_canonicalizes_scalar_url_params():
    from app.core.tracking.click_persist import _canonicalize_click_data_url_params
    import json

    out = _canonicalize_click_data_url_params(
        {"click_id": "c1", "url_params": '{"dp":"1","fbclid":"f"}'}
    )
    data = json.loads(out["url_params"])
    assert data["dp"] == ["1"]
    assert data["fbclid"] == ["f"]


def test_merge_association_url_params_token_empty_keeps_db():
    from app.core.url.url_params_util import merge_association_url_params

    db = {"dp": ["149"], "fbclid": ["x"], "cloak_dp_effective": "149"}
    token = {}
    out = merge_association_url_params(db, token)
    assert out["dp"] == "149"
    assert out["fbclid"] == "x"
    assert out["cloak_dp_effective"] == "149"


def test_merge_association_url_params_token_overrides_scalar():
    from app.core.url.url_params_util import merge_association_url_params

    db = {"dp": ["149"], "utm_source": ["db"]}
    token = {"utm_source": "token", "sub1": "a"}
    out = merge_association_url_params(db, token)
    assert out["dp"] == "149"
    assert out["utm_source"] == "token"
    assert out["sub1"] == "a"


def test_merge_token_db_association_via_associator():
    from app.core.postback.transformers.click_associator import ClickAssociator

    db_assoc = {
        "click_id": "c1",
        "publisher_id": 10,
        "url_params": {"dp": ["149"], "fbclid": ["from_db"]},
    }
    token_assoc = {
        "offer_id": 1,
        "publisher_id": 20,
        "url_params": {},
    }
    merged = ClickAssociator._merge_token_and_db_association(db_assoc, token_assoc)
    assert merged["publisher_id"] == 20
    assert merged["url_params"]["fbclid"] == "from_db"
    assert merged["url_params"]["dp"] == "149"


def test_url_builder_params_from_list_url_params():
    from app.core.postback.forwarding.url_builder import UrlBuilder

    params = UrlBuilder._build_params(
        {"conversion_id": "c1"},
        {
            "click_id": "fallback_cid",
            "offer_id": 99,
            "url_params": {"click_id": ["from_up"], "offer_id": ["88"]},
        },
    )
    assert params["click_id"] == "from_up"
    assert params["offer_id"] == "88"
