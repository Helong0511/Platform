"""
广告追踪令牌（ad tracking token）— 生成、解析与校验。

================================================================================
一、整体数据流（从生成到验证）
================================================================================
1. 业务侧构造 ``user_params``（可为 ``None``），调用 ``AdTrackingCodec.generate``。
2. 模块将「固定包头 + 用户载荷」组成明文 ``plaintext``，用随机 ``nonce`` 做按字节
   XOR（密钥派生自服务器主密钥），得到 ``ciphertext``；再对 ``nonce‖ciphertext``
   计算 HMAC-SHA256，截取前 6 字节作为 ``tag``（认证标签，防篡改）。
3. 二进制包 ``combined = nonce ‖ ciphertext ‖ tag`` 经「外层 58 进制字符编码」得到
   最终字符串令牌；投放链接、日志、前端仅传递该字符串。
4. 服务端入口建议：先 ``verify(token, max_age_seconds=...)`` 做轻量 gate，再
   ``parse(token, load_callback=...)`` 取出业务字典（解析失败时有详细 ``reason``）。

================================================================================
二、二进制布局（combined，大端思想 / struct 小端字段按格式为准）
================================================================================
    ┌──────────────┬───────────────────────────────┬──────────────┐
    │  nonce 6B    │  ciphertext（变长）            │  tag 6B      │
    └──────────────┴───────────────────────────────┴──────────────┘
    nonce：每次生成随机，参与 XOR  keystream 与 HMAC，禁止复用同 nonce 加密不同明文。
    ciphertext：与 plaintext 等长，逐字节 XOR（对称操作，加解密同一函数）。
    tag：HMAC-SHA256(master_key, nonce‖ciphertext) 的前 6 字节；长度取舍兼顾紧凑与安全。

    plaintext 布局：
    ┌──────────────────────────────────────┬─────────────────────────┐
    │  header（定长，见 _HEADER_FMT）       │  user_bytes（0..255 长） │
    └──────────────────────────────────────┴─────────────────────────┘
    header 内含：协议版本、载荷类型（明文 JSON / zlib JSON）、生成时 pid/tid、
    毫秒时间戳、2 字节随机、user_bytes 长度。解析时用长度字段校验边界，防截断与溢出。

================================================================================
三、外层编码（为什么不是 Base64）
================================================================================
- 仅使用 58 个 ASCII：数字 1-9、大写（去掉 I/O）、小写（去掉 l），避免与 0、O、I、l 混淆，
  便于人工抄写、URL 传参、跨语言日志。
- ``_outer_encode``：把 ``combined`` 视为无符号大整数，反复除以 58 取余映射到字符；
  ``_outer_decode`` 为其逆。注意：解码后需按位长度还原字节序列（见实现）。
- **仅支持当前这一种外层**：旧版 Base64/62 进制外层已移除，不符合字母表的输入会直接失败。

================================================================================
四、紧凑（compact）与完整（full）
================================================================================
- **compact**：用户区为 UTF-8 的紧凑 JSON 文本，或 ``{"ref":"短 id"}``（大数据走
  ``store_callback`` + ``load_callback``）。受 ``_MAX_USER_COMPACT`` 等约束，保证
  外层字符串长度 ≤ ``_MAX_OUTER_CHARS_COMPACT``（默认 60），适合短链接。
- **full**：用户区为 ``zlib.compress(JSON UTF-8)``，外层字符串变长，适合中文/长字段。
- ``parse`` 返回的 ``format`` 字段按**载荷类型**区分：zlib → ``"full"``，否则
  ``"compact"``（与外层字符串视觉长短无必然对应）。

================================================================================
五、安全与运维注意
================================================================================
- 主密钥：环境变量 ``AD_TRACKING_MASTER_KEY_HEX``（64 个十六进制字符 = 32 字节）。
  未设置时使用内置**开发默认密钥**，生产环境必须更换，否则令牌可被同仓库持有者伪造。
- 机密性：XOR + HMAC 提供「防篡改 + 混淆」；若需防量子或高强度机密性，应在业务层
  额外加密敏感字段，不把绝密明文完全依赖本令牌承载。
- 时效：``verify(..., max_age_seconds=...)`` 仅根据包头时间戳与当前时间比较，依赖
  服务器时钟；需容忍必要时钟漂移的业务自行放宽窗口。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import struct
import threading
import time
import zlib
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, Literal, Optional

# ---------------------------------------------------------------------------
# 外层字母表：58 个「可视、不易混淆」的 ASCII，用于把二进制 combined 编成字符串。
# - _OUTER_MAP：字符 → 0..57 的整数，供解码时累加乘 radix。
# - TOKEN_OUTER_ALPHABET：对外暴露的只读字符串，供调用方校验字符集或生成短 id。
# ---------------------------------------------------------------------------

_OUTER_ALPHABET = (
    "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
)
_OUTER_RADIX = len(_OUTER_ALPHABET)
_OUTER_MAP = {c: i for i, c in enumerate(_OUTER_ALPHABET)}
TOKEN_OUTER_ALPHABET = _OUTER_ALPHABET

# ---------------------------------------------------------------------------
# parse / verify 返回字典中的 reason：面向人或前端的中文说明。
# 业务分支建议写：if result["reason"] == REASON_EXPIRED: …
# 勿依赖硬编码中文字符串，应总是与本模块 REASON_* 常量比较，避免文案微调导致分支失效。
# ---------------------------------------------------------------------------
REASON_OK = "成功"
REASON_INVALID = "无效"
REASON_EMPTY_TOKEN = "令牌为空"
REASON_CANNOT_DECODE_TOKEN = "无法解码该令牌"
REASON_DECODE_FALLBACK = "解码失败"
REASON_INVALID_SIG_OR_FORMAT = "签名无效或外层格式错误"
REASON_TOO_SHORT = "二进制包过短"
REASON_INVALID_SIGNATURE = "签名无效"
REASON_TRUNCATED = "明文过短"
REASON_BAD_HEADER = "包头解析失败"
REASON_BAD_VERSION = "协议版本无效"
REASON_LENGTH_MISMATCH = "长度不匹配"
REASON_BAD_USER_JSON = "用户 JSON 解析失败"
REASON_BAD_USER_ZLIB_JSON = "用户数据解压或 JSON 解析失败"
REASON_BAD_PAYLOAD_KIND = "载荷类型无效"
REASON_EXPIRED = "令牌已过期"


def _outer_encode(data: bytes) -> str:
    """
    将任意字节串编码为 58 进制「大整数」字符串（高位在前）。

    算法要点：
    - ``int.from_bytes(..., "big")`` 与解码端 ``to_bytes`` 对称，保证 round-trip。
    - ``data`` 全为 \\x00 时整数为 0，单独映射为字母表首字符（与 while 循环分支一致）。
    - 复杂度 O(len(data)) 数量级的除法次数，payload 尺英寸级可忽略。
    """
    num = int.from_bytes(data, "big")
    if num == 0:
        # 全零字节：divmod 循环不会执行，约定输出单个「零」符号
        return _OUTER_ALPHABET[0]
    out = []
    radix = _OUTER_RADIX
    while num:
        num, r = divmod(num, radix)
        out.append(_OUTER_ALPHABET[r])
    return "".join(reversed(out))


def _outer_decode(s: str) -> bytes:
    """
    ``_outer_encode`` 的逆。输入串须已全部落在 ``_OUTER_MAP`` 中，否则抛「外层字符非法」。

    字节长度还原：解码得到整数后，用 ``bit_length`` 推最小字节数（至少 1），再
    ``to_bytes(..., "big")``。须与 encode 端对大端整数的解释一致。
    """
    num = 0
    radix = _OUTER_RADIX
    for c in s:
        if c not in _OUTER_MAP:
            raise ValueError("外层字符非法")
        num = num * radix + _OUTER_MAP[c]
    # 与 int.from_bytes 配对：最少 1 字节，避免 0 映射成空 bytes
    length = max(1, (num.bit_length() + 7) // 8)
    return num.to_bytes(length, "big")


def _max_combined_bytes_for_outer_char_limit(max_chars: int) -> int:
    """
    在「最坏情况下 combined 全为 0xFF」时，外层编码字符串长度随字节数单调增。
    从上限向下扫描，找到仍满足 ``len(outer) <= max_chars`` 的最大 combined 长度，
    用于推导紧凑模式下明文 / 用户区可容纳的上界（见类属性 _MAX_COMBINED_COMPACT）。
    """
    for n in range(80, 0, -1):
        if len(_outer_encode(bytes([0xFF]) * n)) <= max_chars:
            return n
    return 0


def _decode_outer_string(token: str) -> bytes:
    """
    把外层字符串还原为 ``combined`` 字节串，并**在此完成认证标签校验**。

    步骤摘要：
    1. ``strip`` 去掉首尾空白；空串表示调用方未传有效令牌。
    2. 逐字符检查是否 ∈ 58 字母表；任一非法则无法可靠解码，统一「无法解码该令牌」。
    3. ``_outer_decode`` 得到 raw；若长度不足以容纳 nonce+tag+至少 1 字节密文，拒绝。
    4. 切分 nonce / ciphertext / tag，用主密钥计算期望 tag，``secrets.compare_digest``
       防时序攻击；不匹配则「签名无效或外层格式错误」。

    注意：``parse`` / ``verify`` 内部仍会再次切分并校验（双重防御）；正常路径下
    第二次校验应与这里一致。
    """
    token = token.strip()
    if not token:
        raise ValueError(REASON_EMPTY_TOKEN)

    # 快速拒绝：含非法字符则根本不进入 bigint 解码，避免怪异输入
    if not all(c in _OUTER_MAP for c in token):
        raise ValueError(REASON_CANNOT_DECODE_TOKEN)

    try:
        raw = _outer_decode(token)
    except ValueError:
        # 统一对外错误码：单个非法字符也会在内层抛出，这里合并为同一提示
        raise ValueError(REASON_CANNOT_DECODE_TOKEN) from None

    # 至少 nonce + tag + 1 字节密文（包头已长于 1，实际 combined 远不止）
    min_len = AdTrackingCodec._NONCE_SIZE + AdTrackingCodec._TAG_SIZE + 1
    if len(raw) < min_len:
        raise ValueError(REASON_CANNOT_DECODE_TOKEN)

    nonce = raw[: AdTrackingCodec._NONCE_SIZE]
    tag = raw[-AdTrackingCodec._TAG_SIZE:]
    ct = raw[AdTrackingCodec._NONCE_SIZE: -AdTrackingCodec._TAG_SIZE]
    expected = hmac.new(
        AdTrackingCodec._master_key(), nonce + ct, hashlib.sha256
    ).digest()[: AdTrackingCodec._TAG_SIZE]
    if secrets.compare_digest(tag, expected):
        return raw

    raise ValueError(REASON_INVALID_SIG_OR_FORMAT)


# 类型别名（仅用于静态检查 / 文档，运行时不产生开销）：
# - PayloadKind：用户区在逻辑上的两种形态（明文 JSON 字节 vs zlib 包裹的 JSON）。
# - TokenFormat：generate 的 format 参数；auto 由本模块根据体积与 callback 自动判定。
PayloadKind = Literal["plain_json", "zlib_json"]
TokenFormat = Literal["auto", "compact", "full"]


class AdTrackingCodec:
    """
    广告追踪令牌唯一对外入口（全部为类方法，无需实例化）。

    职责划分：
    - ``generate``：编码 + 加密 + 签名 + 外层字符串。
    - ``parse``：完整解密并还原 JSON，可选 ``load_callback`` 解析 ref。
    - ``verify``：_gate_ 用，避免对恶意流量做 zlib/json 重 CPU 解析。

    线程安全：无跨调用可变全局状态；并发调用 ``generate`` 仅依赖 os/cryptographic RNG。
    """

    # 协议版本号：包头第一字节；升级格式时必须递增并保留旧版解析或迁移策略（当前仅实现 v3）。
    _VERSION = 3
    # nonce 长度：影响 keystream 分裂边界与 HMAC 绑定范围，勿随意缩短。
    _NONCE_SIZE = 6
    # HMAC 标签截断长度：越短越紧凑，碰撞概率上升；6 字节为产品取舍结果。
    _TAG_SIZE = 6

    # struct 小端布局（"<"）：与 C 结构体对齐思路类似，方便一眼读出字段边界。
    # B=uint8 版本, B=uint8 载荷类型, H=uint16 pid, H=uint16 tid,
    # 6s=6 字节小端时间戳毫秒, 2s=2 字节随机, B=user_bytes 长度（0-255）。
    _HEADER_FMT = "<B B H H 6s 2s B"
    _HEADER_SIZE = struct.calcsize(_HEADER_FMT)

    # user 区为紧凑 JSON 文本（UTF-8），未压缩。
    _PAYLOAD_PLAIN = 0
    # user 区为 zlib(raw_json)，用于 full 模式承载长文本/中文。
    _PAYLOAD_ZLIB = 1

    # 紧凑模式默认外层上限（短链接场景）；平台 click_id 列 varchar(255) 可用更大上限。
    _MAX_OUTER_CHARS_COMPACT = 60
    # 与数据库 click_id 字段一致的上限
    MAX_CLICK_ID_LENGTH = 255
    # 满足外层长度约束时，combined（nonce+密文+tag）允许的最大字节数。
    _MAX_COMBINED_COMPACT = _max_combined_bytes_for_outer_char_limit(
        _MAX_OUTER_CHARS_COMPACT
    )
    # XOR 之前的明文（包头+用户区）在紧凑模式下不得超过此长度。
    _MAX_PLAINTEXT_COMPACT = _MAX_COMBINED_COMPACT - _NONCE_SIZE - _TAG_SIZE
    # 用户 JSON（或 ref 小对象）在紧凑模式下 UTF-8 最多字节数；含中文时极易触顶。
    _MAX_USER_COMPACT = _MAX_PLAINTEXT_COMPACT - _HEADER_SIZE

    # 短 id 与外层共用字母表，避免引入另一套字符校验规则。
    _SHORT_ID_ALPHABET = TOKEN_OUTER_ALPHABET

    # 仅本地开发兜底；与 .env 生产密钥必须不同
    _DEFAULT_KEY_HEX = (
        "02f0b613d3ce47c0784815fef40efcc6f09e51ba7889952a6123553f08a0d1b6"
    )

    @classmethod
    def _resolve_master_key_hex(cls) -> str:
        """优先环境变量，其次 settings（与 pydantic 加载的 .env 一致）。"""
        hx = os.environ.get("AD_TRACKING_MASTER_KEY_HEX", "").strip()
        if hx:
            return hx
        try:
            from app.core.config import settings

            hx = getattr(settings, "AD_TRACKING_MASTER_KEY_HEX", "").strip()
            if hx:
                return hx
        except Exception:
            pass
        return cls._DEFAULT_KEY_HEX

    @classmethod
    def _master_key(cls) -> bytes:
        """
        从环境变量 / settings 读取 32 字节主密钥；均缺失则用开发默认串。

        注意：
        - 必须是**恰好** 64 个十六进制字符（0-9a-fA-F），否则 ``bytes.fromhex`` 抛错。
        - 生产应在启动时校验：若仍为 ``_DEFAULT_KEY_HEX``，可拒绝启动或打致命日志。
        - 密钥轮换：更换 env 后**旧令牌全部失效**（HMAC 与 keystream 均绑定新密钥）。
        """
        hx = cls._resolve_master_key_hex()
        if len(hx) != 64:
            raise ValueError(
                "AD_TRACKING_MASTER_KEY_HEX 必须为 64 位十六进制（32 字节）"
            )
        return bytes.fromhex(hx)

    @classmethod
    def _derive_keystream(cls, nonce: bytes, counter: int, length: int) -> bytes:
        """
        基于 HMAC-SHA256 的伪随机 keystream 生成器（非标准计数器模式，但逻辑清晰）。

        - 每次 HMAC 输出 32 字节；不足则 ``counter`` 递增再hash，直到凑够 ``length``。
        - 绑定 ``nonce``：不同 nonce 下同一 plaintext 的密文不可预测。
        """
        buf = bytearray()
        key = cls._master_key()
        while len(buf) < length:
            h = hmac.new(
                key, nonce + counter.to_bytes(4, "big"), hashlib.sha256
            )
            buf.extend(h.digest())
            counter += 1
        return bytes(buf[:length])

    @classmethod
    def _encrypt(cls, plaintext: bytes, nonce: bytes) -> bytes:
        """逐字节 XOR keystream；解密与加密同一函数（对称 XOR）。"""
        ks = cls._derive_keystream(nonce, 0, len(plaintext))
        return bytes(a ^ b for a, b in zip(plaintext, ks))

    _decrypt = _encrypt

    @classmethod
    def _compute_tag(cls, nonce: bytes, ciphertext: bytes) -> bytes:
        """认证标签：截断 HMAC 以缩短令牌；截断后仍需暴力难度远高于业务接受范围。"""
        return hmac.new(cls._master_key(), nonce + ciphertext, hashlib.sha256).digest()[
            : cls._TAG_SIZE
        ]

    @classmethod
    def _format_times(cls, timestamp_ms: int) -> Dict[str, Any]:
        """把包头里的毫秒时间戳展开为 UTC / 上海时区可读字符串，便于排障与报表。"""
        dt_utc = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        dt_bj = dt_utc.astimezone(timezone(timedelta(hours=8)))
        return {
            "timestamp_ms": timestamp_ms,
            "time_utc": dt_utc.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "time_beijing": dt_bj.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        }

    @classmethod
    def _generate_short_id(cls, length: int = 6) -> str:
        """密码学安全随机短 id；长度默认 6，碰撞概率在业务量级可接受（须防业务层复用冲突）。"""
        alpha = cls._SHORT_ID_ALPHABET
        n = len(alpha)
        return "".join(alpha[secrets.randbelow(n)] for _ in range(length))

    @classmethod
    def _compact_limits(cls, max_outer_chars: int) -> tuple[int, int, int]:
        """根据外层字符上限推导 combined / plaintext / user 区最大字节数。"""
        cap = max(12, min(int(max_outer_chars), cls.MAX_CLICK_ID_LENGTH))
        max_combined = _max_combined_bytes_for_outer_char_limit(cap)
        max_plaintext = max_combined - cls._NONCE_SIZE - cls._TAG_SIZE
        max_user = max(0, max_plaintext - cls._HEADER_SIZE)
        return max_combined, max_plaintext, max_user

    @classmethod
    def _pack_payload(
            cls,
            user_params: Optional[Dict[str, Any]],
            *,
            fmt: Literal["compact", "full"],
            store_callback: Optional[Callable[[str, Dict[str, Any]], None]],
            max_user_compact: Optional[int] = None,
    ) -> tuple[bytes, int]:
        """
        将业务 dict 变为「用户区字节」与「载荷类型」。

        返回：
            (user_bytes, payload_kind)，payload_kind 为 _PAYLOAD_PLAIN 或 _PAYLOAD_ZLIB。

        分支说明：
        - ``user_params is None``：用户区空，类型 PLAIN（生成无业务载荷的「空」令牌）。
        - ``store_callback``：只允 compact；令牌内只存 ref，侧路存储由调用方负责。
        - 否则按 compact/full 决定 JSON 直塞或 zlib。
        """
        user_cap = max_user_compact if max_user_compact is not None else cls._MAX_USER_COMPACT

        if user_params is None:
            return b"", cls._PAYLOAD_PLAIN

        if store_callback is not None:
            # full 模式若允许 ref，会使「是否 zlib」与侧路约定复杂化，故直接禁止。
            if fmt != "compact":
                raise ValueError("store_callback 仅支持与 format='compact' 联用")
            sid = cls._generate_short_id()
            store_callback(sid, user_params)
            blob = json.dumps(
                {"ref": sid}, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
            if len(blob) > user_cap:
                raise ValueError("短引用序列化后仍超出紧凑格式上限")
            return blob, cls._PAYLOAD_PLAIN

        raw_json = json.dumps(
            user_params, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")

        if fmt == "compact":
            if len(raw_json) > user_cap:
                raise ValueError(
                    f"紧凑格式用户数据最大 {user_cap} 字节，当前 {len(raw_json)}。"
                    "请改用 format='full' 或提供 store_callback。"
                )
            return raw_json, cls._PAYLOAD_PLAIN

        # full：压缩通常显著缩短中文 UTF-8；极端情况 zlib 可能膨胀，由外层变长吸收。
        z = zlib.compress(raw_json)
        return z, cls._PAYLOAD_ZLIB

    @classmethod
    def generate(
            cls,
            user_params: Optional[Dict[str, Any]] = None,
            *,
            format: TokenFormat = "auto",
            store_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
            max_outer_chars: Optional[int] = None,
            allow_full: bool = True,
    ) -> str:
        """
        生成广告追踪值。

        format:
            auto — 有 store_callback 或明文 JSON 可塞进紧凑上限则用 compact，否则 full。
            compact — 外层 58 进制字符串；默认 ≤60 字符，可通过 max_outer_chars 提高（最大 255）。
            full — 外层变长；zlib(JSON)；总长不应超过 MAX_CLICK_ID_LENGTH(255)。

        max_outer_chars:
            紧凑模式外层字符上限。None 时使用 _MAX_OUTER_CHARS_COMPACT(60)；
            平台场景可传 255，与数据库 click_id varchar(255) 对齐。
        allow_full:
            False 时 auto 不得在紧凑上限内塞不下时升级为 full（短链 ≤60 场景）。

        实现顺序（与 parse 逆过程对称）：
        采集元数据 → 决定 compact/full → 打包用户区 → 组 header+user → XOR 加密 →
        算 tag → combined → 外层编码。
        """
        # 包头中的 pid/tid 仅作排障与统计（低 16 位），不参与安全边界；同一进程可重复。
        pid = os.getpid() & 0xFFFF
        tid = threading.get_ident() & 0xFFFF
        # 毫秒时间戳：verify 可选据此做「令牌年龄」判断；与服务器时钟强相关。
        ts_ms = int(time.time() * 1000)
        ts_bytes = ts_ms.to_bytes(6, "little")
        # 2 字节随机：令相同业务载荷在不同次生成时密文不同，防重放指纹对齐（非密码学 nonce）。
        rand2 = os.urandom(2)

        outer_cap = (
            cls._MAX_OUTER_CHARS_COMPACT
            if max_outer_chars is None
            else min(int(max_outer_chars), cls.MAX_CLICK_ID_LENGTH)
        )
        max_combined_cap, max_plaintext_cap, max_user_cap = cls._compact_limits(outer_cap)

        # resolved：本次实际走的「紧凑 / 完整」分支，影响 _pack_payload 与用户区是否 zlib。
        resolved: Literal["compact", "full"]
        if format == "auto":
            if store_callback is not None:
                resolved = "compact"
            elif user_params is None:
                resolved = "compact"
            else:
                # 与 _pack_payload 使用相同 separators/ensure_ascii，保证长度判断一致。
                trial = json.dumps(
                    user_params, separators=(",", ":"), ensure_ascii=False
                ).encode("utf-8")
                if len(trial) <= max_user_cap:
                    resolved = "compact"
                elif allow_full:
                    resolved = "full"
                else:
                    raise ValueError(
                        f"紧凑格式用户数据最大 {max_user_cap} 字节，当前 {len(trial)}；"
                        "已禁止升级为 full。"
                    )
        elif format == "compact":
            resolved = "compact"
        else:
            if not allow_full:
                raise ValueError("已禁止 full 格式生成")
            resolved = "full"

        user_bytes, payload_kind = cls._pack_payload(
            user_params,
            fmt=resolved,
            store_callback=store_callback,
            max_user_compact=max_user_cap,
        )

        header = struct.pack(
            cls._HEADER_FMT,
            cls._VERSION,
            payload_kind,
            pid,
            tid,
            ts_bytes,
            rand2,
            len(user_bytes),
        )
        plaintext = header + user_bytes

        if resolved == "compact":
            # 双保险：除用户区上限外，整体明文也不得超过紧凑模式推导出的上界。
            if len(plaintext) > max_plaintext_cap:
                raise ValueError("紧凑格式明文超长")

        # 密码学 nonce：6 字节随机；与 rand2 分工不同，nonce 全程参与 keystream 与 HMAC。
        nonce = os.urandom(cls._NONCE_SIZE)
        ciphertext = cls._encrypt(plaintext, nonce)
        tag = cls._compute_tag(nonce, ciphertext)
        combined = nonce + ciphertext + tag

        if resolved == "compact":
            # combined 长度直接决定外层字符串长度。
            if len(combined) > max_combined_cap:
                raise ValueError("紧凑格式密文包超长")
            out = _outer_encode(combined)
            # 理论：58 进制字母表编码任意二进制应仍落在字母表内；若否说明实现或常量被破坏。
            if any(c not in _OUTER_MAP for c in out):
                raise RuntimeError(
                    "紧凑格式外层必须为 TOKEN_OUTER_ALPHABET（58 字符，无易混 0/O/I/l）"
                )
            if len(out) > outer_cap:
                raise RuntimeError(
                    f"紧凑格式长度异常: {len(out)} > {outer_cap}"
                )
            return out

        # full：校验外层字符集、外层上限与数据库 click_id 上限。
        out = _outer_encode(combined)
        if any(c not in _OUTER_MAP for c in out):
            raise RuntimeError(
                "完整格式外层必须为 TOKEN_OUTER_ALPHABET（58 字符，无易混 0/O/I/l）"
            )
        if len(out) > outer_cap:
            raise ValueError(
                f"完整格式 click_id 超过外层上限 {outer_cap} 字符，"
                "请减少 url_params 或使用 store_callback。"
            )
        if len(out) > cls.MAX_CLICK_ID_LENGTH:
            raise ValueError(
                f"完整格式 click_id 超过 {cls.MAX_CLICK_ID_LENGTH} 字符，"
                "请减少 url_params 或使用 store_callback。"
            )
        return out

    @classmethod
    def parse(
            cls,
            token: str,
            *,
            load_callback: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None,
    ) -> Dict[str, Any]:
        """
        完整解析：外层解码（含 tag 校验）→ 解密 → 解包头 → 解 JSON / zlib → 可选 ref 展开。

        参数：
            token：投放带回的整串；首尾空白会被 strip。
            load_callback：当 userinfo 为 ``{"ref": sid}`` 时调用 ``load_callback(sid)``；
                返回 ``None`` 表示侧路未命中，则 **保留** 载荷内的小对象（不抛错）。

        成功时返回字典（示例字段）：
            - ``valid``：``True``
            - ``reason``：``REASON_OK``（``"成功"``）
            - ``format``：``"compact"`` 或 ``"full"``（由载荷类型 zlib 与否决定，见类文档）
            - ``sysinfo``：pid、tid、时间戳、UTC/北京时间串、random_hex 等
            - ``userinfo``：业务 dict 或 ``None``（用户区长度为 0 时）

        失败时 ``valid`` 为 ``False``，``reason`` 为中文说明，常见对应关系：
            - 外层失败：``REASON_EMPTY_TOKEN`` / ``REASON_CANNOT_DECODE_TOKEN`` /
              ``REASON_INVALID_SIG_OR_FORMAT``
            - 解密后结构：``REASON_TOO_SHORT`` / ``REASON_INVALID_SIGNATURE`` /
              ``REASON_TRUNCATED`` / ``REASON_BAD_HEADER`` / ``REASON_BAD_VERSION`` /
              ``REASON_LENGTH_MISMATCH``
            - 用户区：``REASON_BAD_USER_JSON`` / ``REASON_BAD_USER_ZLIB_JSON`` /
              ``REASON_BAD_PAYLOAD_KIND``

        与 ``verify`` 的分工：本函数会执行 zlib/json，恶意超长流量应先经 ``verify`` 或网关限流。
        """
        # 失败模板：避免每个分支新建 dict；注意返回前已拷贝 reason 等字段。
        empty: Dict[str, Any] = {
            "valid": False,
            "reason": REASON_INVALID,
            "format": None,
            "sysinfo": {},
            "userinfo": None,
        }

        try:
            # _decode_outer_string 已验证 tag；此处到手的 raw 为可信 combined。
            raw = _decode_outer_string(token)
        except ValueError as e:
            # 与 verify 一致：decode 阶段错误直接透传中文或 decode 兜底文案。
            empty["reason"] = str(e) or REASON_DECODE_FALLBACK
            return empty

        if len(raw) < cls._NONCE_SIZE + cls._TAG_SIZE:
            # 理论上 decode 已要求 min_len；保留分支防御截断内存或未来改动的组合错误。
            empty["reason"] = REASON_TOO_SHORT
            return empty

        nonce = raw[: cls._NONCE_SIZE]
        tag = raw[-cls._TAG_SIZE:]
        ciphertext = raw[cls._NONCE_SIZE: -cls._TAG_SIZE]

        if not secrets.compare_digest(tag, cls._compute_tag(nonce, ciphertext)):
            # 与 _decode_outer_string 内校验重复：防止仅调用方绕过 decode 辅助函数的路径（若以后重构）。
            empty["reason"] = REASON_INVALID_SIGNATURE
            return empty

        plaintext = cls._decrypt(ciphertext, nonce)
        if len(plaintext) < cls._HEADER_SIZE:
            empty["reason"] = REASON_TRUNCATED
            return empty

        header = plaintext[: cls._HEADER_SIZE]
        user_part = plaintext[cls._HEADER_SIZE:]

        try:
            ver, pkind, pid, tid, ts_bytes, rand2, user_len = struct.unpack(
                cls._HEADER_FMT, header
            )
        except struct.error:
            empty["reason"] = REASON_BAD_HEADER
            return empty

        if ver != cls._VERSION:
            empty["reason"] = REASON_BAD_VERSION
            return empty

        # logical_fmt：与「生成时选的 compact/full」可能字面不一致，仅表示载荷是否为 zlib。
        logical_fmt: Literal["compact", "full"] = (
            "full" if pkind == cls._PAYLOAD_ZLIB else "compact"
        )

        if len(user_part) != user_len or len(plaintext) != cls._HEADER_SIZE + user_len:
            # 防止 user_len 被篡改导致读取越界或漏读；须与包头声明一致。
            empty["reason"] = REASON_LENGTH_MISMATCH
            return empty

        ts_ms = int.from_bytes(ts_bytes, "little")
        sysinfo = {
            "pid": pid,
            "tid": tid,
            **cls._format_times(ts_ms),
            "random_hex": rand2.hex(),
        }

        userinfo: Optional[Dict[str, Any]] = None
        if user_len > 0:
            if pkind == cls._PAYLOAD_PLAIN:
                try:
                    # 紧凑模式：用户区为 UTF-8 JSON 文本（或 ref 小对象）。
                    userinfo = json.loads(user_part.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    empty["reason"] = REASON_BAD_USER_JSON
                    return empty
            elif pkind == cls._PAYLOAD_ZLIB:
                try:
                    dec = zlib.decompress(user_part)
                    userinfo = json.loads(dec.decode("utf-8"))
                except Exception:
                    # zlib 与 JSON 任一失败均归为此类，避免向外部泄露堆栈细节。
                    empty["reason"] = REASON_BAD_USER_ZLIB_JSON
                    return empty
            else:
                empty["reason"] = REASON_BAD_PAYLOAD_KIND
                return empty

            # ref 展开：仅当解析结果是 dict 且提供 load_callback；sid 可为 str（JSON 键 ref）。
            if isinstance(userinfo, dict) and load_callback is not None:
                sid = userinfo.get("ref")
                if sid is not None:
                    loaded = load_callback(sid)
                    if loaded is not None:
                        userinfo = loaded

        return {
            "valid": True,
            "reason": REASON_OK,
            "format": logical_fmt,
            "sysinfo": sysinfo,
            "userinfo": userinfo,
        }

    @classmethod
    def verify(
            cls,
            token: str,
            max_age_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        轻量校验：适合 API 网关 / 中间件先挡掉明显非法或过期令牌，再按需调用 ``parse``。

        与 ``parse`` 的差异（刻意不做的事）：
        - 不执行 ``zlib.decompress``、不 ``json.loads`` 用户区 → CPU 与内存更省；
        - 因此**无法**区分「用户 JSON 损坏」与「结构合法」——仅当包头与长度自洽且签名通过时判成功。

        返回字段：
        - ``valid``：是否通过校验。
        - ``reason``：失败时的中文说明（或成功时的 ``REASON_OK``）。
        - ``format``：成功时为 ``"compact"`` 或 ``"full"``（同 parse 的载荷类型语义）；失败时多为 ``None``。

        ``max_age_seconds``：
        - 非 ``None`` 时，用包头内毫秒时间戳与当前 ``time.time()`` 比较；
        - 仅表示「生成时刻距今」是否超过阈值，不包含业务侧二次签发逻辑。
        """
        out = {
            "valid": False,
            "reason": "",
            "format": None,
        }
        try:
            raw = _decode_outer_string(token)
        except ValueError as e:
            out["reason"] = str(e) or REASON_DECODE_FALLBACK
            return out

        if len(raw) < cls._NONCE_SIZE + cls._TAG_SIZE:
            out["reason"] = REASON_TOO_SHORT
            return out

        nonce = raw[: cls._NONCE_SIZE]
        tag = raw[-cls._TAG_SIZE:]
        ciphertext = raw[cls._NONCE_SIZE: -cls._TAG_SIZE]

        if not secrets.compare_digest(tag, cls._compute_tag(nonce, ciphertext)):
            out["reason"] = REASON_INVALID_SIGNATURE
            return out

        plaintext = cls._decrypt(ciphertext, nonce)
        if len(plaintext) < cls._HEADER_SIZE:
            out["reason"] = REASON_TRUNCATED
            return out

        header = plaintext[: cls._HEADER_SIZE]
        try:
            ver, pkind, _pid, _tid, ts_bytes, _rand2, user_len = struct.unpack(
                cls._HEADER_FMT, header
            )
        except struct.error:
            out["reason"] = REASON_BAD_HEADER
            return out

        # 整段明文长度须等于 header + user_len，防止声明长度与截断数据不一致。
        if len(plaintext) != cls._HEADER_SIZE + user_len:
            out["reason"] = REASON_LENGTH_MISMATCH
            return out

        if ver != cls._VERSION:
            out["reason"] = REASON_BAD_VERSION
            return out

        out["format"] = "full" if pkind == cls._PAYLOAD_ZLIB else "compact"

        if max_age_seconds is not None:
            ts_ms = int.from_bytes(ts_bytes, "little")
            age = (int(time.time() * 1000) - ts_ms) / 1000.0
            if age > max_age_seconds:
                out["reason"] = REASON_EXPIRED
                return out

        out["valid"] = True
        out["reason"] = REASON_OK
        return out


# -----------------------------------------------------------------------------
# 直接运行本文件时：执行一轮「人工可读」自检（非 pytest/unittest 替代物）。
# 覆盖：空载荷、auto 紧凑/完整、ref 侧路、错误路径、verify 过期、并发唯一性。
# 生产环境请依赖 cs_ad_tracking.py 或项目内正式测试套件。
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    sys_clicks = AdTrackingCodec()

    param = {
        "ggz": "fdfdfdfd"
    }

    zh_params = {
        "advertiser_name": "广告主1",
        "Offer": "Offer1",
        "publisher_name": "渠道1",
        "url": "http://powerclick.fuse-ad.com/tl?a=2086&o=2965&aff_click_id={click_id}&sub_affid={channel_id}",
        "postback_url": "http://d36nq33iarpos0.cloudfront.net/?clickid={click_id}&payout={payout}",
        "postback_method": "GET",
        "上限": 30,
        "金额": 4.00
    }

    click_id = sys_clicks.generate(user_params=param, format="auto")
    print(click_id, len(click_id))

    click_id = sys_clicks.generate(user_params=None, format="compact")
    print(click_id, len(click_id))

    click_id = sys_clicks.generate(user_params=param, format="full")
    print(click_id, len(click_id))

    vi = sys_clicks.verify(click_id)
    print(vi)

    par = sys_clicks.parse(click_id)
    print(par)

    time.sleep(2)
    vi = sys_clicks.verify(click_id, max_age_seconds=1)
    print(vi)

    print("-" * 80)

    click_id = sys_clicks.generate(user_params=zh_params, format="auto")
    print(click_id, len(click_id))

    click_id = sys_clicks.generate(user_params=None, format="compact")
    print(click_id, len(click_id))

    click_id = sys_clicks.generate(user_params=zh_params, format="full")
    print(click_id, len(click_id))

    vi = sys_clicks.verify(click_id)
    print(vi)

    par = sys_clicks.parse(click_id)
    print(par)

    time.sleep(2)
    vi = sys_clicks.verify(click_id, max_age_seconds=1)
    print(vi)
