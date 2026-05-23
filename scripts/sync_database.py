#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================
数据库同步脚本
============================================================

将本地 musicdb 数据库同步到远程服务器 192.168.3.3 的 musicdb

使用方式:
    ~/miniconda3/envs/music_recommend/bin/python scripts/sync_database.py

增量同步说明:
    - 默认 INCREMENTAL_MODE = True，仅同步本地新增的记录
    - 已存在的记录不会被覆盖
    - 表配置支持两种格式：'table_name' 或 ('table_name', 'unique_key')
    - unique_key 用于判断记录是否已存在，默认是 'id'
============================================================
"""

import psycopg2
from contextlib import contextmanager

# 添加项目路径
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))


# =============================================================================
# 配置
# =============================================================================

LOCAL_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', '5432')),
    'database': os.getenv('DB_NAME', 'musicdb'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'luke')
}

REMOTE_CONFIG = {
    'host': '192.168.3.3',
    'port': 5432,
    'database': 'musicdb',
    'user': 'postgres',
    'password': 'luke'  # 请根据实际情况修改
}

# 需要同步的表（按依赖顺序排列）
# format: 'table_name' or ('table_name', 'unique_column')
# 如果不指定 unique_column，则使用 id 列
TABLES = [
    'artists',
    ('songs', 'song_id'),
    'playlists',
    'song_playlist',
    'song_playlist_agg',
    'comments',
    'song_comment_agg',
    ('music_features', 'song_id'),
    ('music_features_14b', 'song_id'),
    ('music_features_api', 'song_id'),
    ('music_features_skip', 'song_id'),
    ('music_features_14b_skip', 'song_id'),
    'artist_songs_relation',
    'male_artists',
    'female_artists',
    'recommendation_history',
    'recommendation_feedback'
]

# 增量同步模式（默认关闭）
INCREMENTAL_MODE = True


@contextmanager
def get_conn(config):
    """获取数据库连接"""
    conn = psycopg2.connect(**config)
    try:
        yield conn
    finally:
        conn.close()


def get_table_row_count(cursor, table_name):
    """获取表的记录数"""
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    return cursor.fetchone()[0]


def normalize_table_spec(table_spec):
    """规范化表配置，支持两种格式：'table_name' 或 ('table_name', 'unique_col')"""
    if isinstance(table_spec, tuple):
        return table_spec[0], table_spec[1]
    else:
        return table_spec, 'id'


def get_existing_keys(cursor, table_name: str, key_column: str) -> set:
    """获取远程表中已存在的 key 列值"""
    cursor.execute(f"SELECT {key_column} FROM {table_name}")
    return set(row[0] for row in cursor.fetchall())


def sync_table(table_name: str, unique_key: str = 'id', incremental: bool = True):
    """同步单个表的数据

    Args:
        table_name: 表名
        unique_key: 唯一键列名，用于判断是否已存在
        incremental: True=增量同步(仅插入新记录)，False=全量覆盖(先清空)
    """
    print(f"\n同步表: {table_name}")

    with get_conn(LOCAL_CONFIG) as local_conn:
        local_cursor = local_conn.cursor()

        try:
            local_count = get_table_row_count(local_cursor, table_name)
        except Exception as e:
            print(f"  本地表不存在或查询失败: {e}")
            return

        print(f"  本地记录数: {local_count:,}")

        if local_count == 0:
            print(f"  表为空，跳过")
            return

        # 获取表数据
        local_cursor.execute(f"SELECT * FROM {table_name}")
        columns = [desc[0] for desc in local_cursor.description]
        rows = local_cursor.fetchall()

    with get_conn(REMOTE_CONFIG) as remote_conn:
        remote_cursor = remote_conn.cursor()

        # 检查远程表是否存在
        remote_cursor.execute(f"""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = '{table_name}'
        """)
        if remote_cursor.fetchone()[0] == 0:
            print(f"  远程表不存在，跳过")
            return

        remote_count = get_table_row_count(remote_cursor, table_name)
        print(f"  远程记录数: {remote_count:,}")

        # 确定唯一键列的索引
        try:
            key_idx = columns.index(unique_key)
        except ValueError:
            print(f"  警告: 列 '{unique_key}' 不在表中，使用所有列判断")
            key_idx = None

        rows_to_insert = rows

        if incremental:
            # 增量模式：获取远程已存在的 key，仅同步新记录
            existing_keys = get_existing_keys(remote_cursor, table_name, unique_key)
            print(f"  远程已有键值数: {len(existing_keys):,}")

            if key_idx is not None:
                rows_to_insert = [row for row in rows if row[key_idx] not in existing_keys]
            else:
                # 如果无法确定key列，降级为跳过（不做覆盖）
                new_count = len(rows) - remote_count
                if new_count <= 0:
                    print(f"  无新增记录，跳过")
                    return
                rows_to_insert = rows[:new_count]  # 假设新增的在前面

            print(f"  需同步的新记录数: {len(rows_to_insert):,}")

            if len(rows_to_insert) == 0:
                print(f"  无新数据需要同步，跳过")
                return
        else:
            # 全量覆盖模式
            remote_cursor.execute(f"TRUNCATE TABLE {table_name} CASCADE")
            remote_conn.commit()
            print(f"  已清空远程表")

        # 批量插入
        placeholders = ','.join(['%s'] * len(columns))
        insert_sql = f"INSERT INTO {table_name} ({','.join(columns)}) VALUES ({placeholders})"

        batch_size = 1000
        inserted = 0
        for i in range(0, len(rows_to_insert), batch_size):
            batch = rows_to_insert[i:i+batch_size]
            try:
                remote_cursor.executemany(insert_sql, batch)
                remote_conn.commit()
                inserted += len(batch)
                print(f"  已插入 {inserted:,}/{len(rows_to_insert):,} 条")
            except Exception as e:
                print(f"  批量插入失败: {e}")
                remote_conn.rollback()
                # 逐条插入失败的记录
                for row in batch:
                    try:
                        remote_cursor.execute(insert_sql, row)
                        remote_conn.commit()
                        inserted += 1
                    except Exception as e2:
                        pass  # 忽略已存在的记录

        print(f"  同步完成 (新增 {inserted:,} 条)")


def main():
    print("=" * 60)
    print("数据库同步：本地 -> 192.168.3.3")
    print("=" * 60)
    print(f"\n本地: {LOCAL_CONFIG['host']}:{LOCAL_CONFIG['port']}/{LOCAL_CONFIG['database']}")
    print(f"远程: {REMOTE_CONFIG['host']}:{REMOTE_CONFIG['port']}/{REMOTE_CONFIG['database']}")

    # 测试连接
    try:
        with get_conn(REMOTE_CONFIG) as conn:
            print("\n远程数据库连接成功")
    except Exception as e:
        print(f"\n远程数据库连接失败: {e}")
        print("请检查 REMOTE_CONFIG 配置")
        return

    # 同步每个表
    success_count = 0
    fail_count = 0

    for table_spec in TABLES:
        table_name, unique_key = normalize_table_spec(table_spec)
        try:
            sync_table(table_name, unique_key=unique_key, incremental=INCREMENTAL_MODE)
            success_count += 1
        except Exception as e:
            print(f"  同步失败: {e}")
            fail_count += 1

    print(f"\n{'=' * 60}")
    print("同步完成")
    print(f"  成功: {success_count}")
    print(f"  失败: {fail_count}")
    print("=" * 60)


if __name__ == "__main__":
    main()