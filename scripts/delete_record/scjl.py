import pymysql
import time
import logging
import signal

# ================= 日志配置 =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ================= 低配服务器参数 =================
BATCH_SIZE = 500        # 每批删除行数（越小越稳）
SLEEP_SECONDS = 0.5     # 每批间隔时间（秒）
MAX_EXEC_MS = 1500      # 单条 SQL 最大执行时间（ms）


class LowSpecSafeDeleter:
    def __init__(self, db_config):
        self.conn = pymysql.connect(
            host=db_config['host'],
            user=db_config['user'],
            password=db_config['password'],
            database=db_config['database'],
            port=db_config.get('port', 3306),
            charset='utf8mb4',
            autocommit=False
        )

        # 只限制 DELETE 的执行时间，防止拖死 MySQL
        with self.conn.cursor() as cur:
            cur.execute(f"SET SESSION MAX_EXECUTION_TIME = {MAX_EXEC_MS}")

        self.running = True

    # ========== 信号处理 ==========
    def stop(self, sig, frame):
        logger.warning("收到停止信号，正在安全退出...")
        self.running = False

    # ========== 表是否存在 ==========
    def table_exists(self, table):
        sql = """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
              AND table_name = %s
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, (table,))
            return cur.fetchone() is not None

    # ========== 字段是否存在 ==========
    def column_exists(self, table, column):
        sql = """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = %s
              AND column_name = %s
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, (table, column))
            return cur.fetchone() is not None

    # ========== 核心删除逻辑 ==========
    def batch_delete(self, table, time_col, days, conditions):
        where = " AND ".join(
            [f"{k}=%s" for k in conditions.keys()]
            + [f"{time_col} < NOW() - INTERVAL %s DAY"]
        )

        sql = f"""
            DELETE FROM {table}
            WHERE {where}
            LIMIT %s
        """

        total_deleted = 0
        batch_no = 0

        with self.conn.cursor() as cur:
            while self.running:
                cur.execute(
                    sql,
                    tuple(conditions.values()) + (days, BATCH_SIZE)
                )
                rows = cur.rowcount
                logger.info(f"[{table}] 第 {batch_no + 1} 批删除 {rows} 行")

                if rows == 0:
                    break

                self.conn.commit()
                total_deleted += rows
                batch_no += 1
                time.sleep(SLEEP_SECONDS)

        logger.info(f"[{table}] 删除结束，共删除 {total_deleted} 行")

    def close(self):
        self.conn.close()


def main():
    # ========== 数据库配置 ==========
    db_config = {
        'host': 'localhost',
        'user': 'remote',
        'password': 'kb7$rL3d8!tQ',
        'database': 'platform',
    }

    # ========== 业务删除条件 ==========
    delete_conditions = {
        'advertiser_id': 9,
        'offer_id': 46,
        'publisher_id': 9
    }

    # ========== 时间条件 ==========
    time_column = 'created_at'   # ⚠️ 按你的真实字段名修改
    days_before = 2              # 删除 2 天前的数据

    # ========== 目标表 ==========
    tables = [
        'clicks',
        'click_stats'
    ]

    deleter = LowSpecSafeDeleter(db_config)

    # 支持 Ctrl + C / kill 安全中断
    signal.signal(signal.SIGINT, deleter.stop)
    signal.signal(signal.SIGTERM, deleter.stop)

    try:
        logger.info("低配服务器安全删除模式启动（无 COUNT / 有容错）")

        for table in tables:
            # 表不存在
            if not deleter.table_exists(table):
                logger.warning(f"[{table}] 表不存在，已跳过")
                continue

            # 时间字段不存在
            if not deleter.column_exists(table, time_column):
                logger.warning(
                    f"[{table}] 字段 `{time_column}` 不存在，已跳过"
                )
                continue

            logger.info(f"[{table}] 表 & 字段检查通过，开始安全删除")

            deleter.batch_delete(
                table,
                time_column,
                days_before,
                delete_conditions
            )

        logger.info("所有表删除流程结束")

    finally:
        deleter.close()


if __name__ == "__main__":
    main()
