#!/usr/bin/env python3
"""
端到端推荐测试

测试两阶段推荐流程（向量召回 + LLM精排）

运行测试：
    # 确保后端服务已启动
    cd ~/code_project/music-project/backend
    ~/miniconda3/envs/music/bin/python app.py &

    # 运行测试
    ~/miniconda3/envs/music/bin/python /home/luke/code_project/musicRecommend/tests/test_recommend_e2e.py
"""

import requests
import json

BASE_URL = 'http://localhost:5000'


def test_recommend():
    """测试推荐接口"""

    print("=" * 60)
    print("测试1：复杂查询 - 欢快的凯尔特音乐，有小提琴伴奏")
    print("=" * 60)

    response = requests.post(
        f'{BASE_URL}/api/recommend',
        json={
            'query': '欢快的凯尔特音乐，有小提琴伴奏',
            'session_id': 'test_001',
            'max_results': 20
        }
    )

    print(f"状态码: {response.status_code}")
    result = response.json()
    print(f"成功: {result.get('success')}")
    print(f"结果数量: {result.get('total')}")
    print(f"响应时间: {result.get('latency_ms')} ms")
    print(f"history_id: {result.get('history_id')}")

    if result.get('results'):
        print("\n前3个结果:")
        for i, song in enumerate(result['results'][:3], 1):
            print(f"\n{i}. song_id: {song.get('song_id')}")
            print(f"   歌名: {song['song_name']} - {song['artist']}")
            print(f"   匹配度: {song.get('match_score', 0)}")
            print(f"   理由: {song.get('match_reason', '')}")

    print("\n" + "=" * 60)
    print("测试2：简单查询 - 适合工作的轻音乐")
    print("=" * 60)

    response = requests.post(
        f'{BASE_URL}/api/recommend',
        json={
            'query': '适合工作的轻音乐',
            'session_id': 'test_001'
        }
    )

    result = response.json()
    print(f"成功: {result.get('success')}")
    print(f"结果数量: {result.get('total')}")
    print(f"响应时间: {result.get('latency_ms')} ms")

    if result.get('results'):
        print("\n前3个结果:")
        for i, song in enumerate(result['results'][:3], 1):
            print(f"\n{i}. song_id: {song.get('song_id')}")
            print(f"   歌名: {song['song_name']} - {song['artist']}")
            print(f"   匹配度: {song.get('match_score', 0)}")
            print(f"   理由: {song.get('match_reason', '')}")

    print("\n" + "=" * 60)
    print("测试3：古诗词查询 - 明月几时有")
    print("=" * 60)

    response = requests.post(
        f'{BASE_URL}/api/recommend',
        json={
            'query': '明月几时有，把酒问青天',
            'session_id': 'test_002'
        }
    )

    result = response.json()
    print(f"成功: {result.get('success')}")
    print(f"结果数量: {result.get('total')}")
    print(f"响应时间: {result.get('latency_ms')} ms")

    if result.get('results'):
        print("\n前3个结果:")
        for i, song in enumerate(result['results'][:3], 1):
            print(f"\n{i}. song_id: {song.get('song_id')}")
            print(f"   歌名: {song['song_name']} - {song['artist']}")
            print(f"   匹配度: {song.get('match_score', 0)}")
            print(f"   理由: {song.get('match_reason', '')}")


if __name__ == '__main__':
    test_recommend()