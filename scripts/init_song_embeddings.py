#!/usr/bin/env python3
"""
初始化 song_embeddings 表

将 songs 表的数据结合 song_playlist_agg 表生成文本描述，
然后通过 Embedding API 生成向量，存储到 song_embeddings 表。

使用方法:
    ~/miniconda3/envs/music/bin/python scripts/init_song_embeddings.py

注意:
    1. 需要先创建 song_embeddings 表，参见 database/schema.sql
    2. 需要配置 .env 文件中的 Embedding API 相关环境变量
    3. 建议先执行 init_song_playlist_agg.py 确保歌单数据已就绪
"""

import os
import sys
import time
from dotenv import load_dotenv

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from openai import OpenAI

# 加载环境变量
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(env_path)

# 初始化 Embedding 客户端
embedding_client = OpenAI(
    api_key=os.getenv('EMBEDDING_API_KEY'),
    base_url=os.getenv('EMBEDDING_PROVIDER_URL')
)

EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL_NAME')

def get_db_connection():
    """获取数据库连接"""
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'musicdb'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', 'luke')
    )


def generate_embedding(text: str):
    """调用 Embedding API 生成向量"""
    try:
        response = embedding_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text,
            encoding_format="float"
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"    Embedding API 错误: {e}")
        return None


def build_text_description(song_name, artist, album, playlist_names=None, playlist_categories=None):
    """构建歌曲的文本描述（用于生成 embedding）"""
    parts = []

    # 歌曲名
    if song_name:
        parts.append(song_name)

    # 艺术家
    if artist:
        parts.append(artist)

    # 专辑
    if album:
        parts.append(album)

    # 歌单名称（最多取5个）
    if playlist_names:
        if isinstance(playlist_names, str):
            playlists = playlist_names.split('##')[:5]
        elif isinstance(playlist_names, list):
            playlists = playlist_names[:5]
        else:
            playlists = []
        parts.extend([p.strip() for p in playlists if p.strip()])

    # 歌单分类（最多取3个）
    if playlist_categories:
        if isinstance(playlist_categories, str):
            categories = playlist_categories.split('##')[:3]
        elif isinstance(playlist_categories, list):
            categories = playlist_categories[:3]
        else:
            categories = []
        parts.extend([c.strip() for c in categories if c.strip()])

    return ' '.join(parts)

# 文本描述构建说明：
# - 只用歌名+艺术家+专辑+歌单信息，暂不加入评论数据
# - 原因：评论内容较杂乱（"太好听了"、"一般般"），不适合作为语义特征
# - 歌单名称/分类（如"欧美流行"、"欢快"）更能反映歌曲风格/情绪/场景等语义信息


def init_song_embeddings(batch_size=1000):
    """
    初始化 song_embeddings 表

    Args:
        batch_size: 每批处理的歌曲数量，默认1000
    """
    print("=" * 60)
    print("song_embeddings 向量生成开始")
    print("=" * 60)
    print(f"Embedding 模型: {EMBEDDING_MODEL}")
    print(f"批次大小: {batch_size}")
    print()

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. 统计信息
        print("[1/4] 统计歌曲信息...")
        cursor.execute("SELECT COUNT(*) FROM songs")
        total_songs = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM song_embeddings WHERE embedding IS NOT NULL")
        existing_count = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM songs s
            LEFT JOIN song_embeddings se ON s.song_id = se.song_id
            WHERE se.id IS NULL
        """)
        pending_count = cursor.fetchone()[0]

        print(f"    歌曲总数: {total_songs:,}")
        print(f"    已生成向量: {existing_count:,}")
        print(f"    待生成: {pending_count:,}")

        if pending_count == 0:
            print("\n✅ 所有歌曲向量已生成完毕，无需重复执行")
            return

        # 2. 批量获取待处理的歌曲
        print("\n[2/4] 开始生成向量...")
        print("    (按 Enter 继续，按 Ctrl+C 取消)")

        processed = 0
        batch_num = 0

        while True:
            # 获取一批待处理的歌曲
            cursor.execute("""
                SELECT
                    s.song_id,
                    s.song_name,
                    s.artist,
                    s.album,
                    spa.playlist_names_str,
                    spa.playlist_categories_str
                FROM songs s
                LEFT JOIN song_embeddings se ON s.song_id = se.song_id
                LEFT JOIN song_playlist_agg spa ON s.song_id = spa.song_id
                WHERE se.id IS NULL
                LIMIT %s
            """, (batch_size,))

            rows = cursor.fetchall()

            if not rows:
                print("\n    所有歌曲向量已生成完毕!")
                break

            batch_num += 1
            print(f"\n    批次 #{batch_num}: 处理 {len(rows)} 首歌曲")
            batch_start = time.time()

            for i, row in enumerate(rows, 1):
                song_id = row[0]
                song_name = row[1] or ''
                artist = row[2] or ''
                album = row[3] or ''
                playlist_names = row[4]
                playlist_categories = row[5]

                # 构建文本描述
                text_desc = build_text_description(
                    song_name, artist, album,
                    playlist_names, playlist_categories
                )

                # 生成向量
                embedding = generate_embedding(text_desc)

                if embedding is None:
                    print(f"      [{i}/{len(rows)}] song_id={song_id}: 向量生成失败，跳过")
                    # 插入空向量记录，避免重复查询
                    cursor.execute("""
                        INSERT INTO song_embeddings (song_id, text_description, embedding)
                        VALUES (%s, %s, NULL)
                        ON CONFLICT (song_id) DO NOTHING
                    """, (song_id, text_desc))
                    conn.commit()
                    continue

                # 写入数据库
                try:
                    cursor.execute("""
                        INSERT INTO song_embeddings (song_id, text_description, embedding)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (song_id) DO UPDATE SET
                            text_description = EXCLUDED.text_description,
                            embedding = EXCLUDED.embedding,
                            updated_at = CURRENT_TIMESTAMP
                    """, (song_id, text_desc, embedding))
                    conn.commit()
                    processed += 1

                except Exception as e:
                    print(f"      [{i}/{len(rows)}] song_id={song_id}: 数据库写入错误: {e}")
                    conn.rollback()
                    continue

                if (i + 1) % 100 == 0:
                    elapsed = time.time() - batch_start
                    speed = i / elapsed if elapsed > 0 else 0
                    print(f"      已处理 {i}/{len(rows)} 首 (速度: {speed:.1f} 首/秒)")

                # 避免 API 限流
                time.sleep(0.05)

            batch_elapsed = time.time() - batch_start
            print(f"    批次完成: {processed} 首, 耗时: {batch_elapsed:.1f} 秒")

        # 3. 验证结果
        print("\n[3/4] 验证数据...")
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(embedding) as with_embedding,
                COUNT(*) - COUNT(embedding) as without_embedding
            FROM song_embeddings
        """)
        row = cursor.fetchone()
        print(f"    song_embeddings 表:")
        print(f"      - 总记录数: {row[0]:,}")
        print(f"      - 有向量: {row[1]:,}")
        print(f"      - 无向量: {row[2]:,}")

        # 4. 显示样例
        print("\n[4/4] 样例数据:")
        cursor.execute("""
            SELECT song_id, text_description
            FROM song_embeddings
            WHERE embedding IS NOT NULL
            LIMIT 3
        """)
        for row in cursor.fetchall():
            desc_preview = row[1][:80] + '...' if len(row[1]) > 80 else row[1]
            print(f"    song_id={row[0]}: {desc_preview}")

        print("\n" + "=" * 60)
        print(f"✅ song_embeddings 向量生成完成!")
        print(f"   本次新增: {processed} 首")
        print("=" * 60)

    except KeyboardInterrupt:
        print("\n\n⚠️ 用户取消操作")
        print(f"   已处理: {processed} 首")
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"\n❌ 错误: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    init_song_embeddings(batch_size=1000)