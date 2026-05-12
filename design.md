# 音乐推荐引擎 - 项目设计方案

## 1. 项目概述

### 1.1 目标

为 music-project-uniapp (前端) 和 music-project/backend (后端) 添加基于文本描述的智能音乐推荐功能。用户可以输入简单的场景/情感描述（如"欢快的凯尔特音乐"、"怀旧的适合心情郁闷的时候"）或复杂的文学内容（如古诗词），系统从曲库中返回匹配的音乐。

### 1.2 项目现状

| 项目 | 技术栈 | 说明 |
|------|--------|------|
| 后端 | Python Flask + PostgreSQL + MongoDB | 提供REST API，音乐数据存储在PostgreSQL，评论数据在MongoDB |
| 前端 | Vue 3 + UniApp | 跨平台（微信小程序/H5/App）音乐播放器 |

---

#### 1.2.1 PostgreSQL 数据库表结构

**表1: songs（歌曲表）**

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `id` | SERIAL | 自增主键 | 1 |
| `song_id` | BIGINT | 歌曲唯一标识 | 1893728473 |
| `song_name` | VARCHAR(255) | 歌曲名称 | "Ye Netherlands, Where I Have a Love" |
| `artist` | VARCHAR(255) | 艺术家/歌手 | "Johan Wagenaar" |
| `album` | VARCHAR(255) | 专辑名 | "Orchestral Works" |
| `music_file` | VARCHAR(255) | 音乐文件路径 | "/ssd11/music/song_download/1893728473.mp3" |
| `created_at` | TIMESTAMP | 创建时间 | "2024-01-15 10:30:00" |

**数据样例：**

| song_id | song_name | artist | album |
|---------|-----------|--------|-------|
| 1893728473 | Ye Netherlands, Where I Have a Love | Johan Wagenaar | Orchestral Works |
| 1457702766 | Dance of the Knights | Sergei Prokofiev | Romeo & Juliet |
| 1397612833 | 琵琶行 | Various | 经典古诗词配乐 |

**文本信息利用构想：**
- `song_name` + `artist` + `album` → 提取歌曲风格、年代、艺术家类型
- 歌曲名称可能包含情绪词（如"忧伤的"、"欢快的"）
- 外文歌曲名称可推断语言属性

---

**表2: playlists（歌单表）**

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `id` | SERIAL | 自增主键 | 1 |
| `playlist_id` | BIGINT | 歌单唯一标识 | 7213567821 |
| `playlist_name` | VARCHAR(255) | 歌单名称 | "【古典】宁静致远 · 放松身心" |
| `category` | VARCHAR(100) | 分类/标签 | "古典" |
| `created_at` | TIMESTAMP | 创建时间 | "2024-02-20 14:00:00" |

**数据样例：**

| playlist_id | playlist_name | category |
|-------------|---------------|----------|
| 7213567821 | 【古典】宁静致远 · 放松身心 | 古典 |
| 6521347890 | 夜深沉 · 孤独患者的深夜独酌 | 深夜 |
| 8097451234 | 凯尔特风情 · 翡翠之岛的旋律 | 凯尔特 |
| 7456321890 | 工作时的专注背景音 | 工作 |
| 6789012345 | 地铁上的通勤时光 | 通勤 |
| 7123456789 | 运动健身 · 燃脂动感 | 运动 |
| 7890123456 | 心情郁闷时听的100首治愈系 | 治愈 |

**文本信息利用构想：**
- `playlist_name` 包含丰富的场景/情绪信息（"宁静致远"、"深夜独酌"、"燃脂动感"）
- `category` 提供粗粒度的类型分类
- 通过 `song_playlist` 关联，歌曲继承歌单的场景/情绪标签

---

**表3: song_playlist（歌曲-歌单关联表）**

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `id` | SERIAL | 自增主键 | 1 |
| `song_id` | BIGINT | 歌曲ID (FK) | 1893728473 |
| `playlist_id` | BIGINT | 歌单ID (FK) | 7213567821 |
| `created_at` | TIMESTAMP | 创建时间 | "2024-01-15 10:30:00" |

**数据样例：**

| song_id | playlist_id | 歌单名称 |
|---------|-------------|----------|
| 1893728473 | 7213567821 | 【古典】宁静致远 · 放松身心 |
| 1893728473 | 6521347890 | 夜深沉 · 孤独患者的深夜独酌 |
| 1457702766 | 7213567821 | 【古典】宁静致远 · 放松身心 |
| 1457702766 | 8097451234 | 凯尔特风情 · 翡翠之岛的旋律 |

**文本信息利用构想：**
- 一首歌曲可属于多个歌单，聚合所有歌单的 `playlist_name` 和 `category`
- 歌单名传递了丰富的场景语义，歌曲可继承这些语义标签
- 例如：歌曲出现在"深夜独酌"歌单 → 推断该歌曲适合深夜、独处、忧郁场景

---

#### 1.2.2 MongoDB 数据库表结构

**集合: comments（评论表）**

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `_id` | ObjectId | MongoDB自动生成 | ObjectId("...") |
| `song_id` | BIGINT | 歌曲ID | 1893728473 |
| `content` | TEXT | 评论内容 | "这曲子太美了，夜晚独自聆听仿佛置身星河" |
| `nickname` | VARCHAR(255) | 评论者昵称 | "音乐爱好者123" |
| `likedCount` | INTEGER | 点赞数 | 1523 |
| `sentiment` | VARCHAR(20) | 情感倾向 | "positive" / "neutral" / "negative" |
| `polarity` | FLOAT | 情感极性 (-1~1) | 0.85 |

**数据样例：**

| song_id | content | sentiment | polarity |
|---------|---------|-----------|----------|
| 1893728473 | 这曲子太美了，夜晚独自聆听仿佛置身星河 | positive | 0.85 |
| 1893728473 | 一般般，没什么感觉 | neutral | 0.1 |
| 1457702766 | 战斗进行曲！每次听都热血沸腾！ | positive | 0.92 |
| 1457702766 | 听起来有点压抑 | negative | -0.3 |

**文本信息利用构想：**
- `content` 字段包含大量用户生成的文本描述，可提取：
  - 场景描述（"夜晚"、"清晨"、"工作时分"）
  - 情绪感受（"治愈"、"热血沸腾"、"压抑"）
  - 使用建议（"适合独自聆听"、"运动时听"）
- `sentiment` 和 `polarity` 可用于筛选高正面评价的歌曲
- `likedCount` 高且正面情感强的评论，其内容权重更高

---

#### 1.2.3 文本信息汇总与利用策略

| 数据源 | 可提取的文本信息 | 提取方式 | 用途 |
|--------|-----------------|----------|------|
| `songs.song_name` | 歌曲名中的情绪词、类型词 | 关键词匹配 | 快速初筛 |
| `songs.artist` | 艺术家类型（古典/流行/民族） | 映射表 | 辅助分类 |
| `songs.album` | 专辑风格 | 关键词匹配 | 辅助分类 |
| `playlists.playlist_name` | 场景、情绪、功能描述 | LLM提取 | 核心特征 |
| `playlists.category` | 粗粒度分类 | 直接使用 | 快速过滤 |
| `song_playlist` 关联 | 歌曲→场景的映射 | 歌单传递 | 标签传递 |
| `comments.content` | 用户描述的场景/情绪/感受 | LLM提取 | 情感增强 |

---

## 2. 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端 (UniApp/Vue 3)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │  首页推荐入口 │  │  推荐页面    │  │  推荐结果展示组件    │   │
│  │  (文字输入)  │  │  (文字/语音) │  │  (歌曲列表+反馈)    │   │
│  └──────────────┘  └──────────────┘  └──────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ HTTP/REST
┌─────────────────────────────────────────────────────────────────┐
│                     后端 (Flask Python)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │  现有API     │  │  推荐API     │  │  LLM调用服务         │   │
│  │  /api/songs │  │  /api/recommend│ │  MiniMax API         │   │
│  │  /api/search│  │             │  │                      │   │
│  └──────────────┘  └──────────────┘  └──────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
           ┌──────────────────┼──────────────────┐
           ▼                  ▼                  ▼
┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐
│  PostgreSQL       │ │  MongoDB          │ │  MiniMax API      │
│  songs            │ │  comments         │ │  (LLM推理)        │
│  playlists        │ │                   │ │                   │
│  song_playlist    │ │                   │ │                   │
│  music_features   │ │                   │ │                   │
└───────────────────┘ └───────────────────┘ └───────────────────┘
```

---

## 3. 数据库扩展设计

### 3.1 新增表：音乐特征表 (music_features)

为每首歌曲提取和存储语义特征，便于LLM理解和匹配。所有特征通过LLM分析歌曲的原始信息（歌名、艺术家、专辑、歌单名、评论内容）自动生成。

```sql
CREATE TABLE music_features (
    id SERIAL PRIMARY KEY,
    song_id BIGINT UNIQUE NOT NULL REFERENCES songs(song_id),

    -- 基础特征（LLM从歌曲原始信息推断生成）
    genre VARCHAR(100),           -- 流派/风格：流行、摇滚、古典、民谣、电子、爵士、蓝调、凯尔特、新世纪等
    mood VARCHAR(200),            -- 情绪标签（逗号分隔）：欢快、忧伤、平静、激烈、浪漫、神秘、怀旧、励志、治愈等
    tempo VARCHAR(50),            -- 节拍：快、中、慢
    instruments VARCHAR(200),     -- 主要乐器：钢琴、吉他、鼓、弦乐、风笛、古筝、琵琶等
    scene VARCHAR(200),           -- 适用场景：夜晚、工作、运动、休息、阅读、旅行、聚会、独处、冥想、驾车等
    language VARCHAR(50),        -- 歌曲语言：中文、英文、日文、纯音乐等
    era VARCHAR(50),              -- 时代/年代：80年代、90年代、2000s、2010s、新世纪等

    -- 复杂特征（LLM综合分析生成）
    description TEXT,             -- AI生成的歌曲描述（100-200字），综合歌名、艺术家、专辑、歌单、评论等信息
    emotional_tags VARCHAR(500),   -- 细腻情感标签（逗号分隔）
    theme_keywords VARCHAR(500),   -- 主题关键词（逗号分隔）

    -- 扩展信息（从歌单继承）
    inherited_tags VARCHAR(500),   -- 从所属歌单继承的场景/情绪标签

    -- 向量表示（可选，用于向量检索）
    -- 如启用向量检索，使用 PostgreSQL pgvector 扩展
    feature_vector vector(1536),   -- 嵌入向量（可选，默认不启用）

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 索引设计说明：
-- genre, mood, scene 作为索引列，支持基于标签的快速过滤查询
-- 例如：WHERE mood LIKE '%忧伤%' 或 WHERE scene LIKE '%夜晚%'
CREATE INDEX idx_music_features_genre ON music_features(genre);
CREATE INDEX idx_music_features_mood ON music_features(mood);
CREATE INDEX idx_music_features_scene ON music_features(scene);
CREATE INDEX idx_music_features_song_id ON music_features(song_id);
```

**特征生成来源说明：**

| 特征 | 主要来源 | 生成方式 |
|------|----------|----------|
| `genre` | 歌曲名、艺术家、专辑、歌单category | LLM推断 |
| `mood` | 歌单名、评论内容 | LLM提取 |
| `tempo` | 歌曲名（"快节奏"等）、评论 | LLM推断 |
| `instruments` | 评论中提到的乐器、歌单名 | LLM提取 |
| `scene` | 歌单名（"深夜"、"工作"）、评论 | LLM提取+继承 |
| `language` | 歌曲名语言、艺术家 | 规则匹配+LLM |
| `era` | 歌曲名（"80年代"）、艺术家年代 | 规则匹配+LLM |
| `description` | 综合所有信息 | LLM生成 |
| `inherited_tags` | 所属歌单的playlist_name | 从歌单关联提取 |

---

### 3.2 新增表：推荐历史与反馈 (recommendation_history & recommendation_feedback)

#### 设计理念

用户的主动行为是推荐系统的灵魂。通过记录用户在获取推荐后的真实互动（播放、跳过、完成度等），系统能够持续学习用户偏好，迭代优化推荐算法。这些数据使得推荐从"一次性的静态匹配"演变为"持续优化的动态反馈系统"。

#### 3.2.1 推荐历史表 (recommendation_history)

记录用户每次主动查询的内容及返回结果。

```sql
CREATE TABLE recommendation_history (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(100),         -- 会话标识（可跨查询关联同一用户）
    user_id VARCHAR(100),            -- 用户标识（可选，若已登录）

    -- 用户输入的查询内容
    query_text TEXT NOT NULL,        -- 用户输入的原始查询文本
    query_type VARCHAR(50),          -- 查询类型：simple/complex/poem/voice
    query_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 查询时间

    -- 返回结果信息
    result_count INTEGER,            -- 返回结果数量
    result_song_ids BIGINT[],        -- 返回的歌曲ID列表（方便后续关联行为）
    latency_ms INTEGER,              -- 响应时间（毫秒）

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 索引设计
CREATE INDEX idx_history_session ON recommendation_history(session_id);
CREATE INDEX idx_history_user ON recommendation_history(user_id);
CREATE INDEX idx_history_query_time ON recommendation_history(query_timestamp);
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_id` | VARCHAR(100) | 匿名会话ID，用于关联同一用户的多次查询 |
| `user_id` | VARCHAR(100) | 登录用户ID（可选），登录后关联行为 |
| `query_text` | TEXT | 用户输入的原始查询，如"欢快的凯尔特音乐" |
| `query_type` | VARCHAR(50) | 查询类型：simple(简单场景)/complex(复杂描述)/poem(古诗词)/voice(语音) |
| `query_timestamp` | TIMESTAMP | 查询发生的时间 |
| `result_count` | INTEGER | 返回的结果数量 |
| `result_song_ids` | BIGINT[] | 返回的歌曲ID数组，便于后续关联播放行为 |
| `latency_ms` | INTEGER | 此次请求的响应时间 |

---

#### 3.2.2 推荐反馈表 (recommendation_feedback)

记录用户对推荐结果的后续行为，包括播放完成度、是否跳过等核心指标。

```sql
CREATE TABLE recommendation_feedback (
    id SERIAL PRIMARY KEY,
    history_id INTEGER REFERENCES recommendation_history(id) ON DELETE CASCADE,
    song_id BIGINT NOT NULL,         -- 被反馈的歌曲

    -- 播放行为追踪（核心字段）
    playback_duration_seconds INTEGER,           -- 实际播放时长（秒）
    song_duration_seconds INTEGER,               -- 歌曲总时长（秒）
    playback_completion_rate DECIMAL(5,2),        -- 播放完成度百分比（0-100），计算得出
    skipped BOOLEAN DEFAULT FALSE,                -- 是否点击了"下一首"跳过（TRUE=跳过）
    looped BOOLEAN DEFAULT FALSE,                 -- 是否点击了循环播放（TRUE=循环）

    -- 主动反馈（用户显式操作）
    feedback_type VARCHAR(20),                   -- 显式反馈：like/dislike/null
    feedback_detail VARCHAR(100),               -- 详细反馈：too_sad/too_happy/not_match等

    -- 行为元数据
    action_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 行为发生时间
    play_source VARCHAR(50),                     -- 播放来源：recommend/playlist/search/history

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- 约束：同一查询中的同一歌曲只记录一条行为
    UNIQUE(history_id, song_id)
);

-- 索引设计
CREATE INDEX idx_feedback_history ON recommendation_feedback(history_id);
CREATE INDEX idx_feedback_song ON recommendation_feedback(song_id);
CREATE INDEX idx_feedback_type ON recommendation_feedback(feedback_type);
CREATE INDEX idx_feedback_skipped ON recommendation_feedback(skipped);
CREATE INDEX idx_feedback_completion ON recommendation_feedback(playback_completion_rate);
```

**核心字段设计说明：**

| 字段 | 类型 | 说明 | 数据来源 |
|------|------|------|----------|
| `playback_duration_seconds` | INTEGER | 用户实际播放的秒数 | 前端播放器上报 |
| `song_duration_seconds` | INTEGER | 歌曲本身的时长 | 歌曲元数据 |
| `playback_completion_rate` | DECIMAL(5,2) | 播放完成度：`playback_duration / song_duration * 100` | 计算字段 |
| `skipped` | BOOLEAN | 用户是否主动点击"下一首"跳过 | 前端播放器上报 |
| `looped` | BOOLEAN | 用户是否点击循环播放 | 前端播放器上报 |

**行为信号分析：**

| 用户行为 | 信号强度 | 推荐算法意义 |
|----------|----------|--------------|
| 播放完成度 > 80% | ⭐⭐⭐⭐⭐ | 强烈正向信号，用户完整听完 |
| 播放完成度 50%-80% | ⭐⭐⭐⭐ | 正向信号，用户比较喜欢 |
| 播放完成度 30%-50% | ⭐⭐ | 弱信号，可能不太感兴趣 |
| 播放完成度 < 30% | ⭐ | 负向信号，用户很快跳过 |
| `skipped = TRUE` | ⭐ | 明确负向信号，主动跳过 |
| `looped = TRUE` | ⭐⭐⭐⭐⭐ | 强烈正向信号，循环播放 |

**播放完成度计算公式：**

```
playback_completion_rate = (playback_duration_seconds / song_duration_seconds) * 100
```

> **设计思考**：为什么用播放完成度而不是播放时长？
> - 歌曲时长差异很大（3分钟 vs 10分钟），单纯时长不具可比性
> - 完成度标准化了这一差异，更准确反映用户意愿
> - 结合 `skipped` 字段可以交叉验证：完成度50%左右且skipped=TRUE，说明用户主动跳过

**数据上报时机：**

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户行为上报流程                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. 用户点击推荐结果中的歌曲 → 开始播放                          │
│         │                                                        │
│         ▼                                                        │
│  2. 播放器定时上报播放进度（每30秒或歌曲切换时）                  │
│         │                                                        │
│         ▼                                                        │
│  3. 歌曲播放结束/用户跳过 → 上报最终行为数据                      │
│         │                                                        │
│         ▼                                                        │
│  4. 后端记录 feedback 表                                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**未来扩展方向（初版暂不实现）：**

- 用户收藏/加入歌单行为
- 用户分享行为
- 用户评论行为
- 同一会话内的多轮交互（类似对话式推荐）

---

### 3.3 数据库存储选型分析

#### 3.3.1 music_features 表存储选择：PostgreSQL vs 向量数据库

**核心问题**：music_features 表中的 `feature_vector` 向量字段应该存在哪里？

**方案对比：**

| 维度 | PostgreSQL + pgvector | 专用向量数据库（Milvus/Pinecone等） |
|------|------------------------|--------------------------------------|
| **架构复杂度** | ⭐⭐ 低（单数据库） | ⭐⭐⭐⭐ 高（需维护独立服务） |
| **成本** | ⭐⭐ 低（无需额外服务） | ⭐⭐⭐⭐ 高（云服务或自建集群） |
| **查询性能** | ⭐⭐⭐ 中等 | ⭐⭐⭐⭐⭐ 优秀（针对向量优化） |
| **扩展性** | ⭐⭐ 受限于PostgreSQL | ⭐⭐⭐⭐⭐ 按需扩展 |
| **运维成本** | ⭐⭐ 低 | ⭐⭐⭐⭐ 高 |
| **适用规模** | 百万级向量 | 千万级以上 |

**本项目建议：PostgreSQL + pgvector（可选）**

理由：
1. **初版规模预估**：假设曲库10万首歌曲，向量维度1536
   - 总存储：10万 × 1536 × 4字节 ≈ 600MB
   - PostgreSQL 完全可承载

2. **pgvector 能力**：
   - 支持向量相似度搜索（余弦相似度、欧氏距离）
   - 支持 HNSW 和 IVFFlat 索引
   - 可处理百万级向量，延迟 < 100ms

3. **运维简化**：与现有 PostgreSQL 统一管理，降低复杂度

4. **扩展路径**：如果未来曲库规模超过500万首，再考虑迁移到专用向量数据库

**pgvector 配置示例：**

```sql
-- 启用 pgvector 扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- 添加向量列（1536维，与 MiniMax embedding 维度对齐）
ALTER TABLE music_features ADD COLUMN feature_vector vector(1536);

-- 创建 HNSW 索引（适合追求查询速度的场景）
CREATE INDEX idx_music_features_vector_hnsw
ON music_features USING hnsw (feature_vector vector_cosine_ops);

-- 或创建 IVFFlat 索引（适合数据量大、内存受限的场景）
CREATE INDEX idx_music_features_vector_ivfflat
ON music_features USING ivfflat (feature_vector vector_cosine_ops);
```

**是否启用向量检索的判断流程：**

```
┌─────────────────────────────────────────────────────────────────┐
│                     向量检索启用判断                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  曲库规模 <= 100万首？                                          │
│         │                                                        │
│    是 ◄─┴─► 否                                                  │
│    │         │                                                   │
│    ▼         ▼                                                   │
│  PostgreSQL  考虑专用向量数据库                                  │
│  + pgvector                                                │
│                                                                  │
│  是否需要高精度召回？                                            │
│    是 ◄─┴─► 否                                                  │
│    │         │                                                   │
│    ▼         ▼                                                   │
│  pgvector   纯标签匹配足够                                       │
│  HNSW索引                                                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

#### 3.3.2 推荐历史与反馈存储选择：数据量大时的应对策略

**核心问题**：用户行为数据量持续增长，单表存储会成为瓶颈吗？

**数据量预估：**

| 指标 | 估算值 |
|------|--------|
| 日活用户 | 10,000 |
| 每用户日均推荐查询 | 5 次 |
| 每查询平均返回 | 15 首 |
| 每首播放行为记录 | 1 条 |

| 时间维度 | 预估数据量 |
|----------|------------|
| 每日新增 | 10,000 × 5 = 50,000 条 history |
| 每日反馈 | 50,000 × 15 = 750,000 条 feedback |
| 每月 | 约 2,250 万条 feedback |
| 每年 | 约 2.7 亿条 feedback |

**存储需求：**
- feedback 表每条约 200 字节（包含多个字段）
- 每年约 50GB 数据

**方案对比：**

| 方案 | 描述 | 优点 | 缺点 | 适用场景 |
|------|------|------|------|----------|
| **方案A：MongoDB** | 行为数据存 MongoDB | 扩展性强，Schema灵活 | 需要维护独立服务 | 大规模、灵活查询 |
| **方案B：时序数据库** | 使用 TimescaleDB/InfluxDB | 内置时序优化、压缩 | 需额外学习 | 纯时序数据 |
| **方案C：PostgreSQL 分区表** | 按时间分区 | 统一数据库，查询方便 | 分区管理复杂 | 中等规模（<1亿） |
| **方案D：冷热分离** | 热数据PostgreSQL，冷数据归档 | 平衡性能和成本 | 实现复杂 | 大规模数据 |

**本项目建议：方案C - PostgreSQL 分区表（初版）→ 方案A MongoDB（扩展）**

**理由：**

1. **初版规模（<100万用户）**：
   - PostgreSQL 分区表完全可应对
   - 按月分区，每年新增约 50GB
   - 配合索引，查询性能可接受

2. **PostgreSQL 分区表设计：**

```sql
-- 创建分区表（按月分区）
CREATE TABLE recommendation_feedback (
    id SERIAL,
    history_id INTEGER,
    song_id BIGINT,
    playback_duration_seconds INTEGER,
    song_duration_seconds INTEGER,
    playback_completion_rate DECIMAL(5,2),
    skipped BOOLEAN DEFAULT FALSE,
    looped BOOLEAN DEFAULT FALSE,
    feedback_type VARCHAR(20),
    feedback_detail VARCHAR(100),
    action_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    play_source VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id, action_timestamp)
) PARTITION BY RANGE (action_timestamp);

-- 创建月度分区
CREATE TABLE recommendation_feedback_2025_01 PARTITION OF recommendation_feedback
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
CREATE TABLE recommendation_feedback_2025_02 PARTITION OF recommendation_feedback
    FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');
-- ... 以此类推

-- 自动创建未来分区的函数
CREATE OR REPLACE FUNCTION create_monthly_partition()
RETURNS void AS $$
DECLARE
    next_month DATE;
    partition_name TEXT;
BEGIN
    next_month := date_trunc('month', CURRENT_DATE + INTERVAL '1 month');
    partition_name := 'recommendation_feedback_' || to_char(next_month, 'YYYY_MM');
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF recommendation_feedback
         FOR VALUES FROM (%L) TO (%L)',
        partition_name,
        next_month,
        next_month + INTERVAL '1 month'
    );
END;
$$ LANGUAGE plpgsql;
```

3. **历史数据归档策略：**

```
┌─────────────────────────────────────────────────────────────────┐
│                      数据生命周期管理                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   热数据（< 3个月）    │   温数据（3-12个月）   │   冷数据（> 1年） │
│   ─────────────────   │   ─────────────────   │   ─────────────  │
│   PostgreSQL 主表     │   PostgreSQL 分区     │   归档到对象存储   │
│   全量索引，高可用     │   减少索引，定期压缩    │   (S3/OSS)       │
│                                                                  │
│   用于实时推荐         │   用于分析统计         │   用于模型训练    │
│   快速查询            │   趋势分析             │   历史样本        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

4. **扩展路径**：当数据量超过 1 亿条或查询延迟明显上升时，再迁移到 MongoDB

**MongoDB 迁移方案（预留）：**

```javascript
// MongoDB 集合设计
db.recommendation_feedback.createIndex({ "history_id": 1, "song_id": 1 }, { unique: true });
db.recommendation_feedback.createIndex({ "action_timestamp": 1 });
db.recommendation_feedback.createIndex({ "song_id": 1, "playback_completion_rate": 1 });

// 分片策略：按 user_id 或 time 进行分片
sh.shardCollection("music_recommend.recommendation_feedback", { "user_id": "hashed" });
```

**总结：存储选型建议**

| 数据表 | 初版存储 | 扩展存储 | 说明 |
|--------|----------|----------|------|
| `music_features` | PostgreSQL | PostgreSQL + pgvector | 10万首规模 PostgreSQL 足够 |
| `recommendation_history` | PostgreSQL | PostgreSQL 分区表 | 按时间分区 |
| `recommendation_feedback` | PostgreSQL 分区表 | MongoDB | 按月分区，年度归档 |

---

## 4. 后端API设计

### 4.1 新增端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/recommend` | 文本推荐接口 |
| POST | `/api/recommend/feedback` | 提交推荐反馈 |
| GET | `/api/recommend/history` | 获取推荐历史 |
| POST | `/api/recommend/batch` | 批量推荐接口 |
| GET | `/api/songs/<song_id>/features` | 获取歌曲特征 |
| POST | `/api/features/generate` | 批量生成歌曲特征（管理员） |
| GET | `/api/health` | 健康检查（含LLM可用性） |

### 4.2 推荐接口详情

**POST /api/recommend**

Request:
```json
{
    "query": "欢快的凯尔特音乐",
    "session_id": "user_123_session_abc",  // 可选，用于关联反馈
    "max_results": 20,                       // 可选，默认20
    "include_reason": true                  // 可选，是否返回推荐理由
}
```

Response:
```json
{
    "success": true,
    "query": "欢快的凯尔特音乐",
    "query_type": "simple",
    "results": [
        {
            "song_id": 1893728473,
            "song_name": "Ye Netherlands, Where I Have a Love",
            "artist": "Johan Wagenaar",
            "album": "Orchestral Works",
            "music_file": "/ssd11/music/song_download/1893728473.mp3",
            "match_score": 0.92,
            "match_reason": "这首曲子具有欢快明亮的凯尔特风格，适合作为背景音乐或庆祝场景",
            "tags": ["凯尔特", "欢快", "古典", "管弦乐"]
        }
    ],
    "total": 15,
    "latency_ms": 1234
}
```

**POST /api/recommend/feedback**

Request:
```json
{
    "history_id": 123,
    "song_id": 1893728473,
    "feedback_type": "like",
    "feedback_detail": null
}
```

---

## 5. 前端集成设计

### 5.1 新增页面/组件

| 组件 | 路径 | 说明 |
|------|------|------|
| 推荐页面 | `/pages/recommend/recommend.vue` | 文本输入和结果展示 |
| 推荐结果卡片 | `/components/RecommendCard.vue` | 单个推荐结果展示+反馈按钮 |
| 首页入口 | `/pages/index/index.vue` | 添加"AI推荐"入口按钮 |

### 5.2 语音输入设计

参考微信聊天输入框的设计，支持文字/语音切换：

```
┌─────────────────────────────────────────────────────────────┐
│  ┌─────────────────────────────────────────────────────┐    │
│  │  请描述你想要的音乐...（如：欢快的凯尔特音乐）      │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│      🎤 语音                                    🔊 文字模式 │
└─────────────────────────────────────────────────────────────┘
```

**交互说明：**
- 点击 🎤 按钮 → 切换到语音输入模式，按住说话
- 语音识别完成后自动转换为文字，可编辑后发送
- 点击 🔊 按钮 → 切换回文字输入模式
- 支持类似微信的按住说话、上滑取消等交互

---

## 6. 实现步骤（详细）

### 6.1 阶段一：环境准备与基础设施（预计工作量：1-2天）

#### 6.1.1 后端环境检查

**目标**：确认后端项目结构和依赖

**执行步骤**：

1. **检查现有项目结构**
   ```bash
   cd /path/to/music-project/backend
   ls -la
   # 确认存在: app.py, requirements.txt, .env 等文件
   ```

2. **检查 Python 版本和依赖**
   ```bash
   python3 --version  # 需 >= 3.9
   pip3 list | grep -E "Flask|psycopg2|pymongo"
   ```

3. **安装必要依赖**
   ```bash
   pip3 install flask psycopg2-binary pymongo redis minimax-api python-dotenv
   ```

4. **配置 .env 文件**（参考 8.配置文件更新）

#### 6.1.2 MiniMax API 账号准备

**目标**：获取 MiniMax API Key 并测试连通性

**执行步骤**：

1. 联系项目负责人获取 MiniMax API Key
2. 测试 API 连通性：
   ```python
   from minimax import MiniMax

   client = MiniMax(api_key="your_key")
   # 测试 chat API
   response = client.chat.completions.create(
       model="abab6.5s-chat",
       messages=[{"role": "user", "content": "你好"}]
   )
   print(response.choices[0].message.content)
   ```

3. 确认 embedding API 可用：
   ```python
   # 测试 embedding
   embedding = client.embeddings.create(
       model="embo-01",
       input="测试文本"
   )
   print(len(embedding.data[0].embedding))
   ```

#### 6.1.3 前端环境检查

**目标**：确认 UniApp 项目可运行

**执行步骤**：

1. **检查 Node.js 环境**
   ```bash
   node --version  # 需 >= 16
   npm --version
   ```

2. **检查 UniApp CLI**
   ```bash
   npx vue --version
   # 或
   npm install -g @vue/cli
   ```

3. **安装项目依赖**
   ```bash
   cd /path/to/music-project-uniapp
   npm install
   ```

---

### 6.2 阶段二：数据库设计与创建（预计工作量：1-2天）

#### 6.2.1 创建 PostgreSQL 数据库表

**目标**：在 PostgreSQL 中创建 music_features 和 recommendation_history 表

**执行步骤**：

1. **连接到 PostgreSQL**
   ```bash
   psql -h localhost -U postgres -d music_db
   # 或使用管理工具（如 pgAdmin、DBeaver）
   ```

2. **创建 music_features 表**
   ```sql
   CREATE TABLE music_features (
       id SERIAL PRIMARY KEY,
       song_id BIGINT UNIQUE NOT NULL REFERENCES songs(song_id),

       -- 基础特征
       genre VARCHAR(100),
       mood VARCHAR(200),
       tempo VARCHAR(50),
       instruments VARCHAR(200),
       scene VARCHAR(200),
       language VARCHAR(50),
       era VARCHAR(50),

       -- 复杂特征
       description TEXT,
       emotional_tags VARCHAR(500),
       theme_keywords VARCHAR(500),

       -- 扩展信息
       inherited_tags VARCHAR(500),

       -- 向量表示（可选，初版先不启用）
       -- feature_vector vector(1536),

       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   );

   -- 创建索引
   CREATE INDEX idx_music_features_genre ON music_features(genre);
   CREATE INDEX idx_music_features_mood ON music_features(mood);
   CREATE INDEX idx_music_features_scene ON music_features(scene);
   CREATE INDEX idx_music_features_song_id ON music_features(song_id);
   ```

3. **创建 recommendation_history 表**
   ```sql
   CREATE TABLE recommendation_history (
       id SERIAL PRIMARY KEY,
       session_id VARCHAR(100),
       user_id VARCHAR(100),

       query_text TEXT NOT NULL,
       query_type VARCHAR(50),
       query_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

       result_count INTEGER,
       result_song_ids BIGINT[],
       latency_ms INTEGER,

       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   );

   -- 创建索引
   CREATE INDEX idx_history_session ON recommendation_history(session_id);
   CREATE INDEX idx_history_user ON recommendation_history(user_id);
   CREATE INDEX idx_history_query_time ON recommendation_history(query_timestamp);
   ```

4. **创建 recommendation_feedback 分区表**（初版先用普通表）
   ```sql
   CREATE TABLE recommendation_feedback (
       id SERIAL PRIMARY KEY,
       history_id INTEGER REFERENCES recommendation_history(id) ON DELETE CASCADE,
       song_id BIGINT NOT NULL,

       playback_duration_seconds INTEGER,
       song_duration_seconds INTEGER,
       playback_completion_rate DECIMAL(5,2),
       skipped BOOLEAN DEFAULT FALSE,
       looped BOOLEAN DEFAULT FALSE,

       feedback_type VARCHAR(20),
       feedback_detail VARCHAR(100),
       action_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       play_source VARCHAR(50),

       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       UNIQUE(history_id, song_id)
   );

   -- 创建索引
   CREATE INDEX idx_feedback_history ON recommendation_feedback(history_id);
   CREATE INDEX idx_feedback_song ON recommendation_feedback(song_id);
   CREATE INDEX idx_feedback_type ON recommendation_feedback(feedback_type);
   CREATE INDEX idx_feedback_skipped ON recommendation_feedback(skipped);
   CREATE INDEX idx_feedback_completion ON recommendation_feedback(playback_completion_rate);
   ```

5. **验证表创建成功**
   ```sql
   \dt music_features recommendation_history recommendation_feedback
   ```

#### 6.2.2 创建 MongoDB 索引（如使用 MongoDB 存储评论）

**目标**：确保评论集合有适当索引

```javascript
// 在 MongoDB shell 中执行
use music_comments

db.comments.createIndex({ "song_id": 1 })
db.comments.createIndex({ "sentiment": 1, "polarity": 1 })
```

---

### 6.3 阶段三：后端核心功能开发（预计工作量：4-6天）

#### 6.3.1 MiniMax API 封装模块

**目标**：创建 `backend/services/llm_service.py`，封装 LLM 调用

**文件结构**：
```
backend/
├── services/
│   ├── __init__.py
│   ├── llm_service.py      # MiniMax API 封装
│   ├── feature_service.py   # 歌曲特征服务
│   └── recommend_service.py # 推荐服务
├── routes/
│   ├── __init__.py
│   └── recommend.py         # 推荐 API 路由
└── models/
    ├── __init__.py
    └── database.py           # 数据库连接
```

**llm_service.py 实现要点**：
```python
# backend/services/llm_service.py

import os
from minimax import MiniMax
from typing import List, Dict, Optional

class LLMService:
    def __init__(self):
        self.client = MiniMax(
            api_key=os.getenv("MINIMAX_API_KEY"),
            base_url="https://api.minimax.chat"
        )
        self.model = os.getenv("MINIMAX_MODEL", "abab6.5s-chat")
        self.embedding_model = os.getenv("MINIMAX_EMBEDDING_MODEL", "embo-01")

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7) -> str:
        """发送对话请求"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature
        )
        return response.choices[0].message.content

    def extract_features_prompt(self, song_info: Dict) -> str:
        """构建特征提取 Prompt"""
        return f"""请分析以下歌曲信息，提取特征标签。

歌曲名称：{song_info['song_name']}
艺术家：{song_info['artist']}
专辑：{song_info.get('album', '未知')}
歌单标签：{song_info.get('playlist_names', '无')}
用户评论摘要：{song_info.get('comment_summary', '无')}

请提取以下信息（JSON格式）：
- genre: 流派/风格
- mood: 情绪标签（最多5个，用逗号分隔）
- tempo: 节拍（快/中/慢）
- instruments: 主要乐器（最多3个，用逗号分隔）
- scene: 适用场景（最多5个，用逗号分隔）
- language: 语言
- era: 年代
- description: 100字左右的歌曲描述
"""

    def generate_embedding(self, text: str) -> List[float]:
        """生成文本 embedding"""
        response = self.client.embeddings.create(
            model=self.embedding_model,
            input=text
        )
        return response.data[0].embedding

    def match_songs_prompt(self, query: str, songs_context: str) -> str:
        """构建歌曲匹配 Prompt"""
        return f"""用户查询："{query}"

候选歌曲信息：
{songs_context}

请从候选歌曲中选择最匹配用户查询的歌曲，返回 JSON 格式：
{{
  "matched_songs": [
    {{
      "song_id": 123,
      "match_score": 0.95,
      "match_reason": "匹配原因说明"
    }}
  ]
}}

注意：只返回匹配度 >= 0.6 的歌曲，最多返回20首。
"""
```

#### 6.3.2 歌曲特征批量生成服务

**目标**：创建 `backend/services/feature_service.py`，批量生成歌曲特征

**feature_service.py 实现要点**：
```python
# backend/services/feature_service.py

from typing import List, Dict
import psycopg2
from .llm_service import LLMService
import json

class FeatureService:
    def __init__(self, db_connection):
        self.db = db_connection
        self.llm = LLMService()

    def get_songs_without_features(self, limit: int = 100) -> List[Dict]:
        """获取尚未生成特征的歌曲"""
        query = """
            SELECT s.song_id, s.song_name, s.artist, s.album,
                   ARRAY_AGG(DISTINCT p.playlist_name) as playlist_names
            FROM songs s
            LEFT JOIN music_features mf ON s.song_id = mf.song_id
            LEFT JOIN song_playlist sp ON s.song_id = sp.song_id
            LEFT JOIN playlists p ON sp.playlist_id = p.playlist_id
            WHERE mf.id IS NULL
            GROUP BY s.song_id, s.song_name, s.artist, s.album
            LIMIT %s
        """
        # 执行查询...

    def generate_feature_for_song(self, song_info: Dict) -> Dict:
        """为单首歌曲生成特征"""
        prompt = self.llm.extract_features_prompt(song_info)
        response = self.llm.chat([{"role": "user", "content": prompt}])

        # 解析 LLM 返回的 JSON
        features = json.loads(response)
        features['song_id'] = song_info['song_id']
        return features

    def batch_generate_features(self, batch_size: int = 50):
        """批量生成特征（供定时任务调用）"""
        songs = self.get_songs_without_features(limit=batch_size)
        for song in songs:
            features = self.generate_feature_for_song(song)
            self.save_feature(features)
            print(f"Generated features for song_id: {song['song_id']}")

    def save_feature(self, features: Dict):
        """保存特征到数据库"""
        query = """
            INSERT INTO music_features (
                song_id, genre, mood, tempo, instruments,
                scene, language, era, description,
                emotional_tags, theme_keywords, inherited_tags
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        # 执行插入...

    def search_by_tags(self, tags: List[str], limit: int = 20) -> List[Dict]:
        """基于标签搜索歌曲"""
        # 使用 PostgreSQL 的 LIKE 或数组包含查询
        # ...
```

#### 6.3.3 推荐服务核心逻辑

**目标**：创建 `backend/services/recommend_service.py`，实现推荐算法

**recommend_service.py 实现要点**：
```python
# backend/services/recommend_service.py

from typing import List, Dict, Optional
import time
from .llm_service import LLMService
from .feature_service import FeatureService

class RecommendService:
    def __init__(self, db_connection):
        self.db = db_connection
        self.llm = LLMService()
        self.feature_service = FeatureService(db_connection)

    def recommend(self, query: str, session_id: str = None,
                  max_results: int = 20, user_id: str = None) -> Dict:
        """核心推荐方法"""

        start_time = time.time()

        # 1. 识别查询类型
        query_type = self.classify_query(query)

        # 2. 获取候选歌曲（从 music_features 表）
        candidates = self.get_candidates(query_type)

        # 3. 构建上下文，让 LLM 匹配
        songs_context = self.build_songs_context(candidates)

        # 4. 调用 LLM 进行语义匹配
        match_result = self.llm_match(query, songs_context)

        # 5. 记录推荐历史
        history_id = self.save_history(
            session_id=session_id,
            user_id=user_id,
            query_text=query,
            query_type=query_type,
            result_song_ids=[r['song_id'] for r in match_result],
            latency_ms=int((time.time() - start_time) * 1000)
        )

        # 6. 构建返回结果
        return self.build_response(
            query=query,
            query_type=query_type,
            matches=match_result,
            history_id=history_id,
            latency_ms=int((time.time() - start_time) * 1000)
        )

    def classify_query(self, query: str) -> str:
        """识别查询类型"""
        # 简单场景描述 -> simple
        # 复杂情感描述 -> complex
        # 古诗词 -> poem
        # 语音输入 -> voice
        if len(query) < 20 and any(kw in query for kw in ['音乐', '歌曲']):
            return 'simple'
        elif any(char in query for char in ['，', '。', '、', '兮', '吾']):
            return 'poem'
        return 'complex'

    def get_candidates(self, query_type: str, limit: int = 500) -> List[Dict]:
        """获取候选歌曲"""
        # 从 music_features 表获取候选
        query = """
            SELECT mf.*, s.song_name, s.artist, s.album, s.music_file
            FROM music_features mf
            JOIN songs s ON mf.song_id = s.song_id
            ORDER BY RANDOM()
            LIMIT %s
        """
        # 执行查询并返回...

    def build_songs_context(self, candidates: List[Dict]) -> str:
        """构建发送给 LLM 的歌曲上下文"""
        context_lines = []
        for song in candidates[:100]:  # 限制数量，避免 token 过多
            line = f"song_id: {song['song_id']}, " \
                   f"名称: {song['song_name']}, " \
                   f"艺术家: {song['artist']}, " \
                   f"风格: {song.get('genre', '未知')}, " \
                   f"情绪: {song.get('mood', '未知')}, " \
                   f"场景: {song.get('scene', '未知')}"
            context_lines.append(line)
        return "\n".join(context_lines)

    def llm_match(self, query: str, songs_context: str) -> List[Dict]:
        """LLM 语义匹配"""
        prompt = self.llm.match_songs_prompt(query, songs_context)
        response = self.llm.chat([{"role": "user", "content": prompt}])

        # 解析返回的 JSON
        result = json.loads(response)
        return result.get('matched_songs', [])

    def build_response(self, query: str, query_type: str,
                      matches: List[Dict], history_id: int,
                      latency_ms: int) -> Dict:
        """构建 API 响应"""
        # 填充完整的歌曲信息...
        results = []
        for match in matches:
            song = self.get_song_detail(match['song_id'])
            results.append({
                "song_id": song['song_id'],
                "song_name": song['song_name'],
                "artist": song['artist'],
                "album": song['album'],
                "music_file": song['music_file'],
                "match_score": match['match_score'],
                "match_reason": match.get('match_reason', ''),
                "tags": [song.get('genre', ''), song.get('mood', '')]
            })

        return {
            "success": True,
            "query": query,
            "query_type": query_type,
            "results": results,
            "total": len(results),
            "history_id": history_id,
            "latency_ms": latency_ms
        }
```

#### 6.3.4 API 路由开发

**目标**：创建 `backend/routes/recommend.py`，暴露 REST API

**recommend.py 实现要点**：
```python
# backend/routes/recommend.py

from flask import Blueprint, request, jsonify
from services.recommend_service import RecommendService
from services.feature_service import FeatureService
from models.database import get_db_connection
import psycopg2

recommend_bp = Blueprint('recommend', __name__, url_prefix='/api')

def get_recommend_service():
    db = get_db_connection()
    return RecommendService(db)

@recommend_bp.route('/recommend', methods=['POST'])
def recommend():
    """POST /api/recommend - 文本推荐接口"""
    data = request.get_json()

    query = data.get('query', '').strip()
    if not query:
        return jsonify({"success": False, "error": "查询文本不能为空"}), 400

    session_id = data.get('session_id')
    max_results = data.get('max_results', 20)
    user_id = data.get('user_id')

    service = get_recommend_service()
    result = service.recommend(
        query=query,
        session_id=session_id,
        max_results=max_results,
        user_id=user_id
    )

    return jsonify(result)

@recommend_bp.route('/recommend/feedback', methods=['POST'])
def submit_feedback():
    """POST /api/recommend/feedback - 提交推荐反馈"""
    data = request.get_json()

    required_fields = ['history_id', 'song_id']
    for field in required_fields:
        if field not in data:
            return jsonify({"success": False, "error": f"缺少必填字段: {field}"}), 400

    db = get_db_connection()
    cursor = db.cursor()

    query = """
        INSERT INTO recommendation_feedback (
            history_id, song_id, playback_duration_seconds,
            song_duration_seconds, playback_completion_rate,
            skipped, looped, feedback_type, feedback_detail, play_source
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (history_id, song_id) DO UPDATE SET
            playback_duration_seconds = EXCLUDED.playback_duration_seconds,
            song_duration_seconds = EXCLUDED.song_duration_seconds,
            playback_completion_rate = EXCLUDED.playback_completion_rate,
            skipped = EXCLUDED.skipped,
            looped = EXCLUDED.looped,
            feedback_type = COALESCE(EXCLUDED.feedback_type, recommendation_feedback.feedback_type),
            action_timestamp = CURRENT_TIMESTAMP
    """

    cursor.execute(query, (
        data['history_id'],
        data['song_id'],
        data.get('playback_duration_seconds'),
        data.get('song_duration_seconds'),
        data.get('playback_completion_rate'),
        data.get('skipped', False),
        data.get('looped', False),
        data.get('feedback_type'),
        data.get('feedback_detail'),
        data.get('play_source', 'recommend')
    ))

    db.commit()
    return jsonify({"success": True})

@recommend_bp.route('/recommend/history', methods=['GET'])
def get_history():
    """GET /api/recommend/history - 获取推荐历史"""
    session_id = request.args.get('session_id')
    user_id = request.args.get('user_id')
    limit = request.args.get('limit', 20, type=int)

    if not session_id and not user_id:
        return jsonify({"success": False, "error": "需要 session_id 或 user_id"}), 400

    db = get_db_connection()
    cursor = db.cursor()

    query = """
        SELECT id, query_text, query_type, query_timestamp,
               result_count, latency_ms
        FROM recommendation_history
        WHERE (%s IS NOT NULL AND session_id = %s)
           OR (%s IS NOT NULL AND user_id = %s)
        ORDER BY query_timestamp DESC
        LIMIT %s
    """

    cursor.execute(query, (session_id, session_id, user_id, user_id, limit))
    rows = cursor.fetchall()

    history = [{
        "id": row[0],
        "query_text": row[1],
        "query_type": row[2],
        "query_timestamp": row[3].isoformat(),
        "result_count": row[4],
        "latency_ms": row[5]
    } for row in rows]

    return jsonify({"success": True, "history": history})

@recommend_bp.route('/songs/<int:song_id>/features', methods=['GET'])
def get_song_features(song_id):
    """GET /api/songs/<song_id>/features - 获取歌曲特征"""
    db = get_db_connection()
    cursor = db.cursor()

    query = """
        SELECT song_id, genre, mood, tempo, instruments,
               scene, language, era, description,
               emotional_tags, theme_keywords, inherited_tags
        FROM music_features
        WHERE song_id = %s
    """

    cursor.execute(query, (song_id,))
    row = cursor.fetchone()

    if not row:
        return jsonify({"success": False, "error": "歌曲特征不存在"}), 404

    features = {
        "song_id": row[0],
        "genre": row[1],
        "mood": row[2],
        "tempo": row[3],
        "instruments": row[4],
        "scene": row[5],
        "language": row[6],
        "era": row[7],
        "description": row[8],
        "emotional_tags": row[9],
        "theme_keywords": row[10],
        "inherited_tags": row[11]
    }

    return jsonify({"success": True, "features": features})

@recommend_bp.route('/features/generate', methods=['POST'])
def generate_features():
    """POST /api/features/generate - 批量生成歌曲特征（管理员）"""
    data = request.get_json()
    batch_size = data.get('batch_size', 50)

    service = FeatureService(get_db_connection())
    service.batch_generate_features(batch_size=batch_size)

    return jsonify({"success": True, "message": f"已提交生成任务，批次大小: {batch_size}"})
```

#### 6.3.5 数据库连接模块

**目标**：创建 `backend/models/database.py`，统一管理数据库连接

```python
# backend/models/database.py

import psycopg2
from contextlib import contextmanager
import os

def get_db_connection():
    """获取 PostgreSQL 连接"""
    return psycopg2.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=os.getenv('POSTGRES_PORT', 5432),
        database=os.getenv('POSTGRES_DB', 'music_db'),
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '')
    )

@contextmanager
def get_db_cursor():
    """上下文管理器，自动管理数据库连接"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()
```

---

### 6.4 阶段四：后端 API 集成与注册（预计工作量：0.5天）

#### 6.4.1 注册 Blueprint 到 Flask App

**目标**：在 `app.py` 中注册推荐 API

```python
# backend/app.py (示例修改)

from routes.recommend import recommend_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object('config')

    # 注册推荐 API Blueprint
    app.register_blueprint(recommend_bp)

    # ... 其他现有代码

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
```

#### 6.4.2 验证 API 可用性

```bash
# 启动后端服务
cd backend
python app.py

# 测试推荐接口
curl -X POST http://localhost:5000/api/recommend \
  -H "Content-Type: application/json" \
  -d '{"query": "欢快的凯尔特音乐", "session_id": "test_001"}'

# 测试健康检查
curl http://localhost:5000/api/health
```

---

### 6.5 阶段五：前端开发（预计工作量：3-4天）

#### 6.5.1 创建推荐页面

**目标**：创建 `/pages/recommend/recommend.vue`

**文件结构**：
```
music-project-uniapp/
├── pages/
│   ├── recommend/
│   │   └── recommend.vue    # 推荐页面
│   └── index/
│       └── index.vue        # 修改首页，添加入口
├── components/
│   └── RecommendCard.vue     # 推荐结果卡片
└── api/
    └── recommend.js          # API 调用封装
```

#### 6.5.2 API 封装

**api/recommend.js**：
```javascript
// api/recommend.js

const API_BASE = 'http://localhost:5000/api'

export const recommendApi = {
  /**
   * 文本推荐
   * @param {string} query - 推荐查询文本
   * @param {string} sessionId - 会话ID
   * @param {number} maxResults - 最大返回数量
   */
  recommend(query, sessionId, maxResults = 20) {
    return uni.request({
      url: `${API_BASE}/recommend`,
      method: 'POST',
      data: {
        query,
        session_id: sessionId,
        max_results: maxResults
      }
    })
  },

  /**
   * 提交推荐反馈
   * @param {Object} feedback - 反馈数据
   */
  submitFeedback(feedback) {
    return uni.request({
      url: `${API_BASE}/recommend/feedback`,
      method: 'POST',
      data: feedback
    })
  },

  /**
   * 获取推荐历史
   * @param {string} sessionId - 会话ID
   */
  getHistory(sessionId) {
    return uni.request({
      url: `${API_BASE}/recommend/history`,
      method: 'GET',
      data: { session_id: sessionId }
    })
  }
}
```

#### 6.5.3 推荐页面实现

**pages/recommend/recommend.vue** 核心逻辑：

```vue
<template>
  <view class="recommend-page">
    <!-- 搜索输入区 -->
    <view class="search-section">
      <textarea
        class="search-input"
        v-model="queryText"
        placeholder="请描述你想要的音乐...（如：欢快的凯尔特音乐）"
        :disabled="loading"
      />
      <view class="search-actions">
        <button
          class="voice-btn"
          @click="toggleVoiceInput"
          :class="{ active: voiceInputActive }"
        >
          🎤 语音
        </button>
        <button
          class="search-btn"
          @click="handleSearch"
          :disabled="!queryText.trim() || loading"
        >
          {{ loading ? '搜索中...' : '搜索' }}
        </button>
      </view>
    </view>

    <!-- 推荐结果列表 -->
    <view class="results-section" v-if="results.length > 0">
      <view class="result-item" v-for="item in results" :key="item.song_id">
        <RecommendCard
          :song="item"
          :history-id="historyId"
          @play="handlePlay"
          @feedback="handleFeedback"
        />
      </view>
    </view>

    <!-- 空状态 -->
    <view class="empty-state" v-else-if="!loading && searched">
      <text>未找到匹配的音乐，请尝试其他描述</text>
    </view>
  </view>
</template>

<script>
import { recommendApi } from '@/api/recommend'

export default {
  data() {
    return {
      queryText: '',
      sessionId: '',
      historyId: null,
      loading: false,
      searched: false,
      results: [],
      voiceInputActive: false
    }
  },

  onLoad() {
    // 生成或获取 sessionId
    this.sessionId = uni.getStorageSync('recommend_session_id')
    if (!this.sessionId) {
      this.sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9)
      uni.setStorageSync('recommend_session_id', this.sessionId)
    }
  },

  methods: {
    async handleSearch() {
      if (!this.queryText.trim()) return

      this.loading = true
      this.searched = true

      try {
        const response = await recommendApi.recommend(
          this.queryText,
          this.sessionId,
          20
        )

        if (response.data.success) {
          this.results = response.data.results
          this.historyId = response.data.history_id
        } else {
          uni.showToast({
            title: response.data.error || '推荐失败',
            icon: 'none'
          })
        }
      } catch (error) {
        uni.showToast({
          title: '网络错误，请稍后重试',
          icon: 'none'
        })
      } finally {
        this.loading = false
      }
    },

    handlePlay(song) {
      // 调用播放器播放
      uni.navigateTo({
        url: `/pages/player/player?song_id=${song.song_id}`
      })
    },

    async handleFeedback({ song, feedbackType }) {
      // 上报反馈
      await recommendApi.submitFeedback({
        history_id: this.historyId,
        song_id: song.song_id,
        feedback_type: feedbackType,
        play_source: 'recommend'
      })
    },

    toggleVoiceInput() {
      // TODO: 实现语音输入
      this.voiceInputActive = !this.voiceInputActive
    }
  }
}
</script>
```

#### 6.5.4 推荐卡片组件

**components/RecommendCard.vue**：

```vue
<template>
  <view class="recommend-card">
    <view class="song-info" @click="$emit('play', song)">
      <image class="album-art" src="/static/default-album.png" mode="aspectFill" />
      <view class="song-detail">
        <text class="song-name">{{ song.song_name }}</text>
        <text class="artist">{{ song.artist }}</text>
        <view class="tags">
          <text class="tag" v-for="tag in validTags" :key="tag">{{ tag }}</text>
        </view>
        <text class="match-reason" v-if="song.match_reason">{{ song.match_reason }}</text>
      </view>
    </view>
    <view class="actions">
      <button class="action-btn like" @click="onLike">👍 喜欢</button>
      <button class="action-btn skip" @click="onSkip">跳过</button>
    </view>
  </view>
</template>

<script>
export default {
  props: {
    song: {
      type: Object,
      required: true
    },
    historyId: {
      type: Number,
      required: true
    }
  },

  computed: {
    validTags() {
      return (this.song.tags || []).filter(tag => tag && tag !== '未知')
    }
  },

  methods: {
    onLike() {
      this.$emit('feedback', { song: this.song, feedbackType: 'like' })
      uni.showToast({ title: '已记录喜欢', icon: 'success' })
    },

    onSkip() {
      this.$emit('feedback', { song: this.song, feedbackType: 'dislike' })
    }
  }
}
</script>
```

#### 6.5.5 首页添加 AI 推荐入口

**pages/index/index.vue** 修改：

```vue
<template>
  <!-- 在现有首页基础上添加 AI 推荐入口 -->
  <view class="index-page">
    <!-- 现有内容... -->

    <!-- AI 推荐入口 -->
    <view class="ai-recommend-entry" @click="goToRecommend">
      <image class="entry-icon" src="/static/ai-icon.png" />
      <view class="entry-info">
        <text class="entry-title">AI 智能推荐</text>
        <text class="entry-desc">用文字描述你想要音乐</text>
      </view>
      <text class="entry-arrow">›</text>
    </view>

    <!-- 现有其他内容... -->
  </view>
</template>

<script>
export default {
  methods: {
    goToRecommend() {
      uni.navigateTo({
        url: '/pages/recommend/recommend'
      })
    }
  }
}
</script>
```

#### 6.5.6 前端播放器行为上报

**播放器组件修改**（播放反馈上报）：

```javascript
// 在播放器组件中，歌曲播放完成或被跳过时上报

methods: {
  onSongEnd() {
    this.reportPlaybackFeedback({
      playback_duration_seconds: this.currentDuration,
      song_duration_seconds: this.totalDuration,
      playback_completion_rate: (this.currentDuration / this.totalDuration) * 100,
      skipped: false,
      looped: false
    })
    this.playNext()
  },

  onSkip() {
    this.reportPlaybackFeedback({
      playback_duration_seconds: this.currentDuration,
      song_duration_seconds: this.totalDuration,
      playback_completion_rate: (this.currentDuration / this.totalDuration) * 100,
      skipped: true,
      looped: false
    })
    this.playNext()
  },

  reportPlaybackFeedback(playbackData) {
    if (!this.historyId) return  // 只有推荐来源才上报

    recommendApi.submitFeedback({
      history_id: this.historyId,
      song_id: this.currentSong.song_id,
      ...playbackData,
      play_source: 'recommend'
    })
  }
}
```

---

### 6.6 阶段六：测试与部署（预计工作量：2-3天）

#### 6.6.1 单元测试

**后端测试** (`backend/tests/test_recommend.py`)：

```python
import pytest
from app import create_app

@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_recommend_endpoint(client):
    """测试推荐接口"""
    response = client.post('/api/recommend', json={
        'query': '欢快的凯尔特音乐',
        'session_id': 'test_001'
    })
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] == True
    assert 'results' in data

def test_feedback_endpoint(client):
    """测试反馈接口"""
    # 先创建推荐获取 history_id
    rec_response = client.post('/api/recommend', json={
        'query': '测试音乐',
        'session_id': 'test_001'
    })
    history_id = rec_response.get_json()['history_id']

    # 提交反馈
    response = client.post('/api/recommend/feedback', json={
        'history_id': history_id,
        'song_id': 123456,
        'playback_completion_rate': 85.5,
        'skipped': False
    })
    assert response.status_code == 200
```

**前端测试**（使用 uni-app 内置测试或手动测试）

#### 6.6.2 功能验证清单

| 功能 | 验证点 | 状态 |
|------|--------|------|
| 推荐接口 | 输入"欢快的凯尔特音乐"返回匹配结果 | ☐ |
| 推荐接口 | 输入古诗词"琵琶行"返回匹配结果 | ☐ |
| 反馈接口 | 播放完成后正确上报播放完成度 | ☐ |
| 反馈接口 | 点击跳过正确设置 skipped=true | ☐ |
| 历史记录 | 同一 session_id 的查询历史正确关联 | ☐ |
| 特征生成 | 批量生成接口可正常执行 | ☐ |

#### 6.6.3 部署

**后端部署**：

```bash
# 1. 安装 Gunicorn (生产环境)
pip install gunicorn

# 2. 启动服务
gunicorn -w 4 -b 0.0.0.0:5000 app:app

# 3. 使用 systemd 管理服务
sudo tee /etc/systemd/system/music-recommend.service <<EOF
[Unit]
Description=Music Recommend Service
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/path/to/backend
ExecStart=/usr/local/bin/gunicorn -w 4 -b 0.0.0.0:5000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable music-recommend
sudo systemctl start music-recommend
```

**前端部署**：

```bash
# H5 平台
npm run build:h5

# 微信小程序
npm run build:mp-weixin
# 然后在微信开发者工具中上传
```

---

### 6.7 实现进度汇总

| 阶段 | 工作内容 | 预计工时 | 依赖关系 |
|------|----------|----------|----------|
| **阶段一** | 环境准备与基础设施 | 1-2天 | 无 |
| **阶段二** | 数据库设计与创建 | 1-2天 | 阶段一 |
| **阶段三** | 后端核心功能开发 | 4-6天 | 阶段二 |
| **阶段四** | 后端 API 集成 | 0.5天 | 阶段三 |
| **阶段五** | 前端开发 | 3-4天 | 阶段四 |
| **阶段六** | 测试与部署 | 2-3天 | 阶段五 |

**总预计工时：11.5 - 17.5 人天**

**里程碑**：

1. **M1（阶段二完成后）**：数据库设计评审通过
2. **M2（阶段四完成后）**：后端 API 可用
3. **M3（阶段五完成后）**：前端页面可用
4. **M4（阶段六完成后）**：功能测试通过，可上线

---

---

## 7. 技术选型

### 7.1 LLM 与 Agent 方案对比分析

在设计智能音乐推荐系统时，面临一个关键决策：使用纯大模型（LLM）还是基于大模型的 Agent（智能体）？以下是两种方案的详细对比：

#### 方案A：纯大模型（LLM）

**架构特点：**
- 单次请求-响应模式
- 用户输入 → LLM推理 → 返回结果
- 无状态，每次交互独立

**优缺点：**

| 优点 | 缺点 |
|------|------|
| 实现简单，延迟低 | 无法进行多轮对话式推荐 |
| 成本可控 | 无法自主规划查询策略 |
| 易于部署和监控 | 无法处理复杂决策流程 |
| 适合一次性精准匹配 | 缺乏自我纠错能力 |

**适用场景：**
- 查询语义理解和意图识别
- 歌曲特征提取和标签生成
- 单次推荐匹配（输入 → 输出）

---

#### 方案B：大模型 Agent（智能体）

**架构特点：**
```
┌─────────────────────────────────────────────────────────────┐
│                      Agent 架构                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────┐                                             │
│  │   用户输入   │                                             │
│  └──────┬──────┘                                             │
│         │                                                    │
│         ▼                                                    │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐       │
│  │   Planning  │───▶│   Action   │───▶│   Observe   │       │
│  │   (规划)    │    │   (执行)   │    │   (观察)   │       │
│  └─────────────┘    └─────────────┘    └──────┬──────┘       │
│         ▲                                       │            │
│         │          ┌─────────────┐              │            │
│         └──────────│   Loop ◯   │◀─────────────┘            │
│                    │   (循环)   │                           │
│                    └─────────────┘                           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**核心能力：**

| 能力 | 说明 |
|------|------|
| **循环（Loop）** | Agent可以多次执行"思考→行动→观察"循环，直到达到目标 |
| **工具调用（Tool Use）** | 可调用外部工具（搜索、数据库查询、API调用） |
| **自我反思（Reflection）** | 可根据中间结果调整策略 |
| **多轮交互（Multi-turn）** | 可与用户进行对话式澄清 |

**优缺点：**

| 优点 | 缺点 |
|------|------|
| 支持多轮对话，精准澄清用户意图 | 实现复杂度高 |
| 可自主规划搜索策略 | 延迟可能较高 |
| 支持复杂决策流程 | 成本更高（多次调用） |
| 可进行自我纠错 | 调试和监控困难 |

---

#### 本项目方案建议：**混合方案（推荐）**

**理由：**

1. **核心推荐用 LLM**：音乐推荐的核心是"语义匹配"，单次LLM调用即可完成：
   - 用户查询理解 → 生成筛选条件
   - 数据库匹配 → 返回结果
   - 这是强确定性任务，LLM足够

2. **复杂场景用 Agent**：在以下场景 Agent 更有价值：
   - 用户说"刚才那首不错，来点类似的" → 多轮上下文理解
   - 用户意图模糊，需要主动询问澄清 → 对话式交互
   - 推荐结果不满意，需要重新规划搜索策略 → 自我纠错

3. **成本与效率考量**：
   - 80%的查询是简单场景，LLM单次调用即可
   - 20%的复杂场景才需要 Agent
   - 避免为简单任务支付 Agent 的额外开销

**混合架构设计：**

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户查询                                   │
└──────────────────────────┬────────────────────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │    意图分类器 (LLM)     │
              │  simple → LLM 直接匹配  │
              │  complex → Agent 处理  │
              └────────────┬───────────┘
                           │
           ┌───────────────┴───────────────┐
           ▼                               ▼
┌─────────────────────┐         ┌─────────────────────┐
│    LLM 快速路径      │         │   Agent 复杂路径      │
│  (单次调用完成)      │         │  (多轮循环处理)       │
│                     │         │                      │
│  • 查询语义理解      │         │  • 规划搜索策略       │
│  • 生成筛选条件      │         │  • 调用多个工具       │
│  • 返回推荐结果      │         │  • 自我反思纠错       │
│                     │         │  • 返回推荐结果       │
└─────────────────────┘         └─────────────────────┘
```

**初版实现建议：**

| 阶段 | 实现方案 | 说明 |
|------|----------|------|
| **初版（推荐）** | 纯 LLM | 先实现核心功能，验证推荐效果 |
| **后续迭代** | 混合方案 | 根据实际需求，复杂场景引入 Agent |
| **预留接口** | Agent 接口设计 | 保持架构扩展性，Agent 可独立迭代 |

> **最终建议**：初版使用**纯 LLM 方案**，原因：
> 1. 实现简单，能快速验证推荐效果
> 2. 成本可控，易于监控和优化
> 3. Agent 可作为后续迭代方向，不影响核心功能
> 4. 本项目的推荐逻辑（语义匹配）不需要循环和多轮交互也能完成

---

### 7.2 技术组件选型

| 组件 | 选择 | 理由 |
|------|------|------|
| LLM Provider | **MiniMax** | 您指定使用MiniMax模型 |
| Embedding | MiniMax Embedding API | 与LLM配套 |
| 向量数据库 | PostgreSQL pgvector (可选) | 扩展向量检索能力，先以标签匹配为主 |
| 缓存层 | Redis (可选) | 高并发场景优化 |
| 语音识别 | 微信小程序API / 讯飞API (预留) | 语音输入扩展 |

---

## 8. 配置文件更新

### backend/.env 新增配置

```env
# MiniMax LLM Configuration
LLM_PROVIDER=minimax
MINIMAX_API_KEY=your_minimax_api_key
MINIMAX_MODEL=abab6.5s-chat
MINIMAX_EMBEDDING_MODEL=embo-01

# Recommendation Settings
MAX_RECOMMEND_RESULTS=20
RECOMMEND_TIMEOUT_MS=30000
ENABLE_FEATURE_CACHE=true

# MongoDB Configuration (for comments)
MONGO_HOST=localhost
MONGO_PORT=27017
MONGO_DATABASE=music_comments
```

---

## 9. 错误处理

| 错误类型 | 处理方式 |
|----------|----------|
| LLM API 超时 | 返回缓存结果或"暂时无法推荐，请稍后重试" |
| LLM API 配额用尽 | 优雅降级到基于关键词的搜索推荐 |
| 数据库连接失败 | 返回错误码，前端提示"服务暂时不可用" |
| 查询文本为空 | 前端校验，提示用户输入描述 |
| 无匹配结果 | 返回空列表，提示"未找到匹配的音乐，请尝试其他描述" |

---

## 10. 性能考虑

1. **批量预计算**: 歌曲特征在入库时预计算，避免实时生成
2. **LLM调用优化**: 使用结构化输出减少token消耗
3. **缓存策略**: 相同/相似查询结果缓存
4. **异步处理**: 批量特征生成使用异步任务队列
5. **限流**: 用户端请求限流，防止滥用