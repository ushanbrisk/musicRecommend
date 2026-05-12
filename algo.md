# 音乐推荐引擎 - 核心算法设计

## 1. 概述

本文档详细描述基于LLM的智能音乐推荐算法的设计思路和架构。该算法支持：
- 简单场景/情感描述（"欢快的凯尔特音乐"）
- 复杂文本内容（诗歌、散文）
- 扩展到语音输入的能力

---

## 2. 核心挑战分析

### 2.1 现有数据源分析

音乐推荐的核心挑战是：**从有限的文本信息中理解歌曲的内容、风格、情绪和使用场景**。

#### 2.1.1 数据源详述

| 数据源 | 表/集合 | 关键字段 | 信息量评估 |
|--------|---------|----------|------------|
| **歌曲基础信息** | `songs` | song_name, artist, album | ★★☆☆☆ - 歌曲名可能包含情绪词，艺术家可推断类型 |
| **歌单信息** | `playlists` | playlist_name, category | ★★★★☆ - 歌单名包含丰富的场景/情绪描述 |
| **歌曲-歌单关联** | `song_playlist` | song_id, playlist_id | ★★★☆☆ - 通过关联继承歌单的场景标签 |
| **用户评论** | MongoDB `comments` | song_id, content, sentiment, polarity | ★★★★★ - 用户用自然语言描述歌曲感受 |

#### 2.1.2 文本信息聚合

对于每首歌曲，系统聚合以下信息作为LLM输入：

```python
def aggregate_song_text_info(song_id: int) -> dict:
    """
    聚合单首歌曲的所有文本信息
    """
    # 1. 歌曲基础信息
    song = get_song(song_id)

    # 2. 所属歌单信息（可能有多个）
    playlists = get_playlists_for_song(song_id)
    playlist_names = [p.playlist_name for p in playlists]
    categories = [p.category for p in playlists]

    # 3. 评论内容（按情感和点赞数加权）
    comments = get_comments_for_song(song_id)
    # 高点赞正面评论权重更高
    top_comments = sorted(comments, key=lambda c: c.likedCount * c.polarity, reverse=True)[:10]

    return {
        "song_name": song.song_name,
        "artist": song.artist,
        "album": song.album,
        "playlist_names": playlist_names,
        "categories": categories,
        "top_comments": [c.content for c in top_comments]
    }
```

**聚合后的文本示例**：

```
歌曲名：Ye Netherlands, Where I Have a Love
艺术家：Johan Wagenaar
专辑：Orchestral Works

所属歌单：
- 【古典】宁静致远 · 放松身心 (分类: 古典)
- 夜深沉 · 孤独患者的深夜独酌 (分类: 深夜)

用户评论精选：
- "这曲子太美了，夜晚独自聆听仿佛置身星河" (👍 1523)
- "适合深夜独处时听，很治愈" (👍 856)
- "工作时分听意外地能让人平静下来" (👍 423)
```

### 2.2 解决思路

采用 **混合推荐架构**：

```
┌─────────────────────────────────────────────────────────────┐
│                      用户输入查询                            │
│            "欢快的凯尔特音乐" 或 "琵琶行"                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    查询意图分析模块                           │
│   - 简单查询 → 提取关键词/标签                               │
│   - 复杂查询 → LLM深度理解 + 情感曲线分析                    │
└─────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
    ┌──────────┐       ┌──────────┐       ┌──────────┐
    │ 标签匹配  │       │ 语义检索  │       │ LLM排序   │
    │ (快速)   │       │ (向量)   │       │ (精准)   │
    └──────────┘       └──────────┘       └──────────┘
          │                   │                   │
          └───────────────────┼───────────────────┘
                              ▼
                    ┌──────────────────┐
                    │   分数融合与排名   │
                    │  (RRF + 权重)    │
                    └──────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │    返回Top N结果  │
                    └──────────────────┘
```

---

## 3. 数据预处理：歌曲特征提取

### 3.1 特征结构设计

每首歌曲的语义特征（存储在 `music_features` 表）：

```python
@dataclass
class MusicFeature:
    song_id: int

    # 基础特征（LLM从聚合后的文本信息推断生成）
    genre: List[str]           # ["凯尔特", "古典", "新世纪"]
    mood: List[str]            # ["欢快", "明亮", "积极"]
    tempo: str                  # "medium"
    instruments: List[str]      # ["风笛", "竖琴", "管弦乐"]
    scene: List[str]           # ["节日", "庆祝", "背景音乐"]
    language: str              # "英语"
    era: str                    # "新世纪"

    # 语义描述（LLM生成）
    description: str            # 100-200字的AI生成描述
    emotional_tags: List[str]  # 更细腻的情感标签
    theme_keywords: List[str]   # 主题关键词

    # 扩展信息
    inherited_tags: List[str]   # 从歌单继承的场景/情绪标签

    # 向量表示（可选，用于向量检索）
    embedding: Optional[List[float]]
```

### 3.2 特征生成流程

```
歌曲列表 → 文本聚合 → LLM分析 → 特征提取 → 存储
    │                                         │
    │  ┌────────────────────────────────────┐ │
    │  │ 聚合的歌单信息、评论内容一并输入   │ │
    │  │ LLM综合所有信息生成特征           │ │
    │  └────────────────────────────────────┘ │
    └──────────────────────────────────────────┘
                    ▼
           music_features 表
```

**LLM Prompt 模板（生成歌曲特征）**：

```
你是音乐专家。请根据提供的歌曲信息，为每首歌曲生成详细的特征描述。

## 歌曲信息（已聚合文本）

{song_name}
艺术家：{artist}
专辑：{album}

所属歌单：
{playlist_names}

用户评论精选：
{top_comments}

---

请为上述歌曲生成JSON格式的特征信息：
{{
    "description": "综合歌曲名、艺术家、专辑、歌单和用户评论，生成100-200字的中文描述，描述其音乐风格、情感基调、适合场景等",
    "genre": ["流派1", "流派2"],
    "mood": ["情绪1", "情绪2"],
    "tempo": "快/中/慢",
    "instruments": ["主要乐器1", "乐器2"],
    "scene": ["场景1", "场景2"],
    "emotional_tags": ["细腻情感词1", "情感词2"],
    "theme_keywords": ["主题词1", "主题词2"],
    "inherited_tags": ["从歌单继承的场景标签1", "标签2"]
}}

注意：
- genre从：流行、摇滚、古典、民谣、电子、爵士、蓝调、凯尔特、新世纪、电影配乐、民族 等中选择
- mood从：欢快、忧伤、平静、激烈、浪漫、神秘、怀旧、励志、治愈、孤独、兴奋、沉思、温馨 等中选择
- scene从：工作、运动、休息、入睡、阅读、旅行、聚会、独处、冥想、驾车、深夜、清晨、节日、庆祝 等中选择
- 如果某些信息不足以判断，请标注为"待定"而非猜测
```

---

## 4. 查询处理算法

### 4.1 简单查询处理

适用于：场景描述、情绪描述、类型描述

**输入示例**：
- "欢快的凯尔特音乐"
- "适合心情郁闷的时候"
- "工作时听的轻音乐"

**处理流程**：

```python
def process_simple_query(query: str) -> QueryAnalysis:
    """
    1. 使用LLM提取查询中的关键属性
    2. 映射到music_features表的字段
    """
    prompt = f"""分析以下用户查询，提取音乐偏好属性。

查询："{query}"

请用JSON格式返回提取的属性：
{{
    "mood": ["需要提取的情绪标签"],
    "genre": ["需要提取的音乐类型"],
    "scene": ["需要提取的使用场景"],
    "tempo": "快/中/慢（如果适用）",
    "instruments": ["提到的乐器"],
    "language": "语言偏好（如果提到）",
    "era": "年代偏好（如果提到）"
}}

如果某项不适用，返回空数组或null。"""

    # 调用MiniMax LLM获取结构化属性
    response = minimax.chat.completions.create(
        model="abab6.5s-chat",
        messages=[
            {"role": "system", "content": MUSIC_EXTRACT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"}
    )
    attributes = json.loads(response.choices[0].message.content)

    return QueryAnalysis(
        original_query=query,
        extracted_attributes=attributes,
        query_type="simple"
    )
```

### 4.2 复杂查询处理（诗歌/散文）

适用于：长文本、诗歌、散文、文学内容

**输入示例**：
- 白居易《琵琶行》全文
- 一段心情随笔
- 电影台词

**处理流程**：

```python
def process_complex_query(query: str) -> QueryAnalysis:
    """
    1. 理解文本的整体情感曲线
    2. 识别情感转折点
    3. 提取核心情绪主题
    4. 生成音乐匹配建议
    """
    prompt = f"""请分析以下文本，理解其情感脉络，并给出匹配的音乐特征建议。

文本：
---
{query}
---

请用JSON格式返回分析结果：
{{
    "overall_mood": "整体情感基调（悲伤/欢快/平静/激昂等）",
    "emotional_arc": [
        {{"section": "开头", "mood": "情感", "description": "描述"}},
        {{"section": "中段", "mood": "情感", "description": "描述"}},
        {{"section": "高潮", "mood": "情感", "description": "描述"}},
        {{"section": "结尾", "mood": "情感", "description": "描述"}}
    ],
    "core_themes": ["核心主题词1", "核心主题词2"],
    "recommended_music_features": {{
        "genre": ["推荐类型"],
        "mood": ["推荐情绪"],
        "tempo": "推荐节拍",
        "instruments": ["推荐乐器"],
        "scene": ["推荐场景"]
    }},
    "summary": "一句话总结这段文本适合什么样的音乐"
}}"""

    response = minimax.chat.completions.create(
        model="abab6.5s-chat",
        messages=[
            {"role": "system", "content": MUSIC_ANALYSIS_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"}
    )
    result = json.loads(response.choices[0].message.content)

    return QueryAnalysis(
        original_query=query,
        query_type="complex/poem",
        emotional_arc=result.emotional_arc,
        recommended_features=result.recommended_music_features,
        summary=result.summary
    )
```

---

## 5. 匹配算法架构

### 5.1 三路召回策略

#### 召回路1：标签过滤 + 评分

```python
def tag_based_match(query_attrs: dict, songs: List[MusicFeature]) -> List[Tuple[int, float]]:
    """
    基于提取的标签进行过滤和评分
    """
    scores = []

    for song in songs:
        score = 0.0
        total_weight = 0.0

        # 情绪匹配（权重最高）
        if query_attrs.get('mood') and song.mood:
            mood_score = len(set(query_attrs['mood']) & set(song.mood)) / len(query_attrs['mood'])
            score += mood_score * 0.35
            total_weight += 0.35

        # 类型匹配
        if query_attrs.get('genre') and song.genre:
            genre_score = len(set(query_attrs['genre']) & set(song.genre)) / len(query_attrs['genre'])
            score += genre_score * 0.25
            total_weight += 0.25

        # 场景匹配
        if query_attrs.get('scene') and song.scene:
            scene_score = len(set(query_attrs['scene']) & set(song.scene)) / len(query_attrs['scene'])
            score += scene_score * 0.2
            total_weight += 0.2

        # 乐器匹配
        if query_attrs.get('instruments') and song.instruments:
            inst_score = len(set(query_attrs['instruments']) & set(song.instruments)) / len(query_attrs['instruments'])
            score += inst_score * 0.1
            total_weight += 0.1

        # 节拍匹配
        if query_attrs.get('tempo') and song.tempo:
            score += (query_attrs['tempo'] == song.tempo) * 0.1
            total_weight += 0.1

        # 归一化
        if total_weight > 0:
            score = score / total_weight if total_weight < 1.0 else score

        scores.append((song.song_id, score))

    return sorted(scores, key=lambda x: x[1], reverse=True)
```

#### 召回路2：语义向量检索（可选）

```python
def semantic_search(query: str, songs: List[MusicFeature], top_k: int = 50) -> List[Tuple[int, float]]:
    """
    使用embedding进行语义相似度搜索
    需要 songs 表有 feature_vector 字段
    """
    # 生成查询向量
    query_embedding = embedding_model.encode(query)

    # 计算余弦相似度
    scored_songs = []
    for song in songs:
        if song.embedding:
            similarity = cosine_similarity(query_embedding, song.embedding)
            scored_songs.append((song.song_id, similarity))

    # 返回Top K
    return sorted(scored_songs, key=lambda x: x[1], reverse=True)[:top_k]
```

#### 召回路3：LLM直接排序（小候选集）

```python
def llm_rerank(query: str, candidate_songs: List[Song], top_n: int = 20) -> Dict:
    """
    使用MiniMax LLM对候选歌曲进行精确排序
    适用于最终精准排序
    """
    # 构建prompt
    songs_context = "\n".join([
        f"- {s.song_name} by {s.artist}: 标签[{','.join(s.mood)}] 描述{s.description or '无'}"
        for s in candidate_songs[:50]  # 限制数量
    ])

    prompt = f"""用户查询："{query}"

以下是候选歌曲列表（包含歌曲名、艺术家、标签和描述）：
{songs_context}

请根据歌曲与查询的相关性进行排序，返回前{top_n}首最匹配的歌曲ID列表和匹配理由。
只返回与查询相关的歌曲，如果候选歌曲都不匹配，也应返回空列表。

请用JSON格式返回：
{{
    "ranked_song_ids": [song_id1, song_id2, ...],
    "reasons": {{
        "song_id1": "匹配理由...",
        "song_id2": "匹配理由..."
    }}
}}"""

    response = minimax.chat.completions.create(
        model="abab6.5s-chat",
        messages=[
            {"role": "system", "content": MUSIC_RERANK_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"}
    )
    result = json.loads(response.choices[0].message.content)
    return result
```

### 5.2 多路召回融合

采用 **Reciprocal Rank Fusion (RRF)** 算法融合多路召回结果：

```python
def reciprocal_rank_fusion(
    tag_results: List[Tuple[int, float]],      # (song_id, score)
    vector_results: List[Tuple[int, float]],  # (song_id, score)
    llm_results: List[int],                   # [song_id, ...] 排序列表
    k: int = 60
) -> List[Tuple[int, float]]:
    """
    RRF融合多路召回结果
    """
    rrf_scores = defaultdict(float)

    # Tag-based results (权重0.4)
    for rank, (song_id, score) in enumerate(tag_results):
        rrf_scores[song_id] += score * 0.4 / (k + rank + 1)

    # Vector search results (权重0.3，可选启用)
    for rank, (song_id, score) in enumerate(vector_results):
        rrf_scores[song_id] += score * 0.3 / (k + rank + 1)

    # LLM rerank results (权重0.3)
    for rank, song_id in enumerate(llm_results):
        rrf_scores[song_id] += 0.3 / (k + rank + 1)

    # 排序返回
    sorted_results = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_results
```

---

## 6. LLM调用设计

### 6.1 MiniMax API 配置

```python
from openai import OpenAI

# MiniMax API配置
minimax = OpenAI(
    api_key=os.getenv("MINIMAX_API_KEY"),
    base_url="https://api.minimax.chat/v1"
)

# 模型配置
CHAT_MODEL = "abab6.5s-chat"  # MiniMax Chat模型
EMBEDDING_MODEL = "embo-01"     # MiniMax Embedding模型
```

### 6.2 Prompt工程

#### 系统提示词（System Prompt）

```python
# 查询属性提取
MUSIC_EXTRACT_SYSTEM_PROMPT = """你是一个音乐推荐专家，擅长从用户描述中提取音乐偏好属性。

请从用户查询中提取以下维度的属性：
- mood: 情绪标签（欢快、忧伤、平静、激烈、浪漫、神秘、怀旧、励志、治愈等）
- genre: 音乐类型（流行、摇滚、古典、民谣、电子、爵士、蓝调、凯尔特、新世纪等）
- scene: 使用场景（工作、运动、休息、入睡、阅读、旅行、聚会、独处、深夜等）
- tempo: 节拍（快、中、慢）
- instruments: 提到的乐器
- language: 语言偏好
- era: 年代偏好

只返回与查询明确相关的属性，不要过度猜测。"""

# 复杂文本/诗歌分析
MUSIC_ANALYSIS_SYSTEM_PROMPT = """你是一个专业的文学音乐分析师，擅长分析文本的情感脉络并推荐匹配的音乐。

你的能力：
1. 理解文本的整体情感基调和变化
2. 识别情感转折点和主题
3. 提取与音乐匹配的关键特征
4. 生成精准的音乐推荐建议

请始终以JSON格式返回结构化分析结果。"""

# LLM重排
MUSIC_RERANK_SYSTEM_PROMPT = """你是一个音乐推荐专家，负责对候选歌曲进行精准排序。

根据用户查询，从候选列表中选择最匹配的歌曲。只返回与查询真正相关的歌曲。
考虑因素：
1. 歌曲风格是否匹配查询描述
2. 情感基调是否一致
3. 适合场景是否重合
4. 用户评论中提到的使用场景

请以JSON格式返回排序结果和理由。"""
```

### 6.3 输出结构化保证

使用 **response_format={"type": "json_object"}** 保证LLM输出可解析：

```python
response = minimax.chat.completions.create(
    model="abab6.5s-chat",
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_query}
    ],
    response_format={"type": "json_object"},  # 强制JSON输出
    temperature=0.3  # 低随机性，保证稳定性
)
```

### 6.4 批量处理优化

特征生成使用批量调用减少API开销：

```python
async def batch_generate_features(songs: List[Song], batch_size: int = 20) -> List[MusicFeature]:
    """
    批量生成歌曲特征
    """
    all_features = []

    for i in range(0, len(songs), batch_size):
        batch = songs[i:i + batch_size]

        # 构建批量prompt
        songs_context = []
        for idx, s in enumerate(batch):
            info = aggregate_song_text_info(s.song_id)
            songs_context.append(
                f"[{idx}] 歌名：{info['song_name']}，艺术家：{info['artist']}，专辑：{info['album']}\n"
                f"    歌单：{'; '.join(info['playlist_names'])}\n"
                f"    评论：{' | '.join(info['top_comments'][:3])}"
            )

        prompt = f"""请为以下批量歌曲生成特征信息。每首歌信息格式为[序号] 歌名...：

{' '.join(songs_context)}

请为每首歌生成JSON格式的特征信息：
{{
    "songs": [
        {{"index": 0, "description": "...", "genre": [...], "mood": [...], ...}},
        {{"index": 1, "description": "...", "genre": [...], "mood": [...], ...}}
    ]
}}"""

        response = minimax.chat.completions.create(
            model="abab6.5s-chat",
            messages=[
                {"role": "system", "content": MUSIC_FEATURE_GENERATION_PROMPT},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )

        result = json.loads(response.choices[0].message.content)
        # 解析并关联到对应歌曲
        for song_result in result.get("songs", []):
            idx = song_result["index"]
            features = parse_features(song_result)
            features.song_id = batch[idx].song_id
            all_features.append(features)

    return all_features
```

---

## 7. 缓存策略

### 7.1 三级缓存

```
┌─────────────────────────────────────────────────────────────┐
│                     L1: 查询结果缓存                         │
│              相同查询文本 → 直接返回缓存结果                  │
│                    TTL: 1小时                               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    L2: 特征向量缓存                          │
│           song_id → embedding 向量缓存                       │
│                    TTL: 24小时                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    L3: 歌曲特征缓存                          │
│           song_id → MusicFeature 对象缓存                   │
│                    TTL: 7天                                 │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 缓存实现

```python
import hashlib
import json
from typing import Optional, List

class RecommendationCache:
    def __init__(self, redis_client=None):
        self.redis = redis_client
        self.local_cache = {}  # 进程内缓存

    def _make_key(self, prefix: str, data: str) -> str:
        """生成缓存key"""
        return f"{prefix}:{hashlib.md5(data.encode()).hexdigest()}"

    # ========== L1: 查询结果缓存 ==========
    def get_query_result(self, query: str) -> Optional[List[dict]]:
        """L1: 查询缓存"""
        cache_key = self._make_key("qresult", query)
        # 先查本地缓存
        if cache_key in self.local_cache:
            return self.local_cache[cache_key]
        # 再查Redis
        if self.redis:
            cached = self.redis.get(cache_key)
            if cached:
                return json.loads(cached)
        return None

    def set_query_result(self, query: str, results: List[dict], ttl: int = 3600):
        """L1: 设置查询缓存"""
        cache_key = self._make_key("qresult", query)
        # 存本地
        self.local_cache[cache_key] = results
        # 存Redis
        if self.redis:
            self.redis.setex(cache_key, ttl, json.dumps(results))

    # ========== L2: 向量缓存 ==========
    def get_song_embedding(self, song_id: int) -> Optional[List[float]]:
        """L2: 向量缓存"""
        cache_key = f"emb:{song_id}"
        if self.redis:
            cached = self.redis.get(cache_key)
            if cached:
                return json.loads(cached)
        return None

    def set_song_embedding(self, song_id: int, embedding: List[float], ttl: int = 86400):
        """L2: 设置向量缓存"""
        cache_key = f"emb:{song_id}"
        if self.redis:
            self.redis.setex(cache_key, ttl, json.dumps(embedding))

    # ========== L3: 特征缓存 ==========
    def get_song_features(self, song_id: int) -> Optional[MusicFeature]:
        """L3: 特征缓存"""
        cache_key = f"feat:{song_id}"
        if self.redis:
            cached = self.redis.get(cache_key)
            if cached:
                return MusicFeature(**json.loads(cached))
        return None

    def set_song_features(self, song_id: int, features: MusicFeature, ttl: int = 604800):
        """L3: 设置特征缓存"""
        cache_key = f"feat:{song_id}"
        if self.redis:
            self.redis.setex(cache_key, ttl, json.dumps(asdict(features)))
```

---

## 8. 反馈机制（负反馈支持）

### 8.1 反馈数据收集

用户可以对推荐结果进行反馈：

```python
@dataclass
class RecommendFeedback:
    history_id: int      # 关联的查询记录ID
    song_id: int         # 被反馈的歌曲
    feedback_type: str    # like / dislike / skip
    feedback_detail: Optional[str]  # 详细原因
```

### 8.2 反馈在算法中的应用

```
┌─────────────────────────────────────────────────────────────┐
│                    用户反馈数据                              │
│         like (+) / dislike (-) / skip (0)                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    反馈日志分析                               │
│   - 统计每首歌的正/负反馈比例                                │
│   - 识别负面反馈的普遍原因                                   │
│   - 调整召回权重或过滤规则                                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    算法优化                                  │
│   - 降低dislike率高的歌曲的召回权重                          │
│   - skip多的歌曲降低展示优先级                               │
│   - 提取dislike原因更新标签匹配规则                          │
└─────────────────────────────────────────────────────────────┘
```

---

## 9. 语音输入扩展（预留）

### 9.1 架构预留

```
语音输入 → 语音识别(ASR) → 文本 → 文本推荐引擎
              ↑
         支持多语言
```

### 9.2 接口预留

```python
# 未来可扩展的语音推荐接口
@app.route('/api/recommend/voice', methods=['POST'])
def recommend_by_voice():
    """
    支持语音输入的推荐
    {
        "audio_data": "base64编码的音频",
        "language": "zh-CN",  # 语音语言
        "max_results": 20
    }
    """
    # 1. 语音识别 (预留接口)
    text = asr_service.recognize(audio_data, language)

    # 2. 文本推荐
    result = recommend_service.recommend(text)

    return result
```

---

## 10. 完整推荐流程示例

### 示例1：简单场景查询

**输入**："欢快的凯尔特音乐"

**流程**：

```
1. 意图分析 → 简单查询
   提取属性：{mood: ["欢快"], genre: ["凯尔特", "民谣"]}

2. 标签召回
   → 匹配 mood包含"欢快" AND genre包含"凯尔特"的歌曲
   → 返回 30 首，评分 0.6-0.95

3. 向量召回（可选）
   → 查找描述与"欢快的凯尔特音乐"语义相似的歌曲
   → 返回 20 首

4. MiniMax LLM精排（Top 20）
   → 输入查询 + Top 20 候选
   → 输出最终排序和理由

5. 结果返回
   → 展示前 15 首，附推荐理由
```

### 示例2：诗歌查询

**输入**：白居易《琵琶行》（节选）

**流程**：

```
1. 意图分析 → 复杂/诗歌查询
   情感分析：
   - 整体基调：悲伤、感慨
   - 情感曲线：开始（离别）→ 中段（繁华）→ 高潮（沦落）→ 结尾（无奈）
   - 主题：琵琶声、离别、沦落人生、历史感
   - 推荐音乐特征：古典、忧伤、优雅、古筝/琵琶、夜晚、独处

2. 多维度召回
   - 标签：genre=古典, mood=忧伤, instruments=古筝/琵琶
   - 向量：寻找"古典忧伤"语义空间的歌曲

3. MiniMax LLM精排
   → 考虑诗歌的"转"法，选择有层次感的音乐

4. 结果
   → 返回适合《琵琶行》意境的古典音乐
```

---

## 11. 核心代码结构

```
backend/
├── services/
│   ├── __init__.py
│   ├── recommender.py          # 推荐服务主类
│   ├── query_analyzer.py       # 查询意图分析
│   ├── tag_matcher.py          # 标签匹配
│   ├── vector_search.py        # 向量检索（可选）
│   ├── llm_reranker.py         # LLM精排（MiniMax）
│   └── fusion.py               # 多路融合
├── utils/
│   ├── cache.py                # 缓存工具
│   ├── feature_generator.py    # 特征生成工具
│   └── text_aggregator.py      # 歌曲文本信息聚合
├── prompts/
│   └── music_prompts.py        # Prompt模板
├── llm/
│   └── minimax_client.py       # MiniMax API客户端
└── app.py                      # API入口
```

---

## 12. 算法效果评估

### 12.1 离线评估指标

| 指标 | 说明 |
|------|------|
| Precision@K | Top-K结果中相关歌曲的比例 |
| MRR | 平均倒数排名 |
| NDCG | 归一化折损累计增益 |
| 覆盖率 | 推荐结果覆盖的歌曲比例 |

### 12.2 在线评估

- 用户点击率
- 推荐结果播放率
- 用户满意度反馈（like/dislike/skip）
- 重复使用率

---

## 13. 风险与对策

| 风险 | 影响 | 对策 |
|------|------|------|
| MiniMax API 响应慢 | 体验差 | 增加缓存、异步处理、超时降级 |
| MiniMax API 成本 | 费用大 | 批量处理、缓存优化、限制调用频率 |
| 歌曲特征缺失 | 覆盖率低 | 优先处理有完整信息的歌曲 |
| 语义相似但标签不匹配 | 漏召回 | 向量召回作为补充 |
| LLM幻觉 | 推荐不准 | Few-shot examples、输出校验 |
| 评论质量差 | 特征不准 | 只用高点赞+正面情感的评论 |