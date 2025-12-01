import base64
from typing import Union
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.backends import default_backend


# -------------------------
# 工具：字符串 → bytes
# -------------------------
def to_bytes(data: Union[str, bytes]) -> bytes:
    if isinstance(data, bytes):
        return data
    return data.encode("utf-8")


# -------------------------
# PEM ↔ DER(Base64)
# -------------------------
def pem_to_der_b64(pem: str) -> str:
    if "PRIVATE" in pem:
        key = serialization.load_pem_private_key(to_bytes(pem), None)
        der = key.private_bytes(
            serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        return base64.b64encode(der).decode()
    else:
        key = serialization.load_pem_public_key(to_bytes(pem))
        der = key.public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return base64.b64encode(der).decode()


def der_b64_to_pem(key_b64: str) -> str:
    der = base64.b64decode(key_b64)

    # 尝试私钥
    try:
        key = serialization.load_der_private_key(der, None)
        return key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
    except Exception:
        pass

    # 尝试公钥
    key = serialization.load_der_public_key(der)
    return key.public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


# -------------------------
# 自动加载 PEM / Base64-DER
# -------------------------
def load_private_key(key: str):
    try:
        return serialization.load_pem_private_key(to_bytes(key), None)
    except Exception:
        der = base64.b64decode(key)
        return serialization.load_der_private_key(der, None)


def load_public_key(key: str):
    try:
        return serialization.load_pem_public_key(to_bytes(key))
    except Exception:
        der = base64.b64decode(key)
        return serialization.load_der_public_key(der)


# -------------------------
# RSA-OAEP 加密 / 解密
# -------------------------
def rsa_encrypt_oaep(pub_key: str, msg: Union[str, bytes]) -> str:
    pub = load_public_key(pub_key)
    cipher = pub.encrypt(
        to_bytes(msg),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        )
    )
    return base64.b64encode(cipher).decode()


def rsa_decrypt_oaep(pri_key: str, cipher_b64: str) -> str:
    pri = load_private_key(pri_key)
    plain = pri.decrypt(
        base64.b64decode(cipher_b64),
        padding.OAEP(
            mgf=padding.MGF1(hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        )
    )
    return plain.decode()


# -------------------------
# SHA256withRSA 签名 / 验证
# -------------------------
def rsa_sign_sha256(pri_key: str, msg: Union[str, bytes]) -> str:
    pri = load_private_key(pri_key)
    signature = pri.sign(
        to_bytes(msg),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode()


def rsa_verify_sha256(pub_key: str, msg: Union[str, bytes], sig_b64: str) -> bool:
    pub = load_public_key(pub_key)
    try:
        pub.verify(
            base64.b64decode(sig_b64),
            to_bytes(msg),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except Exception:
        return False


# -------------------------
# RSA 密钥生成
# -------------------------
def generate_rsa_keypair(bits=2048):
    priv = rsa.generate_private_key(
        public_exponent=65537,
        key_size=bits,
        backend=default_backend(),
    )
    pub = priv.public_key()

    # PEM
    priv_pem = priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()

    pub_pem = pub.public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()

    # Base64 DER（适合存 MySQL）
    priv_der_b64 = base64.b64encode(
        priv.private_bytes(
            serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    ).decode()

    pub_der_b64 = base64.b64encode(
        pub.public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    ).decode()

    return {
        "private_pem": priv_pem,
        "public_pem": pub_pem,
        "private_der_b64": priv_der_b64,
        "public_der_b64": pub_der_b64,
    }
