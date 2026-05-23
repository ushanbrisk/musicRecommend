#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================
数据库同步脚本
============================================================

将本地 musicdb 数据库同步到远程服务器 192.168.3.3 的 musicdb

使用方式:
    ~/miniconda3/envs/music_recommend/bin/python scripts/sync_database.py

注意:
    - 远程数据库连接信息需要在 .env 中配置
    - 默认同步所有表，数据会被覆盖
    - 执行前请确认远程数据库为空或可接受覆盖
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
TABLES = [
    'artists',
    'songs',
    'playlists',
    'song_playlist',
    'song_playlist_agg',
    'comments',
    'song_comment_agg',
    'music_features',
    'music_features_14b',
    'music_features_api',
    'music_features_skip',
    'music_features_14b_skip',
    'artist_songs_relation',
    'male_artists',
    'female_artists',
    'recommendation_history',
    'recommendation_feedback'
]


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


def sync_table(table_name: str, use_truncate: bool = True):
    """同步单个表的数据"""
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

        if use_truncate:
            # 清除远程表数据（全量覆盖）
            remote_cursor.execute(f"TRUNCATE TABLE {table_name} CASCADE")
            remote_conn.commit()
            print(f"  已清空远程表")

        # 批量插入
        placeholders = ','.join(['%s'] * len(columns))
        insert_sql = f"INSERT INTO {table_name} ({','.join(columns)}) VALUES ({placeholders})"

        batch_size = 1000
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i+batch_size]
            try:
                remote_cursor.executemany(insert_sql, batch)
                remote_conn.commit()
                print(f"  已插入 {min(i+batch_size, len(rows)):,}/{len(rows):,} 条")
            except Exception as e:
                print(f"  插入失败: {e}")
                remote_conn.rollback()
                # 如果插入失败，尝试逐条插入
                for row in batch:
                    try:
                        remote_cursor.execute(insert_sql, row)
                        remote_conn.commit()
                    except Exception as e2:
                        print(f"    单条插入失败: {e2}")
                        remote_conn.rollback()

        print(f"  同步完成")


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

    for table in TABLES:
        try:
            sync_table(table)
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