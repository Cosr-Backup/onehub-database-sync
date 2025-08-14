#!/usr/bin/env python3
"""
用于将数据从 SQLite 迁移到 MySQL 数据库的脚本。
本脚本会处理表结构、数据迁移以及主键的自动递增。

依赖:
  - mysql-connector-python: pip install mysql-connector-python
  - toml: pip install toml (如果使用 config.toml 配置文件)
"""

import os
import sys
import sqlite3
import mysql.connector
from mysql.connector import errorcode
import tomllib

# 数据类型映射配置 (SQLite to MySQL)
# 此处可为特定表的特定字段强制指定 MySQL 数据类型
SCHEMA_MAPPING = {
    "channels": {
        "status": "BIGINT", 
        "type": "BIGINT",
        "base_url": "VARCHAR(255)",
        "tag": "VARCHAR(255)",
        "proxy": "VARCHAR(255)",
        "test_model": "VARCHAR(255)",
        "model_headers": "VARCHAR(255)",
        "custom_parameter": "VARCHAR(255)",
        "group": "VARCHAR(100)",
        "models": "TEXT",
        "model_mapping": "TEXT",
        "other": "TEXT",
        "plugin": "TEXT",
        "disabled_stream": "TEXT"
    },
    "payments": {
        "fixed_fee": "DECIMAL(10,2)",
        "percent_fee": "DECIMAL(10,2)",
        "config": "TEXT"
    },
    "users": {
        "access_token": "VARCHAR(255)",
        "group": "VARCHAR(100)",
        "avatar_url": "VARCHAR(255)",
        "password": "VARCHAR(255)",
        "email": "VARCHAR(255)",
        "github_id": "VARCHAR(255)",
        "wechat_id": "VARCHAR(255)",
        "lark_id": "VARCHAR(255)",
        "aff_code": "VARCHAR(255)",
        "oidc_id": "VARCHAR(255)"
    },
    "tokens": {
        "group": "VARCHAR(100)",
        "key": "VARCHAR(255)",
        "name": "VARCHAR(255)",
        "setting": "TEXT"
    },
    "logs": {
        "username": "VARCHAR(100)",
        "token_name": "VARCHAR(100)",
        "model_name": "VARCHAR(100)",
        "source_ip": "VARCHAR(100)",
        "content": "TEXT",
        "metadata": "TEXT"
    },
    "telegram_menus": {
        "description": "VARCHAR(255)",
        "parse_mode": "VARCHAR(50)",
        "command": "VARCHAR(255)",
        "reply_message": "TEXT"
    },
    "prices": {
        "type": "VARCHAR(50)",
        "model": "VARCHAR(255)",
        "extra_ratios": "TEXT"
    },
    # 处理主键重复的表
    "statistics": {
        "user_id": "BIGINT",
        "channel_id": "BIGINT",
        "model_name": "VARCHAR(255)"
    },
    "statistics_months": {
        "user_id": "BIGINT",
        "model_name": "VARCHAR(255)"
    },
    "abilities": {
        "channel_id": "BIGINT",
        "group": "VARCHAR(100)",
        "model": "VARCHAR(255)"
    },
    # 长文本字段映射
    "midjourneys": {
        "action": "VARCHAR(255)",
        "mj_id": "VARCHAR(255)",
        "prompt": "TEXT",
        "prompt_en": "TEXT",
        "description": "TEXT",
        "state": "VARCHAR(100)",
        "status": "VARCHAR(100)",
        "progress": "VARCHAR(100)",
        "fail_reason": "TEXT",
        "image_url": "TEXT",  # 修改为TEXT类型
        "buttons": "TEXT",
        "properties": "TEXT",
        "mode": "VARCHAR(100)"
    },
    "tasks": {
        "task_id": "VARCHAR(255)",
        "platform": "VARCHAR(100)",
        "action": "VARCHAR(255)",
        "status": "VARCHAR(100)",
        "fail_reason": "TEXT",
        "properties": "TEXT",
        "data": "TEXT",  # 修改为TEXT类型
        "notify_hook": "TEXT"
    },
    "chat_caches": {
        "hash": "VARCHAR(255)",
        "data": "TEXT"
    },
    "redemptions": {
        "key": "VARCHAR(255)",
        "name": "VARCHAR(255)"
    },
    "options": {
        "key": "VARCHAR(255)",
        "value": "TEXT"
    },
    "migrations": {
        "id": "VARCHAR(255)"
    },
    "user_groups": {
        "symbol": "VARCHAR(100)",
        "name": "VARCHAR(255)"
    },
    "model_owned_by": {
        "name": "VARCHAR(255)",
        "icon": "VARCHAR(255)"
    },
    "orders": {
        "trade_no": "VARCHAR(255)",
        "gateway_no": "VARCHAR(255)",
        "order_currency": "VARCHAR(50)",
        "status": "VARCHAR(100)"
    }
}

# 特殊处理：需要使用TEXT类型且允许设置默认值的字段列表
SPECIAL_TEXT_FIELDS_WITH_DEFAULTS = [
    # 表名, 字段名
    ("users", "group"),
    ("users", "avatar_url"),
    ("tokens", "group"),
    ("logs", "username"),
    ("logs", "token_name"),
    ("logs", "model_name"),
    ("logs", "source_ip"),
    ("telegram_menus", "description"),
    ("telegram_menus", "parse_mode"),
    ("prices", "type"),
    ("channels", "base_url"),
    ("channels", "tag"),
    ("channels", "group"),
    ("channels", "proxy"),
    ("channels", "test_model"),
    ("channels", "model_headers"),
    ("channels", "custom_parameter"),
]

def load_config():
    """
    加载配置文件，返回配置字典。
    首先尝试从环境变量获取，如果失败则尝试从配置文件加载。
    """
    print("正在尝试首先从环境变量加载配置...")
    config = load_config_from_env()
    if config:
        return config

    print("未设置环境变量。正在尝试从 config.toml 加载...")
    try:
        config_path = os.environ.get("CONFIG_PATH", "config.toml")
        print(f"正在从以下位置加载配置: {config_path}")
        
        if not os.path.exists(config_path):
            print(f"错误: 在 {config_path} 未找到配置文件且未设置环境变量。")
            return None
            
        with open(config_path, "rb") as f:
            config = tomllib.load(f)
        
        # 验证必要的配置项
        if "database" not in config or "mysql" not in config:
            print("错误: 配置文件结构无效。缺少 [database] 或 [mysql] 部分。")
            return None
            
        return config
    except Exception as e:
        print(f"从文件加载配置时出错: {e}")
        return None

def load_config_from_env():
    """
    从环境变量中加载配置
    """
    required_vars = ["MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE", "SQLITE_PATH"]
    if all(os.environ.get(var) for var in required_vars):
        print("已找到所有必需的 MySQL 环境变量。")
        return {
            "database": {
                "sqlite_file": os.environ.get("SQLITE_PATH")
            },
            "mysql": {
                "host": os.environ.get("MYSQL_HOST"),
                "port": os.environ.get("MYSQL_PORT"),
                "user": os.environ.get("MYSQL_USER"),
                "password": os.environ.get("MYSQL_PASSWORD"),
                "database": os.environ.get("MYSQL_DATABASE")
            }
        }
    return None

def convert_type(sqlite_type, table_name, col_name):
    """
    根据 schema 映射表将 SQLite 数据类型转换为 MySQL 数据类型
    """
    # 1. 检查是否有强制的显式映射
    if table_name in SCHEMA_MAPPING and col_name in SCHEMA_MAPPING[table_name]:
        return SCHEMA_MAPPING[table_name][col_name]

    # 2. 默认类型映射
    sqlite_type = sqlite_type.lower().strip()
    if "int" in sqlite_type:
        return "BIGINT"
    if any(t in sqlite_type for t in ["char", "clob", "text"]):
        # 根据内容判断是否使用TEXT或VARCHAR
        # 默认使用VARCHAR(255)，除非是可能包含长文本的字段
        if col_name in ["description", "content", "data", "properties", "config", "prompt", "image_url", "value"]:
            return "TEXT"
        return "VARCHAR(255)"
    if "blob" in sqlite_type:
        return "BLOB"
    if any(t in sqlite_type for t in ["real", "double", "float"]):
        return "DOUBLE"
    if "numeric" in sqlite_type or "decimal" in sqlite_type:
        return "DECIMAL(10, 2)"
    if "boolean" in sqlite_type:
        return "BOOLEAN" # 在 MySQL 中是 TINYINT(1) 的别名
    if "date" in sqlite_type:
        return "DATE"
    if "time" in sqlite_type:
        return "DATETIME"
    
    # 默认回退到 VARCHAR
    return "VARCHAR(255)"

def test_mysql_connection(mysql_config):
    """
    测试 MySQL 连接是否可用
    """
    try:
        print(f"正在测试 MySQL 连接到 {mysql_config['host']}:{mysql_config['port']} 用户名 {mysql_config['user']}...")
        conn = mysql.connector.connect(**mysql_config)
        conn.close()
        print("MySQL 连接测试成功。")
        return True
    except mysql.connector.Error as err:
        print(f"MySQL 连接测试失败: {err}")
        return False

def get_primary_key_info(sqlite_conn, table):
    """
    获取表的主键信息
    """
    cursor = sqlite_conn.cursor()
    cursor.execute(f"PRAGMA table_info(`{table}`)")
    columns = cursor.fetchall()
    
    pk_columns = []
    for col in columns:
        if col[5] > 0:  # 第5个元素是主键标志
            pk_columns.append((col[1], col[5]))  # 返回列名和主键顺序
    
    # 按主键顺序排序
    pk_columns.sort(key=lambda x: x[1])
    return [col[0] for col in pk_columns]

def is_special_text_field(table, col_name):
    """
    判断是否为需要特殊处理的TEXT字段（允许有默认值的TEXT）
    """
    return (table, col_name) in SPECIAL_TEXT_FIELDS_WITH_DEFAULTS

def migrate_table_structure(sqlite_conn, mysql_conn):
    """
    迁移表结构从 SQLite 到 MySQL
    """
    sqlite_cursor = sqlite_conn.cursor()
    mysql_cursor = mysql_conn.cursor()

    sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [row[0] for row in sqlite_cursor.fetchall()]

    for table in tables:
        try:
            print(f"正在迁移表结构: `{table}`")
            
            # 先删除已存在的表
            mysql_cursor.execute(f"DROP TABLE IF EXISTS `{table}`;")
            
            sqlite_cursor.execute(f"PRAGMA table_info(`{table}`);")
            columns = sqlite_cursor.fetchall()

            # 获取主键信息
            pk_columns = get_primary_key_info(sqlite_conn, table)

            column_defs = []
            for col in columns:
                # col: (cid, name, type, notnull, dflt_value, pk)
                col_name = col[1]
                col_type = convert_type(col[2], table, col_name)
                not_null = " NOT NULL" if col[3] else ""
                
                # 处理主键和自增
                is_pk = col[5] > 0
                auto_increment = ""
                # 只有第一个主键列且是整型才设置为AUTO_INCREMENT
                if is_pk and col_type == "BIGINT" and (not pk_columns or col_name == pk_columns[0]):
                    auto_increment = " AUTO_INCREMENT"

                # 处理默认值
                default_val = col[4]
                default = ""
                if default_val is not None:
                    # 处理默认值
                    # 对于普通类型或特殊处理的TEXT字段，设置默认值
                    if col_type not in ["BLOB", "TEXT", "MEDIUMTEXT", "LONGTEXT"] or is_special_text_field(table, col_name):
                        if col_type in ["BIGINT", "DOUBLE", "DECIMAL(10, 2)", "BOOLEAN"]:
                            default = f" DEFAULT {default_val}"
                        else:
                            escaped_val = str(default_val).replace("'", "''")
                            default = f" DEFAULT '{escaped_val}'"
                
                # 将 `group` 等关键字用反引号包裹
                safe_col_name = f"`{col_name}`"
                column_defs.append(f"{safe_col_name} {col_type}{not_null}{default}{auto_increment}")

            # 添加主键约束
            if pk_columns:
                pk_cols_str = ", ".join([f"`{col}`" for col in pk_columns])
                column_defs.append(f"PRIMARY KEY ({pk_cols_str})")

            create_table_sql = f"CREATE TABLE `{table}` (\n    " + ",\n    ".join(column_defs) + "\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;"
            
            print(f"正在执行 SQL: \n{create_table_sql}")
            mysql_cursor.execute(create_table_sql)
            print(f"表 `{table}` 创建成功。")

        except mysql.connector.Error as err:
            print(f"创建表 `{table}` 时出错: {err}")
        except Exception as e:
            print(f"处理表 `{table}` 时发生意外错误: {e}")

    mysql_cursor.close()

def migrate_data(sqlite_conn, mysql_conn):
    """
    迁移数据从 SQLite 到 MySQL
    """
    sqlite_cursor = sqlite_conn.cursor()
    mysql_cursor = mysql_conn.cursor()

    sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [row[0] for row in sqlite_cursor.fetchall()]

    for table in tables:
        try:
            print(f"正在迁移表 `{table}` 的数据")
            sqlite_cursor.execute(f"SELECT * FROM `{table}`")
            rows = sqlite_cursor.fetchall()

            if not rows:
                print(f"表 `{table}` 为空，跳过。")
                continue

            # 获取列名
            columns = [description[0] for description in sqlite_cursor.description]
            safe_columns = [f"`{col}`" for col in columns]
            
            # 准备插入语句
            placeholders = ", ".join(["%s"] * len(columns))
            insert_sql = f"INSERT INTO `{table}` ({', '.join(safe_columns)}) VALUES ({placeholders})"
            
            # 处理主键重复的情况 - 对于特定表使用REPLACE INTO
            if table in ["abilities", "statistics", "statistics_months"]:
                insert_sql = insert_sql.replace("INSERT INTO", "REPLACE INTO")
                print(f"使用REPLACE INTO避免主键冲突: {table}")
            
            # 使用批量插入，但每次只插入50条记录，避免一次性处理太多数据
            batch_size = 50
            for i in range(0, len(rows), batch_size):
                batch = rows[i:i+batch_size]
                try:
                    mysql_cursor.executemany(insert_sql, batch)
                    mysql_conn.commit()
                    print(f"已迁移 {len(batch)} 行数据到表 `{table}`（总计进度: {i+len(batch)}/{len(rows)}）。")
                except mysql.connector.Error as err:
                    print(f"批量插入数据到表 `{table}` 时出错: {err}")
                    # 尝试逐条插入，跳过错误记录
                    success_count = 0
                    for row in batch:
                        try:
                            mysql_cursor.execute(insert_sql, row)
                            mysql_conn.commit()
                            success_count += 1
                        except mysql.connector.Error as row_err:
                            print(f"插入单条记录时出错，已跳过: {row_err}")
                            mysql_conn.rollback()
                    print(f"单条插入完成，成功: {success_count}/{len(batch)}")

        except mysql.connector.Error as err:
            print(f"迁移数据到表 `{table}` 时出错: {err}")
            mysql_conn.rollback()
        except Exception as e:
            print(f"为表 `{table}` 迁移数据时发生意外错误: {e}")
    
    mysql_cursor.close()

def main():
    """
    主函数，处理数据库迁移流程
    """
    sqlite_conn = None
    mysql_conn = None
    
    try:
        config = load_config()
        if not config:
            print("加载配置失败，正在退出。")
            sys.exit(1)
        
        sqlite_db_file = config["database"]["sqlite_file"]
        mysql_db_config = {
            "database": config["mysql"]["database"],
            "user": config["mysql"]["user"],
            "password": config["mysql"]["password"],
            "host": config["mysql"]["host"],
            "port": int(config["mysql"]["port"]),
        }
        
        print(f"SQLite 数据库: {sqlite_db_file}")
        
        # 连接 SQLite
        sqlite_conn = sqlite3.connect(sqlite_db_file)
        print("SQLite 连接已成功建立。")
        
        # 测试并连接到 MySQL
        if not test_mysql_connection(mysql_db_config):
            sys.exit(1)
        mysql_conn = mysql.connector.connect(**mysql_db_config)
        print("MySQL 连接已成功建立。")
        
        # 执行迁移
        migrate_table_structure(sqlite_conn, mysql_conn)
        migrate_data(sqlite_conn, mysql_conn)
        
        print("\n迁移成功完成！")
        
    except Exception as e:
        print(f"\n迁移过程中发生错误: {e}")
        sys.exit(1)
    finally:
        if sqlite_conn:
            sqlite_conn.close()
            print("SQLite 连接已关闭。")
        if mysql_conn:
            mysql_conn.close()
            print("MySQL 连接已关闭。")

if __name__ == "__main__":
    main()
