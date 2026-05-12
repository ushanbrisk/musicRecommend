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

### 3.2 新增表：推荐历史与反馈 (recommendation_history)

记录用户的推荐查询和反馈，支持正负反馈用于优化推荐算法。

```sql
CREATE TABLE recommendation_history (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(100),         -- 会话标识（可跨查询关联同一用户）
    query_text TEXT NOT NULL,        -- 用户输入的查询文本
    query_type VARCHAR(50),          -- simple/complex/poem/voice
    result_count INTEGER,            -- 返回结果数量
    latency_ms INTEGER,             -- 响应时间（毫秒）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 推荐反馈表（支持正负反馈，类似抖音）
CREATE TABLE recommendation_feedback (
    id SERIAL PRIMARY KEY,
    history_id INTEGER REFERENCES recommendation_history(id) ON DELETE CASCADE,
    song_id BIGINT NOT NULL,         -- 被反馈的歌曲
    feedback_type VARCHAR(20) NOT NULL,  -- like(喜欢)/dislike(不喜欢)/skip(划走)
    feedback_detail VARCHAR(100),   -- 详细反馈：too_sad/too_happy/not_match等
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- 同一用户对同一歌曲在同一查询中只记录一条反馈
    UNIQUE(history_id, song_id)
);

-- 索引
CREATE INDEX idx_feedback_history ON recommendation_feedback(history_id);
CREATE INDEX idx_feedback_song ON recommendation_feedback(song_id);
CREATE INDEX idx_feedback_type ON recommendation_feedback(feedback_type);
```

**反馈类型说明：**

| feedback_type | 含义 | 使用场景 |
|---------------|------|----------|
| `like` | 喜欢/感兴趣 | 正样本，强化推荐 |
| `dislike` | 不喜欢 | 负样本，减少推荐 |
| `skip` | 划走/不感兴趣 | 弱负样本，降低权重 |

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

## 6. 实现步骤（待审批）

（略，待1.2、2、3.1、3.2、5.1审核通过后补充）

---

## 7. 技术选型

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