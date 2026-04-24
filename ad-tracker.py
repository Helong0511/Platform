"""
广告追踪值生成、验证、解析工具（增强版）

设计目标：
1) 统一追踪值格式，支持版本演进
2) 提供防篡改签名校验（HMAC-SHA256）
3) 提供过期时间（TTL）与时钟偏移容忍
4) 生成、验证、解析接口职责清晰
5) 错误可分类，便于定位与监控
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any, Callable


TRACKER_VERSION = "v1"
DEFAULT_ALGORITHM = "HS256"
DEFAULT_NONCE_BYTES = 8
DEFAULT_CLOCK_SKEW_SECONDS = 120


class TrackerError(Exception):
    """追踪值处理基类异常。"""


class InvalidTrackerFormatError(TrackerError):
    """追踪值格式非法。"""


class InvalidTrackerSignatureError(TrackerError):
    """追踪值签名非法。"""


class TrackerExpiredError(TrackerError):
    """追踪值已过期。"""


class TrackerNotYetValidError(TrackerError):
    """追踪值签发时间在未来，暂不可用。"""


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(encoded: str) -> bytes:
    if not encoded:
        raise InvalidTrackerFormatError("Base64URL 字段为空")
    padded = encoded + "=" * (-len(encoded) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except Exception as exc:  # pragma: no cover - 防御性分支
        raise InvalidTrackerFormatError("Base64URL 解码失败") from exc


def _json_dumps_compact(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


@dataclass(frozen=True)
class TrackerPayload:
    """追踪值负载结构。"""

    click_id: str
    offer_id: str
    publisher_id: str
    issued_at: int
    expires_at: int
    nonce: str
    extra: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "cid": self.click_id,
            "oid": self.offer_id,
            "pid": self.publisher_id,
            "iat": self.issued_at,
            "exp": self.expires_at,
            "n": self.nonce,
            "ext": self.extra,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "TrackerPayload":
        required_keys = ("cid", "oid", "pid", "iat", "exp", "n", "ext")
        for key in required_keys:
            if key not in data:
                raise InvalidTrackerFormatError(f"负载缺少字段: {key}")

        cid = str(data["cid"]).strip()
        oid = str(data["oid"]).strip()
        pid = str(data["pid"]).strip()
        nonce = str(data["n"]).strip()
        ext = data["ext"]

        if not cid:
            raise InvalidTrackerFormatError("cid 不能为空")
        if not oid:
            raise InvalidTrackerFormatError("oid 不能为空")
        if not pid:
            raise InvalidTrackerFormatError("pid 不能为空")
        if not nonce:
            raise InvalidTrackerFormatError("n 不能为空")
        if not isinstance(ext, dict):
            raise InvalidTrackerFormatError("ext 必须是对象")

        try:
            iat = int(data["iat"])
            exp = int(data["exp"])
        except (TypeError, ValueError) as exc:
            raise InvalidTrackerFormatError("iat/exp 必须是整数时间戳") from exc

        return TrackerPayload(
            click_id=cid,
            offer_id=oid,
            publisher_id=pid,
            issued_at=iat,
            expires_at=exp,
            nonce=nonce,
            extra=ext,
        )


class AdTracker:
    """
    广告追踪值处理器。

    追踪值格式：
        v1.<payload_b64url>.<sig_b64url>

    payload（JSON）字段：
    - cid: click_id
    - oid: offer_id
    - pid: publisher_id
    - iat: 签发时间（秒）
    - exp: 过期时间（秒）
    - n: nonce（防重放辅助字段）
    - ext: 扩展业务字段（对象）
    """

    def __init__(
        self,
        secret_key: str,
        *,
        default_ttl_seconds: int = 3600,
        clock_skew_seconds: int = DEFAULT_CLOCK_SKEW_SECONDS,
        now_fn: Callable[[], int] | None = None,
    ) -> None:
        if not secret_key or not secret_key.strip():
            raise ValueError("secret_key 不能为空")
        if default_ttl_seconds <= 0:
            raise ValueError("default_ttl_seconds 必须大于 0")
        if clock_skew_seconds < 0:
            raise ValueError("clock_skew_seconds 不能小于 0")

        self._secret = secret_key.encode("utf-8")
        self._default_ttl_seconds = int(default_ttl_seconds)
        self._clock_skew_seconds = int(clock_skew_seconds)
        self._now_fn = now_fn or (lambda: int(time.time()))

    def generate_value(
        self,
        *,
        click_id: str,
        offer_id: str | int,
        publisher_id: str | int,
        ttl_seconds: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> str:
        if not str(click_id).strip():
            raise ValueError("click_id 不能为空")
        if not str(offer_id).strip():
            raise ValueError("offer_id 不能为空")
        if not str(publisher_id).strip():
            raise ValueError("publisher_id 不能为空")

        effective_ttl = self._default_ttl_seconds if ttl_seconds is None else int(ttl_seconds)
        if effective_ttl <= 0:
            raise ValueError("ttl_seconds 必须大于 0")

        now = self._now_fn()
        payload = TrackerPayload(
            click_id=str(click_id),
            offer_id=str(offer_id),
            publisher_id=str(publisher_id),
            issued_at=now,
            expires_at=now + effective_ttl,
            nonce=secrets.token_urlsafe(DEFAULT_NONCE_BYTES),
            extra=extra.copy() if extra else {},
        )

        payload_json = _json_dumps_compact(payload.to_dict()).encode("utf-8")
        payload_encoded = _b64url_encode(payload_json)
        signature = self._sign_payload(payload_encoded)
        return f"{TRACKER_VERSION}.{payload_encoded}.{signature}"

    def parse_value(self, tracker_value: str) -> dict[str, Any]:
        """
        仅解析，不进行签名/时效验证。

        场景：
        - 故障排查
        - 日志审计
        - 离线分析
        """
        version, payload_encoded, _ = self._split_tracker_value(tracker_value)
        if version != TRACKER_VERSION:
            raise InvalidTrackerFormatError(f"不支持的版本: {version}")

        payload_raw = _b64url_decode(payload_encoded)
        try:
            payload_data = json.loads(payload_raw.decode("utf-8"))
        except Exception as exc:
            raise InvalidTrackerFormatError("负载 JSON 解析失败") from exc

        payload = TrackerPayload.from_dict(payload_data)
        return self._build_parsed_result(version, payload)

    def validate_value(self, tracker_value: str) -> bool:
        """
        仅返回是否有效，不抛错细节，适用于快速判断。
        """
        try:
            self.parse_and_validate(tracker_value)
            return True
        except TrackerError:
            return False

    def parse_and_validate(self, tracker_value: str) -> dict[str, Any]:
        """
        完整流程：解析 + 签名校验 + 时间合法性校验。
        """
        version, payload_encoded, signature = self._split_tracker_value(tracker_value)
        if version != TRACKER_VERSION:
            raise InvalidTrackerFormatError(f"不支持的版本: {version}")

        expected = self._sign_payload(payload_encoded)
        if not hmac.compare_digest(signature, expected):
            raise InvalidTrackerSignatureError("签名校验失败")

        payload_raw = _b64url_decode(payload_encoded)
        try:
            payload_data = json.loads(payload_raw.decode("utf-8"))
        except Exception as exc:
            raise InvalidTrackerFormatError("负载 JSON 解析失败") from exc

        payload = TrackerPayload.from_dict(payload_data)
        self._validate_time_window(payload)
        return self._build_parsed_result(version, payload)

    def _split_tracker_value(self, tracker_value: str) -> tuple[str, str, str]:
        if not tracker_value or not tracker_value.strip():
            raise InvalidTrackerFormatError("追踪值为空")

        parts = tracker_value.split(".")
        if len(parts) != 3:
            raise InvalidTrackerFormatError("追踪值格式非法，应为 3 段")

        version, payload_encoded, signature = parts
        if not version or not payload_encoded or not signature:
            raise InvalidTrackerFormatError("追踪值存在空段")
        return version, payload_encoded, signature

    def _sign_payload(self, payload_encoded: str) -> str:
        sign_input = f"{TRACKER_VERSION}.{payload_encoded}".encode("utf-8")
        digest = hmac.new(self._secret, sign_input, hashlib.sha256).digest()
        return _b64url_encode(digest)

    def _validate_time_window(self, payload: TrackerPayload) -> None:
        now = self._now_fn()

        # 容忍小范围时钟偏移，避免分布式环境下误判。
        if payload.issued_at > now + self._clock_skew_seconds:
            raise TrackerNotYetValidError(
                f"追踪值签发时间在未来: iat={payload.issued_at}, now={now}"
            )

        if payload.expires_at < now - self._clock_skew_seconds:
            raise TrackerExpiredError(
                f"追踪值已过期: exp={payload.expires_at}, now={now}"
            )

        if payload.expires_at <= payload.issued_at:
            raise InvalidTrackerFormatError("exp 必须大于 iat")

    @staticmethod
    def _build_parsed_result(version: str, payload: TrackerPayload) -> dict[str, Any]:
        return {
            "version": version,
            "algorithm": DEFAULT_ALGORITHM,
            "click_id": payload.click_id,
            "offer_id": payload.offer_id,
            "publisher_id": payload.publisher_id,
            "issued_at": payload.issued_at,
            "expires_at": payload.expires_at,
            "nonce": payload.nonce,
            "extra": payload.extra,
        }


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="广告追踪值工具")
    parser.add_argument("--secret", required=True, help="签名密钥")
    parser.add_argument("--ttl", type=int, default=3600, help="默认过期秒数")
    parser.add_argument(
        "--mode",
        required=True,
        choices=["generate", "parse", "validate", "parse-validate"],
        help="运行模式",
    )
    parser.add_argument("--tracker", help="待处理追踪值（parse/validate 模式必填）")
    parser.add_argument("--click-id", help="点击ID（generate 模式必填）")
    parser.add_argument("--offer-id", help="上游ID（generate 模式必填）")
    parser.add_argument("--publisher-id", help="下游ID（generate 模式必填）")
    parser.add_argument(
        "--extra-json",
        default="{}",
        help='扩展字段 JSON（generate 模式可选，例: \'{"sub_id":"abc"}\'）',
    )
    return parser


def _main() -> int:
    parser = _build_cli()
    args = parser.parse_args()

    tracker = AdTracker(secret_key=args.secret, default_ttl_seconds=args.ttl)

    if args.mode == "generate":
        if not args.click_id or not args.offer_id or not args.publisher_id:
            parser.error("generate 模式需要 --click-id --offer-id --publisher-id")
        try:
            extra = json.loads(args.extra_json)
            if not isinstance(extra, dict):
                parser.error("--extra-json 必须是 JSON 对象")
        except json.JSONDecodeError as exc:
            parser.error(f"--extra-json 不是合法 JSON: {exc}")
            return 2

        value = tracker.generate_value(
            click_id=args.click_id,
            offer_id=args.offer_id,
            publisher_id=args.publisher_id,
            extra=extra,
        )
        print(value)
        return 0

    if not args.tracker:
        parser.error(f"{args.mode} 模式需要 --tracker")

    try:
        if args.mode == "parse":
            print(json.dumps(tracker.parse_value(args.tracker), ensure_ascii=False, indent=2))
        elif args.mode == "validate":
            print("true" if tracker.validate_value(args.tracker) else "false")
        else:
            print(
                json.dumps(
                    tracker.parse_and_validate(args.tracker), ensure_ascii=False, indent=2
                )
            )
        return 0
    except TrackerError as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(_main())
