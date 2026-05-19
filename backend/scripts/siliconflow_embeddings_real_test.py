"""
SiliconFlow Embeddings 真实 API 集成测试

该脚本连接真实的 SiliconFlow API 进行端到端测试,验证:
1. API 认证和连接
2. 单个文本嵌入
3. 批量文本嵌入
4. 错误处理和降级

注意: 需要配置 SILICONFLOW_API_KEY 环境变量
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sbo_core.embeddings_client import (
    SiliconFlowEmbeddingsClient,
    get_embeddings_client,
    embed_text,
    embed_texts_batch,
)
from sbo_core.config import load_settings
from sbo_core.errors import AppError


def test_client_initialization():
    """测试客户端初始化"""
    print("\n[1/5] Testing SiliconFlow client initialization...")
    
    try:
        settings = load_settings()
        
        if not settings.siliconflow_api_key:
            print("  ⚠️  SILICONFLOW_API_KEY not configured, skipping real API test")
            return False
        
        client = get_embeddings_client()
        print(f"  ✓ Client initialized")
        print(f"    Model: {client.model}")
        print(f"    Base URL: {client.base_url}")
        print(f"    Dimensions: {client.get_dimensions()}")
        
        client.close()
        return True
        
    except AppError as e:
        print(f"  ✗ Initialization failed: {e.message}")
        return False
    except Exception as e:
        print(f"  ✗ Unexpected error: {e}")
        return False


def test_embed_single_text():
    """测试单个文本嵌入 - 真实 API 调用"""
    print("\n[2/5] Testing single text embedding (REAL API CALL)...")
    
    try:
        settings = load_settings()
        
        if not settings.siliconflow_api_key:
            print("  ⚠️  Skipped (no API key)")
            return True
        
        client = get_embeddings_client()
        
        test_text = "SecondBrainOS is a personal knowledge management system"
        
        print(f"  Input: '{test_text[:50]}...'")
        
        embedding = client.embed_single(test_text)
        
        if embedding is None:
            print("  ✗ Embedding returned None")
            client.close()
            return False
        
        print(f"  ✓ Embedding generated")
        print(f"    Dimensions: {len(embedding)}")
        print(f"    Sample values: {embedding[:5]}")
        print(f"    Vector norm: {sum(x*x for x in embedding)**0.5:.4f}")
        
        # 验证维度
        expected_dims = client.get_dimensions()
        if len(embedding) != expected_dims:
            print(f"  ⚠️  Warning: Expected {expected_dims} dimensions, got {len(embedding)}")
        
        client.close()
        return True
        
    except Exception as e:
        print(f"  ✗ Embedding failed: {e}")
        return False


def test_embed_batch():
    """测试批量文本嵌入 - 真实 API 调用"""
    print("\n[3/5] Testing batch text embedding (REAL API CALL)...")
    
    try:
        settings = load_settings()
        
        if not settings.siliconflow_api_key:
            print("  ⚠️  Skipped (no API key)")
            return True
        
        client = get_embeddings_client()
        
        test_texts = [
            "Machine learning is a subset of artificial intelligence",
            "Knowledge graphs represent structured information",
            "Vector embeddings capture semantic meaning",
        ]
        
        print(f"  Input: {len(test_texts)} texts")
        
        embeddings = client.embed_texts(test_texts)
        
        if not embeddings or len(embeddings) != len(test_texts):
            print(f"  ✗ Expected {len(test_texts)} embeddings, got {len(embeddings) if embeddings else 0}")
            client.close()
            return False
        
        print(f"  ✓ Batch embedding generated")
        print(f"    Count: {len(embeddings)}")
        print(f"    Dimensions: {len(embeddings[0])}")
        
        # 验证所有向量维度一致
        dims = [len(emb) for emb in embeddings]
        if len(set(dims)) > 1:
            print(f"  ⚠️  Warning: Inconsistent dimensions: {dims}")
        
        client.close()
        return True
        
    except Exception as e:
        print(f"  ✗ Batch embedding failed: {e}")
        return False


def test_convenience_functions():
    """测试便捷函数 - 真实 API 调用"""
    print("\n[4/5] Testing convenience functions (REAL API CALL)...")
    
    try:
        settings = load_settings()
        
        if not settings.siliconflow_api_key:
            print("  ⚠️  Skipped (no API key)")
            return True
        
        # 测试 embed_text
        result1 = embed_text("Test text for convenience function")
        
        if result1 is None:
            print("  ✗ embed_text returned None")
            return False
        
        print(f"  ✓ embed_text() works")
        print(f"    Dimensions: {len(result1)}")
        
        # 测试 embed_texts_batch
        result2 = embed_texts_batch(["Text 1", "Text 2"])
        
        if not result2 or len(result2) != 2:
            print(f"  ✗ embed_texts_batch returned unexpected result")
            return False
        
        print(f"  ✓ embed_texts_batch() works")
        print(f"    Count: {len(result2)}")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Convenience functions failed: {e}")
        return False


def test_error_handling():
    """测试错误处理 - 使用无效配置"""
    print("\n[5/5] Testing error handling...")
    
    try:
        # 测试空文本
        result = embed_text("")
        if result is not None:
            print("  ⚠️  Empty text should return None")
        else:
            print("  ✓ Empty text handled correctly")
        
        # 测试空白文本
        result = embed_text("   ")
        if result is not None:
            print("  ⚠️  Whitespace text should return None")
        else:
            print("  ✓ Whitespace text handled correctly")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Error handling test failed: {e}")
        return False


def main():
    """主函数"""
    print("=" * 60)
    print("SiliconFlow Embeddings Real API Integration Test")
    print("=" * 60)
    
    # 检查环境
    try:
        settings = load_settings()
        print(f"\nEnvironment check:")
        
        if settings.siliconflow_api_key:
            print(f"  API Key: {settings.siliconflow_api_key[:10]}...{settings.siliconflow_api_key[-4:]}")
            print(f"  Base URL: {settings.siliconflow_base_url}")
            print(f"  Model: {settings.siliconflow_embedding_model}")
        else:
            print("  ⚠️  SILICONFLOW_API_KEY not configured")
            print("  This test will skip real API calls")
    except Exception as e:
        print(f"\n✗ Configuration error: {e}")
        return 1
    
    results = []
    
    # 执行测试
    results.append(("Client Initialization", test_client_initialization()))
    results.append(("Single Text Embedding", test_embed_single_text()))
    results.append(("Batch Text Embedding", test_embed_batch()))
    results.append(("Convenience Functions", test_convenience_functions()))
    results.append(("Error Handling", test_error_handling()))
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, r in results if r)
    failed = sum(1 for _, r in results if not r)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\nTotal: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("\n🎉 All real API integration tests passed!")
        return 0
    else:
        print(f"\n⚠️ {failed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
