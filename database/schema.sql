-- 本项目新增数据库表结构
-- PostgreSQL
--
-- 本文件包含 musicRecommend 项目独立创建的表
-- 与 ~/code_project/music-project/database/schema.sql 中的原有表相互独立
-- 两套表结构共存于同一数据库，通过 song_id 外键关联

-- ============================================
-- 6.2 阶段二：music_features 表
-- ============================================
-- 存储歌曲的特征信息，用于推荐系统

CREATE TABLE IF NOT EXISTS music_features (
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
CREATE INDEX IF NOT EXISTS idx_music_features_genre ON music_features(genre);
CREATE INDEX IF NOT EXISTS idx_music_features_mood ON music_features(mood);
CREATE INDEX IF NOT EXISTS idx_music_features_scene ON music_features(scene);
CREATE INDEX IF NOT EXISTS idx_music_features_song_id ON music_features(song_id);

-- ============================================
-- 6.2 阶段二：recommendation_history 表
-- ============================================
-- 存储推荐历史记录，用于分析用户行为和优化推荐算法

CREATE TABLE IF NOT EXISTS recommendation_history (
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
CREATE INDEX IF NOT EXISTS idx_history_session ON recommendation_history(session_id);
CREATE INDEX IF NOT EXISTS idx_history_user ON recommendation_history(user_id);
CREATE INDEX IF NOT EXISTS idx_history_query_time ON recommendation_history(query_timestamp);

-- ============================================
-- 6.2 阶段二：recommendation_feedback 表
-- ============================================
-- 存储用户对推荐结果的反馈，用于持续优化推荐质量

CREATE TABLE IF NOT EXISTS recommendation_feedback (
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
CREATE INDEX IF NOT EXISTS idx_feedback_history ON recommendation_feedback(history_id);
CREATE INDEX IF NOT EXISTS idx_feedback_song ON recommendation_feedback(song_id);
CREATE INDEX IF NOT EXISTS idx_feedback_type ON recommendation_feedback(feedback_type);
CREATE INDEX IF NOT EXISTS idx_feedback_skipped ON recommendation_feedback(skipped);
CREATE INDEX IF NOT EXISTS idx_feedback_completion ON recommendation_feedback(playback_completion_rate);