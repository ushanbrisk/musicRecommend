#!/usr/bin/env python3
"""
性能基准测试

测试两阶段推荐的响应时间性能

性能目标：
    - 向量召回：< 100 ms
    - LLM 精排：< 2000 ms
    - 总响应时间：< 2500 ms

运行测试：
    # 确保后端服务已启动
    cd ~/code_project/music-project/backend
    ~/miniconda3/envs/music/bin/python app.py &

    # 运行基准测试
    ~/miniconda3/envs/music/bin/python /home/luke/code_project/musicRecommend/tests/test_benchmark.py
"""

import requests
import time
import statistics

BASE_URL = 'http://localhost:5000'


def benchmark_recommend():
    """性能基准测试"""
    test_queries = [
        "欢快的凯尔特音乐，有小提琴伴奏",
        "适合工作的轻音乐",
        "悲伤的钢琴曲",
        "激昂的摇滚音乐",
        "安静的钢琴曲，适合冥想",
        "古风音乐，优雅舒缓"
    ]

    latencies = []

    for query in test_queries:
        start = time.time()
        response = requests.post(
            'http://localhost:5000/api/recommend',
            json={'query': query, 'session_id': 'benchmark'}
        )
        latency = (time.time() - start) * 1000
        latencies.append(latency)

        result = response.json()
        print(f"查询: {query}")
        print(f"  响应时间: {latency:.0f} ms")
        print(f"  结果数量: {result.get('total', 0)}")
        print(f"  成功: {result.get('success', False)}")
        print()

    print("=" * 60)
    print("性能统计:")
    print(f"  平均响应时间: {statistics.mean(latencies):.0f} ms")
    print(f"  最小响应时间: {min(latencies):.0f} ms")
    print(f"  最大响应时间: {max(latencies):.0f} ms")
    if len(latencies) > 1:
        print(f"  标准差: {statistics.stdev(latencies):.0f} ms")
    print("=" * 60)

    print("\n性能目标检查:")
    avg_latency = statistics.mean(latencies)
    if avg_latency < 2500:
        print(f"  ✅ 平均响应时间 ({avg_latency:.0f} ms) < 目标 (2500 ms)")
    else:
        print(f"  ❌ 平均响应时间 ({avg_latency:.0f} ms) > 目标 (2500 ms)")


if __name__ == '__main__':
    benchmark_recommend()