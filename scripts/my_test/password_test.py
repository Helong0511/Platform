import mysql.connector  # pip3 install mysql-connector-python
from passlib.context import CryptContext

# 密码上下文，用于密码哈希和验证
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """生成密码哈希"""
    return pwd_context.hash(password)


# 数据库连接配置
config = {
    'user': 'remote',
    'password': 'kb7$rL3d8!tQ',
    'host': '159.138.133.34',
    'database': 'platform',
    'raise_on_warnings': True
}

# 连接到 MySQL 数据库
conn = mysql.connector.connect(**config)
cur = conn.cursor()

username = 'zhuzhouyiya'

password = 'admin123'

hash_password = get_password_hash(password)
print(password, hash_password)
print(verify_password(password, hash_password))

up_sql = "UPDATE `users` SET `hashed_password` = %s WHERE `username` = %s"
cur.execute(up_sql, (hash_password, username))
conn.commit()
print(f'已经将用户：[{username}] 的密码更新成：[{password}]')

cur.close()
conn.close()
