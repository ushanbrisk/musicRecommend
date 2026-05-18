# 推荐功能完整数据流程详解

## 场景概述

当用户在前端页面 `http://192.168.3.8:5173/#/pages/recommend/recommend` 输入 **"欢快的凯尔特音乐"** 并发送后，系统经历以下完整的数据流程。

---

## 一、前端部分

### 1.1 用户输入与发送

**文件**: `music-project-uniapp/src/pages/recommend/recommend.vue`

**关键代码 (行 59-72, 103-131)**:
```vue
<!-- 底部输入区 -->
<view class="input-area">
  <view class="input-wrapper">
    <textarea
      class="chat-input"
      v-model="queryText"
      placeholder="描述你想要音乐..."
      :disabled="store.loading"
      @confirm="handleSend"
      confirm-type="send"
    />
    <view class="send-btn" @click="handleSend" v-if="queryText.trim()">
      <text>发送</text>
    </view>
  </view>
</view>
```

**用户操作流程**:
1. 用户在文本框输入 `"欢快的凯尔特音乐"`
2. 点击发送按钮，触发 `handleSend()` 函数

---

### 1.2 推荐页面组件处理

**文件**: `music-project-uniapp/src/pages/recommend/recommend.vue`

**`handleSend()` 函数 (行 103-131)**:
```typescript
async function handleSend() {
  const text = queryText.value.trim()
  if (!text || store.loading) return

  // 1. 添加用户消息到消息列表
  messages.value.push({ type: 'user', content: text })
  queryText.value = ''  // 清空输入框

  store.searched = true

  // 2. 添加 AI 消息（显示正在分析）
  const aiMsg = { type: 'ai' as const, content: '🤖 AI 正在分析您的描述...', results: [] }
  messages.value.push(aiMsg)
  scrollToBottom()

  // 3. 调用 Pinia Store 的 recommend 方法
  await store.recommend(text)

  // 4. 更新 AI 消息显示结果
  if (store.results.length > 0) {
    aiMsg.results = store.results
    aiMsg.content = '根据您的描述，为您推荐以下音乐：'
  } else if (store.error) {
    aiMsg.content = '抱歉，' + store.error
  }
  scrollToBottom()
}
```

---

### 1.3 Pinia Store 状态管理

**文件**: `music-project-uniapp/src/stores/recommend.ts`

**`recommend()` Action (行 103-126)**:
```typescript
async recommend(query: string) {
  if (!query.trim()) return

  this.loading = true
  this.error = null
  this.searched = true

  // 初始化会话 ID（从本地存储恢复或生成新的）
  this.initSessionId()

  try {
    // 调用 API: POST /api/recommend
    const res = await recommendApi.recommend(query, this.sessionId, 20)

    if (res.success) {
      // 更新状态
      this.results = res.results        // 推荐结果列表
      this.historyId = res.history_id  // 历史记录 ID
    } else {
      this.error = res.error || '推荐失败'
      this.results = []
    }
  } catch (e: any) {
    this.error = e.message || '网络错误，请稍后重试'
    this.results = []
  } finally {
    this.loading = false
  }
}
```

---

### 1.4 API 请求封装

**文件**: `music-project-uniapp/src/api/recommend.ts`

**`recommend()` API 方法 (行 135-143)**:
```typescript
async recommend(query: string, sessionId: string, maxResults = 20): Promise<RecommendResult> {
  return request<RecommendResult>(`${BASE_URL}/api/recommend`, {
    method: 'POST',
    data: {
      query,                    // "欢快的凯尔特音乐"
      session_id: sessionId,    // 会话 ID
      max_results: maxResults   // 20
    }
  })
}
```

**请求配置**:
- **URL**: `http://localhost:5000/api/recommend` (或 `http://192.168.3.8:5000/api/recommend`)
- **Method**: `POST`
- **Content-Type**: `application/json`
- **Request Body**:
```json
{
  "query": "欢快的凯尔特音乐",
  "session_id": "session_1716000000000_abc123xyz",
  "max_results": 20
}
```

---

### 1.5 统一请求函数

**文件**: `music-project-uniapp/src/api/recommend.ts` (行 102-122)

```typescript
async function request<T>(url: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', data } = options

  return new Promise((resolve, reject) => {
    uni.request({
      url,
      method,
      data,
      success: (res) => {
        if (res.statusCode === 200) {
          resolve(res.data as T)
        } else {
          reject(new Error(`请求失败: ${res.statusCode}`))
        }
      },
      fail: (err) => {
        reject(new Error(err.errMsg || '网络请求失败'))
      }
    })
  })
}
```

---

## 二、后端部分

### 2.1 Flask 路由接收

**文件**: `music-project/backend/routes/recommend.py`

**`recommend()` 路由函数 (行 22-47)**:
```python
@recommend_bp.route('/recommend', methods=['POST'])
def recommend():
    """POST /api/recommend - 文本推荐接口"""
    # 1. 获取 JSON 请求体
    data = request.get_json()

    # 2. 提取参数
    query = data.get('query', '').strip()
    if not query:
        return jsonify({"success": False, "error": "查询文本不能为空"}), 400

    session_id = data.get('session_id')
    max_results = data.get('max_results', 20)
    user_id = data.get('user_id')

    # 3. 获取 RecommendService 实例并调用
    service = get_recommend_service()
    result = service.recommend(
        query=query,
        session_id=session_id,
        max_results=max_results,
        user_id=user_id
    )

    # 4. 如果特征库为空，返回 503
    if not result.get('success', True):
        return jsonify(result), 503

    return jsonify(result)
```

**路由注册**: 在 `backend/app.py` (行 966-968) 中注册蓝图:
```python
from routes.recommend import recommend_bp
app.register_blueprint(recommend_bp)
```

---

### 2.2 RecommendService 核心推荐逻辑

**文件**: `music-project/backend/services/recommend_service.py`

**`recommend()` 方法 (行 16-71)**:
```python
def recommend(self, query: str, session_id: str = None,
              max_results: int = 20, user_id: str = None) -> Dict:
    """核心推荐方法"""

    start_time = time.time()

    # === 步骤 0: 检查 music_features 是否为空 ===
    cursor = self.db.cursor()
    cursor.execute("SELECT COUNT(*) FROM music_features")
    feature_count = cursor.fetchone()[0]
    cursor.close()

    if feature_count == 0:
        return {
            "success": False,
            "error": "音乐特征库为空，请先调用 /api/features/generate 接口生成特征数据",
            "code": "EMPTY_FEATURES_TABLE",
            "query": query,
            "results": [],
            "total": 0,
            "history_id": None,
            "latency_ms": 0
        }

    # === 步骤 1: 识别查询类型 ===
    query_type = self.classify_query(query)
    # 输入 "欢快的凯尔特音乐" -> 返回 'simple' 或 'complex'

    # === 步骤 2: 获取候选歌曲（随机采样 500 首）===
    candidates = self.get_candidates(limit=500)

    # === 步骤 3: 构建上下文，让 LLM 匹配 ===
    songs_context = self.build_songs_context(candidates)

    # === 步骤 4: 调用 LLM 进行语义匹配 ===
    match_result = self.llm_match(query, songs_context)

    # === 步骤 5: 记录推荐历史 ===
    latency_ms = int((time.time() - start_time) * 1000)
    history_id = self.save_history(
        session_id=session_id,
        user_id=user_id,
        query_text=query,
        query_type=query_type,
        result_song_ids=[r['song_id'] for r in match_result],
        result_count=len(match_result),
        latency_ms=latency_ms
    )

    # === 步骤 6: 构建返回结果 ===
    return self.build_response(
        query=query,
        query_type=query_type,
        matches=match_result,
        history_id=history_id,
        latency_ms=latency_ms
    )
```

---

### 2.3 查询类型分类

**文件**: `music-project/backend/services/recommend_service.py`

**`classify_query()` 方法 (行 73-83)**:
```python
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
```

**对于 "欢快的凯尔特音乐"**:
- 长度 < 20 且包含 "音乐" -> 返回 `'simple'`

---

### 2.4 获取候选歌曲

**文件**: `music-project/backend/services/recommend_service.py`

**`get_candidates()` 方法 (行 85-101)**:
```python
def get_candidates(self, limit: int = 500) -> List[Dict]:
    """获取候选歌曲（随机采样）"""
    cursor = self.db.cursor()
    query = """
        SELECT mf.*, s.song_name, s.artist, s.album, s.music_file
        FROM music_features mf
        JOIN songs s ON mf.song_id = s.song_id
        ORDER BY RANDOM()
        LIMIT %s
    """
    cursor.execute(query, (limit,))
    columns = [desc[0] for desc in cursor.description]
    results = []
    for row in cursor.fetchall():
        results.append(dict(zip(columns, row)))
    cursor.close()
    return results
```

**SQL 查询说明**:
```sql
SELECT mf.*, s.song_name, s.artist, s.album, s.music_file
FROM music_features mf
JOIN songs s ON mf.song_id = s.song_id
ORDER BY RANDOM()
LIMIT 500
```

**涉及的表**:
- `music_features` - 歌曲特征表
- `songs` - 歌曲信息表

**返回**: 500 首随机采样的歌曲，每首包含所有特征字段和基本信息

---

### 2.5 构建 LLM 上下文

**文件**: `music-project/backend/services/recommend_service.py`

**`build_songs_context()` 方法 (行 103-114)**:
```python
def build_songs_context(self, candidates: List[Dict]) -> str:
    """构建发送给 LLM 的歌曲上下文（限制100首）"""
    context_lines = []
    for song in candidates[:100]:
        line = f"song_id: {song['song_id']}, " \
               f"名称: {song['song_name']}, " \
               f"艺术家: {song['artist']}, " \
               f"风格: {song.get('genre', '未知')}, " \
               f"情绪: {song.get('mood', '未知')}, " \
               f"场景: {song.get('scene', '未知')}"
        context_lines.append(line)
    return "\n".join(context_lines)
```

**上下文示例**:
```
song_id: 1893728473, 名称: Ye Netherlands Where I Have a Love, 艺术家: Johan Wagenaar, 风格: 古典, 情绪: 欢快, 场景: 庆典
song_id: 1457702766, 名称: Dance of the Knights, 艺术家: Sergei Prokofiev, 风格: 古典, 情绪: 激烈, 场景: 战斗
...
```

**注意**: 只取前 100 首歌曲发送给 LLM（避免上下文过长）

---

### 2.6 LLM 语义匹配

**文件**: `music-project/backend/services/llm_service.py`

**`match_songs_prompt()` 方法 (行 91-110)**:
```python
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

**LLM 请求发送**:

**文件**: `music-project/backend/services/llm_service.py` (行 16-23)

```python
def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7) -> str:
    """发送对话请求"""
    response = self.client.chat.completions.create(
        model=self.model,  # os.getenv("LLM_MODEL_NAME", "abab6.5s-chat")
        messages=messages,
        temperature=temperature
    )
    return response.choices[0].message.content
```

**LLM 配置** (通过环境变量):
```python
self.client = OpenAI(
    api_key=os.getenv("LLM_PROVIDER_KEY"),
    base_url=os.getenv("LLM_PROVIDER_URL")
)
self.model = os.getenv("LLM_MODEL_NAME", "abab6.5s-chat")
```

**发送给 LLM 的完整消息**:
```json
{
  "model": "abab6.5s-chat",
  "messages": [
    {
      "role": "user",
      "content": "用户查询：\"欢快的凯尔特音乐\"\n\n候选歌曲信息：\nsong_id: 1893728473, 名称: Ye Netherlands Where I Have a Love, 艺术家: Johan Wagenaar, 风格: 古典, 情绪: 欢快, 场景: 庆典\nsong_id: 1457702766, 名称: Dance of the Knights, 艺术家: Sergei Prokofiev, 风格: 古典, 情绪: 激烈, 场景: 战斗\n...\n\n请从候选歌曲中选择最匹配用户查询的歌曲，返回 JSON 格式：\n{\n  \"matched_songs\": [\n    {\n      \"song_id\": 123,\n      \"match_score\": 0.95,\n      \"match_reason\": \"匹配原因说明\"\n    }\n  ]\n}\n\n注意：只返回匹配度 >= 0.6 的歌曲，最多返回20首。"
  }
  ],
  "temperature": 0.7
}
```

**LLM 返回示例**:
```json
{
  "matched_songs": [
    {
      "song_id": 8097451234,
      "match_score": 0.92,
      "match_reason": "这是一首典型的凯尔特风格音乐，节奏欢快，适合节日庆典场景"
    },
    {
      "song_id": 1457702766,
      "match_score": 0.85,
      "match_reason": "虽然是古典音乐，但节奏明快，情绪积极向上"
    }
  ]
}
```

---

### 2.7 解析 LLM 返回并匹配

**文件**: `music-project/backend/services/recommend_service.py`

**`llm_match()` 方法 (行 116-126)**:
```python
def llm_match(self, query: str, songs_context: str) -> List[Dict]:
    """LLM 语义匹配"""
    prompt = self.llm.match_songs_prompt(query, songs_context)
    response = self.llm.chat([{"role": "user", "content": prompt}])

    # 解析返回的 JSON
    try:
        result = json.loads(response)
        return result.get('matched_songs', [])
    except json.JSONDecodeError:
        return []
```

---

### 2.8 保存推荐历史

**文件**: `music-project/backend/services/recommend_service.py`

**`save_history()` 方法 (行 128-147)**:
```python
def save_history(self, session_id: str, user_id: str, query_text: str,
                 query_type: str, result_song_ids: List[int],
                 result_count: int, latency_ms: int) -> int:
    """保存推荐历史"""
    cursor = self.db.cursor()
    query = """
        INSERT INTO recommendation_history (
            session_id, user_id, query_text, query_type,
            result_count, result_song_ids, latency_ms
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """
    cursor.execute(query, (
        session_id, user_id, query_text, query_type,
        result_count, result_song_ids, latency_ms
    ))
    history_id = cursor.fetchone()[0]
    self.db.commit()
    cursor.close()
    return history_id
```

**SQL 语句**:
```sql
INSERT INTO recommendation_history (
    session_id, user_id, query_text, query_type,
    result_count, result_song_ids, latency_ms
) VALUES ('session_xxx', NULL, '欢快的凯尔特音乐', 'simple', 2, '{8097451234,1457702766}', 1523)
RETURNING id
```

**涉及的表**: `recommendation_history`

**表结构**:
| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL | 自增主键 |
| session_id | VARCHAR(100) | 会话标识 |
| user_id | VARCHAR(100) | 用户标识（可选） |
| query_text | TEXT | 用户查询文本 |
| query_type | VARCHAR(50) | 查询类型 (simple/complex/poem/voice) |
| result_count | INTEGER | 返回结果数量 |
| result_song_ids | BIGINT[] | 返回的歌曲 ID 数组 |
| latency_ms | INTEGER | 响应时间（毫秒） |

---

### 2.9 构建最终响应

**文件**: `music-project/backend/services/recommend_service.py`

**`build_response()` 方法 (行 149-184)**:
```python
def build_response(self, query: str, query_type: str,
                  matches: List[Dict], history_id: int,
                  latency_ms: int) -> Dict:
    """构建 API 响应"""
    cursor = self.db.cursor()
    results = []
    for match in matches:
        song_id = match['song_id']
        # 获取歌曲详情
        cursor.execute(
            "SELECT song_id, song_name, artist, album, music_file FROM songs WHERE song_id = %s",
            (song_id,)
        )
        row = cursor.fetchone()
        if row:
            results.append({
                "song_id": row[0],
                "song_name": row[1],
                "artist": row[2],
                "album": row[3],
                "music_file": row[4],
                "match_score": match.get('match_score', 0),
                "match_reason": match.get('match_reason', ''),
                "tags": [match.get('genre', ''), match.get('mood', '')]
            })
    cursor.close()

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

**涉及的数据表**: `songs`

---

## 三、数据表汇总

### 3.1 涉及的数据库表

| 表名 | 数据库类型 | 用途 |
|------|-----------|------|
| `songs` | PostgreSQL | 存储歌曲基本信息（song_id, song_name, artist, album, music_file） |
| `song_playlist_agg` | PostgreSQL | 【预聚合表】存储每首歌曲关联的所有歌单名称和分类 |
| `song_comment_agg` | PostgreSQL | 【预聚合表】存储每首歌曲的评论摘要和情感统计 |
| `music_features` | PostgreSQL | 存储歌曲特征（genre, mood, scene, instruments 等） |
| `recommendation_history` | PostgreSQL | 存储推荐历史记录 |
| `comments` | MongoDB | 原始评论数据（已被 song_comment_agg 预聚合） |

### 3.2 表结构

#### songs 表
```sql
CREATE TABLE songs (
    id SERIAL PRIMARY KEY,
    song_id BIGINT UNIQUE NOT NULL,
    song_name VARCHAR(255),
    artist VARCHAR(255),
    album VARCHAR(255),
    music_file VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### song_playlist_agg 表（预聚合表）
```sql
CREATE TABLE song_playlist_agg (
    id SERIAL PRIMARY KEY,
    song_id BIGINT UNIQUE NOT NULL REFERENCES songs(song_id),
    playlist_names TEXT[],           -- 所有歌单名称的数组
    playlist_categories TEXT[],      -- 所有歌单分类的数组
    playlist_count INTEGER DEFAULT 0,
    playlist_names_str VARCHAR(1000), -- 逗号分隔形式
    playlist_categories_str VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### song_comment_agg 表（预聚合表）
```sql
CREATE TABLE song_comment_agg (
    id SERIAL PRIMARY KEY,
    song_id BIGINT UNIQUE NOT NULL REFERENCES songs(song_id),
    comment_count INTEGER DEFAULT 0,
    top_comments TEXT[],             -- 点赞最高的评论（最多5条）
    comment_summary TEXT,            -- 评论内容摘要
    positive_count INTEGER DEFAULT 0,
    neutral_count INTEGER DEFAULT 0,
    negative_count INTEGER DEFAULT 0,
    avg_polarity DECIMAL(3,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### music_features 表
```sql
CREATE TABLE music_features (
    id SERIAL PRIMARY KEY,
    song_id BIGINT UNIQUE NOT NULL REFERENCES songs(song_id),
    genre VARCHAR(100),
    mood VARCHAR(200),
    tempo VARCHAR(50),
    instruments VARCHAR(200),
    scene VARCHAR(200),
    language VARCHAR(50),
    era VARCHAR(50),
    description TEXT,
    emotional_tags VARCHAR(500),
    theme_keywords VARCHAR(500),
    inherited_tags VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### recommendation_history 表
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
    latency_ms INTEGER
);
```

---

## 四、完整数据流时序图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              前端 (Vue 3 / UniApp)                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. 用户输入 "欢快的凯尔特音乐"                                               │
│     └── recommend.vue: handleSend()                                          │
│                                                                              │
│  2. 调用 Pinia Store recommend()                                             │
│     └── stores/recommend.ts: recommend() action                              │
│                                                                              │
│  3. 调用 recommendApi.recommend()                                            │
│     └── api/recommend.ts: recommend()                                        │
│                                                                              │
│  4. 发送 HTTP POST 请求                                                       │
│     └── uni.request() -> http://localhost:5000/api/recommend                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ HTTP POST
                        ┌───────────────────────────┐
                        │        请求体 JSON         │
                        │  {                        │
                        │    "query": "欢快的凯尔特音乐",  │
                        │    "session_id": "xxx",   │
                        │    "max_results": 20      │
                        │  }                        │
                        └───────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           后端 (Flask Python)                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  5. Flask 路由接收请求                                                        │
│     └── routes/recommend.py: recommend() @recommend_bp.route('/recommend') │
│                                                                              │
│  6. 调用 RecommendService.recommend()                                         │
│     └── services/recommend_service.py: RecommendService.recommend()          │
│                                                                              │
│  7. 检查 music_features 表是否为空                                            │
│     └── SELECT COUNT(*) FROM music_features                                 │
│                                                                              │
│  8. 分类查询类型                                                              │
│     └── classify_query("欢快的凯尔特音乐") -> 'simple'                        │
│                                                                              │
│  9. 随机采样 500 首候选歌曲                                                   │
│     └── SELECT ... FROM music_features JOIN songs ... ORDER BY RANDOM()     │
│                                                                              │
│  10. 构建 LLM 上下文（取前 100 首）                                            │
│      └── build_songs_context(candidates)                                    │
│                                                                              │
│  11. 调用 LLM 进行语义匹配                                                    │
│      └── LLMService.chat() -> MiniMax API                                   │
│                                                                              │
│  12. 解析 LLM 返回的 JSON                                                    │
│      └── json.loads(response) -> matched_songs                              │
│                                                                              │
│  13. 保存推荐历史到 recommendation_history                                   │
│      └── INSERT INTO recommendation_history ...                             │
│                                                                              │
│  14. 查询歌曲详情构建响应                                                     │
│      └── SELECT ... FROM songs WHERE song_id = ?                            │
│                                                                              │
│  15. 返回 JSON 响应                                                          │
│      └── jsonify(result)                                                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ HTTP 200 OK
                        ┌───────────────────────────┐
                        │        响应体 JSON         │
                        │  {                        │
                        │    "success": true,       │
                        │    "query": "欢快的凯尔特音乐",  │
                        │    "query_type": "simple", │
                        │    "results": [...],       │
                        │    "total": 2,             │
                        │    "history_id": 123,      │
                        │    "latency_ms": 1523      │
                        │  }                        │
                        └───────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              前端 (继续)                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  16. 接收响应，更新 Store 状态                                                │
│      └── stores/recommend.ts: this.results = res.results                   │
│                                                                              │
│  17. 更新 AI 消息，显示推荐结果                                               │
│      └── recommend.vue: aiMsg.results = store.results                       │
│                                                                              │
│  18. 页面渲染推荐卡片                                                        │
│      └── <RecommendCard v-for="item in msg.results" />                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 五、API 响应示例

### 请求
```http
POST /api/recommend
Content-Type: application/json

{
  "query": "欢快的凯尔特音乐",
  "session_id": "session_1716000000000_abc123xyz",
  "max_results": 20
}
```

### 响应
```json
{
  "success": true,
  "query": "欢快的凯尔特音乐",
  "query_type": "simple",
  "results": [
    {
      "song_id": 8097451234,
      "song_name": "The Irish Rovers - The Orange Mara",
      "artist": "The Irish Rovers",
      "album": "Classic Celtic Songs",
      "music_file": "/ssd11/music/song_download/8097451234.mp3",
      "match_score": 0.92,
      "match_reason": "典型的凯尔特风格音乐，节奏欢快，充满了翡翠之岛的风情",
      "tags": ["凯尔特", "欢快"]
    },
    {
      "song_id": 1893728473,
      "song_name": "Ye Netherlands, Where I Have a Love",
      "artist": "Johan Wagenaar",
      "album": "Orchestral Works",
      "music_file": "/ssd11/music/song_download/1893728473.mp3",
      "match_score": 0.85,
      "match_reason": "充满活力的管弦乐作品，情绪欢快，适合节日场景",
      "tags": ["古典", "欢快"]
    }
  ],
  "total": 2,
  "history_id": 456,
  "latency_ms": 1523
}
```

---

## 六、关键文件路径汇总

### 前端文件
| 文件 | 说明 |
|------|------|
| `music-project-uniapp/src/pages/recommend/recommend.vue` | 推荐页面组件 |
| `music-project-uniapp/src/stores/recommend.ts` | Pinia 状态管理 |
| `music-project-uniapp/src/api/recommend.ts` | API 请求封装 |

### 后端文件
| 文件 | 说明 |
|------|------|
| `music-project/backend/routes/recommend.py` | Flask 路由定义 |
| `music-project/backend/services/recommend_service.py` | 推荐核心逻辑 |
| `music-project/backend/services/llm_service.py` | LLM API 调用 |
| `music-project/backend/models/database.py` | 数据库连接 |

### 数据库表
| 表名 | 说明 |
|------|------|
| `songs` | 歌曲信息表 |
| `music_features` | 歌曲特征表 |
| `recommendation_history` | 推荐历史表 |

---

## 七、数据库查询汇总

### 查询 1: 检查特征库是否为空
```sql
SELECT COUNT(*) FROM music_features
```

### 查询 2: 随机采样候选歌曲
```sql
SELECT mf.*, s.song_name, s.artist, s.album, s.music_file
FROM music_features mf
JOIN songs s ON mf.song_id = s.song_id
ORDER BY RANDOM()
LIMIT 500
```

### 查询 3: 保存推荐历史
```sql
INSERT INTO recommendation_history (
    session_id, user_id, query_text, query_type,
    result_count, result_song_ids, latency_ms
) VALUES (%s, %s, %s, %s, %s, %s, %s)
RETURNING id
```

### 查询 4: 获取歌曲详情
```sql
SELECT song_id, song_name, artist, album, music_file
FROM songs
WHERE song_id = %s
```