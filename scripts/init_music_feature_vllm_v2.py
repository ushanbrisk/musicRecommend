#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================
vLLM 批量特征生成脚本
============================================================

根据 inference.md 设计，使用本地 vLLM 服务进行批量特征生成。

## 架构

    歌曲池 (12万首)
         │
         ▼
    song_id % 2 == 0  ──→  组 A (vLLM:8000)  ──→  约 6 万首
    song_id % 2 == 1  ──→  组 B (vLLM:8001)  ──→  约 6 万首

## 使用方法

1. 启动 vLLM 服务:
   bash scripts/start_vllm_servers.sh all

2. 运行特征生成:
   ~/miniconda3/envs/music_recommend/bin/python scripts/init_music_feature_vllm.py

3. 查看服务状态:
   bash scripts/start_vllm_servers.sh status

============================================================
"""

import os
import sys
import time
import json
import asyncio
import aiohttp
import psycopg2
from typing import List, Dict, Optional
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

# =============================================================================
# 配置
# =============================================================================

# vLLM 服务端点 (单一大模型，TP=5)
VLLM_ENDPOINT = "http://localhost:8000"

# 动态获取模型名称
def get_vllm_model(endpoint: str) -> str:
    import urllib.request
    import json
    url = f"{endpoint}/v1/models"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return data['data'][0]['id']
    except Exception as e:
        print(f"获取模型名称失败 {endpoint}: {e}")
        return None

VLLM_MODEL = get_vllm_model(VLLM_ENDPOINT)

# 批量配置 - 支持动态调整
INITIAL_BATCH_SIZE = int(os.getenv('VLLM_BATCH_SIZE', '10'))  # 初始每批歌曲数
MIN_BATCH_SIZE = 2  # 最小 batch_size
MAX_BATCH_SIZE = int(os.getenv('VLLM_MAX_BATCH_SIZE', '20'))  # 最大每批歌曲数
MAX_TOKENS = 1024  # 减少输出长度以加快速度
TEMPERATURE = 0.3
REQUEST_TIMEOUT = 180  # 秒

# 连续失败跳过配置
MAX_FAIL_COUNT = 5  # 连续失败 5 次后跳过该歌曲

# 动态 batch_size 配置
CURRENT_BATCH_SIZE = INITIAL_BATCH_SIZE
CONTINUOUS_SUCCESS_COUNT = 0  # 连续成功计数
CONTINUOUS_FAIL_COUNT = 0  # 连续失败计数


def ensure_skip_table_exists(conn):
    """
    确保跳过记录表存在
    """
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS music_features_skip (
            song_id VARCHAR(64) PRIMARY KEY,
            fail_reason TEXT,
            fail_count INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cursor.close()


def get_songs_without_features(cursor, limit: int = 100) -> List[Dict]:
    """
    获取尚未生成特征的歌曲（按文本内容长度升序排序，排除已跳过的歌曲）

    使用预聚合表 song_playlist_agg 和 song_comment_agg，避免实时 JOIN
    按 (playlist_names_str + playlist_categories_str + comment_summary) 长度升序排序
    这样开始时可以用较大的 batch_size，后面内容变长时自动适应
    """
    query = """
        SELECT
            s.song_id,
            s.song_name,
            s.artist,
            s.album,
            COALESCE(spa.playlist_names_str, '') as playlist_names_str,
            COALESCE(spa.playlist_categories_str, '') as playlist_categories_str,
            COALESCE(sca.comment_summary, '') as comment_summary,
            COALESCE(sca.avg_polarity, 0) as avg_polarity,
            LENGTH(COALESCE(spa.playlist_names_str, '')) + LENGTH(COALESCE(spa.playlist_categories_str, '')) + LENGTH(COALESCE(sca.comment_summary, '')) as content_length
        FROM songs s
        LEFT JOIN song_playlist_agg spa ON s.song_id = spa.song_id
        LEFT JOIN song_comment_agg sca ON s.song_id = sca.song_id
        LEFT JOIN music_features mf ON s.song_id = mf.song_id
        LEFT JOIN music_features_skip sk ON s.song_id::text = sk.song_id
        WHERE mf.id IS NULL
          AND sk.song_id IS NULL
          AND spa.song_id IS NOT NULL
          AND sca.song_id IS NOT NULL
        ORDER BY content_length ASC
        LIMIT %s
    """
    cursor.execute(query, (limit,))
    columns = [desc[0] for desc in cursor.description]
    results = []
    for row in cursor.fetchall():
        results.append(dict(zip(columns, row)))
    return results


def mark_song_skipped(conn, song_id: int, fail_reason: str):
    """
    标记歌曲为跳过状态
    """
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO music_features_skip (song_id, fail_reason, fail_count, updated_at)
        VALUES (%s, %s, 1, CURRENT_TIMESTAMP)
        ON CONFLICT (song_id) DO UPDATE SET
            fail_reason = EXCLUDED.fail_reason,
            fail_count = music_features_skip.fail_count + 1,
            updated_at = CURRENT_TIMESTAMP
    """, (str(song_id), fail_reason))
    conn.commit()
    cursor.close()


# 音乐特征系统提示词
MUSIC_FEATURE_SYSTEM_PROMPT = """你是一个专业的音乐分析师，负责根据歌曲的文本信息生成音乐特征。

## 你的任务

根据提供的歌曲信息（可能包含歌名、艺术家、专辑、所属歌单、用户评论等），生成以下JSON格式的特征：

{
    "song_id": "歌曲ID（从输入中提取）",
    "description": "100-200字的中文描述，综合所有信息描述歌曲风格",
    "genre": ["流派1", "流派2"],
    "mood": ["情绪1", "情绪2"],
    "tempo": "快/中/慢",
    "instruments": ["主要乐器1", "乐器2"],
    "scene": ["场景1", "场景2"],
    "emotional_tags": ["细腻情感词1", "情感词2"],
    "theme_keywords": ["主题词1", "主题词2"]
}

## 取值范围参考

- genre: 流行、摇滚、古典、民谣、电子、爵士、蓝调、凯尔特、新世纪、电影配乐、民族、说唱、R&B、灵魂乐等
- mood: 欢快、忧伤、平静、激烈、浪漫、神秘、怀旧、励志、治愈、孤独、兴奋、沉思、温馨等
- tempo: 快、中、慢
- instruments: 吉他、钢琴、鼓、贝斯、提琴、笛子、古筝、琵琶、二胡、合成器等
- scene: 工作、运动、休息、入睡、阅读、旅行、聚会、独处、冥想、驾车、深夜、清晨、节日、庆祝等

## 注意事项

1. 只基于提供的文本信息推断，不要猜测
2. 如果信息不足以判断某项，标注为"待定"
3. description 应综合所有信息，描述歌曲的整体风格和感受
4. 返回格式必须是合法的 JSON
5. song_id 必须与输入中的序号对应
"""


# =============================================================================
# 数据库连接
# =============================================================================

def get_db_connection():
    """获取 PostgreSQL 连接"""
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', '5432')),
        database=os.getenv('DB_NAME', 'musicdb'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', 'luke')
    )


# =============================================================================
# 数据获取
# =============================================================================


# =============================================================================
# Prompt 构建
# =============================================================================

def format_song_text(song: Dict, index: int) -> str:
    """
    格式化单首歌曲的文本信息

    Args:
        song: 歌曲信息字典
        index: 序号（用于输出时匹配 song_id）
    """
    parts = [
        f"[序号 {index}]",
        f"歌曲ID: {song['song_id']}",
        f"歌名: {song['song_name']}",
        f"艺术家: {song['artist']}",
        f"专辑: {song.get('album', '未知')}",
    ]

    if song.get('playlist_names_str'):
        parts.append(f"所属歌单: {song['playlist_names_str']}")

    if song.get('playlist_categories_str'):
        parts.append(f"歌单分类: {song['playlist_categories_str']}")

    if song.get('comment_summary'):
        parts.append(f"用户评论: {song['comment_summary']}")

    return "\n".join(parts)


def build_batch_prompt(songs: List[Dict]) -> str:
    """
    构建批量歌曲的 prompt

    根据 inference.md 设计，每批 15-30 首歌曲拼接后送入 LLM
    由于 song_comment_agg 中评论已压缩到 5 条，单首歌文本量小（200-500 tokens）
    所以可以更激进的批量
    """
    lines = []
    for i, song in enumerate(songs):
        lines.append(format_song_text(song, i))

    return "\n\n---\n\n".join(lines)


def build_batch_request_prompt(songs: List[Dict]) -> str:
    """
    构建批量请求的完整 prompt
    """
    batch_content = build_batch_prompt(songs)

    return f"""请为以下批量歌曲生成特征信息。每首歌信息格式为[序号] 歌名...：

{batch_content}

请为每首歌生成一个独立的JSON对象，格式如下：
[
    {{"song_id": xxx, "description": "...", "genre": [...], "mood": [...], ...}},
    {{"song_id": xxx, "description": "...", "genre": [...], "mood": [...], ...}}
]

注意：
1. song_id 必须与输入中的序号对应
2. 每首歌的JSON必须在一行内完整
3. 只返回JSON数组，不要其他文字
"""


# =============================================================================
# vLLM API 调用
# =============================================================================

async def call_vllm_async(session: aiohttp.ClientSession, endpoint: str, model_name: str, songs: List[Dict]) -> List[Dict]:
    """
    异步调用 vLLM API 生成特征

    Args:
        session: aiohttp 会话
        endpoint: vLLM 服务端点
        model_name: 模型名称
        songs: 歌曲列表

    Returns:
        特征列表
    """
    prompt = build_batch_request_prompt(songs)

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": MUSIC_FEATURE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS
    }

    try:
        async with session.post(f"{endpoint}/v1/chat/completions", json=payload, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                print(f"      vLLM API 错误 {resp.status}: {error_text[:200]}")
                return []

            result = await resp.json()

            if 'choices' not in result or len(result['choices']) == 0:
                print(f"      vLLM 返回格式错误: {result}")
                return []

            content = result['choices'][0]['message']['content']
            return parse_batch_response(content, songs)

    except asyncio.TimeoutError:
        print(f"      请求超时 ({REQUEST_TIMEOUT}s)")
        return []
    except Exception as e:
        print(f"      请求异常: {e}")
        return []

    return []


def parse_batch_response(content: str, songs: List[Dict]) -> List[Dict]:
    """
    解析批量响应

    vLLM 可能返回被 thinking tags 包裹的内容，需要清理
    """
    try:
        # 去掉 <|reserved_...|> 等特殊标签
        if "<think>" in content:
            content = content.split("<think>")[-1].strip()

        if "<|reserved_" in content:
            content = content.split("<|reserved_")[-1].strip()

        # 去掉 ```json ... ``` 包裹
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1])

        # 尝试解析 JSON 数组
        # 可能返回的是 JSON Lines 格式（每行一个 JSON）
        lines = content.strip().split('\n')
        results = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 去掉可能的 JSON prefix
            if line.startswith('```'):
                continue

            try:
                obj = json.loads(line)
                results.append(obj)
            except json.JSONDecodeError:
                # 尝试从行中提取 JSON 对象
                start = line.find('{')
                end = line.rfind('}') + 1
                if start >= 0 and end > start:
                    try:
                        obj = json.loads(line[start:end])
                        results.append(obj)
                    except:
                        pass

        # 如果是完整的 JSON 数组
        if not results:
            try:
                results = json.loads(content)
                if isinstance(results, list):
                    return results
            except:
                pass

        return results

    except Exception as e:
        print(f"      解析响应失败: {e}")
        return []


# =============================================================================
# 特征保存
# =============================================================================

def save_features(features_list: List[Dict], cursor, conn):
    """
    批量保存特征到数据库（upsert 模式）
    """
    for features in features_list:
        try:
            song_id = features.get('song_id')
            if not song_id:
                continue

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
                song_id,
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

        except Exception as e:
            print(f"      保存特征失败: {e}")

    conn.commit()


# =============================================================================
# 主处理函数
# =============================================================================

def adjust_batch_size(success: bool, error_msg: str = ""):
    """
    动态调整 batch_size

    - 连续成功时，逐步增加 batch_size
    - 失败时（包括 context overflow），减少 batch_size
    - 溢出错误优先处理
    """
    global CURRENT_BATCH_SIZE, CONTINUOUS_SUCCESS_COUNT, CONTINUOUS_FAIL_COUNT

    # 检测是否是 context overflow 错误
    is_overflow = "maximum context length" in error_msg.lower() or "requested" in error_msg.lower() and "tokens" in error_msg.lower()

    if success:
        CONTINUOUS_SUCCESS_COUNT += 1
        CONTINUOUS_FAIL_COUNT = 0

        # 连续成功 5 次，尝试增加 batch_size
        if CONTINUOUS_SUCCESS_COUNT >= 5:
            if CURRENT_BATCH_SIZE < MAX_BATCH_SIZE:
                old_size = CURRENT_BATCH_SIZE
                CURRENT_BATCH_SIZE = min(CURRENT_BATCH_SIZE + 1, MAX_BATCH_SIZE)
                CONTINUOUS_SUCCESS_COUNT = 0
                if CURRENT_BATCH_SIZE > old_size:
                    print(f"      [自适应] batch_size: {old_size} → {CURRENT_BATCH_SIZE} (连续成功)")
    else:
        CONTINUOUS_SUCCESS_COUNT = 0
        CONTINUOUS_FAIL_COUNT += 1

        if is_overflow:
            # 溢出错误，直接减半
            if CURRENT_BATCH_SIZE > MIN_BATCH_SIZE:
                old_size = CURRENT_BATCH_SIZE
                CURRENT_BATCH_SIZE = max(MIN_BATCH_SIZE, CURRENT_BATCH_SIZE // 2)
                print(f"      [自适应] batch_size: {old_size} → {CURRENT_BATCH_SIZE} (context overflow)")
        elif CONTINUOUS_FAIL_COUNT >= 2:
            # 连续失败 2 次，减少 batch_size
            if CURRENT_BATCH_SIZE > MIN_BATCH_SIZE:
                old_size = CURRENT_BATCH_SIZE
                CURRENT_BATCH_SIZE = max(MIN_BATCH_SIZE, CURRENT_BATCH_SIZE - 1)
                print(f"      [自适应] batch_size: {old_size} → {CURRENT_BATCH_SIZE} (连续失败)")


def is_context_overflow_error(error_msg: str) -> bool:
    """检测是否是 context overflow 错误"""
    error_lower = error_msg.lower()
    return ("maximum context length" in error_lower or
            ("requested" in error_lower and "tokens" in error_lower and "exceeds" in error_lower))


async def process_all_async(total_to_process: int):
    """
    异步处理所有歌曲（单一大模型，动态 batch_size）
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    global CURRENT_BATCH_SIZE
    CURRENT_BATCH_SIZE = INITIAL_BATCH_SIZE  # 重置 batch_size

    print(f"\n{'='*60}")
    print(f"处理全部歌曲 (endpoint: {VLLM_ENDPOINT}, model: {VLLM_MODEL})")
    print(f"{'='*60}")
    print(f"  初始 batch_size: {INITIAL_BATCH_SIZE}")
    print(f"  动态范围: {MIN_BATCH_SIZE} ~ {MAX_BATCH_SIZE}")
    print(f"  连续失败跳过阈值: {MAX_FAIL_COUNT} 次")

    success_count = 0
    fail_count = 0
    start_time = time.time()

    # 跟踪每首歌曲的失败次数
    song_fail_count = {}  # song_id -> fail_count
    skipped_songs = set()  # 已跳过的歌曲集合

    async with aiohttp.ClientSession() as session:
        while True:
            # 获取待处理歌曲（按内容长度升序，每次获取当前 batch_size 的 10 倍用于缓冲）
            fetch_limit = CURRENT_BATCH_SIZE * 10
            songs = get_songs_without_features(cursor, limit=fetch_limit)
            if not songs:
                break

            print(f"\n  批次开始 (获取 {len(songs)} 首, batch_size={CURRENT_BATCH_SIZE})...")

            # 分批调用 vLLM
            for i in range(0, len(songs), CURRENT_BATCH_SIZE):
                batch = songs[i:i+CURRENT_BATCH_SIZE]

                try:
                    features_list = await call_vllm_async(session, VLLM_ENDPOINT, VLLM_MODEL, batch)

                    if features_list:
                        # 构建 inherited_tags
                        for features in features_list:
                            song_id = features.get('song_id')
                            song = next((s for s in batch if str(s['song_id']) == str(song_id)), None)
                            if song and song.get('playlist_categories_str'):
                                features['inherited_tags'] = f"来自歌单分类: {song['playlist_categories_str']}"

                        save_features(features_list, cursor, conn)
                        success_count += len(features_list)
                        adjust_batch_size(success=True)

                        # 成功时清除失败记录
                        for song in batch:
                            song_id = str(song['song_id'])
                            if song_id in song_fail_count:
                                del song_fail_count[song_id]
                    else:
                        # vLLM 调用失败 - 追踪每首歌曲的失败
                        for song in batch:
                            song_id = str(song['song_id'])
                            song_fail_count[song_id] = song_fail_count.get(song_id, 0) + 1

                            if song_fail_count[song_id] >= MAX_FAIL_COUNT and song_id not in skipped_songs:
                                reason = f"连续失败 {song_fail_count[song_id]} 次 (vLLM API error)"
                                mark_song_skipped(conn, song['song_id'], reason)
                                skipped_songs.add(song_id)
                                print(f"      跳过歌曲 {song_id} (已连续失败 {song_fail_count[song_id]} 次)")

                        fail_count += len(batch)
                        print(f"      批次 {i//CURRENT_BATCH_SIZE + 1} 失败")
                        adjust_batch_size(success=False, error_msg="vLLM API error")

                except Exception as e:
                    # 处理异常 - 追踪每首歌曲的失败
                    for song in batch:
                        song_id = str(song['song_id'])
                        song_fail_count[song_id] = song_fail_count.get(song_id, 0) + 1

                        if song_fail_count[song_id] >= MAX_FAIL_COUNT and song_id not in skipped_songs:
                            reason = f"连续失败 {song_fail_count[song_id]} 次: {str(e)[:100]}"
                            mark_song_skipped(conn, song['song_id'], reason)
                            skipped_songs.add(song_id)
                            print(f"      跳过歌曲 {song_id} (已连续失败 {song_fail_count[song_id]} 次)")

                    fail_count += len(batch)
                    error_msg = str(e)
                    print(f"      批次处理异常: {error_msg}")
                    adjust_batch_size(success=False, error_msg=error_msg)

                # 进度显示
                elapsed = time.time() - start_time
                processed = success_count + fail_count
                rate = success_count / elapsed if elapsed > 0 else 0
                eta = (total_to_process - processed) / rate if rate > 0 else 0

                print(f"      进度: {processed}/{total_to_process} ({rate:.1f} 首/秒, ETA: {eta/60:.1f} 分钟)")

    cursor.close()
    conn.close()

    elapsed = time.time() - start_time
    print(f"\n处理完成:")
    print(f"  - 成功: {success_count}")
    print(f"  - 失败: {fail_count}")
    print(f"  - 耗时: {elapsed:.1f} 秒")
    print(f"  - 最终 batch_size: {CURRENT_BATCH_SIZE}")

    return success_count, fail_count


async def init_music_feature_vllm():
    """
    使用 vLLM 批量生成音乐特征（单一大模型版本）

    所有歌曲共用一个 vLLM 服务 (TP=5)
    动态 batch_size 根据内容长度和错误情况自适应调整
    """
    global CURRENT_BATCH_SIZE

    print("=" * 60)
    print("vLLM 批量特征生成开始 (单一大模型 TP=5, 动态 batch_size)")
    print("=" * 60)
    print(f"  初始 batch_size: {INITIAL_BATCH_SIZE}")
    print(f"  最大 batch_size: {MAX_BATCH_SIZE}")
    print(f"  最小 batch_size: {MIN_BATCH_SIZE}")
    print(f"  端点: {VLLM_ENDPOINT}")
    print(f"  模型: {VLLM_MODEL}")
    print()

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 0. 确保跳过表存在
        print("[0/4] 初始化跳过表...")
        ensure_skip_table_exists(conn)
        cursor.execute("SELECT COUNT(*) FROM music_features_skip")
        skip_count = cursor.fetchone()[0]
        print(f"      music_features_skip: {skip_count:,} 条 (已跳过的歌曲)")

        # 1. 检查预聚合表
        print("[1/4] 检查预聚合表数据...")
        cursor.execute("SELECT COUNT(*) FROM song_playlist_agg")
        spa_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM song_comment_agg")
        sca_count = cursor.fetchone()[0]
        print(f"      song_playlist_agg: {spa_count:,} 条")
        print(f"      song_comment_agg: {sca_count:,} 条")

        if spa_count == 0 and sca_count == 0:
            print("\n错误: 预聚合表为空，请先执行:")
            print("    python scripts/init_song_playlist_agg.py")
            print("    python scripts/init_song_comment_agg.py")
            return

        # 2. 统计待处理歌曲
        print("[2/4] 统计待处理歌曲...")

        cursor.execute("""
            SELECT COUNT(*)
            FROM songs s
            LEFT JOIN music_features mf ON s.song_id = mf.song_id
            LEFT JOIN song_playlist_agg spa ON s.song_id = spa.song_id
            LEFT JOIN song_comment_agg sca ON s.song_id = sca.song_id
            WHERE mf.id IS NULL
              AND spa.song_id IS NOT NULL
              AND sca.song_id IS NOT NULL
        """)
        total_to_process = cursor.fetchone()[0]

        print(f"      待处理总数: {total_to_process:,} 首")

        if total_to_process == 0:
            print("\n所有歌曲都已生成特征，无需处理")
            return

        # 3. 启动 vLLM 批量处理
        print("[3/4] 启动 vLLM 批量处理...")

        start_time = time.time()

        # 处理所有歌曲（单一大模型）
        success_count, fail_count = await process_all_async(total_to_process)

        # 4. 验证结果
        print("[4/4] 验证结果...")
        cursor.execute("SELECT COUNT(*) FROM music_features")
        total_features = cursor.fetchone()[0]

        print(f"\n{'='*60}")
        print("处理结果统计:")
        print(f"  - 总处理: {success_count + fail_count:,}")
        print(f"  - 成功:   {success_count:,}")
        print(f"  - 失败:   {fail_count:,}")
        print(f"  - music_features 表: {total_features:,}")
        print(f"  - 总耗时: {elapsed:.1f} 秒 ({elapsed/60:.1f} 分钟)")
        print(f"  - 平均速度: {success_count/elapsed:.2f} 首/秒" if elapsed > 0 else "  - 平均速度: N/A")
        print(f"{'='*60}")

        # 显示样例
        print("\n样例数据:")
        cursor.execute("""
            SELECT song_id, genre, mood, scene
            FROM music_features
            LIMIT 3
        """)
        for row in cursor.fetchall():
            print(f"  song_id={row[0]}, genre={row[1]}, mood={row[2]}, scene={row[3]}")

        print("\nvLLM 特征生成完成!")

    except Exception as e:
        print(f"\n错误: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


# =============================================================================
# 入口
# =============================================================================

if __name__ == "__main__":
    asyncio.run(init_music_feature_vllm())
