"""校验 .env 中各 LP 的 Facebook 像素 ID 与 Access Token 是否被 Graph API 接受。

用法（在项目根目录）:
  python scripts/verify_fb_pixels.py
  python scripts/verify_fb_pixels.py --env /path/to/.env

仅发起 GET /{pixel-id}?fields=id,name，不会发送转化事件。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

import requests

# 与 tracker/facebook_tracker.py 保持一致
API_VERSION = "v21.0"
SUFFIXES = ("", "_B", "_C", "_D")
SUFFIX_LABEL = ("A", "B", "C", "D")

ROOT = Path(__file__).resolve().parent.parent


def _load_module(mod_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# 禁止 `from utils.validators`，否则会执行 utils/__init__.py 拉取数据库等重依赖
_env = _load_module("_landing_env_loader", ROOT / "utils" / "env_loader.py")
_validators = _load_module("_landing_validators", ROOT / "utils" / "validators.py")
load_env_file = _env.load_env_file
is_real_config = _validators.is_real_config


def _mask(s: str, head: int = 8, tail: int = 4) -> str:
    if not s:
        return ""
    s = str(s)
    if len(s) <= head + tail + 3:
        return "***"
    return f"{s[:head]}...{s[-tail:]}"


def main() -> int:
    parser = argparse.ArgumentParser(description="验证 FB 像素与 Token")
    parser.add_argument(
        "--env",
        type=str,
        default=None,
        help="可选：指定 .env 路径（默认项目根 .env）",
    )
    args = parser.parse_args()

    env_path = Path(args.env) if args.env else None
    if not load_env_file(env_path):
        print("未找到或未读取 .env，请确认路径。")
        return 2

    ok_count = 0
    skip_count = 0
    fail_count = 0

    print(f"Graph API: {API_VERSION}\n")

    for i in range(1, 7):
        for idx, suffix in enumerate(SUFFIXES):
            key_p = f"FB_PIXEL_ID_LP{i}{suffix}"
            key_t = f"FB_TOKEN_LP{i}{suffix}"
            # 与 tracker/facebook_tracker._build_fb_pixel_list 一致：直接读环境变量
            pid = os.environ.get(key_p, "") or ""
            tok = os.environ.get(key_t, "") or ""

            if not pid.strip() and not tok.strip():
                continue

            label = f"lp{i}.{SUFFIX_LABEL[idx]}"

            if not (is_real_config(pid) and is_real_config(tok)):
                print(f"[跳过] {label}  ({key_p} / {key_t})  非有效配置或占位符")
                print(f"       pixel={_mask(pid, 6, 4)}  token={_mask(tok, 8, 4)}")
                skip_count += 1
                continue

            url = f"https://graph.facebook.com/{API_VERSION}/{pid}"
            try:
                r = requests.get(
                    url,
                    params={"fields": "id,name", "access_token": tok},
                    timeout=15,
                )
            except requests.RequestException as e:
                print(f"[异常] {label}  pixel_id={pid}  请求失败: {e}")
                fail_count += 1
                continue

            try:
                body = r.json()
            except ValueError:
                body = {"raw": (r.text or "")[:500]}

            if r.status_code == 200 and isinstance(body, dict) and body.get("id"):
                name = body.get("name") or "(无 name 字段)"
                print(f"[通过] {label}  id={body.get('id')}  name={name}")
                ok_count += 1
            else:
                err = body.get("error") if isinstance(body, dict) else body
                print(
                    f"[失败] {label}  pixel_id={pid}  HTTP {r.status_code}  "
                    f"token={_mask(tok)}"
                )
                print(f"       {json.dumps(err, ensure_ascii=False)[:800]}")
                fail_count += 1

    print(
        f"\n汇总: 通过={ok_count}  失败={fail_count}  跳过(空/占位)={skip_count}"
    )
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
