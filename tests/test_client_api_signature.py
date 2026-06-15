"""客户开放 API 签名验证单元测试。"""
import hashlib

from app.core.api_auth import verify_signature


def test_verify_signature_without_dimension():
    secret = "test-secret-key"
    temp = "client_id=1000&data_type=all&req_time=1745656222&key=test-secret-key"
    expected = hashlib.md5(temp.encode()).hexdigest().lower()

    assert verify_signature(
        client_id=1000,
        secret_key=secret,
        req_time=1745656222,
        sign=expected,
        data_type="all",
    )


def test_verify_signature_with_dimension():
    secret = "test-secret-key"
    temp = (
        "client_id=1000&data_type=day&dimension=country"
        "&end_date=2024-01-31&req_time=1745656222&start_date=2024-01-01"
        f"&key={secret}"
    )
    expected = hashlib.md5(temp.encode()).hexdigest().lower()

    assert verify_signature(
        client_id=1000,
        secret_key=secret,
        req_time=1745656222,
        sign=expected,
        data_type="day",
        dimension="country",
        start_date="2024-01-01",
        end_date="2024-01-31",
    )
