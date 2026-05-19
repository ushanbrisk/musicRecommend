#!/usr/bin/env python3
"""
初始化 music_feature 表

利用 song_comment_agg 和 song_playlist_agg 表中的数据，通过 LLM 生成每首歌曲的特征，
填充到 music_feature 表中。

使用方法:
    ~/miniconda3/envs/music/bin/python scripts/init_music_feature.py

注意:
    - 需要先完成 song_playlist_agg 和 song_comment_agg 的填充
    - 需要配置 LLM API（MINIMAX_API_KEY、LLM_PROVIDER_URL 等）
    - 环境变量通过项目根目录的 .env 文件加载
"""

import os
import sys
import time
import json

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

# 加载环境变量
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

import psycopg2
from openai import OpenAI


def get_db_connection():
    """获取数据库连接"""
    return psycopg2.connect(
        host=os.getenv('PG_HOST', 'localhost'),
        port=os.getenv('PG_PORT', '5432'),
        database=os.getenv('PG_DB', 'musicdb'),
        user=os.getenv('PG_USER', 'postgres'),
        password=os.getenv('PG_PASSWORD', 'luke')
    )


def get_llm_client():
    """获取 LLM 客户端"""
    return OpenAI(
        api_key=os.getenv('LLM_PROVIDER_KEY'),
        base_url=os.getenv('LLM_PROVIDER_URL')
    )


def build_feature_prompt(song_info: dict) -> str:
    """构建特征提取 Prompt"""
    playlist_str = song_info.get('playlist_names_str', '')
    comments_str = song_info.get('comment_summary', '')

    return f"""请分析以下歌曲信息，提取特征标签。

## 歌曲基本信息
- 歌曲名称：{song_info['song_name']}
- 艺术家：{song_info['artist']}
- 专辑：{song_info.get('album', '未知')}

## 归属歌单（该歌曲可能出现在多个歌单中）
{playlist_str if playlist_str else '无'}

## 用户评论摘要（反映听众的真实感受）
{comments_str if comments_str else '暂无评论'}

## 已知信息（如有）
- 语言：{song_info.get('language', '未知')}
- 节拍：{song_info.get('tempo', '未知')}（如已知）

请提取以下特征（JSON格式返回）：
{{
  "genre": "流派/风格，如：古典、流行、凯尔特、电子、爵士等",
  "mood": "情绪标签（最多5个，用逗号分隔），如：欢快、忧伤、平静、激烈、浪漫、神秘、怀旧、励志、治愈等",
  "tempo": "节拍：快/中/慢（如歌曲名含"快节奏"等信息可推断）",
  "instruments": "主要乐器（最多3个，用逗号分隔），如：钢琴、吉他、鼓、弦乐、风笛、古筝等",
  "scene": "适用场景（最多5个，用逗号分隔），如：夜晚、工作、运动、休息、阅读、旅行、聚会、独处、冥想等",
  "language": "歌曲语言：中文、英文、日文、纯音乐等",
  "era": "时代/年代，如：80年代、90年代、2000s、2010s、新世纪、古典时期等",
  "description": "100字左右的歌曲描述，综合以上信息生成",
  "emotional_tags": "细腻情感标签（更多细分情绪，用逗号分隔），如：乡愁、憧憬、释然、热血、孤独等",
  "theme_keywords": "主题关键词（逗号分隔），如：自然、爱情、思乡、战争、和平等"
}}

注意：
1. 一首歌可能属于多个歌单，歌单名传递了不同场景/情绪的语义
2. 用户评论能反映真实感受，优先从评论中提取情绪和场景信息
3. 仅基于文本信息推断，不要假设未知信息
"""


def extract_features(song_info: dict, llm_client, model_name: str) -> dict:
    """调用 LLM 提取歌曲特征"""
    prompt = build_feature_prompt(song_info)

    response = llm_client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )

    try:
        features = json.loads(response.choices[0].message.content)
    except json.JSONDecodeError:
        features = {
            "genre": "未知",
            "mood": "未知",
            "tempo": "未知",
            "instruments": "未知",
            "scene": "未知",
            "language": "未知",
            "era": "未知",
            "description": "特征提取失败",
            "emotional_tags": "",
            "theme_keywords": ""
        }

    return features


def get_songs_without_features(cursor, limit: int = 100):
    """获取尚未生成特征的歌曲"""
    # 使用预聚合表 song_playlist_agg 和 song_comment_agg，避免实时 JOIN
    query = """
        SELECT
            s.song_id,
            s.song_name,
            s.artist,
            s.album,
            COALESCE(spa.playlist_names_str, '') as playlist_names_str,
            COALESCE(spa.playlist_categories_str, '') as playlist_categories_str,
            COALESCE(sca.comment_summary, '') as comment_summary,
            COALESCE(sca.avg_polarity, 0) as avg_polarity
        FROM songs s
        LEFT JOIN song_playlist_agg spa ON s.song_id = spa.song_id
        LEFT JOIN song_comment_agg sca ON s.song_id = sca.song_id
        LEFT JOIN music_features mf ON s.song_id = mf.song_id
        WHERE mf.id IS NULL
          AND (
              -- 只处理有歌单或评论数据的歌曲
              spa.song_id IS NOT NULL
              OR sca.song_id IS NOT NULL
          )
        LIMIT %s
    """
    cursor.execute(query, (limit,))
    columns = [desc[0] for desc in cursor.description]
    results = []
    for row in cursor.fetchall():
        results.append(dict(zip(columns, row)))
    return results


def save_feature(features: dict, cursor):
    """保存特征到数据库（upsert 模式）"""
    query = """
        INSERT INTO music_features (
            song_id, genre, mood, tempo, instruments,
            scene, language, era, description,
            emotional_tags, theme_keywords, inherited_tags,
            updated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (song_id) DO UPDATE SET
            genre = EXCLUDED.genre,
            mood = EXCLUDED.mood,
            tempo = EXCLUDED.tempo,
            instruments = EXCLUDED.instruments,
            scene = EXCLUDED.scene,
            language = EXCLUDED.language,
            era = EXCLUDED.era,
            description = EXCLUDED.description,
            emotional_tags = EXCLUDED.emotional_tags,
            theme_keywords = EXCLUDED.theme_keywords,
            inherited_tags = EXCLUDED.inherited_tags,
            updated_at = CURRENT_TIMESTAMP
    """
    cursor.execute(query, (
        features.get('song_id'),
        features.get('genre'),
        features.get('mood'),
        features.get('tempo'),
        features.get('instruments'),
        features.get('scene'),
        features.get('language'),
        features.get('era'),
        features.get('description'),
        features.get('emotional_tags'),
        features.get('theme_keywords'),
        features.get('inherited_tags', '')
    ))


def init_music_feature():
    """初始化 music_feature 表"""
    print("=" * 60)
    print("music_feature 数据填充开始")
    print("=" * 60)

    conn = get_db_connection()
    cursor = conn.cursor()

    # 初始化 LLM 客户端
    llm_client = get_llm_client()
    model_name = os.getenv('LLM_MODEL_NAME', 'MiniMax-M2.7')

    try:
        # 1. 检查预聚合表是否已有数据
        print("\n[1/4] 检查预聚合表数据...")
        cursor.execute("SELECT COUNT(*) FROM song_playlist_agg")
        spa_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM song_comment_agg")
        sca_count = cursor.fetchone()[0]
        print(f"      song_playlist_agg: {spa_count:,} 条")
        print(f"      song_comment_agg: {sca_count:,} 条")

        if spa_count == 0 and sca_count == 0:
            print("\n❌ 错误: 预聚合表为空，请先执行:")
            print("    python scripts/init_song_playlist_agg.py")
            print("    python scripts/init_song_comment_agg.py")
            return

        # 2. 统计待处理的歌曲数
        print("\n[2/4] 统计待处理歌曲...")
        cursor.execute("""
            SELECT COUNT(*)
            FROM songs s
            LEFT JOIN music_features mf ON s.song_id = mf.song_id
            LEFT JOIN song_playlist_agg spa ON s.song_id = spa.song_id
            LEFT JOIN song_comment_agg sca ON s.song_id = sca.song_id
            WHERE mf.id IS NULL
              AND (spa.song_id IS NOT NULL OR sca.song_id IS NOT NULL)
        """)
        remaining = cursor.fetchone()[0]
        print(f"      待处理歌曲数: {remaining:,}")

        if remaining == 0:
            print("\n✅ 所有歌曲都已生成特征，无需处理")
            return

        # 3. 分批处理
        print(f"\n[3/4] 开始填充数据（每批 50 首）...")
        print(f"      使用 LLM 模型: {model_name}")
        batch_size = 50
        total_processed = 0
        success_count = 0
        fail_count = 0
        start_time = time.time()

        while True:
            songs = get_songs_without_features(cursor, limit=batch_size)
            if not songs:
                break

            batch_num = total_processed // batch_size + 1
            print(f"\n  处理批次 {batch_num} ({len(songs)} 首)...")

            for song in songs:
                try:
                    features = extract_features(song, llm_client, model_name)
                    features['song_id'] = song['song_id']

                    # 构建 inherited_tags 从歌单继承
                    inherited = []
                    if song.get('playlist_categories_str'):
                        inherited.append(f"来自歌单分类: {song['playlist_categories_str']}")
                    features['inherited_tags'] = '; '.join(inherited)

                    save_feature(features, cursor)
                    success_count += 1

                    if success_count % 100 == 0:
                        conn.commit()
                        elapsed = time.time() - start_time
                        rate = success_count / elapsed if elapsed > 0 else 0
                        print(f"      已处理: {success_count}/{remaining} ({rate:.1f} 首/秒)")

                except Exception as e:
                    fail_count += 1
                    print(f"      ❌ song_id={song['song_id']}: {e}")

                total_processed += 1

            conn.commit()

        elapsed = time.time() - start_time

        # 4. 验证结果
        print("\n[4/4] 验证数据...")
        cursor.execute("SELECT COUNT(*) FROM music_features")
        total_features = cursor.fetchone()[0]

        print(f"\n{'=' * 60}")
        print("填充结果统计:")
        print(f"  - 总处理数:           {total_processed:,}")
        print(f"  - 成功:               {success_count:,}")
        print(f"  - 失败:               {fail_count:,}")
        print(f"  - music_features 表:  {total_features:,}")
        print(f"  - 总耗时:             {elapsed:.1f} 秒")
        print(f"  - 平均速度:           {success_count/elapsed:.2f} 首/秒")
        print(f"{'=' * 60}")

        # 显示样例
        print("\n样例数据:")
        cursor.execute("""
            SELECT song_id, genre, mood, scene
            FROM music_features
            LIMIT 3
        """)
        for row in cursor.fetchall():
            print(f"  song_id={row[0]}, genre={row[1]}, mood={row[2]}, scene={row[3]}")

        print("\n✅ music_feature 填充完成!")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ 错误: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    init_music_feature()