import random

import pymysql.cursors

from rsa_utils import *  # 导入我们改进后的RSA工具

# ----------------------------------------------------
# 数据库连接配置 (请修改为您的真实配置)
# ----------------------------------------------------
DB_CONFIG = {
    'host': '159.138.133.34',
    "port": 3306,
    'user': 'remote',
    'password': 'kb7$rL3d8!tQ',
    'db': 'platform',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

"""
CREATE TABLE IF NOT EXISTS rsa_app_keys (
    id INT AUTO_INCREMENT PRIMARY KEY,
    app_id VARCHAR(100) UNIQUE NOT NULL COMMENT '应用或服务的唯一标识',
    public_key_b64 TEXT NOT NULL COMMENT 'Base64 DER格式的公钥',
    private_key_b64 TEXT NOT NULL COMMENT 'Base64 DER格式的私钥'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

APP_ID = str(random.randint(1000, 9999))

MESSAGE_TO_TEST = f"Testing key {APP_ID} retrieval from real MySQL database."


# ----------------------------------------------------
# 数据库操作函数
# ----------------------------------------------------

def get_db_connection():
    """建立数据库连接，加入容错处理"""
    try:
        conn = pymysql.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        logger.critical(f"Database Connection Failed: {e}")
        return None


def store_keys_to_db(app_id: str, pub_key: str, pri_key: str) -> bool:
    """将 Base64 DER 密钥存储到数据库"""
    conn = get_db_connection()
    if not conn: return False

    sql = """
          INSERT INTO rsa_app_keys (app_id, public_key_b64, private_key_b64)
          VALUES (%s, %s, %s) ON DUPLICATE KEY \
          UPDATE public_key_b64 = \
          VALUES (public_key_b64), private_key_b64 = \
          VALUES (private_key_b64) \
          """
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, (app_id, pub_key, pri_key))
        conn.commit()
        logger.info(f"Keys for {app_id} stored/updated successfully.")
        return True
    except Exception as e:
        logger.error(f"Failed to store keys in DB: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def retrieve_keys_from_db(app_id: str) -> Optional[Dict[str, str]]:
    """从数据库检索 Base64 DER 密钥"""
    conn = get_db_connection()
    if not conn: return None

    sql = "SELECT public_key_b64, private_key_b64 FROM rsa_app_keys WHERE app_id = %s"

    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, (app_id,))
            result = cursor.fetchone()
            if result:
                logger.info(f"Keys for {app_id} retrieved successfully.")
                return {
                    "public_key": result["public_key_b64"],
                    "private_key": result["private_key_b64"]
                }
            else:
                logger.warning(f"No keys found for {app_id}.")
                return None
    except Exception as e:
        logger.error(f"Failed to retrieve keys from DB: {e}")
        return None
    finally:
        conn.close()


# ----------------------------------------------------
# 主测试逻辑
# ----------------------------------------------------

print("\n=== 1. 密钥生成与插入真实 MySQL ===")
keys = generate_rsa_keypair(bits=4096)

if not keys:
    print("密钥生成失败，测试终止。")
    exit()

for item in keys:
    print(item, keys.get(item))

# 1. 存储密钥
storage_success = store_keys_to_db(
    APP_ID,
    keys["public_der_b64"],
    keys["private_der_b64"]
)

if not storage_success:
    print("❌ 密钥存储到 MySQL 失败，请检查配置和表结构。")
    exit()

print("✅ 密钥已成功存储到 MySQL。")

# 2. 检索密钥
print("\n=== 2. 从 MySQL 检索并测试密钥有效性 ===")
retrieved_keys = retrieve_keys_from_db(APP_ID)

if not retrieved_keys:
    print("❌ 密钥检索失败，测试终止。")
    exit()

retrieved_pub = retrieved_keys["public_key"]
retrieved_pri = retrieved_keys["private_key"]
print("✅ 密钥已成功检索。开始加密测试...")

# 3. 使用检索到的密钥进行加密
ciphertext = rsa_encrypt_oaep(retrieved_pub, MESSAGE_TO_TEST)
if not ciphertext:
    print("❌ 加密失败。请检查检索到的公钥是否有效。")
    exit()
print("✅ 加密成功。")

# 4. 使用检索到的密钥进行解密
plaintext = rsa_decrypt_oaep(retrieved_pri, ciphertext)

if plaintext == MESSAGE_TO_TEST:
    print(f"✅ 解密成功。原文: {plaintext}")
else:
    print("❌ 解密失败。")

# 5. 签名和验签测试
signature = rsa_sign_sha256(retrieved_pri, MESSAGE_TO_TEST)
is_valid = rsa_verify_sha256(retrieved_pub, MESSAGE_TO_TEST, signature)

if is_valid:
    print("✅ 签名验证：通过")
else:
    print("❌ 签名验证：失败")

print("\n--- 测试完成 ---")
