# 本地大模型部署指南

## 概述

本指南详细说明如何在本地服务器上部署 vLLM 推理服务，替代云端 API 调用，实现 12 万首歌曲的音乐特征批量生成。

## 硬件配置

```
组 A: 2×RTX 3090 (24GB) → GPU 0, 4
组 B: 2×RTX 3080 (20GB) → GPU 1, 2
空闲: GPU 3, 5 (备用)
```

## 推荐模型

- **组 A**: `Qwen/Qwen2.5-32B-Instruct` (AWQ Int4 量化)
- **组 B**: `Qwen/Qwen2.5-14B-Instruct` (AWQ Int4 量化)

## 部署步骤

### 步骤 1：安装依赖

```bash
# 创建 Python 环境
conda create -n music python=3.10 -y
conda activate music

# 安装核心依赖
pip install --upgrade pip
pip install vllm>=0.4.0
pip install aiohttp psycopg2-binary python-dotenv

# 或者使用 requirements.txt（如果已有）
pip install -r requirements.txt
```

### 步骤 2：配置 HuggingFace 访问

vLLM 需要从 HuggingFace 下载模型，有两种方式：

#### 方式一：使用 HuggingFace Token（推荐）

```bash
# 1. 注册 HuggingFace 账号：https://huggingface.co/join
# 2. 生成 Token：https://huggingface.co/settings/tokens
# 3. 配置环境变量
export HF_TOKEN="your_huggingface_token_here"

# 或者使用 huggingface-cli
pip install huggingface-hub
huggingface-cli login
```

#### 方式二：使用国内镜像（ModelScope）

```bash
# 安装 ModelScope
pip install modelscope

# 配置镜像
export HF_ENDPOINT="https://hf-mirror.com"
```

### 步骤 3：预下载模型（可选但推荐）

提前下载模型可以避免启动时等待：

```bash
# 方式 1：使用 huggingface-cli
huggingface-cli download Qwen/Qwen2.5-32B-Instruct
huggingface-cli download Qwen/Qwen2.5-14B-Instruct

# 方式 2：使用 Python 脚本
python -c "
from transformers import AutoTokenizer
AutoTokenizer.from_pretrained('Qwen/Qwen2.5-32B-Instruct')
AutoTokenizer.from_pretrained('Qwen/Qwen2.5-14B-Instruct')
"

# 方式 3：手动指定下载目录
export HF_HOME="/path/to/your/model/cache"
```

模型默认下载到：`~/.cache/huggingface/hub/`

### 步骤 4：配置数据库环境变量

编辑项目根目录的 `.env` 文件：

```bash
# PostgreSQL 配置
PG_HOST=localhost
PG_PORT=5432
PG_DB=musicdb
PG_USER=postgres
PG_PASSWORD=luke

# vLLM 配置（可选，使用默认值）
VLLM_ENDPOINT_A=http://localhost:8000/v1/chat/completions
VLLM_ENDPOINT_B=http://localhost:8001/v1/chat/completions
VLLM_BATCH_SIZE=20
VLLM_MAX_CONCURRENT=16
VLLM_REQUEST_TIMEOUT=180
VLLM_MAX_RETRIES=3
```

### 步骤 5：启动 vLLM 服务

```bash
# 检查脚本是否可执行
chmod +x scripts/start_vllm_servers.sh

# 启动所有服务（组 A + 组 B）
bash scripts/start_vllm_servers.sh all

# 或者分别启动
bash scripts/start_vllm_servers.sh group_a  # 启动组 A
bash scripts/start_vllm_servers.sh group_b  # 启动组 B
```

**预计启动时间**：
- 首次启动（需下载模型）：10-20 分钟
- 后续启动（模型已缓存）：3-5 分钟

**查看启动日志**：
```bash
# 查看组 A 日志
tail -f logs/vllm_group_a.log

# 查看组 B 日志
tail -f logs/vllm_group_b.log
```

**查看服务状态**：
```bash
bash scripts/start_vllm_servers.sh status
```

### 步骤 6：验证服务

```bash
# 测试组 A（端口 8000）
curl http://localhost:8000/v1/models

# 测试组 B（端口 8001）
curl http://localhost:8001/v1/models

# 发送测试请求
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen",
    "messages": [{"role": "user", "content": "你好"}],
    "max_tokens": 100
  }'
```

### 步骤 7：运行批量特征生成

```bash
# 确保预聚合表已填充
# python scripts/init_song_playlist_agg.py
# python scripts/init_song_comment_agg.py

# 运行 vLLM 批量生成
~/miniconda3/envs/music/bin/python scripts/init_music_feature_vllm.py
```

**预计处理时间**：
- 12 万首歌曲
- 批量大小：20 首/批
- 预计速度：100-160 songs/s
- **总耗时：约 12-20 分钟**

### 步骤 8：监控进度

```bash
# 查看 GPU 使用情况
watch -n 1 nvidia-smi

# 查看数据库进度
PGPASSWORD=luke psql -h localhost -U postgres -d musicdb -c \
  "SELECT COUNT(*) FROM music_features;"

# 查看脚本输出
# 脚本会实时显示处理进度和速度
```

## 常见问题排查

### 问题 1：模型下载失败

**症状**：
```
Connection error: Unable to download model
```

**解决方案**：
```bash
# 1. 配置国内镜像
export HF_ENDPOINT="https://hf-mirror.com"

# 2. 或手动下载模型到指定目录
mkdir -p ~/models
cd ~/models
git lfs install
git clone https://huggingface.co/Qwen/Qwen2.5-32B-Instruct
git clone https://huggingface.co/Qwen/Qwen2.5-14B-Instruct

# 3. 修改启动脚本，使用本地路径
# 编辑 scripts/start_vllm_servers.sh
MODEL_GROUP_A="~/models/Qwen2.5-32B-Instruct"
MODEL_GROUP_B="~/models/Qwen2.5-14B-Instruct"
```

### 问题 2：显存不足（OOM）

**症状**：
```
CUDA out of memory
```

**解决方案**：
```bash
# 1. 减小 gpu-memory-utilization
# 编辑 scripts/start_vllm_servers.sh
GPU_MEMORY_UTILIZATION=0.85  # 从 0.90 降低到 0.85

# 2. 减小 max-num-seqs
MAX_NUM_SEQS_GROUP_A=16  # 从 32 降低到 16
MAX_NUM_SEQS_GROUP_B=32  # 从 64 降低到 32

# 3. 减小 max-model-len
MAX_MODEL_LEN=4096  # 从 8192 降低到 4096
```

### 问题 3：vLLM 服务启动失败

**症状**：
```
RuntimeError: CUDA error: invalid device ordinal
```

**解决方案**：
```bash
# 1. 确认 GPU 可见性
nvidia-smi -L

# 2. 检查 GPU 分配是否正确
# 编辑 scripts/start_vllm_servers.sh
GPU_GROUP_A="0,4"  # 2×RTX 3090
GPU_GROUP_B="1,2"  # 2×RTX 3080

# 3. 检查 CUDA 驱动
nvidia-smi
```

### 问题 4：推理速度慢

**症状**：
- 吞吐量 < 50 songs/s

**解决方案**：
```bash
# 1. 增加批量大小
export VLLM_BATCH_SIZE=32  # 从 20 增加到 32

# 2. 增加并发数
export VLLM_MAX_CONCURRENT=32  # 从 16 增加到 32

# 3. 检查 GPU 利用率
nvidia-smi dmon -s u

# 4. 确保两组服务都在运行
bash scripts/start_vllm_servers.sh status
```

### 问题 5：数据库连接失败

**症状**：
```
psycopg2.OperationalError: could not connect to server
```

**解决方案**：
```bash
# 1. 检查 PostgreSQL 状态
sudo systemctl status postgresql

# 2. 检查 .env 配置
cat .env | grep PG_

# 3. 测试连接
PGPASSWORD=luke psql -h localhost -U postgres -d musicdb -c "SELECT 1;"
```

### 问题 6：JSON 解析失败

**症状**：
```
解析响应失败: Expecting value
```

**解决方案**：
- 这通常是因为 LLM 返回格式不标准
- 脚本已内置多种解析策略，会自动重试
- 如果频繁出现，可以：
  1. 降低 temperature（在脚本中设置为 0.1）
  2. 在 prompt 中更明确地要求 JSON 格式

## 性能优化建议

### 1. 使用本地模型缓存

```bash
# 将模型下载到 SSD 而非机械硬盘
export HF_HOME="/path/to/ssd/huggingface"
```

### 2. 启用 Tensor Parallelism

已在启动脚本中启用：
- 组 A：TP=2（2 块 GPU）
- 组 B：TP=2（2 块 GPU）

### 3. 调整批量参数

根据实际情况调整 `.env`：
```bash
VLLM_BATCH_SIZE=24        # 每批歌曲数（推荐 16-32）
VLLM_MAX_CONCURRENT=20    # 最大并发请求（推荐 16-32）
```

### 4. 使用更快的量化方法

如果 AWQ 不够快，可以尝试：
```bash
# 编辑 scripts/start_vllm_servers.sh
QUANTIZATION="bitsandbytes"  # 或 "squeezellm"
```

## 停止服务

```bash
# 停止所有 vLLM 服务
bash scripts/start_vllm_servers.sh stop

# 或手动 kill
pkill -f "vllm.entrypoints.openai.api_server"
```

## 验证最终结果

```bash
# 查看生成的特征数量
PGPASSWORD=luke psql -h localhost -U postgres -d musicdb -c \
  "SELECT COUNT(*) FROM music_features;"

# 查看样例数据
PGPASSWORD=luke psql -h localhost -U postgres -d musicdb -c \
  "SELECT song_id, genre, mood, scene, description FROM music_features LIMIT 5;"

# 查看失败的歌曲
PGPASSWORD=luke psql -h localhost -U postgres -d musicdb -c \
  "SELECT COUNT(*) FROM songs s
   LEFT JOIN music_features mf ON s.song_id = mf.song_id
   WHERE mf.id IS NULL;"
```

## 架构图

```
                ┌─────────────────────────────┐
                │   12 万首歌曲（songs 表）     │
                └──────────────┬──────────────┘
                               │
                ┌──────────────┴──────────────┐
                │                             │
        按 song_id % 2 分组                   │
                │                             │
    ┌───────────┴──────────┐     ┌───────────┴──────────┐
    │   组 A: 约 6 万首    │     │   组 B: 约 6 万首    │
    │   song_id % 2 == 0   │     │   song_id % 2 == 1   │
    └───────────┬──────────┘     └───────────┬──────────┘
                │                             │
    ┌───────────▼──────────┐     ┌───────────▼──────────┐
    │   vLLM 组 A 服务     │     │   vLLM 组 B 服务     │
    │   Port: 8000        │     │   Port: 8001        │
    │   2×RTX 3090        │     │   2×RTX 3080        │
    │   Qwen2.5-32B       │     │   Qwen2.5-14B       │
    │   TP=2, AWQ Int4    │     │   TP=2, AWQ Int4    │
    └───────────┬──────────┘     └───────────┬──────────┘
                │                             │
                └──────────────┬──────────────┘
                               ▼
                ┌─────────────────────────────┐
                │  music_features 表          │
                │  (存储生成的特征)            │
                └─────────────────────────────┘
```

## 预期性能

| 指标 | 目标值 | 实际值（待测） |
|------|--------|----------------|
| 总处理歌曲数 | 120,000 | - |
| 批量大小 | 20 首/批 | - |
| 组 A 吞吐量 | 30-50 songs/s | - |
| 组 B 吞吐量 | 50-70 songs/s | - |
| **总吞吐量** | **80-120 songs/s** | - |
| **预计总耗时** | **15-25 分钟** | - |
| GPU 利用率 | > 80% | - |
| 成功率 | > 99% | - |

## 下一步

完成特征生成后：
1. 验证数据质量（抽样检查）
2. 更新后端 API，使用 `music_features` 表
3. 测试推荐功能
4. 可以关闭 vLLM 服务节省资源

## 技术支持

如遇到问题：
1. 查看日志：`logs/vllm_group_*.log`
2. 查看 GPU 状态：`nvidia-smi`
3. 查看数据库状态：`PGPASSWORD=luke psql -h localhost -U postgres -d musicdb`
4. 参考 `inference.md` 设计文档
