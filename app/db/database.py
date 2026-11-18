"""旧数据库引导入口兼容层；生产数据库 provisioning 必须由独立身份执行。"""


async def create_database():
    """
    兼容旧调用名，但永久禁止应用数据库账号创建数据库。

    数据库实例/schema provisioning 必须由独立运维身份完成；
    schema DDL 必须通过 MIGRATION_DATABASE_URL 运行 Migration Runner。
    即使遗留调用点尚未被发现，也必须 fail-closed，不能回退使用应用 DSN。
    """
    raise RuntimeError(
        "禁止通过应用数据库连接创建数据库；"
        "请使用独立 provisioning 身份创建数据库，"
        "并使用 MIGRATION_DATABASE_URL 执行 python -m app.db.migrations apply"
    )
