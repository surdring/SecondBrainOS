"""
SiliconFlow Embeddings 客户端

功能：
1. 集成 SiliconFlow embeddings API
2. 提供同步和异步的 embedding 生成接口
3. 实现错误处理和重试机制
4. 支持批量 embedding 生成

依赖需求：3.5, 4.1.2
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from sbo_core.config import load_settings
from sbo_core.errors import EmbeddingsError, ErrorCode, AppError

_logger = logging.getLogger("sbo_core.embeddings_client")

# 默认配置
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_RETRIES = 3
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-m3"  # SiliconFlow 默认 embedding 模型


class SiliconFlowEmbeddingsClient:
    """SiliconFlow Embeddings API 客户端"""
    
    def __init__(self) -> None:
        settings = load_settings()
        
        self.api_key = settings.siliconflow_api_key
        self.base_url = settings.siliconflow_base_url or "https://api.siliconflow.cn/v1"
        self.model = settings.siliconflow_embedding_model or DEFAULT_EMBEDDING_MODEL
        
        # 配置校验
        if not self.api_key:
            _logger.error("SILICONFLOW_API_KEY is not configured")
            raise AppError(
                code=ErrorCode.CONFIG_MISSING,
                message="SILICONFLOW_API_KEY is required for embeddings",
                status_code=500
            )
        
        # 确保 base_url 不以 / 结尾
        self.base_url = self.base_url.rstrip("/")
        
        # 创建 HTTP 客户端
        self.client = httpx.Client(
            base_url=self.base_url,
            timeout=DEFAULT_TIMEOUT_SECONDS,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        )
        
        _logger.info(f"SiliconFlow embeddings client initialized (model={self.model})")
    
    def _make_request(self, texts: list[str]) -> dict[str, Any]:
        """向 SiliconFlow API 发送 embedding 请求"""
        endpoint = "/embeddings"
        
        payload = {
            "model": self.model,
            "input": texts,
            "encoding_format": "float",
        }
        
        try:
            response = self.client.post(endpoint, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            error_msg = f"SiliconFlow API HTTP error: {status_code}"
            
            if status_code == 401:
                raise EmbeddingsError(
                    error_type="auth_failed",
                    message="SiliconFlow authentication failed (invalid API key)",
                    details={"status_code": status_code}
                ) from e
            elif status_code == 429:
                raise EmbeddingsError(
                    error_type="rate_limited",
                    message="SiliconFlow rate limit exceeded",
                    details={"status_code": status_code}
                ) from e
            else:
                raise EmbeddingsError(
                    error_type="unavailable",
                    message=error_msg,
                    details={"status_code": status_code}
                ) from e
        except httpx.TimeoutException as e:
            raise EmbeddingsError(
                error_type="timeout",
                message="SiliconFlow API timeout",
                details={"timeout_seconds": DEFAULT_TIMEOUT_SECONDS}
            ) from e
        except httpx.RequestError as e:
            raise EmbeddingsError(
                error_type="unavailable",
                message=f"SiliconFlow API request failed: {str(e)}",
                details={"error": str(e)}
            ) from e
    
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        生成文本的向量嵌入
        
        Args:
            texts: 待嵌入的文本列表
            
        Returns:
            向量嵌入列表，每个嵌入是一个浮点数列表
            
        Raises:
            EmbeddingsError: 当 embedding 生成失败时
        """
        if not texts:
            return []
        
        # 过滤空文本
        valid_texts = [t for t in texts if t and t.strip()]
        if not valid_texts:
            return []
        
        _logger.debug(f"Generating embeddings for {len(valid_texts)} texts")
        
        try:
            response_data = self._make_request(valid_texts)
            
            # 解析响应
            embeddings = []
            for item in response_data.get("data", []):
                embedding = item.get("embedding")
                if embedding:
                    embeddings.append(embedding)
            
            if len(embeddings) != len(valid_texts):
                _logger.warning(
                    f"Mismatch between input count ({len(valid_texts)}) and "
                    f"output count ({len(embeddings)})"
                )
            
            _logger.debug(f"Successfully generated {len(embeddings)} embeddings")
            return embeddings
            
        except EmbeddingsError:
            raise
        except Exception as e:
            _logger.error(f"Unexpected error during embedding: {e}")
            raise EmbeddingsError(
                error_type="unavailable",
                message=f"Failed to generate embeddings: {str(e)}",
                details={"error": str(e)}
            ) from e
    
    def embed_single(self, text: str) -> list[float] | None:
        """
        生成单个文本的向量嵌入
        
        Args:
            text: 待嵌入的文本
            
        Returns:
            向量嵌入（浮点数列表），失败时返回 None
        """
        if not text or not text.strip():
            return None
        
        try:
            embeddings = self.embed_texts([text])
            return embeddings[0] if embeddings else None
        except EmbeddingsError as e:
            _logger.error(f"Failed to embed single text: {e.message}")
            return None
    
    def get_dimensions(self) -> int:
        """获取当前模型的向量维度"""
        # SiliconFlow 常用 embedding 模型的维度
        model_dims = {
            "BAAI/bge-m3": 1024,
            "BAAI/bge-large-zh-v1.5": 1024,
            "BAAI/bge-base-zh-v1.5": 768,
            "BAAI/bge-small-zh-v1.5": 512,
        }
        return model_dims.get(self.model, 1024)  # 默认 1024
    
    def close(self) -> None:
        """关闭 HTTP 客户端"""
        self.client.close()
    
    def __enter__(self) -> SiliconFlowEmbeddingsClient:
        return self
    
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


# 全局客户端实例（懒加载）
_client: SiliconFlowEmbeddingsClient | None = None


def get_embeddings_client() -> SiliconFlowEmbeddingsClient:
    """获取 SiliconFlow embeddings 客户端实例"""
    global _client
    if _client is None:
        _client = SiliconFlowEmbeddingsClient()
    return _client


def reset_embeddings_client() -> None:
    """重置客户端实例（用于测试）"""
    global _client
    if _client:
        _client.close()
    _client = None


def embed_text(text: str) -> list[float] | None:
    """
    便捷函数：生成单个文本的向量嵌入
    
    Args:
        text: 待嵌入的文本
        
    Returns:
        向量嵌入（浮点数列表），失败时返回 None
    """
    try:
        client = get_embeddings_client()
        return client.embed_single(text)
    except AppError:
        # 配置错误等，直接返回 None 不阻塞
        return None
    except Exception as e:
        _logger.error(f"Embedding failed: {e}")
        return None


def embed_texts_batch(texts: list[str]) -> list[list[float] | None]:
    """
    便捷函数：批量生成文本的向量嵌入
    
    Args:
        texts: 待嵌入的文本列表
        
    Returns:
        向量嵌入列表，失败的位置为 None
    """
    if not texts:
        return []
    
    try:
        client = get_embeddings_client()
        embeddings = client.embed_texts(texts)
        return embeddings
    except AppError:
        # 配置错误等，返回全 None 不阻塞
        return [None] * len(texts)
    except Exception as e:
        _logger.error(f"Batch embedding failed: {e}")
        return [None] * len(texts)
