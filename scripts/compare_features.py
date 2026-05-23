#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================
特征差异对比脚本
============================================================

对比 Qwen2.5-32B 和 Qwen2.5-14B 提取的音乐特征差异

使用示例:
    ~/miniconda3/envs/music_recommend/bin/python scripts/compare_features.py
============================================================
"""

import psycopg2
import json
import random

# =============================================================================
# 配置
# =============================================================================

DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'musicdb',
    'user': 'postgres',
    'password': 'luke'
}


def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)


def jaccard_similarity(set1, set2):
    """计算两个集合的 Jaccard 相似度"""
    if not set1 and not set2:
        return 1.0
    if not set1 or not set2:
        return 0.0
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union > 0 else 0.0


def parse_json_field(field_value):
    """解析 JSON 数组或 PostgreSQL 数组字段，返回集合"""
    if not field_value:
        return set()
    try:
        # 处理 PostgreSQL 数组格式，如 {电子,流行}
        if isinstance(field_value, str) and field_value.startswith('{'):
            # 去掉外层大括号，按逗号分割
            inner = field_value.strip('{}')
            if inner:
                return set(item.strip().strip('"').strip("'") for item in inner.split(',') if item.strip())
            return set()
        # 处理 Python list
        if isinstance(field_value, list):
            return set(str(item).strip() for item in field_value if item)
        # 处理 JSON 字符串
        parsed = json.loads(field_value)
        if isinstance(parsed, list):
            return set(str(item).strip() for item in parsed if item)
    except:
        pass
    return set()


def compare_features():
    """对比两个模型的特征提取结果"""

    print("=" * 60)
    print("Qwen2.5-32B vs Qwen2.5-14B 特征差异对比报告")
    print("=" * 60)

    conn = get_db_connection()
    cursor = conn.cursor()

    # 数据量统计
    cursor.execute("SELECT COUNT(*) FROM music_features")
    count_32b = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM music_features_14b")
    count_14b = cursor.fetchone()[0]

    print(f"\n数据量统计:")
    print(f"  music_features (32B): {count_32b:,} 条")
    print(f"  music_features_14b (14B): {count_14b:,} 条")

    cursor.execute("""
        SELECT COUNT(*) FROM music_features mf
        INNER JOIN music_features_14b mf14 ON mf.song_id = mf14.song_id
    """)
    common_count = cursor.fetchone()[0]
    print(f"  共同歌曲数: {common_count:,} 条")

    if common_count == 0:
        print("\n没有共同歌曲，无法对比")
        return

    # 定义字段（JSON 数组字段）
    json_fields = ['genre', 'mood', 'instruments', 'scene', 'emotional_tags', 'theme_keywords']
    simple_fields = ['tempo']
    all_fields = json_fields + simple_fields

    # 统计变量
    stats = {f: {'exact_match': 0, 'jaccard_sum': 0, 'count_32b': 0, 'count_14b': 0} for f in all_fields}
    desc_lens_32b = []
    desc_lens_14b = []

    # 查询所有共同歌曲的完整数据
    cursor.execute("""
        SELECT
            mf.song_id,
            mf.genre, mf.mood, mf.tempo, mf.instruments, mf.scene,
            mf.description, mf.emotional_tags, mf.theme_keywords,
            mf14.genre, mf14.mood, mf14.tempo, mf14.instruments, mf14.scene,
            mf14.description, mf14.emotional_tags, mf14.theme_keywords
        FROM music_features mf
        INNER JOIN music_features_14b mf14 ON mf.song_id = mf14.song_id
    """)
    rows = cursor.fetchall()

    for row in rows:
        # 32B: indices 1-8, 14B: indices 9-16
        # genre=1, mood=2, tempo=3, instruments=4, scene=5, description=6, emotional_tags=7, theme_keywords=8
        # genre=9, mood=10, tempo=11, instruments=12, scene=13, description=14, emotional_tags=15, theme_keywords=16

        for i, f in enumerate(json_fields):
            set_32b = parse_json_field(row[1 + i])
            set_14b = parse_json_field(row[9 + i])

            if set_32b == set_14b:
                stats[f]['exact_match'] += 1

            stats[f]['jaccard_sum'] += jaccard_similarity(set_32b, set_14b)
            stats[f]['count_32b'] += len(set_32b)
            stats[f]['count_14b'] += len(set_14b)

        # tempo
        val_32b = (row[3] or '').strip()
        val_14b = (row[11] or '').strip()
        if val_32b == val_14b:
            stats['tempo']['exact_match'] += 1
        stats['tempo']['jaccard_sum'] += jaccard_similarity({val_32b}, {val_14b}) if val_32b or val_14b else 1.0

        # description 长度
        desc_lens_32b.append(len(row[6] or ''))
        desc_lens_14b.append(len(row[14] or ''))

    # 输出统计结果
    print(f"\n{'='*60}")
    print("字段级对比详情")
    print("=" * 60)
    print(f"\n{'字段':<15} {'集合一致率':<12} {'Jaccard':<10} {'32B均标签':<10} {'14B均标签':<10}")
    print("-" * 60)
    for f in all_fields:
        exact_rate = stats[f]['exact_match'] / common_count * 100
        avg_jaccard = stats[f]['jaccard_sum'] / common_count
        avg_count_32b = stats[f]['count_32b'] / common_count
        avg_count_14b = stats[f]['count_14b'] / common_count
        print(f"{f:<15} {exact_rate:>6.1f}%      {avg_jaccard:.3f}    {avg_count_32b:.1f}         {avg_count_14b:.1f}")

    # Description 长度对比
    avg_len_32b = sum(desc_lens_32b) / len(desc_lens_32b)
    avg_len_14b = sum(desc_lens_14b) / len(desc_lens_14b)
    print(f"\n{'='*60}")
    print("Description 长度对比")
    print("=" * 60)
    print(f"  32B 平均: {avg_len_32b:.1f} 字符")
    print(f"  14B 平均: {avg_len_14b:.1f} 字符")
    print(f"  差异: {avg_len_32b - avg_len_14b:+.1f} 字符")

    # 标签数量差异
    print(f"\n{'='*60}")
    print("标签数量对比 (每首歌平均)")
    print("=" * 60)
    for f in json_fields:
        diff = (stats[f]['count_32b'] - stats[f]['count_14b']) / common_count
        print(f"  {f}: 32B={stats[f]['count_32b']/common_count:.1f}, 14B={stats[f]['count_14b']/common_count:.1f}, 差值={diff:+.1f}")

    # 样例对比
    print(f"\n{'='*60}")
    print("样例对比 (随机 5 首)")
    print("=" * 60)

    random.seed(42)
    sample = random.sample(rows, min(5, len(rows)))

    for row in sample:
        song_id = row[0]
        print(f"\n--- 歌曲 {song_id} ---")

        for i, f in enumerate(json_fields):
            set_32b = parse_json_field(row[1 + i])
            set_14b = parse_json_field(row[9 + i])
            match = "✓" if set_32b == set_14b else "✗"
            j = jaccard_similarity(set_32b, set_14b)
            print(f"  {f}: {match} (J={j:.2f})")
            if set_32b or set_14b:
                print(f"    32B: {set_32b}")
                print(f"    14B: {set_14b}")

        val_32b = (row[3] or '').strip()
        val_14b = (row[11] or '').strip()
        match = "✓" if val_32b == val_14b else "✗"
        print(f"  tempo: {match}")
        print(f"    32B: {val_32b or '(空)'}")
        print(f"    14B: {val_14b or '(空)'}")

        desc_32b = (row[6] or '').strip()
        desc_14b = (row[14] or '').strip()
        print(f"  description:")
        print(f"    32B ({len(desc_32b)}字): {desc_32b[:100]}{'...' if len(desc_32b) > 100 else ''}")
        print(f"    14B ({len(desc_14b)}字): {desc_14b[:100]}{'...' if len(desc_14b) > 100 else ''}")

    cursor.close()
    conn.close()

    print(f"\n{'='*60}")
    print("对比完成")
    print("=" * 60)


if __name__ == "__main__":
    compare_features()