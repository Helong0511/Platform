#!/usr/bin/env python3
"""生成 AD_TRACKING_MASTER_KEY_HEX（32 字节随机密钥，64 位十六进制）。"""
import secrets

if __name__ == "__main__":
    key_hex = secrets.token_hex(32)
    print("AD_TRACKING_MASTER_KEY_HEX=" + key_hex)
    print("# 将上一行追加到 .env；启用令牌时同时设置 USE_TRACKING_TOKEN=true")
