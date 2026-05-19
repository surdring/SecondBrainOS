"""
Cross-Encoder 重排任务实现 - 4.1.2

功能：
1. 异步 rerank 任务（独立超时与并发控制）
2. 降级回 fusion 排序并记录审计日志
3. 混合评分（rerank 分数加权融合）
4. 符号查询保护（对高 BM25/lexical 命中设置保底阈值）
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any

from sbo_core.tasks_framework import task_wrapper, enqueue_task, QUEUE_RERANK, TaskPriority
from sbo_core.audit import audit_log
from sbo_core.config import load_settings
from sbo_core.errors import ErrorCode, AppError
from sbo_core.rerank_client import RerankClient, RerankResult

_logger = logging.getLogger("sbo_core.rerank_tasks")


@dataclass
class RerankCandidate:
    """重排候选"""
    evidence_id: str
    text: str
    source: str
    occurred_at: datetime
    scores: dict[str, float]
    original_rank: int


@dataclass
class RerankTaskResult:
    """重排任务结果"""
    candidates: list[RerankCandidate]
    rerank_applied: bool
    fallback_reason: str | None
    provider_used: str | None
    model_used: str | None
    processing_time_ms: int
    ab_test_variant: str | None = None  # A/B 测试分组


@dataclass
class HybridScoreConfig:
    """混合评分配置"""
    rerank_weight: float = 0.5  # rerank 分数权重
    preserve_original: bool = True  # 不完全覆盖原始相关性
    lexical_preservation_floor: float = 0.35  # 符号查询保底阈值
    symbolic_lexical_threshold: float = 0.6  # 触发保底的高 BM25 阈值


class CircuitBreakerState(Enum):
    """熔断器状态"""
    CLOSED = "closed"      # 正常状态，请求通过
    OPEN = "open"          # 熔断状态，拒绝请求
    HALF_OPEN = "half_open"  # 半开状态，允许测试请求


class CircuitBreaker:
    """熔断器 - 防止级联故障
    
    当连续失败次数达到阈值时，熔断器打开，
    在一段时间内拒绝请求，避免资源浪费和级联故障。
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_max_calls: int = 3,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: datetime | None = None
        self._half_open_calls = 0
        self._lock = asyncio.Lock()
    
    @property
    def state(self) -> CircuitBreakerState:
        """获取当前状态"""
        return self._state
    
    async def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """执行被保护的函数
        
        Args:
            func: 要执行的异步函数
            *args: 位置参数
            **kwargs: 关键字参数
            
        Returns:
            函数执行结果
            
        Raises:
            AppError: 当熔断器打开时
        """
        async with self._lock:
            await self._update_state()
            
            if self._state == CircuitBreakerState.OPEN:
                raise AppError(
                    code=ErrorCode.RERANK_FAILED,
                    message="Circuit breaker is open - rerank service temporarily unavailable",
                    status_code=503,
                    details={"circuit_state": self._state.value}
                )
            
            if self._state == CircuitBreakerState.HALF_OPEN:
                if self._half_open_calls >= self.half_open_max_calls:
                    raise AppError(
                        code=ErrorCode.RERANK_FAILED,
                        message="Circuit breaker half-open limit reached",
                        status_code=503,
                        details={"circuit_state": self._state.value}
                    )
                self._half_open_calls += 1
        
        # 在锁外执行调用
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure()
            raise
    
    async def _update_state(self):
        """更新熔断器状态"""
        if self._state == CircuitBreakerState.OPEN:
            # 检查是否已过恢复时间
            if self._last_failure_time:
                elapsed = (datetime.now(timezone.utc) - self._last_failure_time).total_seconds()
                if elapsed >= self.recovery_timeout:
                    _logger.info(f"Circuit breaker transitioning to HALF_OPEN after {elapsed:.0f}s")
                    self._state = CircuitBreakerState.HALF_OPEN
                    self._half_open_calls = 0
                    self._success_count = 0
    
    async def _on_success(self):
        """处理成功调用"""
        async with self._lock:
            if self._state == CircuitBreakerState.HALF_OPEN:
                self._success_count += 1
                # 半开状态下连续成功，关闭熔断器
                if self._success_count >= 2:
                    _logger.info("Circuit breaker transitioning to CLOSED (recovery successful)")
                    self._state = CircuitBreakerState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
            else:
                # 正常状态下，重置失败计数
                self._failure_count = 0
    
    async def _on_failure(self):
        """处理失败调用"""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = datetime.now(timezone.utc)
            
            if self._state == CircuitBreakerState.HALF_OPEN:
                # 半开状态下失败，重新打开
                _logger.warning(f"Circuit breaker transitioning to OPEN (failure in half-open)")
                self._state = CircuitBreakerState.OPEN
            elif self._failure_count >= self.failure_threshold:
                # 达到失败阈值，打开熔断器
                _logger.warning(
                    f"Circuit breaker transitioning to OPEN "
                    f"({self._failure_count} consecutive failures)"
                )
                self._state = CircuitBreakerState.OPEN
    
    def get_stats(self) -> dict[str, Any]:
        """获取熔断器统计信息"""
        return {
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "last_failure_time": self._last_failure_time.isoformat() if self._last_failure_time else None,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
        }


class RerankTaskService:
    """重排任务服务"""
    
    def __init__(self):
        self._config = HybridScoreConfig()
        self._semaphore: asyncio.Semaphore | None = None
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=5,      # 5次连续失败后熔断
            recovery_timeout=60,      # 60秒后尝试恢复
            half_open_max_calls=3,    # 半开状态最多3次测试
        )
        self._ab_test_config: ABTestConfig | None = None
        self._request_counter = 0
    
    def _load_ab_test_config(self) -> ABTestConfig | None:
        """加载 A/B 测试配置（从环境变量或配置中心）"""
        settings = load_settings()
        
        # 检查是否启用了 A/B 测试
        ab_test_enabled = getattr(settings, 'rerank_ab_test_enabled', False)
        if not ab_test_enabled:
            return None
        
        # 加载多 provider 配置
        providers = []
        primary_url = settings.rerank_provider_url
        primary_key = settings.rerank_api_key
        primary_model = settings.rerank_model_id or "default"
        
        if primary_url:
            providers.append({
                "name": "primary",
                "url": primary_url,
                "api_key": primary_key,
                "model": primary_model,
            })
        
        # 检查是否有备用 provider
        alt_url = getattr(settings, 'rerank_alt_provider_url', None)
        alt_key = getattr(settings, 'rerank_alt_api_key', None)
        alt_model = getattr(settings, 'rerank_alt_model_id', None)
        
        if alt_url:
            providers.append({
                "name": "alternative",
                "url": alt_url,
                "api_key": alt_key,
                "model": alt_model or primary_model,
            })
        
        if len(providers) < 2:
            _logger.warning("A/B test enabled but less than 2 providers configured")
            return None
        
        # 流量分配比例
        split_ratio = getattr(settings, 'rerank_ab_split_ratio', [0.5, 0.5])
        if len(split_ratio) != len(providers):
            split_ratio = [1.0 / len(providers)] * len(providers)
        
        return ABTestConfig(
            enabled=True,
            providers=providers,
            split_ratio=split_ratio,
            ab_test_id=getattr(settings, 'rerank_ab_test_id', 'default'),
        )
    
    def _select_ab_test_provider(self, query_hash: str | None = None) -> dict[str, Any] | None:
        """
        根据 A/B 测试策略选择 provider
        
        Args:
            query_hash: 查询哈希（用于一致性分流）
            
        Returns:
            选中的 provider 配置，或 None 表示不使用 A/B 测试
        """
        if self._ab_test_config is None:
            self._ab_test_config = self._load_ab_test_config()
        
        if not self._ab_test_config or not self._ab_test_config.enabled:
            return None
        
        providers = self._ab_test_config.providers
        split_ratio = self._ab_test_config.split_ratio
        
        # 使用一致性哈希或轮询进行分流
        if query_hash:
            # 基于查询哈希的一致性分流（同一查询总是分到同一组）
            import hashlib
            hash_val = int(hashlib.md5(query_hash.encode()).hexdigest(), 16)
            bucket = hash_val % 100
            cumulative = 0
            for i, ratio in enumerate(split_ratio):
                cumulative += int(ratio * 100)
                if bucket < cumulative:
                    return providers[i]
            return providers[-1]
        else:
            # 轮询分流
            self._request_counter += 1
            idx = self._request_counter % len(providers)
            return providers[idx]
    
    def _get_semaphore(self) -> asyncio.Semaphore:
        """获取并发控制信号量（从配置读取最大并发数）"""
        if self._semaphore is None:
            settings = load_settings()
            max_concurrent = settings.rerank_max_concurrent
            # 校验范围
            if not (1 <= max_concurrent <= 50):
                max_concurrent = 5  # 默认值
                _logger.warning(f"Invalid RERANK_MAX_CONCURRENT, using default: 5")
            self._semaphore = asyncio.Semaphore(max_concurrent)
            _logger.info(f"Rerank semaphore initialized with max_concurrent={max_concurrent}")
        return self._semaphore
    
    async def execute_rerank_task(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        is_symbolic: bool = False,
        ab_test_variant: str | None = None,  # 可选：指定 A/B 测试分组
    ) -> RerankTaskResult:
        """
        执行重排任务
        
        Args:
            query: 查询字符串
            candidates: 候选列表（fusion 后的结果）
            is_symbolic: 是否为符号查询
            ab_test_variant: 指定 A/B 测试分组（如 "primary" 或 "alternative"）
            
        Returns:
            RerankTaskResult 包含重排结果和降级信息
        """
        start_time = datetime.now(timezone.utc)
        settings = load_settings()
        
        if not settings.rerank_provider_url:
            # 没有配置重排服务，直接返回原始候选
            return RerankTaskResult(
                candidates=[self._dict_to_candidate(c, i) for i, c in enumerate(candidates)],
                rerank_applied=False,
                fallback_reason="rerank_not_configured",
                provider_used=None,
                model_used=None,
                processing_time_ms=0,
                ab_test_variant=None,
            )
        
        # 限制候选数量
        max_candidates = settings.rerank_max_candidates
        limited_candidates = candidates[:max_candidates]
        
        # 转换为内部格式
        rerank_candidates = [
            self._dict_to_candidate(c, i) for i, c in enumerate(limited_candidates)
        ]
        
        # A/B 测试：选择 provider
        query_hash = f"{query}:{len(candidates)}"
        selected_provider = None
        
        if ab_test_variant:
            # 使用指定的 variant
            ab_config = self._load_ab_test_config()
            if ab_config:
                for p in ab_config.providers:
                    if p["name"] == ab_test_variant:
                        selected_provider = p
                        break
        else:
            # 自动选择
            selected_provider = self._select_ab_test_provider(query_hash)
        
        # 确定最终使用的 provider 和配置
        if selected_provider:
            provider_url = selected_provider["url"]
            api_key = selected_provider["api_key"]
            model_id = selected_provider["model"]
            provider_name = selected_provider["name"]
            ab_test_group = self._ab_test_config.ab_test_id if self._ab_test_config else None
        else:
            provider_url = settings.rerank_provider_url
            api_key = settings.rerank_api_key
            model_id = settings.rerank_model_id or "default"
            provider_name = "default"
            ab_test_group = None
        
        provider_used = provider_url
        model_used = model_id
        
        try:
            # 定义实际的重排调用函数
            async def do_rerank():
                async with self._get_semaphore():
                    client = RerankClient(
                        base_url=provider_url,
                        api_key=api_key,
                        timeout_ms=settings.rerank_timeout_ms,
                    )
                    
                    payload_candidates = [
                        {
                            "evidence_id": c.evidence_id,
                            "text": c.text,
                            "source": c.source,
                            "occurred_at": c.occurred_at.isoformat(),
                            "scores": c.scores,
                        }
                        for c in rerank_candidates
                    ]
                    
                    return await client.rerank(
                        query=query,
                        candidates=payload_candidates,
                        model=model_id or None,
                    )
            
            # 使用熔断器保护重排调用
            results = await self._circuit_breaker.call(do_rerank)
            
            # 应用混合评分
            reranked_candidates = self._apply_hybrid_scoring(
                rerank_candidates, results, is_symbolic, settings.rerank_weight
            )
            
            # 保持未参与重排的候选
            if len(candidates) > len(limited_candidates):
                remaining = [
                    self._dict_to_candidate(c, i + len(limited_candidates))
                    for i, c in enumerate(candidates[len(limited_candidates):])
                ]
                reranked_candidates.extend(remaining)
            
            duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            
            # 审计日志（包含 A/B 测试信息）
            audit_log(
                event="rerank.task",
                outcome="success",
                details={
                    "provider": provider_used,
                    "model": model_used,
                    "provider_name": provider_name,
                    "candidates_in": len(limited_candidates),
                    "candidates_out": len(results),
                    "duration_ms": duration_ms,
                    "is_symbolic": is_symbolic,
                    "ab_test_group": ab_test_group,
                    "ab_test_variant": provider_name if ab_test_group else None,
                }
            )
            
            return RerankTaskResult(
                candidates=reranked_candidates,
                rerank_applied=True,
                fallback_reason=None,
                provider_used=provider_used,
                model_used=model_used,
                processing_time_ms=duration_ms,
                ab_test_variant=provider_name if ab_test_group else None,
            )
            
        except AppError as e:
            # 重排失败，降级到 fusion 结果
            fallback_reason = self._classify_fallback_reason(e)
            duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            
            _logger.warning(
                f"Rerank failed, falling back to fusion: {e.message} (reason={fallback_reason})"
            )
            
            # 审计日志记录降级
            audit_log(
                event="rerank.task",
                outcome="degrade",
                details={
                    "provider": provider_used,
                    "model": model_used,
                    "fallback_reason": fallback_reason,
                    "error_code": e.code if hasattr(e, 'code') else None,
                    "error_message": e.message if hasattr(e, 'message') else str(e),
                    "duration_ms": duration_ms,
                }
            )
            
            return RerankTaskResult(
                candidates=[self._dict_to_candidate(c, i) for i, c in enumerate(candidates)],
                rerank_applied=False,
                fallback_reason=fallback_reason,
                provider_used=provider_used,
                model_used=model_used,
                processing_time_ms=duration_ms,
                ab_test_variant=provider_name if ab_test_group else None,
            )
        
        except Exception as e:
            # 意外错误，降级
            fallback_reason = "unexpected_error"
            duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            
            _logger.error(f"Rerank unexpected error: {e}")
            
            audit_log(
                event="rerank.task",
                outcome="degrade",
                details={
                    "provider": provider_used,
                    "model": model_used,
                    "fallback_reason": fallback_reason,
                    "error": str(e),
                    "duration_ms": duration_ms,
                }
            )
            
            return RerankTaskResult(
                candidates=[self._dict_to_candidate(c, i) for i, c in enumerate(candidates)],
                rerank_applied=False,
                fallback_reason=fallback_reason,
                provider_used=provider_used,
                model_used=model_used,
                processing_time_ms=duration_ms,
                ab_test_variant=provider_name if ab_test_group else None,
            )
    
    def _apply_hybrid_scoring(
        self,
        candidates: list[RerankCandidate],
        rerank_results: list[RerankResult],
        is_symbolic: bool,
        rerank_weight: float,
    ) -> list[RerankCandidate]:
        """
        应用混合评分策略
        
        混合公式：final_score = (1 - w) * fusion_score + w * rerank_score
        
        符号查询保护：
        - 如果原始 BM25/lexical 分数 >= threshold，设置保底 floor
        """
        rerank_map: dict[str, float] = {r.evidence_id: r.score for r in rerank_results}
        
        for candidate in candidates:
            fusion_score = candidate.scores.get("fusion_score", 0.0)
            
            if candidate.evidence_id in rerank_map:
                rerank_score = rerank_map[candidate.evidence_id]
                
                # 混合评分（rerank 不完全覆盖原始相关性）
                final_score = (1.0 - rerank_weight) * fusion_score + rerank_weight * rerank_score
                
                # 符号查询保护：高 BM25 命中设置保底阈值
                if is_symbolic:
                    bm25_score = candidate.scores.get("bm25_score", 0.0)
                    lexical_score = candidate.scores.get("lexical_score", bm25_score)
                    
                    if lexical_score >= self._config.symbolic_lexical_threshold:
                        final_score = max(final_score, self._config.lexical_preservation_floor)
                        candidate.scores["preservation_floor_applied"] = 1.0
                
                candidate.scores["rerank_score"] = rerank_score
                candidate.scores["fusion_score"] = fusion_score
                candidate.scores["hybrid_score"] = final_score
                candidate.scores["rerank_weight"] = rerank_weight
            else:
                # 未参与重排的候选保持原分数
                final_score = fusion_score
                candidate.scores["rerank_missing"] = 1.0
            
            candidate.scores["final_score"] = final_score
        
        # 按最终分数排序
        candidates.sort(key=lambda x: x.scores.get("final_score", 0.0), reverse=True)
        
        return candidates
    
    def _classify_fallback_reason(self, error: AppError) -> str:
        """分类降级原因"""
        code = getattr(error, 'code', None)
        message = getattr(error, 'message', str(error)).lower()
        details = getattr(error, 'details', {})
        
        if code == ErrorCode.RERANK_FAILED:
            if "timeout" in message:
                return "timeout"
            elif "unavailable" in message or "server error" in message:
                return "5xx"
            elif "5" in str(details.get("status_code", "")):
                return "5xx"
            elif "auth" in message:
                return "auth_failed"
        
        return "provider_error"
    
    def _dict_to_candidate(self, data: dict[str, Any], rank: int) -> RerankCandidate:
        """将字典转换为 RerankCandidate"""
        occurred_at_str = data.get("occurred_at", datetime.now(timezone.utc).isoformat())
        if isinstance(occurred_at_str, str):
            occurred_at = datetime.fromisoformat(occurred_at_str.replace('Z', '+00:00'))
        else:
            occurred_at = datetime.now(timezone.utc)
        
        return RerankCandidate(
            evidence_id=data.get("evidence_id", ""),
            text=data.get("text", ""),
            source=data.get("source", ""),
            occurred_at=occurred_at,
            scores=data.get("scores", {}),
            original_rank=rank,
        )


# 全局服务实例
rerank_service = RerankTaskService()


@task_wrapper(max_retries=2, timeout=60)  # 60s timeout per spec
def rerank_candidates_task(
    query: str,
    candidates: list[dict[str, Any]],
    is_symbolic: bool = False,
) -> dict[str, Any]:
    """
    RQ 异步重排任务
    
    该任务可以异步执行重排，适用于：
    - 离线重排优化
    - 批量文档重排
    - 预热缓存
    
    Args:
        query: 查询字符串
        candidates: fusion 后的候选列表
        is_symbolic: 是否为符号查询
        
    Returns:
        重排结果字典
    """
    import asyncio
    
    result = asyncio.run(rerank_service.execute_rerank_task(query, candidates, is_symbolic))
    
    return {
        "candidates": [
            {
                "evidence_id": c.evidence_id,
                "text": c.text,
                "source": c.source,
                "occurred_at": c.occurred_at.isoformat(),
                "scores": c.scores,
                "original_rank": c.original_rank,
            }
            for c in result.candidates
        ],
        "rerank_applied": result.rerank_applied,
        "fallback_reason": result.fallback_reason,
        "provider_used": result.provider_used,
        "model_used": result.model_used,
        "processing_time_ms": result.processing_time_ms,
        "ab_test_variant": result.ab_test_variant,
    }


def enqueue_rerank_task(
    query: str,
    candidates: list[dict[str, Any]],
    is_symbolic: bool = False,
    job_id: str | None = None,
) -> Any:
    """
    将重排任务入队
    
    Args:
        query: 查询字符串
        candidates: 候选列表
        is_symbolic: 是否为符号查询
        job_id: 自定义 job ID
        
    Returns:
        RQ Job 实例
    """
    return enqueue_task(
        rerank_candidates_task,
        query,
        candidates,
        is_symbolic,
        queue_name=QUEUE_RERANK,
        priority=TaskPriority.HIGH,
        job_id=job_id,
        timeout=60,  # 与装饰器保持一致
        max_retries=2,
        retry_intervals=[10, 30],  # 10 秒、30 秒后重试
    )
