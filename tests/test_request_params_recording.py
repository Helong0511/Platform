import json

from starlette.datastructures import QueryParams


def _to_multi_dict(params: QueryParams) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for k, v in params.multi_items():
        out.setdefault(str(k), []).append("" if v is None else str(v))
    return out


def test_query_params_record_all_values_and_duplicates():
    qp = QueryParams("a=1&a=2&b=&c=3")
    multi = _to_multi_dict(qp)
    assert multi == {"a": ["1", "2"], "b": [""], "c": ["3"]}

    s = json.dumps(multi, ensure_ascii=False)
    loaded = json.loads(s)
    assert loaded["a"] == ["1", "2"]

