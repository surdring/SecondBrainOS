from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from sbo_core.errors import WeKnoraError, EmbeddingsError, LLMError


class DegradationStrategy(str, Enum):
    """降级策略枚举"""
    FAIL = "fail"  # 失败策略：返回结构化错误
    DEGRADE = "degrade"  # 降级策略：降级到更简单的模式


class ExternalServiceStatus(str, Enum):
    """外部服务状态"""
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    AUTH_FAILED = "auth_failed"
    RATE_LIMITED = "rate_limited"
    INVALID_RESPONSE = "invalid_response"


class DegradationInfo(BaseModel):
    """降级信息"""
    strategy: DegradationStrategy
    original_mode: str
    degraded_mode: str | None = None
    reason: str
    service: str
    status: ExternalServiceStatus
    details: dict[str, Any] | None = None


class QueryResponse(BaseModel):
    """查询响应模型"""
    answer_hint: str | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    degradation_info: DegradationInfo | None = None
    mode_used: str  # 实际使用的模式


class DegradationPolicy:
    """降级策略管理器"""
    
    def __init__(self, weknora_strategy: DegradationStrategy = DegradationStrategy.FAIL):
        self.weknora_strategy = weknora_strategy
    
    def handle_weknora_error(
        self,
        original_mode: str,
        error: WeKnoraError,
        fallback_mode: str = "fast",
    ) -> tuple[DegradationInfo | None, str]:
        """
        处理 WeKnora 错误
        
        Returns:
            (degradation_info, final_mode)
        """
        if original_mode != "deep":
            # 非 deep 模式不应该调用 WeKnora，直接失败
            return None, original_mode
        
        if self.weknora_strategy == DegradationStrategy.FAIL:
            # 失败策略：直接抛出错误
            raise error
        
        # 降级策略：降级到 fast 模式
        degradation_info = DegradationInfo(
            strategy=DegradationStrategy.DEGRADE,
            original_mode=original_mode,
            degraded_mode=fallback_mode,
            reason=f"WeKnora {error.code.value}: {error.message}",
            service="weknora",
            status=self._map_error_to_status(error.code),
            details=error.details,
        )
        
        return degradation_info, fallback_mode
    
    def _map_error_to_status(self, error_code: str) -> ExternalServiceStatus:
        """将错误码映射到服务状态"""
        if error_code == "weknora_unavailable":
            return ExternalServiceStatus.UNAVAILABLE
        elif error_code == "weknora_timeout":
            return ExternalServiceStatus.TIMEOUT
        elif error_code == "weknora_auth_failed":
            return ExternalServiceStatus.AUTH_FAILED
        elif error_code == "weknora_rate_limited":
            return ExternalServiceStatus.RATE_LIMITED
        elif error_code == "weknora_invalid_response":
            return ExternalServiceStatus.INVALID_RESPONSE
        else:
            return ExternalServiceStatus.UNAVAILABLE
    
    def check_weknora_availability(self, mode: str) -> bool:
        """检查 WeKnora 可用性"""
        if mode == "fast":
            # fast 模式不依赖 WeKnora
            return True
        
        if self.weknora_strategy == DegradationStrategy.FAIL:
            # 失败策略需要 WeKnora 可用
            return True  # 实际检查需要在调用时进行
        
        # 降级策略可以没有 WeKnora
        return True
    
    def create_degraded_response(
        self,
        original_mode: str,
        degraded_mode: str,
        evidence: list[dict[str, Any]],
        reason: str,
    ) -> QueryResponse:
        """创建降级响应"""
        degradation_info = DegradationInfo(
            strategy=DegradationStrategy.DEGRADE,
            original_mode=original_mode,
            degraded_mode=degraded_mode,
            reason=reason,
            service="weknora",
            status=ExternalServiceStatus.UNAVAILABLE,
        )
        
        return QueryResponse(
            evidence=evidence,
            degradation_info=degradation_info,
            mode_used=degraded_mode,
        )


# 全局降级策略实例
degradation_policy = DegradationPolicy()


def configure_degradation_strategy(weknora_strategy: DegradationStrategy) -> None:
    """配置降级策略"""
    global degradation_policy
    degradation_policy.weknora_strategy = weknora_strategy


def get_degradation_strategy() -> DegradationStrategy:
    """获取当前降级策略"""
    return degradation_policy.weknora_strategy


class ServiceHealthChecker:
    """服务健康检查器"""
    
    def __init__(self):
        self._service_status: dict[str, ExternalServiceStatus] = {}
    
    def update_service_status(self, service: str, status: ExternalServiceStatus) -> None:
        """更新服务状态"""
        self._service_status[service] = status
    
    def get_service_status(self, service: str) -> ExternalServiceStatus:
        """获取服务状态"""
        return self._service_status.get(service, ExternalServiceStatus.AVAILABLE)
    
    def is_service_available(self, service: str) -> bool:
        """检查服务是否可用"""
        status = self.get_service_status(service)
        return status == ExternalServiceStatus.AVAILABLE
    
    def handle_service_error(
        self,
        service: str,
        error: Exception,
        mode: str | None = None,
    ) -> tuple[DegradationInfo | None, str]:
        """
        处理服务错误
        
        Returns:
            (degradation_info, final_mode)
        """
        if service == "weknora":
            if not isinstance(error, WeKnoraError):
                error = WeKnoraError(
                    error_type="unavailable",
                    message=str(error),
                )
            return degradation_policy.handle_weknora_error(mode or "fast", error)
        
        # 其他服务的处理逻辑可以在这里扩展
        raise error


# 全局服务健康检查器
health_checker = ServiceHealthChecker()


def get_health_checker() -> ServiceHealthChecker:
    """获取健康检查器实例"""
    return health_checker
