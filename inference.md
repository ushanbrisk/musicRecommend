# 音乐特征生成 - 推理部署方案

## 1. 背景与目标

### 1.1 任务概述

- **目标**：为 12 万首歌曲生成音乐特征（genre、mood、tempo、instruments、scene、description 等）
- **核心诉求**：最大化总吞吐量（tokens/s），而非单次推理延迟
- **数据特点**：
  - 每首歌曲的输入为聚合后的文本（歌单名 + 评论摘要）
  - **重要**：`song_comment_agg` 中每首歌曲的评论已被压缩到 **5 条以内**
  - 因此单首歌曲的输入 token 数可控，批量拼接的上限可以更高

### 1.2 当前方案问题

现有 `init_music_feature_api.py` 的问题：

| 问题 | 影响 |
|------|------|
| 默认 `BATCH_SIZE=1` | 12万首歌需调用12万次API，吞吐量极低 |
| 单次 API 调用 | 无法利用批量折扣，延迟高 |
| 无 Map-Reduce 策略 | 热歌评论过多时只能截断，信息丢失 |
| 串行处理 | 无法利用多卡并行 |

### 1.3 硬件环境

```
组 A：2 × RTX 3090 (24GB)  → GPU 0, 4
组 B：2 × RTX 3080 (20GB)  → GPU 1, 2
空闲：GPU 3, 5 (备用)
```

---

## 2. 推荐模型与部署配置

### 2.1 模型选型

| 组 | GPU | 推荐模型 | 理由 |
|----|-----|----------|------|
| **组 A** | 2 × RTX 3090 (24GB) | **Qwen2.5-32B-Instruct (AWQ Int4)** | 32B 模型理解能力强；Int4 量化后约 16GB，双卡 TP=2 加载 |
| **组 B** | 2 × RTX 3080 (20GB) | **Qwen2.5-14B-Instruct (AWQ Int4)** | 14B 模型适合批量处理；Int4 量化后约 8GB，双卡 TP=2 加载 |

> 注：截至 2026-05-20，Qwen3.7-Max 为旗舰版，但开源社区主流稳定版为 Qwen3.6 系列。

### 2.2 部署架构

```
                    ┌─────────────────────────────────────────┐
                    │           数据分发层 (Data Router)        │
                    │     将 12 万首歌曲按 song_id 哈希分两组   │
                    └─────────────────────────────────────────┘
                              │                        │
                              ▼                        ▼
                    ┌─────────────────┐    ┌─────────────────────────┐
                    │   组 A 服务      │    │       组 B 服务          │
                    │  (vLLM Server)  │    │    (vLLM Server)        │
                    │                 │    │                         │
                    │  2 × RTX 3090   │    │  2 × RTX 3080          │
                    │  Qwen2.5-32B    │    │  Qwen2.5-14B           │
                    │  Int4 + TP=2    │    │  Int4 + TP=2           │
                    │                 │    │                         │
                    │  端口: 8000     │    │  端口: 8001             │
                    └─────────────────┘    └─────────────────────────┘
                              │                        │
                              ▼                        ▼
                    ┌─────────────────┐    ┌─────────────────────────┐
                    │   约 6 万首      │    │      约 6 万首           │
                    │  (组 A 处理)     │    │    (组 B 处理)           │
                    └─────────────────┘    └─────────────────────────┘
```

### 2.3 vLLM 启动命令

**组 A（2 × RTX 3090，张量并行=2）**：

```bash
python -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen2.5-32B-Instruct \
    --quantization awq \
    --tensor-parallel-size 2 \
    --host 0.0.0.0 \
    --port 8000 \
    --gpu-memory-utilization 0.90 \
    --max-model-len 8192 \
    --batch-size 32 \
    --trust-remote-code
```

**组 B（2 × RTX 3080，张量并行=2）**：

```bash
python -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen2.5-14B-Instruct \
    --quantization awq \
    --tensor-parallel-size 2 \
    --host 0.0.0.0 \
    --port 8001 \
    --gpu-memory-utilization 0.90 \
    --max-model-len 8192 \
    --batch-size 64 \
    --trust-remote-code
```

---

## 3. 核心策略：批量拼接

### 3.1 策略原理

由于 `song_comment_agg` 中每首歌曲的评论已被压缩到 **5 条以内**，单首歌曲的输入 token 数较小且可控。因此直接采用**批量拼接**策略，将多首歌曲的文本合并到一次 API 调用中处理。

### 3.2 批量拼接的优势

| 对比项 | 逐首处理 | 批量拼接（推荐） |
|--------|----------|------------------|
| API 调用次数 | 12 万次 | 约 6 千次（每批 20 首） |
| 吞吐量 | ~1 song/s | ~100+ songs/s |
| 上下文利用率 | 低 | 高 |
| 单次延迟 | 低 | 略高但可接受 |

### 3.3 为什么不能无限拼接

| 上下文长度 | Prefill 时间 | 显存占用 | 风险 |
|-----------|--------------|----------|------|
| 8K tokens | ~1s | 低 | 安全 |
| 16K tokens | ~2s | 中 | 安全 |
| 32K tokens | ~5s | 高 | 可能 OOM |
| 128K tokens | ~20s+ | 极高 | 极易 OOM |

**建议**：单次输入控制在 **16K tokens** 以内，每批拼接 **15-20 首**歌曲。

> 由于每首歌曲的评论只有 5 条，单首歌的文本量很小（估计 200-500 tokens），
> 因此每批 20 首歌曲的总 token 数仍在 4K-10K 左右，安全可控。

### 3.4 批量拼接策略

```python
def build_batch_prompt(songs: List[dict], max_tokens: int = 16000) -> str:
    """
    将多首歌曲的文本信息拼接为一个批量 prompt

    策略：
    - 每首歌曲的文本约 200-500 tokens（评论已被压缩到 5 条以内）
    - 每批最多 20 首歌曲（总计约 4K-10K tokens）
    - 超出则拆分为多个批次
    """
    batch_lines = []
    current_tokens = 0

    for song in songs:
        song_text = format_song_text(song)
        song_tokens = estimate_tokens(song_text)

        # 如果加上这首歌会超过 max_tokens，开启新批次
        if current_tokens + song_tokens > max_tokens and batch_lines:
            break

        batch_lines.append(f"[歌曲 {len(batch_lines)}]\n{song_text}")
        current_tokens += song_tokens

    return "\n---\n".join(batch_lines)
```

---

## 4. 多卡并行架构

### 4.1 两组服务并行

```
        歌曲池 (12万首)
             │
             ▼
    ┌────────────────────┐
    │  song_id % 2 == 0  │  →  组 A (vLLM:8000)  →  约 6 万首
    │  song_id % 2 == 1  │  →  组 B (vLLM:8001)  →  约 6 万首
    └────────────────────┘
```

### 4.2 批量请求并行

```python
import asyncio
import aiohttp

async def process_all_songs_concurrent():
    """两组 vLLM 服务并行处理"""
    songs_group_a = [s for s in all_songs if s['song_id'] % 2 == 0]
    songs_group_b = [s for s in all_songs if s['song_id'] % 2 == 1]

    # 并行启动两组处理
    task_a = asyncio.create_task(process_group(songs_group_a, "http://localhost:8000"))
    task_b = asyncio.create_task(process_group(songs_group_b, "http://localhost:8001"))

    results_a, results_b = await asyncio.gather(task_a, task_b)
    return results_a + results_b

async def process_group(songs: List[dict], endpoint: str):
    """处理一组歌曲，使用 Continuous Batching"""
    async with aiohttp.ClientSession() as session:
        # 使用 semaphore 控制并发数，避免压垮 vLLM
        semaphore = asyncio.Semaphore(32)

        async def process_batch(batch):
            async with semaphore:
                payload = {
                    "model": "qwen",
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": build_batch_prompt(batch)}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 2048
                }
                async with session.post(f"{endpoint}/v1/chat/completions", json=payload) as resp:
                    return await resp.json()

        # 分批处理
        batches = [songs[i:i+BATCH_SIZE] for i in range(0, len(songs), BATCH_SIZE)]
        results = []
        for batch in batches:
            result = await process_batch(batch)
            results.extend(parse_batch_result(result))
        return results
```

---

## 5. Prompt 设计

### 5.1 系统提示词

```python
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
"""
```

### 5.2 批量处理 Prompt

```python
BATCH_MUSIC_FEATURE_PROMPT = """请为以下批量歌曲生成特征信息。每首歌信息格式为[序号] 歌名...：

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
```

---

## 6. 性能估算

### 6.1 吞吐量估算

由于每首歌曲的评论已压缩到 5 条以内，单首歌文本量小（200-500 tokens），可以更激进的批量：

| 配置 | 模型 | 每批歌曲数 | 预估速度 |
|------|------|------------|----------|
| 组 A (2×3090) | Qwen2.5-32B Int4 | 20 | ~40 songs/s |
| 组 B (2×3080) | Qwen2.5-14B Int4 | 32 | ~60 songs/s |
| **合计** | - | - | **~100 songs/s** |

### 6.2 总耗时估算

```
12万首歌曲 ÷ 100 songs/s ≈ 1200 秒 ≈ 20 分钟
```

### 6.3 优化空间

如果仍需加速：
1. 增大 `max_model_len` 允许更长上下文 → 可每批处理更多歌曲（32+）
2. 启用 `prefix_caching` → 相同前缀的 prompt 可复用
3. 增加 `gpu_memory_utilization` → 更大的 batch_size

---

## 7. 错误处理与重试

### 7.1 重试机制

```python
MAX_RETRIES = 3
RETRY_DELAY = 5  # 秒

def call_with_retry(prompt: str, endpoint: str) -> dict:
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(endpoint, json=payload, timeout=120)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
            else:
                raise e
```

### 7.2 降级处理

```python
def process_batch_fallback(batch: List[dict], llm_client) -> List[dict]:
    """
    批量调用失败时，降级为逐首处理
    """
    results = []
    for song in batch:
        try:
            result = call_llm_single(song, llm_client)
            results.append(result)
        except Exception as e:
            # 记录失败，使用默认特征
            results.append({
                "song_id": song['song_id'],
                "description": "待定",
                "genre": ["待定"],
                "mood": ["待定"],
                "tempo": "待定",
                "instruments": [],
                "scene": [],
                "emotional_tags": [],
                "theme_keywords": []
            })
    return results
```

---

## 8. 部署检查清单

### 8.1 部署前检查

- [ ] 两组 GPU 驱动安装正确（`nvidia-smi` 可用）
- [ ] vLLM 已安装（`pip install vllm>=0.4.0`）
- [ ] 模型文件已下载或配置好 HuggingFace 镜像
- [ ] 数据库连接配置正确（`.env` 文件）
- [ ] `song_playlist_agg` 和 `song_comment_agg` 预聚合表已有数据

### 8.2 启动顺序

```bash
# 1. 启动组 A 服务（后台运行）
nohup python -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen3.6-27B-Chat \
    --quantization gptq --bits 4 \
    --tensor-parallel-size 2 \
    --port 8000 > logs/vllm_group_a.log 2>&1 &

# 2. 启动组 B 服务（后台运行）
nohup python -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen3.6-30B-A3B-Chat \
    --quantization gptq --bits 4 \
    --tensor-parallel-size 4 \
    --port 8001 > logs/vllm_group_b.log 2>&1 &

# 3. 等待服务就绪（约 5-10 分钟加载模型）
sleep 300

# 4. 验证服务
curl http://localhost:8000/v1/models
curl http://localhost:8001/v1/models

# 5. 运行推理脚本
python scripts/init_music_feature_vllm.py
```

### 8.3 监控指标

| 指标 | 目标值 | 监控方式 |
|------|--------|----------|
| 吞吐量 | > 100 songs/s | 日志统计 |
| 失败率 | < 1% | 数据库失败计数 |
| GPU 利用率 | > 80% | `nvidia-smi` |
| 显存使用 | < 95% | `nvidia-smi` |

---

## 9. 新脚本参考实现

新建 `scripts/init_music_feature_vllm.py`，核心逻辑：

```python
import os
import time
import json
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor

# 配置
VLLM_ENDPOINT_A = "http://localhost:8000/v1/chat/completions"
VLLM_ENDPOINT_B = "http://localhost:8001/v1/chat/completions"
BATCH_SIZE = 8  # 每批歌曲数
MAX_TOKENS = 2048

async def process_song_batch(batch: List[dict], endpoint: str) -> List[dict]:
    """调用 vLLM 处理一批歌曲"""
    prompt = build_batch_prompt(batch)

    payload = {
        "messages": [
            {"role": "system", "content": MUSIC_FEATURE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": MAX_TOKENS
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(endpoint, json=payload, timeout=180) as resp:
            result = await resp.json()
            return parse_batch_result(result)

def main():
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. 获取待处理歌曲
    songs = get_songs_without_features(cursor, limit=100000)

    # 2. 按 song_id 分组
    group_a = [s for s in songs if s['song_id'] % 2 == 0]
    group_b = [s for s in songs if s['song_id'] % 2 == 1]

    # 3. 并行处理
    asyncio.run(process_groups_parallel(group_a, group_b))

    cursor.close()
    conn.close()
```

---

## 10. 总结

| 要点 | 建议 |
|------|------|
| **模型选择** | 组A用 Qwen2.5-32B-Instruct Int4，组B用 Qwen2.5-14B-Instruct Int4 |
| **GPU分配** | 组A用 2×RTX 3090 (GPU 0,4)，组B用 2×RTX 3080 (GPU 1,2)，空闲 GPU 3,5 |
| **并行策略** | 按 song_id 哈希分两组，vLLM 服务并行处理 |
| **批量策略** | 每批 20-32 首歌曲，控制在 8K tokens 以内 |
| **评论限制** | 预聚合表已压缩到 5 条以内，无需 Map-Reduce |
| **框架选择** | vLLM（Continuous Batching 自动合并不同长度任务） |
| **预估耗时** | ~20 分钟处理 12 万首歌曲 |

---

## 11. 创建的文件

### 11.1 scripts/start_vllm_servers.sh

vLLM 服务启动脚本

**使用方法**：
```bash
bash scripts/start_vllm_servers.sh all      # 启动两组服务
bash scripts/start_vllm_servers.sh group_a   # 只启动组A
bash scripts/start_vllm_servers.sh status    # 查看状态
bash scripts/start_vllm_servers.sh stop      # 停止服务
```

**功能**：
- 启动组 A：2×RTX 3090 (GPU 0,4) → Qwen2.5-32B-Instruct (AWQ Int4, TP=2)，端口 8000
- 启动组 B：2×RTX 3080 (GPU 1,2) → Qwen2.5-14B-Instruct (AWQ Int4, TP=2)，端口 8001
- 空闲 GPU 3, 5 备用
- 模型加载完成后自动检测
- 日志输出到 `logs/vllm_group_*.log`

### 11.2 scripts/init_music_feature_vllm.py

vLLM 批量特征生成脚本

**运行命令**：
```bash
~/miniconda3/envs/music/bin/python scripts/init_music_feature_vllm.py
```

**功能**：
- 按 `song_id % 2` 分组并行调用两组 vLLM
- 每批 20 首歌曲（可配置 `VLLM_BATCH_SIZE`）
- 异步 IO + aiohttp 高并发调用
- 自动重试、错误处理
- 进度显示和耗时统计

### 11.3 backend/services/vllm_service.py

vLLM 服务封装，供 Flask 后端实时推荐使用

### 11.4 backend/config.py（更新）

新增 vLLM 配置项：

```python
VLLM_ENDPOINT_A = 'http://localhost:8000/v1/chat/completions'
VLLM_ENDPOINT_B = 'http://localhost:8001/v1/chat/completions'
VLLM_BATCH_SIZE = 20
```

---

## 12. 使用流程

### 12.1 安装依赖

```bash
conda create -n music_recommend python=3.10 -y
conda activate music_recommend
pip install --upgrade pip

pip install vllm>=0.4.0 aiohttp 
or pip install -r requirements.txt
```

### 12.2 启动 vLLM 服务

```bash
bash scripts/start_vllm_servers.sh all
bash scripts/start_vllm_servers_v2.sh start | stop | status
```

> 模型加载需要几分钟时间，可通过以下命令查看状态：
> ```bash
> bash scripts/start_vllm_servers.sh status
> ```

### 12.3 运行批量特征生成

```bash
~/miniconda3/envs/music/bin/python scripts/init_music_feature_vllm.py
```

### 12.4 查看结果

特征生成后，验证数据：

```bash
PGPASSWORD=luke psql -h localhost -U postgres -d musicdb -c "SELECT COUNT(*) FROM music_features;"
PGPASSWORD=luke psql -h localhost -U postgres -d musicdb -c "SELECT song_id, genre, mood FROM music_features LIMIT 3;"
```
