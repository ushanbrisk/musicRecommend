# 数据库表创建指南

本文档说明如何为 musicRecommend 项目创建数据库表。

## 与原有项目的关系

本项目的数据库表**独立于** `~/code_project/music-project/database/schema.sql` 中原有的表结构。

| 项目 | 表结构来源 | 包含的表 |
|------|-----------|----------|
| 原有项目 | `music-project/database/schema.sql` | songs, playlists, artists, song_playlist, comments, male_artists, female_artists, artist_songs_relation |
| 本项目 | `musicRecommend/database/schema.sql` | music_features, recommendation_history, recommendation_feedback |

两套表结构**共存于同一个数据库**，通过 `song_id` 外键关联。

## 前提条件

1. 已连接到 PostgreSQL 数据库
2. 数据库中已有 `songs` 表（来自原有项目的 schema.sql）

## 创建步骤

### 方法一：执行完整 SQL 文件（推荐）

```bash
# 1. 连接到数据库
psql -h localhost -U postgres -d musicdb

# 2. 执行 schema.sql
\i /home/luke/code_project/musicRecommend/database/schema.sql

# 3. 验证表创建成功
\dt music_features recommendation_history recommendation_feedback
```

### 方法二：逐个执行 CREATE TABLE 语句

如果只需要创建特定表，可以在 psql 中直接执行对应的 CREATE TABLE 语句（见 schema.sql 文件）。

## 验证创建成功

```sql
-- 检查表是否存在
\dt music_features recommendation_history recommendation_feedback

-- 验证表结构
\d music_features
\d recommendation_history
\d recommendation_feedback

-- 测试查询（应返回空结果但无报错）
SELECT COUNT(*) FROM music_features LIMIT 1;
SELECT COUNT(*) FROM recommendation_history LIMIT 1;
SELECT COUNT(*) FROM recommendation_feedback LIMIT 1;
```

## 表结构说明

### music_features
存储歌曲的特征信息，用于推荐系统匹配。

### recommendation_history
存储推荐历史记录，分析用户行为。

### recommendation_feedback
存储用户对推荐结果的反馈（播放完成率、跳过、循环等）。

## 后续维护

如需删除所有本项目的表，执行：

```sql
DROP TABLE IF EXISTS recommendation_feedback;
DROP TABLE IF EXISTS recommendation_history;
DROP TABLE IF EXISTS music_features;
```