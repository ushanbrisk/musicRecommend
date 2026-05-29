#!/usr/bin/env python3
"""
Embedding 测试脚本

用法:
    # 单模型测试（使用当前环境变量配置）
    ~/miniconda3/envs/music/bin/python tests/test_embedding.py

    # API 模式测试（强制使用 API）
    EMBEDDING_USE_LOCAL=false ~/miniconda3/envs/music/bin/python tests/test_embedding.py --api-only

    # 本地模式测试（强制使用本地）
    EMBEDDING_USE_LOCAL=true ~/miniconda3/envs/music/bin/python tests/test_embedding.py --local-only

    # 一致性测试（比较 API 和本地模型）
    ~/miniconda3/envs/music/bin/python tests/test_embedding.py --consistency
"""

import sys
import os
import subprocess
import tempfile
import json
from pathlib import Path

sys.path.insert(0, os.path.expanduser('~/code_project/music-project/backend'))

from services.llm_service import LLMService
from dotenv import load_dotenv
import numpy as np

# 加载环境变量
backend_env = os.path.expanduser('~/code_project/music-project/backend/.env')
load_dotenv(backend_env)


def cosine_similarity(a, b):
    """计算余弦相似度"""
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def vector_norm(v):
    """计算向量的 L2 范数"""
    return np.linalg.norm(v)


def test_embedding():
    """测试单一 embedding 生成"""
    print("\n" + "=" * 60)
    print("测试 Embedding 生成")
    print("=" * 60)

    llm = LLMService()
    mode = "本地模型" if llm.use_local else "API"
    print(f"当前模式: {mode}")

    test_text = "欢快的凯尔特音乐，有小提琴伴奏"
    print(f"测试文本: {test_text}")

    embedding = llm.generate_embedding(test_text)

    if embedding:
        print(f"✅ Embedding 生成成功")
        print(f"   向量维度: {len(embedding)}")
        print(f"   前5个值: {embedding[:5]}")
        print(f"   L2 范数: {vector_norm(embedding):.6f}")
        return True
    else:
        print("❌ Embedding 生成失败")
        return False


def test_api_vs_local_consistency():
    """测试 API 和本地模型生成的向量一致性（使用子进程隔离）"""
    print("\n" + "=" * 60)
    print("测试 API 与本地模型 Embedding 一致性")
    print("=" * 60)

    test_texts = [
        "欢快的凯尔特音乐，有小提琴伴奏",
        "安静的钢琴曲，适合冥想",
        "激烈的重金属摇滚",
        "温柔的爵士乐",
    ]

    api_embeddings = []
    local_embeddings = []

    python_path = str(Path.home() / "miniconda3/envs/music/bin/python")

    # 测试脚本模板 - 直接设置环境变量，不使用 dotenv
    test_script_template = '''
import sys
import os
sys.path.insert(0, '/home/luke/code_project/music-project/backend')

# 设置环境变量（不依赖 .env 文件）
os.environ['EMBEDDING_USE_LOCAL'] = '{use_local}'
os.environ['EMBEDDING_API_KEY'] = '{api_key}'
os.environ['EMBEDDING_PROVIDER_URL'] = '{provider_url}'
os.environ['EMBEDDING_MODEL_NAME'] = '{model_name}'
os.environ['LLM_PROVIDER_KEY'] = '{llm_key}'
os.environ['LLM_PROVIDER_URL'] = '{llm_url}'

from services.llm_service import LLMService
import json

llm = LLMService()
texts = {texts}
for text in texts:
    embedding = llm.generate_embedding(text)
    print(json.dumps({{'text': text, 'embedding': embedding}}))
'''

    # 从当前环境获取配置
    api_key = os.getenv('EMBEDDING_API_KEY', '')
    provider_url = os.getenv('EMBEDDING_PROVIDER_URL', '')
    model_name = os.getenv('EMBEDDING_MODEL_NAME', 'BAAI/bge-m3')
    llm_key = os.getenv('LLM_PROVIDER_KEY', '')
    llm_url = os.getenv('LLM_PROVIDER_URL', '')

    # 生成 API embeddings
    print("\n[1/2] 生成 API embedding...")
    test_script = test_script_template.format(
        use_local='false',
        api_key=api_key,
        provider_url=provider_url,
        model_name=model_name,
        llm_key=llm_key,
        llm_url=llm_url,
        texts=str(test_texts)
    )

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(test_script)
        api_script_path = f.name

    try:
        result = subprocess.run(
            [python_path, api_script_path],
            capture_output=True, text=True, timeout=300, cwd='/home/luke/code_project/musicRecommend'
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if line and not line.startswith('Loading'):
                    try:
                        data = json.loads(line)
                        api_embeddings.append(data['embedding'])
                        print(f"  ✅ API embedding 生成成功")
                    except json.JSONDecodeError:
                        pass
        else:
            print(f"  ❌ API 测试失败: {result.stderr[:500]}")
    except Exception as e:
        print(f"  ❌ API 测试异常: {e}")
    finally:
        os.unlink(api_script_path)

    # 生成本地 embeddings
    print("\n[2/2] 生成本地 embedding...")
    test_script = test_script_template.format(
        use_local='true',
        api_key=api_key,
        provider_url=provider_url,
        model_name=model_name,
        llm_key=llm_key,
        llm_url=llm_url,
        texts=str(test_texts)
    )

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(test_script)
        local_script_path = f.name

    try:
        result = subprocess.run(
            [python_path, local_script_path],
            capture_output=True, text=True, timeout=300, cwd='/home/luke/code_project/musicRecommend',
            env={**os.environ, 'PYTHONUNBUFFERED': '1'}
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if line and not line.startswith('Loading') and not line.startswith('Using'):
                    try:
                        data = json.loads(line)
                        local_embeddings.append(data['embedding'])
                        print(f"  ✅ 本地 embedding 生成成功")
                    except json.JSONDecodeError:
                        pass
        else:
            print(f"  ❌ 本地测试失败: {result.stderr[:500]}")
    except Exception as e:
        print(f"  ❌ 本地测试异常: {e}")
    finally:
        os.unlink(local_script_path)

    # 计算相似度
    print("\n" + "=" * 60)
    print("向量相似度对比结果")
    print("=" * 60)

    if len(api_embeddings) == 0 or len(local_embeddings) == 0:
        print("❌ 无法完成对比测试（embedding 生成失败）")
        return False

    all_passed = True
    api_norms = []
    local_norms = []

    for i, text in enumerate(test_texts):
        if i >= len(api_embeddings) or i >= len(local_embeddings):
            continue

        api_vec = np.array(api_embeddings[i])
        local_vec = np.array(local_embeddings[i])

        # 计算 L2 范数
        api_norm = vector_norm(api_vec)
        local_norm = vector_norm(local_vec)
        api_norms.append(api_norm)
        local_norms.append(local_norm)

        # 余弦相似度
        cos_sim = cosine_similarity(api_vec, local_vec)

        # 欧氏距离
        euclidean_dist = np.linalg.norm(api_vec - local_vec)

        # 判断是否通过（余弦相似度 > 0.99 视为通过）
        passed = cos_sim > 0.99

        if not passed:
            all_passed = False

        status = "✅ 通过" if passed else "⚠️  注意"
        print(f"\n文本: {text}")
        print(f"  API 向量 L2 范数: {api_norm:.6f}")
        print(f"  本地向量 L2 范数: {local_norm:.6f}")
        print(f"  余弦相似度: {cos_sim:.6f} (阈值 > 0.99) {status}")
        print(f"  欧氏距离: {euclidean_dist:.6f}")

    print("\n" + "=" * 60)
    print("分析结论")
    print("=" * 60)

    avg_api_norm = np.mean(api_norms)
    avg_local_norm = np.mean(local_norms)

    print(f"API 向量平均 L2 范数: {avg_api_norm:.6f}")
    print(f"本地向量平均 L2 范数: {avg_local_norm:.6f}")

    if all_passed:
        print("\n✅ 所有测试通过！API 和本地模型生成的向量基本一致")
    else:
        print("\n⚠️  API 和本地模型生成的向量存在差异")
        print("   可能原因：")
        print("   1. API 服务提供商（如 SiliconFlow）对模型做了定制化修改")
        print("   2. API 服务可能没有做 L2 归一化，而本地代码做了归一化")
        print("   3. 模型版本或配置可能略有不同")
        print("")
        print("   如果 API 和本地模型使用相同的模型（如都是 BAAI/bge-m3），")
        print("   但向量差异较大，建议：")
        print("   - 确认 API 提供商使用的是相同的模型版本")
        print("   - 或者在使用时对 API 返回的向量也进行 L2 归一化")

    print("=" * 60)

    return all_passed


if __name__ == '__main__':
    if '--consistency' in sys.argv:
        test_api_vs_local_consistency()
    elif '--api-only' in sys.argv:
        # 直接设置环境变量，不重新加载 dotenv（避免 .env 文件覆盖）
        os.environ['EMBEDDING_USE_LOCAL'] = 'false'
        test_embedding()
    elif '--local-only' in sys.argv:
        # 直接设置环境变量，不重新加载 dotenv（避免 .env 文件覆盖）
        os.environ['EMBEDDING_USE_LOCAL'] = 'true'
        test_embedding()
    else:
        test_embedding()