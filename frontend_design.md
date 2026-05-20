# 前端设计详细文档

本文档包含 `design.md` 第 6.5 节（前端开发）的详细代码实现。

---

## 6.5 阶段五：前端开发

### 6.5.1 前端项目结构分析

**现有项目结构**：

```
src/
├── api/
│   └── index.ts              # API 封装（使用 uni.request）
├── stores/
│   ├── songs.ts              # 歌曲状态管理
│   └── player.ts             # 播放器状态管理
├── components/
│   └── PlayerBar.vue         # 播放器组件
├── pages/
│   ├── index/index.vue       # 首页（歌曲列表、分类、搜索）
│   ├── categories/           # 分类页面
│   ├── playlist/             # 歌单页面
│   └── lyric/                # 歌词页面
├── utils/
│   └── audioManager.ts       # 音频播放管理
└── App.vue
```

**技术栈**：
- Vue 3 Composition API（`<script setup lang="ts">`）
- Pinia 状态管理
- UniApp（跨平台）
- SCSS 样式

### 6.5.2 新增/修改文件清单

**新增文件（4个）：**

| 文件路径 | 说明 |
|----------|------|
| `src/api/recommend.ts` | 推荐 API 封装 |
| `src/stores/recommend.ts` | 推荐状态管理 |
| `src/components/RecommendCard.vue` | 推荐结果卡片 |
| `src/pages/recommend/recommend.vue` | AI 推荐页面 |

**修改文件（2个）：**

| 文件路径 | 说明 |
|----------|------|
| `src/pages.json` | 添加推荐页面路由 |
| `src/pages/index/index.vue` | 添加"AI推荐"导航按钮 |

**pages.json 路由配置**：

```json
{
  "pages": [
    // ... 现有页面 ...
    {
      "path": "pages/recommend/recommend",
      "style": {
        "navigationStyle": "custom",
        "navigationBarBackgroundColor": "#1a1a2e"
      }
    }
  ]
}
```

### 6.5.3 API 封装

**src/api/recommend.ts**：

```typescript
// src/api/recommend.ts

const API_BASE = 'http://localhost:5000/api'

export const recommendApi = {
  /**
   * 文本推荐
   */
  async recommend(query: string, sessionId: string, maxResults = 20) {
    const res = await uni.request({
      url: `${API_BASE}/recommend`,
      method: 'POST',
      data: { query, session_id: sessionId, max_results: maxResults }
    })
    return res.data
  },

  /**
   * 提交推荐反馈
   */
  async submitFeedback(feedback: {
    history_id: number
    song_id: number
    feedback_type?: string
    playback_duration_seconds?: number
    song_duration_seconds?: number
    playback_completion_rate?: number
    skipped?: boolean
    looped?: boolean
    play_source?: string
  }) {
    const res = await uni.request({
      url: `${API_BASE}/recommend/feedback`,
      method: 'POST',
      data: feedback
    })
    return res.data
  },

  /**
   * 获取推荐历史
   */
  async getHistory(sessionId: string, limit = 20) {
    const res = await uni.request({
      url: `${API_BASE}/recommend/history`,
      method: 'GET',
      data: { session_id: sessionId, limit }
    })
    return res.data
  },

  /**
   * 获取歌曲特征
   */
  async getSongFeatures(songId: number) {
    const res = await uni.request({
      url: `${API_BASE}/songs/${songId}/features`,
      method: 'GET'
    })
    return res.data
  }
}
```

### 6.5.4 推荐状态管理

**src/stores/recommend.ts**：

```typescript
// src/stores/recommend.ts
import { defineStore } from 'pinia'
import { recommendApi } from '@/api/recommend'

interface RecommendResult {
  song_id: number
  song_name: string
  artist: string
  album: string
  music_file: string
  match_score: number
  match_reason: string
  tags: string[]
}

interface RecommendState {
  results: RecommendResult[]
  historyId: number | null
  sessionId: string
  loading: boolean
  error: string | null
}

export const useRecommendStore = defineStore('recommend', {
  state: (): RecommendState => ({
    results: [],
    historyId: null,
    sessionId: '',
    loading: false,
    error: null
  }),

  actions: {
    // 生成或获取 sessionId
    initSessionId() {
      if (!this.sessionId) {
        const stored = uni.getStorageSync('recommend_session_id')
        if (stored) {
          this.sessionId = stored
        } else {
          this.sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9)
          uni.setStorageSync('recommend_session_id', this.sessionId)
        }
      }
    },

    // 执行推荐
    async recommend(query: string) {
      if (!query.trim()) return

      this.loading = true
      this.error = null
      this.initSessionId()

      try {
        const res = await recommendApi.recommend(query, this.sessionId, 20)
        if (res.success) {
          this.results = res.results
          this.historyId = res.history_id
        } else {
          this.error = res.error || '推荐失败'
        }
      } catch (e: any) {
        this.error = e.message || '网络错误'
      } finally {
        this.loading = false
      }
    },

    // 提交反馈
    async submitFeedback(songId: number, feedbackType: string) {
      if (!this.historyId) return

      try {
        await recommendApi.submitFeedback({
          history_id: this.historyId,
          song_id: songId,
          feedback_type: feedbackType,
          play_source: 'recommend'
        })
      } catch (e) {
        console.error('提交反馈失败:', e)
      }
    },

    // 清空结果
    clearResults() {
      this.results = []
      this.historyId = null
    }
  }
})
```

### 6.5.5 推荐页面实现（聊天风格）

**设计理念**：类似微信、飞书、IntegraTelegram 的聊天窗口风格
- 整体宽度限制在 1200px 以内，与 App.vue 保持一致
- 输入区域固定在底部，类似聊天输入框
- 推荐结果以卡片列表形式展示，AI 回复风格
- 无"搜索"按钮，发送仅通过回车或输入后自动触发

**src/pages/recommend/recommend.vue**：

```vue
<template>
  <view class="recommend-page">
    <!-- 内容区域 -->
    <scroll-view class="chat-container" scroll-y>
      <!-- 欢迎提示 -->
      <view class="welcome-tip" v-if="messages.length === 0">
        <text class="welcome-icon">🎵</text>
        <text class="welcome-text">告诉我你想听什么样的音乐</text>
        <text class="welcome-hint">比如："欢快的凯尔特音乐"、"夜晚独自思考时听"</text>
      </view>

      <!-- 消息列表 -->
      <view
        v-for="(msg, index) in messages"
        :key="index"
        class="message-item"
        :class="msg.type"
      >
        <!-- 用户消息 -->
        <view v-if="msg.type === 'user'" class="user-message">
          <text class="message-text">{{ msg.content }}</text>
        </view>

        <!-- AI 推荐结果 -->
        <view v-else-if="msg.type === 'ai'" class="ai-message">
          <view class="ai-avatar">🤖</view>
          <view class="ai-content">
            <text class="ai-intro">根据您的描述，为您推荐以下音乐：</text>
            <view class="results-list">
              <view
                v-for="item in msg.results"
                :key="item.song_id"
                class="result-card"
              >
                <RecommendCard
                  :song="item"
                  :history-id="store.historyId"
                  @play="handlePlay"
                  @feedback="handleFeedback"
                />
              </view>
            </view>
          </view>
        </view>
      </view>

      <!-- 加载中 -->
      <view class="loading-tip" v-if="store.loading">
        <text>🤖 AI 正在分析并推荐...</text>
      </view>
    </scroll-view>

    <!-- 底部输入区（聊天风格） -->
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
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRecommendStore } from '@/stores/recommend'
import { usePlayerStore } from '@/stores/player'
import RecommendCard from '@/components/RecommendCard.vue'
import type { RecommendSong } from '@/api/recommend'

interface Message {
  type: 'user' | 'ai'
  content: string
  results?: RecommendSong[]
}

const store = useRecommendStore()
const playerStore = usePlayerStore()

const queryText = ref('')
const messages = ref<Message[]>([])

// 发送消息
async function handleSend() {
  const text = queryText.value.trim()
  if (!text || store.loading) return

  // 添加用户消息
  messages.value.push({ type: 'user', content: text })
  queryText.value = ''

  // 调用推荐
  store.searched = true
  await store.recommend(text)

  // 添加 AI 回复
  if (store.results.length > 0) {
    messages.value.push({
      type: 'ai',
      content: '为您推荐',
      results: store.results
    })
  }
}

function handlePlay(song: RecommendSong) {
  playerStore.playSong(song as any, store.results as any)
}

function handleFeedback({ song, feedbackType }: { song: RecommendSong; feedbackType: string }) {
  store.submitFeedback(song.song_id, feedbackType)
}
</script>

<style lang="scss" scoped>
.recommend-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  max-width: 1200px;
  margin: 0 auto;
  background: #1a1a2e;
}

.chat-container {
  flex: 1;
  padding: 20rpx;
  overflow-y: auto;
}

.welcome-tip {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 100rpx 40rpx;
  gap: 16rpx;
}

.welcome-icon {
  font-size: 80rpx;
}

.welcome-text {
  font-size: 32rpx;
  color: #fff;
}

.welcome-hint {
  font-size: 26rpx;
  color: rgba(255, 255, 255, 0.5);
  text-align: center;
}

.message-item {
  margin-bottom: 30rpx;
}

.user-message {
  display: flex;
  justify-content: flex-end;
}

.user-message .message-text {
  max-width: 70%;
  padding: 20rpx 30rpx;
  background: linear-gradient(90deg, #00d4ff, #7b2cbf);
  border-radius: 24rpx;
  color: #fff;
  font-size: 28rpx;
}

.ai-message {
  display: flex;
  gap: 16rpx;
}

.ai-avatar {
  width: 64rpx;
  height: 64rpx;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 32rpx;
  flex-shrink: 0;
}

.ai-content {
  flex: 1;
}

.ai-intro {
  font-size: 26rpx;
  color: rgba(255, 255, 255, 0.6);
  margin-bottom: 16rpx;
}

.results-list {
  display: flex;
  flex-direction: column;
  gap: 16rpx;
}

.loading-tip {
  display: flex;
  justify-content: center;
  padding: 30rpx;
  color: rgba(255, 255, 255, 0.5);
  font-size: 26rpx;
}

.input-area {
  padding: 20rpx;
  background: rgba(0, 0, 0, 0.2);
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.input-wrapper {
  display: flex;
  align-items: flex-end;
  gap: 16rpx;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 40rpx;
  padding: 16rpx 24rpx;
}

.chat-input {
  flex: 1;
  min-height: 48rpx;
  max-height: 120rpx;
  padding: 0;
  background: transparent;
  border: none;
  color: #fff;
  font-size: 28rpx;
  line-height: 1.4;
}

.chat-input::placeholder {
  color: rgba(255, 255, 255, 0.5);
}

.send-btn {
  padding: 12rpx 30rpx;
  background: linear-gradient(90deg, #00d4ff, #7b2cbf);
  border-radius: 30rpx;
  color: #fff;
  font-size: 26rpx;
  flex-shrink: 0;
}
</style>
```

### 6.5.6 推荐卡片组件

**src/components/RecommendCard.vue**：

```vue
<template>
  <view class="recommend-card">
    <view class="song-info" @click="$emit('play', song)">
      <view class="album-cover">
        <text class="music-icon">🎵</text>
      </view>
      <view class="song-detail">
        <text class="song-name">{{ song.song_name }}</text>
        <text class="artist">{{ song.artist }}</text>
        <view class="tags" v-if="validTags.length > 0">
          <text class="tag" v-for="tag in validTags" :key="tag">{{ tag }}</text>
        </view>
        <text class="match-reason" v-if="song.match_reason">
          {{ song.match_reason }}
        </text>
      </view>
      <view class="play-icon">▶</view>
    </view>
    <view class="actions">
      <button class="action-btn like" @click="onLike">👍 喜欢</button>
      <button class="action-btn skip" @click="onSkip">跳过</button>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Song {
  song_id: number
  song_name: string
  artist: string
  album: string
  music_file: string
  match_score: number
  match_reason: string
  tags: string[]
}

const props = defineProps<{
  song: Song
  historyId: number | null
}>()

const emit = defineEmits<{
  (e: 'play', song: Song): void
  (e: 'feedback', payload: { song: Song; feedbackType: string }): void
}>()

const validTags = computed(() => {
  return (props.song.tags || []).filter(tag => tag && tag !== '未知')
})

function onLike() {
  emit('feedback', { song: props.song, feedbackType: 'like' })
  uni.showToast({ title: '已记录', icon: 'success' })
}

function onSkip() {
  emit('feedback', { song: props.song, feedbackType: 'dislike' })
}
</script>

<style lang="scss" scoped>
.recommend-card {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 16rpx;
  padding: 24rpx;
  margin-bottom: 16rpx;
}

.song-info {
  display: flex;
  align-items: center;
  gap: 20rpx;
}

.album-cover {
  width: 100rpx;
  height: 100rpx;
  border-radius: 12rpx;
  background: linear-gradient(135deg, rgba(0, 212, 255, 0.3), rgba(123, 44, 191, 0.3));
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.music-icon {
  font-size: 40rpx;
}

.song-detail {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4rpx;
}

.song-name {
  font-size: 32rpx;
  color: #fff;
  font-weight: 500;
}

.artist {
  font-size: 26rpx;
  color: rgba(255, 255, 255, 0.6);
}

.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8rpx;
  margin-top: 8rpx;
}

.tag {
  padding: 4rpx 16rpx;
  background: rgba(0, 212, 255, 0.2);
  border-radius: 20rpx;
  font-size: 22rpx;
  color: #00d4ff;
}

.match-reason {
  font-size: 24rpx;
  color: rgba(255, 255, 255, 0.7);
  margin-top: 8rpx;
}

.play-icon {
  width: 64rpx;
  height: 64rpx;
  border-radius: 50%;
  background: linear-gradient(90deg, #00d4ff, #7b2cbf);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24rpx;
  flex-shrink: 0;
}

.actions {
  display: flex;
  gap: 16rpx;
  margin-top: 20rpx;
  padding-top: 20rpx;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.action-btn {
  flex: 1;
  padding: 16rpx;
  border: none;
  border-radius: 30rpx;
  font-size: 28rpx;
  color: #fff;
  background: rgba(255, 255, 255, 0.1);
}

.action-btn.like {
  background: linear-gradient(90deg, rgba(0, 212, 255, 0.3), rgba(123, 44, 191, 0.3));
}
</style>
```

### 6.5.7 AI 推荐入口

在首页 `src/pages/index/index.vue` 导航栏区域添加 AI 推荐入口：

```vue
<!-- 在导航栏 nav 中添加，与"歌曲"、"分类"并列 -->
<view
  class="nav-btn ai-recommend-btn"
  @click="goToRecommend"
>AI推荐</view>
```

```typescript
// 在 index.vue 的 methods 中添加
function goToRecommend() {
  uni.navigateTo({
    url: '/pages/recommend/recommend'
  })
}
```

**样式**（在 `.nav-btn` 样式中添加）：

```scss
&.ai-recommend-btn {
  background: linear-gradient(90deg, rgba(0, 212, 255, 0.4), rgba(123, 44, 191, 0.4));
  color: #fff;
  border: 1px solid rgba(0, 212, 255, 0.3);
}
```

### 6.5.8 播放器行为上报

**影响范围**：

| 文件 | 影响说明 |
|------|----------|
| `src/stores/player.ts` | 需要新增 `currentHistoryId` 状态和 `reportPlaybackFeedback()` 方法 |
| `src/components/PlayerBar.vue` | 需要监听播放完成事件并调用 store 的上报方法 |
| `src/utils/audioManager.ts` | 可能需要在音频播放完成时触发状态更新 |

**实现方案**：

**方案 A：在 stores/player.ts 中实现（推荐）**

```typescript
// stores/player.ts 新增状态和方法

// 新增状态
state: () => ({
  // ... 现有状态
  currentHistoryId: null as number | null  // 当前推荐的 history_id
}),

// 新增方法
actions: {
  /**
   * 设置当前推荐的 history_id
   */
  setCurrentHistoryId(historyId: number | null) {
    this.currentHistoryId = historyId
  },

  /**
   * 上报播放反馈
   * 在歌曲播放完成或被跳过时调用
   */
  async reportPlaybackFeedback(params: {
    playback_duration_seconds: number
    song_duration_seconds: number
    playback_completion_rate: number
    skipped: boolean
    looped: boolean
  }) {
    if (!this.currentHistoryId || !this.currentSong) return

    try {
      await recommendApi.submitFeedback({
        history_id: this.currentHistoryId,
        song_id: this.currentSong.song_id,
        ...params,
        play_source: 'recommend'
      })
    } catch (e) {
      console.error('上报播放反馈失败:', e)
    }
  },

  /**
   * 播放下一首（带反馈上报）
   */
  next() {
    // 先上报当前歌曲的播放反馈
    if (this.currentHistoryId && this.currentSong) {
      this.reportPlaybackFeedback({
        playback_duration_seconds: this.currentTime,
        song_duration_seconds: this.duration,
        playback_completion_rate: (this.currentTime / this.duration) * 100,
        skipped: true,
        looped: false
      })
    }
    // 执行切换
    // ... 原有逻辑
  }
}
```

**推荐页面的调用**：

在 `recommend.vue` 的 `handlePlay()` 中设置 `historyId`：

```typescript
function handlePlay(song: RecommendSong) {
  // 设置当前推荐的 history_id，用于后续播放时上报
  playerStore.setCurrentHistoryId(store.historyId)
  playerStore.playSong(song as any, store.results as any)
}
```

---

## 阶段五测试措施

| 测试项 | 验证方法 | 预期结果 | 状态 |
|--------|----------|----------|------|
| 前端编译 | `npm run build:h5` | 编译成功，生成 dist 文件 | ☐ |
| 推荐页面渲染 | 访问推荐页面 | 页面正常显示输入框和按钮 | ☐ |
| API 方法导入 | 检查 recommendApi 是否可被 import | 无错误 | ☐ |
| 组件导入 | 检查 RecommendCard.vue 是否可被 import | 无报错 | ☐ |
| 入口跳转 | 点击 AI 推荐入口 | 跳转到推荐页面 | ☐ |
