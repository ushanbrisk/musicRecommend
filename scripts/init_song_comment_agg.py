#!/usr/bin/env python3
"""
初始化 song_comment_agg 表

从 MongoDB 同步评论数据到 PostgreSQL 预聚合表。

使用方法:
    ~/miniconda3/envs/music/bin/python scripts/init_song_comment_agg.py

注意: 需要先创建 song_comment_agg 表，参见 database/schema.sql
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
from pymongo import MongoClient


def get_pg_connection():
    """获取 PostgreSQL 连接"""
    return psycopg2.connect(
        host=os.getenv('PG_HOST', 'localhost'),
        port=os.getenv('PG_PORT', '5432'),
        database=os.getenv('PG_DB', 'musicdb'),
        user=os.getenv('PG_USER', 'postgres'),
        password=os.getenv('PG_PASSWORD', 'luke')
    )


def get_mongo_client():
    """获取 MongoDB 连接"""
    return MongoClient(
        host=os.getenv('MONGO_HOST', 'localhost'),
        port=int(os.getenv('MONGO_PORT', 27017))
    )


def init_song_comment_agg():
    """初始化 song_comment_agg 表"""
    print("=" * 60)
    print("song_comment_agg 数据填充开始")
    print("=" * 60)

    # 连接数据库
    pg_conn = get_pg_connection()
    pg_cursor = pg_conn.cursor()

    mongo_client = get_mongo_client()
    mongo_db = mongo_client[os.getenv('MONGO_DB', 'netease')]

    try:
        # 1. 清空表
        print("\n[1/4] 清空 song_comment_agg 表...")
        pg_cursor.execute("TRUNCATE song_comment_agg RESTART IDENTITY")
        pg_conn.commit()
        print("      清空完成")

        # 2. 获取所有有评论的歌曲
        print("\n[2/4] 获取所有有评论的歌曲 ID...")
        song_ids = mongo_db.comments.distinct('song_id')
        total_songs = len(song_ids)
        print(f"      共有 {total_songs:,} 首歌曲有评论")

        if total_songs == 0:
            print("\n⚠️  MongoDB 中没有评论数据")
            return

        # 3. 分批处理
        print("\n[3/4] 开始填充数据（分批处理）...")
        batch_size = 1000
        start_time = time.time()

        for i in range(0, total_songs, batch_size):
            batch_song_ids = song_ids[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (total_songs + batch_size - 1) // batch_size

            if batch_num % 10 == 1 or batch_num == total_batches:
                elapsed = time.time() - start_time
                print(f"      处理批次 {batch_num}/{total_batches} ({(i/total_songs*100):.1f}%) - 已耗时 {elapsed:.0f}秒")

            for song_id in batch_song_ids:
                # 获取该歌曲的评论（按点赞数排序，取前5条）
                comments = list(mongo_db.comments.find(
                    {'song_id': song_id},
                    {'content': 1, 'sentiment': 1, 'polarity': 1, 'likedCount': 1}
                ).sort('likedCount', -1).limit(5))

                if not comments:
                    continue

                # 聚合数据
                top_comments = [c['content'][:200].replace('\x00', '') if c.get('content') else '' for c in comments]
                sentiments = [c.get('sentiment', 'neutral') for c in comments]
                polarities = [c.get('polarity', 0) for c in comments]

                positive_count = sentiments.count('positive')
                neutral_count = sentiments.count('neutral')
                negative_count = sentiments.count('negative')

                comment_count = mongo_db.comments.count_documents({'song_id': song_id})

                avg_polarity = sum(polarities) / len(polarities) if polarities else 0

                # 插入 PostgreSQL
                pg_cursor.execute("""
                    INSERT INTO song_comment_agg (
                        song_id, comment_count, top_comments, comment_summary,
                        positive_count, neutral_count, negative_count, avg_polarity
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (song_id) DO UPDATE SET
                        comment_count = EXCLUDED.comment_count,
                        top_comments = EXCLUDED.top_comments,
                        comment_summary = EXCLUDED.comment_summary,
                        positive_count = EXCLUDED.positive_count,
                        neutral_count = EXCLUDED.neutral_count,
                        negative_count = EXCLUDED.negative_count,
                        avg_polarity = EXCLUDED.avg_polarity,
                        updated_at = CURRENT_TIMESTAMP
                """, (
                    song_id, comment_count, top_comments,
                    '; '.join(top_comments).replace('\x00', ''),
                    positive_count, neutral_count, negative_count, avg_polarity
                ))

            pg_conn.commit()

        elapsed = time.time() - start_time
        print(f"      数据填充完成，耗时: {elapsed:.1f} 秒")

        # 4. 验证结果
        print("\n[4/4] 验证数据...")

        # 总数
        pg_cursor.execute("SELECT COUNT(*) FROM song_comment_agg")
        total = pg_cursor.fetchone()[0]

        # 平均评论数
        pg_cursor.execute("SELECT AVG(comment_count) FROM song_comment_agg")
        avg_comments = pg_cursor.fetchone()[0]

        # 平均情感极性
        pg_cursor.execute("SELECT AVG(avg_polarity) FROM song_comment_agg")
        avg_polarity = pg_cursor.fetchone()[0]

        print(f"\n{'=' * 60}")
        print("填充结果统计:")
        print(f"  - 总记录数:           {total:,}")
        print(f"  - 平均评论数:         {avg_comments:.1f}")
        print(f"  - 平均情感极性:       {avg_polarity:.2f}")
        print(f"{'=' * 60}")

        # 显示样例
        print("\n样例数据:")
        pg_cursor.execute("""
            SELECT song_id, comment_count, top_comments, avg_polarity
            FROM song_comment_agg
            LIMIT 3
        """)
        for row in pg_cursor.fetchall():
            comments_preview = row[2][:2] if row[2] else []
            print(f"  song_id={row[0]}, count={row[1]}, top=[{comments_preview[0][:30] if comments_preview else ''}...], polarity={row[3]}")

        print("\n✅ song_comment_agg 填充完成!")

    except Exception as e:
        pg_conn.rollback()
        print(f"\n❌ 错误: {e}")
        raise
    finally:
        mongo_client.close()
        pg_cursor.close()
        pg_conn.close()


if __name__ == "__main__":
    init_song_comment_agg()