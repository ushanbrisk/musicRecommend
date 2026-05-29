#!/usr/bin/env python3
"""
初始化 song_embeddings 表

将 songs 表的数据结合 song_playlist_agg 表生成文本描述，
然后通过 Embedding API 或本地模型生成向量，存储到 song_embeddings 表。

支持两种方案：
- Plan A (默认)：调用 Embedding API 服务
- Plan B：使用本地 GPU 部署的模型，通过 song_id % 6 分组并行

使用方法:
    # Plan A (API 方案)
    ~/miniconda3/envs/music/bin/python scripts/init_song_embeddings.py

    # Plan B (本地 GPU 方案)
    # 注意：如果本地已有模型缓存，需要设置 HF_HUB_OFFLINE=1 避免联网验证
    HF_HUB_OFFLINE=1 EMBEDDING_USE_LOCAL=true GPU_GROUP=0 ~/miniconda3/envs/music/bin/python scripts/init_song_embeddings.py

    # 同时跑 6 个卡（需要先设置 HF_HUB_OFFLINE=1）
    HF_HUB_OFFLINE=1 EMBEDDING_USE_LOCAL=true GPU_GROUP=0 python scripts/init_song_embeddings.py &
    HF_HUB_OFFLINE=1 EMBEDDING_USE_LOCAL=true GPU_GROUP=1 python scripts/init_song_embeddings.py &
    HF_HUB_OFFLINE=1 EMBEDDING_USE_LOCAL=true GPU_GROUP=2 python scripts/init_song_embeddings.py &
    HF_HUB_OFFLINE=1 EMBEDDING_USE_LOCAL=true GPU_GROUP=3 python scripts/init_song_embeddings.py &
    HF_HUB_OFFLINE=1 EMBEDDING_USE_LOCAL=true GPU_GROUP=4 python scripts/init_song_embeddings.py &
    HF_HUB_OFFLINE=1 EMBEDDING_USE_LOCAL=true GPU_GROUP=5 python scripts/init_song_embeddings.py


注意:
    1. 需要先创建 song_embeddings 表，参见 database/schema.sql
    2. Plan A 需要配置 .env 文件中的 Embedding API 相关环境变量
    3. Plan B 需要安装 requirements.txt 中的依赖包
    4. 建议先执行 init_song_playlist_agg.py 确保歌单数据已就绪
    5. 使用本地模型时，建议设置 HF_HUB_OFFLINE=1 避免网络验证问题（如果已有缓存）
"""

import os
import sys
import re
import time
from dotenv import load_dotenv

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2

# 加载环境变量
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(env_path)

# ==================== 配置 ====================

# 是否使用本地模型
USE_LOCAL = os.getenv('EMBEDDING_USE_LOCAL', 'false').lower() == 'true'

# GPU 分组编号 (0-5)，通过环境变量指定，用于 song_id % 6 分组
GPU_GROUP = int(os.getenv('GPU_GROUP', '0'))

EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL_NAME')

# 本地模型名称（可通过环境变量配置）
LOCAL_EMBEDDING_MODEL = os.getenv('LOCAL_EMBEDDING_MODEL', 'BAAI/bge-m3')


def get_db_connection():
    """获取数据库连接"""
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'musicdb'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', 'luke')
    )


# ==================== Plan A: API 方案 ====================

def setup_api_client():
    """初始化 API 客户端"""
    from openai import OpenAI
    return OpenAI(
        api_key=os.getenv('EMBEDDING_API_KEY'),
        base_url=os.getenv('EMBEDDING_PROVIDER_URL')
    )


def generate_embedding_api(text: str, client, model: str):
    """调用 Embedding API 生成向量"""
    try:
        response = client.embeddings.create(
            model=model,
            input=text,
            encoding_format="float"
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"    Embedding API 错误: {e}")
        return None


# ==================== Plan B: 本地 GPU 方案 ====================

def setup_local_model():
    """初始化本地模型"""
    import torch
    from transformers import AutoModel, AutoTokenizer

    # 根据 GPU_GROUP 选择使用的 GPU
    device = f"cuda:{GPU_GROUP}" if torch.cuda.is_available() else "cpu"

    print(f"    加载模型: {LOCAL_EMBEDDING_MODEL}")
    print(f"    使用设备: {device}")

    tokenizer = AutoTokenizer.from_pretrained(LOCAL_EMBEDDING_MODEL, trust_remote_code=True)
    model = AutoModel.from_pretrained(LOCAL_EMBEDDING_MODEL, trust_remote_code=True)
    model.to(device)
    model.eval()

    return model, tokenizer, device

'''
可以验证向量是否归一化
SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (
        WHERE ABS(vector_norm(embedding) - 1.0) < 1e-6
    ) AS normalized_rows
FROM song_embeddings;
'''


def cls_pooling(model_output):
    """CLS Pooling - 取 [CLS] token 的隐藏状态作为句子向量

    BGE-M3 官方推荐使用 CLS Pooling，而非 Mean Pooling。
    CLS 从预训练起就被设计为聚合整个句子信息的特殊 token。
    """
    return model_output[0][:, 0, :]  # 取第一列，即 [CLS] 位置的向量


def generate_embedding_local(text: str, model, tokenizer, device: str):
    """使用本地模型生成向量"""
    import torch
    try:
        encoded_input = tokenizer(text, padding=True, truncation=True, max_length=1024, return_tensors='pt')
        encoded_input = {k: v.to(device) for k, v in encoded_input.items()}

        with torch.no_grad():
            model_output = model(**encoded_input)

        # 使用 CLS Pooling（BGE-M3 官方推荐）
        embedding = cls_pooling(model_output)
        # L2 归一化
        embedding = torch.nn.functional.normalize(embedding, p=2, dim=1)

        return embedding[0].cpu().numpy().tolist()
    except Exception as e:
        print(f"    本地模型推理错误: {e}")
        return None


# ==================== 初始化（根据方案选择） ====================

api_client = None
local_model = None
local_tokenizer = None
local_device = None

if USE_LOCAL:
    print("=" * 60)
    print("使用 Plan B: 本地 GPU 方案")
    print(f"GPU 分组: {GPU_GROUP} (处理 song_id % 6 == {GPU_GROUP} 的歌曲)")
    print("=" * 60)
    local_model, local_tokenizer, local_device = setup_local_model()
else:
    print("=" * 60)
    print("使用 Plan A: API 方案")
    print("=" * 60)
    api_client = setup_api_client()


def generate_embedding(text: str):
    """生成向量的统一接口，根据配置选择 API 或本地模型"""
    if USE_LOCAL:
        return generate_embedding_local(text, local_model, local_tokenizer, local_device)
    else:
        return generate_embedding_api(text, api_client, EMBEDDING_MODEL)


# ==================== 通用函数 ====================

def clean_text(text: str) -> str:
    """基础清洗：去除特殊字符、多余空白"""
    text = re.sub(r"[^\w\u4e00-\u9fa5]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def split_by_separator(tag_str: str, sep: str = ",", top_k: int = 20) -> str:
    """分隔 + 去重 + 截断"""
    if not tag_str:
        return ""
    tags = [clean_text(t) for t in tag_str.split(sep) if t.strip()]
    seen = set()
    result = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            result.append(t)
        if len(result) >= top_k:
            break
    return " ".join(result)


def build_text_description(song_name: str, artist: str, album: str,
                          playlist_names=None, playlist_categories=None) -> str:
    """构建歌曲的文本描述（用于生成 embedding）"""
    # 歌单名称和分类用 ## 分割（取决于数据存储格式）
    playlist = split_by_separator(playlist_names, sep="##", top_k=20)
    category = split_by_separator(playlist_categories, sep="##", top_k=10)

    return f"歌名：{clean_text(song_name)}\n" \
           f"作者：{clean_text(artist)}\n" \
           f"专辑：{clean_text(album)}\n" \
           f"类别：{category}\n" \
           f"歌单：{playlist}"

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
    if USE_LOCAL:
        print(f"方案: Plan B (本地 GPU)")
        print(f"模型: {LOCAL_EMBEDDING_MODEL}")
        print(f"GPU 分组: {GPU_GROUP}")
    else:
        print(f"方案: Plan A (API)")
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

        # Plan B: 只统计当前 GPU 分组对应的歌曲
        if USE_LOCAL:
            cursor.execute("""
                SELECT COUNT(*) FROM songs s
                LEFT JOIN song_embeddings se ON s.song_id = se.song_id
                WHERE MOD(s.song_id, 6) = %s
                  AND (se.id IS null or (se.id IS not null and se.embedding is null))
            """, (GPU_GROUP,))
        else:
            cursor.execute("""
                SELECT COUNT(*) FROM songs s
                LEFT JOIN song_embeddings se ON s.song_id = se.song_id
                WHERE (se.id IS null or (se.id IS not null and se.embedding is null))
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
        print("    (按 Ctrl+C 取消)")

        processed = 0
        batch_num = 0

        while True:
            # 获取一批待处理的歌曲
            # Plan B: 添加 song_id % 6 过滤
            if USE_LOCAL:
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
                    WHERE MOD(s.song_id, 6) = %s
                      AND (se.id IS null or (se.id IS not null and se.embedding is null))
                    LIMIT %s
                """, (GPU_GROUP, batch_size))
            else:
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
                    WHERE (se.id IS null or (se.id IS not null and se.embedding is null))
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

                # 避免 API 限流（Plan A 需要，Plan B 可适当调大）
                if not USE_LOCAL:
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