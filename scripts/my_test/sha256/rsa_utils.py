import base64
import logging
import binascii
from typing import Union, Optional, Dict

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm

# 配置简单的日志
logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("RSA_UTILS")


# -------------------------
# 工具：字符串 → bytes
# -------------------------
def to_bytes(data: Union[str, bytes, None]) -> Optional[bytes]:
    if data is None:
        return None
    if isinstance(data, bytes):
        return data
    if isinstance(data, str):
        return data.encode("utf-8")
    # 容错：如果传入了 int 或其他类型，尝试转 str 再转 bytes
    try:
        return str(data).encode("utf-8")
    except Exception as e:
        logger.error(f"Failed to convert data to bytes: {e}")
        return None


# -------------------------
# PEM ↔ DER(Base64)
# -------------------------
def pem_to_der_b64(pem: str) -> Optional[str]:
    """将 PEM 格式转换为 Base64 编码的 DER 字符串"""
    if not pem:
        return None

    data_bytes = to_bytes(pem)
    try:
        # 尝试作为私钥加载
        if "PRIVATE KEY" in pem.upper():
            key = serialization.load_pem_private_key(data_bytes, None, default_backend())
            der = key.private_bytes(
                serialization.Encoding.DER,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        # 尝试作为公钥加载
        else:
            key = serialization.load_pem_public_key(data_bytes, default_backend())
            der = key.public_bytes(
                serialization.Encoding.DER,
                serialization.PublicFormat.SubjectPublicKeyInfo
            )
        return base64.b64encode(der).decode()
    except Exception as e:
        logger.error(f"pem_to_der_b64 failed: {e}")
        return None


def der_b64_to_pem(key_b64: str) -> Optional[str]:
    """将 Base64 编码的 DER 转换为 PEM 字符串"""
    if not key_b64:
        return None

    try:
        der = base64.b64decode(key_b64)
    except binascii.Error as e:
        logger.error(f"Invalid Base64 string in der_b64_to_pem: {e}")
        return None

    # 尝试私钥
    try:
        key = serialization.load_der_private_key(der, None, default_backend())
        return key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
    except Exception:
        pass  # 继续尝试公钥

    # 尝试公钥
    try:
        key = serialization.load_der_public_key(der, default_backend())
        return key.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
    except Exception as e:
        logger.error(f"Failed to convert DER to PEM (neither private nor public): {e}")
        return None


# -------------------------
# 自动加载 PEM / Base64-DER
# -------------------------
def load_private_key(key: Union[str, bytes]):
    """加载私钥，支持 PEM 文本或 Base64 DER 字符串"""
    if not key:
        logger.error("load_private_key: Key is empty")
        return None

    key_bytes = to_bytes(key)

    # 1. 尝试直接加载 PEM
    try:
        return serialization.load_pem_private_key(key_bytes, None, default_backend())
    except ValueError:
        # 不是 PEM，可能是 DER Base64，继续尝试
        pass
    except Exception as e:
        logger.error(f"Error loading PEM private key: {e}")
        return None

    # 2. 尝试 Base64 Decode -> DER
    try:
        # 移除可能存在的换行符
        if isinstance(key, str):
            key = key.replace("\n", "").replace("\r", "")

        der = base64.b64decode(key)
        return serialization.load_der_private_key(der, None, default_backend())
    except (binascii.Error, ValueError, TypeError) as e:
        logger.error(f"Failed to load private key (Invalid Format/Base64): {e}")
        return None


def load_public_key(key: Union[str, bytes]):
    """加载公钥，支持 PEM 文本或 Base64 DER 字符串"""
    if not key:
        logger.error("load_public_key: Key is empty")
        return None

    key_bytes = to_bytes(key)

    # 1. 尝试直接加载 PEM
    try:
        return serialization.load_pem_public_key(key_bytes, default_backend())
    except ValueError:
        pass
    except Exception as e:
        logger.error(f"Error loading PEM public key: {e}")
        return None

    # 2. 尝试 Base64 Decode -> DER
    try:
        if isinstance(key, str):
            key = key.replace("\n", "").replace("\r", "")

        der = base64.b64decode(key)
        return serialization.load_der_public_key(der, default_backend())
    except (binascii.Error, ValueError, TypeError) as e:
        logger.error(f"Failed to load public key (Invalid Format/Base64): {e}")
        return None


# -------------------------
# RSA-OAEP 加密 / 解密
# -------------------------
def rsa_encrypt_oaep(pub_key: str, msg: Union[str, bytes]) -> Optional[str]:
    """RSA 加密，返回 Base64 字符串。失败返回 None"""
    if not msg:
        return None

    pub = load_public_key(pub_key)
    if not pub:
        return None

    msg_bytes = to_bytes(msg)

    try:
        cipher = pub.encrypt(
            msg_bytes,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            )
        )
        return base64.b64encode(cipher).decode()
    except ValueError as e:
        # 通常是消息太长，超过了密钥长度允许的范围
        logger.error(f"Encryption failed (Data too long?): {e}")
    except Exception as e:
        logger.error(f"Encryption unexpected error: {e}")

    return None


def rsa_decrypt_oaep(pri_key: str, cipher_b64: str) -> Optional[str]:
    """RSA 解密。输入 Base64 字符串。失败返回 None"""
    if not cipher_b64:
        return None

    pri = load_private_key(pri_key)
    if not pri:
        return None

    try:
        cipher_bytes = base64.b64decode(cipher_b64)
        plain = pri.decrypt(
            cipher_bytes,
            padding.OAEP(
                mgf=padding.MGF1(hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            )
        )
        return plain.decode("utf-8")
    except binascii.Error:
        logger.error("Decryption failed: Invalid Base64 input")
    except ValueError as e:
        logger.error(f"Decryption failed (Decryption error/Padding): {e}")
    except UnicodeDecodeError:
        logger.error("Decryption failed: Result is not valid UTF-8 string")
    except Exception as e:
        logger.error(f"Decryption unexpected error: {e}")

    return None


# -------------------------
# SHA256withRSA 签名 / 验证
# -------------------------
def rsa_sign_sha256(pri_key: str, msg: Union[str, bytes]) -> Optional[str]:
    """签名。返回 Base64 签名串。失败返回 None"""
    if not msg:
        return None

    pri = load_private_key(pri_key)
    if not pri:
        return None

    try:
        signature = pri.sign(
            to_bytes(msg),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode()
    except Exception as e:
        logger.error(f"Signing failed: {e}")
        return None


def rsa_verify_sha256(pub_key: str, msg: Union[str, bytes], sig_b64: str) -> bool:
    """验签。成功返回 True，失败返回 False"""
    if not msg or not sig_b64:
        return False

    pub = load_public_key(pub_key)
    if not pub:
        return False

    try:
        sig_bytes = base64.b64decode(sig_b64)
        pub.verify(
            sig_bytes,
            to_bytes(msg),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except (binascii.Error, ValueError):
        logger.warning("Verification failed: Invalid signature format")
        return False
    except InvalidSignature:
        # 签名不匹配是正常业务逻辑，不需要 error 级别日志，或者不记录
        return False
    except Exception as e:
        logger.error(f"Verification unexpected error: {e}")
        return False


# -------------------------
# RSA 密钥生成
# -------------------------
def generate_rsa_keypair(bits=2048) -> Optional[Dict[str, str]]:
    try:
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

        # Base64 DER
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
    except Exception as e:
        logger.critical(f"Key generation failed: {e}")
        return None