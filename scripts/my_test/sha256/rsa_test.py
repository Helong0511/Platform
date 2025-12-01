from rsa_utils import *

print("=== 生成密钥 ===")
keys = generate_rsa_keypair(bits=4096)

private_key = keys["private_der_b64"]
public_key = keys["public_der_b64"]

# 存 MySQL 用 private_key / public_key 即可

print(f"Private (Base64 DER): {private_key}")
print(f"Private (Base64 DER): {len(private_key)}")
print(f"Public  (Base64 DER): {public_key}")
print(f"Public  (Base64 DER): {len(public_key)}")

msg = "Hello RSA!"

# -----------------------
# 加密、解密
# -----------------------
cipher = rsa_encrypt_oaep(public_key, msg)
print("加密结果：", cipher)
print("加密结果：", len(cipher))

plain = rsa_decrypt_oaep(private_key, cipher)
print("解密结果：", plain)

# -----------------------
# 签名、验签
# -----------------------
sign = rsa_sign_sha256(private_key, msg)
print("签名：", sign)
print("签名：", len(sign))

verify = rsa_verify_sha256(public_key, msg, sign)
print("验证：", verify)
