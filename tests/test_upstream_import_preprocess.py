"""上游导入预处理。"""
import os
import sys

os.environ.setdefault("UNIT_TEST", "1")
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def test_preprocess_addermobi_match_counts():
    from app.scheduler_module.upstream_import import preprocess_addermobi_match_counts

    data = [
        {
            "AdRequests": 100,
            "AdRequestsCoverage": 0.5,
            "MatchedAdRequests": 0,
        }
    ]
    out = preprocess_addermobi_match_counts(data)
    assert out[0]["MatchedAdRequests"] == 50
