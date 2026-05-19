#!/usr/bin/env python3
"""
初始化 song_playlist_agg 表

将 songs 通过 song_playlist 关联 playlists 的结果预先聚合存储。

使用方法:
    ~/miniconda3/envs/music/bin/python scripts/init_song_playlist_agg.py

注意: 需要先创建 song_playlist_agg 表，参见 database/schema.sql
"""

import os
import sys
import time

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

# 加载环境变量
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

import psycopg2


def get_db_connection():
    """获取数据库连接"""
    return psycopg2.connect(
        host=os.getenv('PG_HOST', 'localhost'),
        port=os.getenv('PG_PORT', '5432'),
        database=os.getenv('PG_DB', 'musicdb'),
        user=os.getenv('PG_USER', 'postgres'),
        password=os.getenv('PG_PASSWORD', 'luke')
    )


def init_song_playlist_agg():
    """初始化 song_playlist_agg 表"""
    print("=" * 60)
    print("song_playlist_agg 数据填充开始")
    print("=" * 60)

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. 清空表
        print("\n[1/3] 清空 song_playlist_agg 表...")
        cursor.execute("TRUNCATE song_playlist_agg RESTART IDENTITY")
        conn.commit()
        print("      清空完成")

        # 2. 执行聚合插入
        print("\n[2/3] 执行聚合查询（这可能需要几分钟）...")
        start_time = time.time()

        cursor.execute("""
            INSERT INTO song_playlist_agg (
                song_id, playlist_names, playlist_categories,
                playlist_count, playlist_names_str, playlist_categories_str
            )
            SELECT
                s.song_id,
                ARRAY_AGG(DISTINCT p.playlist_name) FILTER (WHERE p.playlist_name IS NOT NULL),
                ARRAY_AGG(DISTINCT p.category) FILTER (WHERE p.category IS NOT NULL),
                COUNT(DISTINCT sp.playlist_id),
                STRING_AGG(DISTINCT p.playlist_name, ', ') FILTER (WHERE p.playlist_name IS NOT NULL),
                STRING_AGG(DISTINCT p.category, ', ') FILTER (WHERE p.category IS NOT NULL)
            FROM songs s
            LEFT JOIN song_playlist sp ON s.song_id = sp.song_id
            LEFT JOIN playlists p ON sp.playlist_id = p.playlist_id
            GROUP BY s.song_id
        """)

        conn.commit()
        elapsed = time.time() - start_time
        print(f"      聚合完成，耗时: {elapsed:.1f} 秒")

        # 3. 验证结果
        print("\n[3/3] 验证数据...")

        # 总数
        cursor.execute("SELECT COUNT(*) FROM song_playlist_agg")
        total = cursor.fetchone()[0]

        # 有歌单的歌曲数
        cursor.execute("""
            SELECT COUNT(*) FROM song_playlist_agg
            WHERE playlist_names IS NOT NULL
            AND array_length(playlist_names, 1) > 0
        """)
        with_playlists = cursor.fetchone()[0]

        # 无歌单的歌曲数
        cursor.execute("""
            SELECT COUNT(*) FROM song_playlist_agg
            WHERE playlist_names IS NULL
            OR array_length(playlist_names, 1) = 0
        """)
        without_playlists = cursor.fetchone()[0]

        print(f"\n{'=' * 60}")
        print("填充结果统计:")
        print(f"  - 总记录数:           {total:,}")
        print(f"  - 有歌单的歌曲:       {with_playlists:,}")
        print(f"  - 无歌单的歌曲:       {without_playlists:,}")
        print(f"{'=' * 60}")

        # 显示样例
        print("\n样例数据:")
        cursor.execute("""
            SELECT song_id, playlist_names, playlist_count
            FROM song_playlist_agg
            WHERE array_length(playlist_names, 1) > 0
            LIMIT 3
        """)
        for row in cursor.fetchall():
            print(f"  song_id={row[0]}, playlists={row[1][:2] if row[1] else []}..., count={row[2]}")

        print("\n✅ song_playlist_agg 填充完成!")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ 错误: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    init_song_playlist_agg()