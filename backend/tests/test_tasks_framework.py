"""
RQ 任务框架单元测试

测试覆盖：
1. 队列管理
2. 任务入队
3. 重试机制
4. 任务监控
5. 任务包装器
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone

from sbo_core.tasks_framework import (
    get_queue,
    get_queue_by_priority,
    get_all_queues,
    TaskPriority,
    TaskStatus,
    task_wrapper,
    TaskMonitor,
    QUEUE_DEFAULT,
    QUEUE_HIGH,
    QUEUE_LOW,
    QUEUE_ARCHIVE,
    QUEUE_LIFECYCLE,
    QUEUE_RERANK,
)


class TestQueueManagement:
    """测试队列管理"""
    
    def test_get_default_queue(self):
        """测试获取默认队列"""
        with patch('sbo_core.tasks_framework.get_redis_connection'):
            with patch('sbo_core.tasks_framework.Queue') as MockQueue:
                mock_queue = MagicMock()
                MockQueue.return_value = mock_queue
                
                queue = get_queue()
                
                MockQueue.assert_called_once()
                assert queue == mock_queue
    
    def test_get_queue_by_priority(self):
        """测试根据优先级获取队列"""
        with patch('sbo_core.tasks_framework.get_redis_connection') as mock_redis:
            mock_redis.return_value = MagicMock()
            with patch('sbo_core.tasks_framework.Queue') as MockQueue:
                mock_queue = MagicMock()
                MockQueue.return_value = mock_queue
                
                # 测试高优先级
                queue_high = get_queue_by_priority(TaskPriority.HIGH)
                MockQueue.assert_called_with(QUEUE_HIGH, connection=mock_redis.return_value)
                
                # 测试普通优先级
                queue_normal = get_queue_by_priority(TaskPriority.NORMAL)
                MockQueue.assert_called_with(QUEUE_DEFAULT, connection=mock_redis.return_value)
                
                # 测试低优先级
                queue_low = get_queue_by_priority(TaskPriority.LOW)
                MockQueue.assert_called_with(QUEUE_LOW, connection=mock_redis.return_value)
    
    def test_get_all_queues(self):
        """测试获取所有队列"""
        with patch('sbo_core.tasks_framework.get_redis_connection'):
            with patch('sbo_core.tasks_framework.Queue') as MockQueue:
                MockQueue.return_value = MagicMock()
                
                queues = get_all_queues()
                
                assert len(queues) == 6
                assert MockQueue.call_count == 6
    
    def test_queue_constants(self):
        """测试队列名称常量"""
        assert QUEUE_DEFAULT == "sbo_default"
        assert QUEUE_HIGH == "sbo_high"
        assert QUEUE_LOW == "sbo_low"
        assert QUEUE_ARCHIVE == "sbo_archive"
        assert QUEUE_LIFECYCLE == "sbo_lifecycle"
        assert QUEUE_RERANK == "sbo_rerank"


class TestTaskWrapper:
    """测试任务包装器"""
    
    def test_task_wrapper_basic(self):
        """测试基本任务包装"""
        
        @task_wrapper(max_retries=3, timeout=300)
        def sample_task(x: int, y: int) -> int:
            return x + y
        
        # 验证配置被保存
        assert hasattr(sample_task, '_task_config')
        assert sample_task._task_config['max_retries'] == 3
        assert sample_task._task_config['timeout'] == 300
        
        # 验证函数仍然可调用
        result = sample_task(1, 2)
        assert result == 3
    
    def test_task_wrapper_with_exception(self):
        """测试任务包装器异常处理"""
        
        call_count = 0
        
        @task_wrapper(max_retries=2, timeout=60)
        def failing_task():
            nonlocal call_count
            call_count += 1
            raise ValueError("Test error")
        
        # 验证异常被抛出
        with pytest.raises(ValueError, match="Test error"):
            failing_task()
        
        # 验证函数被调用一次（包装器不重试，依赖 RQ）
        assert call_count == 1
    
    def test_task_wrapper_preserves_metadata(self):
        """测试任务包装器保留函数元数据"""
        
        @task_wrapper(max_retries=3)
        def my_important_task(param1: str, param2: int = 10) -> dict:
            """这是一个重要的任务。"""
            return {"param1": param1, "param2": param2}
        
        # 验证文档字符串被保留
        assert my_important_task.__doc__ == "这是一个重要的任务。"
        # 验证函数名被保留
        assert my_important_task.__name__ == "my_important_task"


class TestTaskPriority:
    """测试任务优先级枚举"""
    
    def test_priority_values(self):
        """测试优先级值"""
        assert TaskPriority.HIGH.value == "high"
        assert TaskPriority.NORMAL.value == "normal"
        assert TaskPriority.LOW.value == "low"
    
    def test_status_values(self):
        """测试状态值"""
        assert TaskStatus.QUEUED.value == "queued"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.SUCCEEDED.value == "succeeded"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.RETRYING.value == "retrying"


class TestTaskMonitor:
    """测试任务监控"""
    
    def test_get_queue_stats(self):
        """测试获取队列统计"""
        with patch('sbo_core.tasks_framework.get_all_queues') as mock_get_queues:
            mock_queue = MagicMock()
            mock_queue.name = "test_queue"
            mock_queue.count = 5
            mock_queue.scheduled_job_registry.count = 2
            mock_queue.started_job_registry.count = 1
            mock_queue.finished_job_registry.count = 100
            mock_queue.failed_job_registry.count = 3
            mock_queue.deferred_job_registry.count = 0
            
            mock_get_queues.return_value = [mock_queue]
            
            stats = TaskMonitor.get_queue_stats()
            
            assert "test_queue" in stats
            assert stats["test_queue"]["queued"] == 5
            assert stats["test_queue"]["failed"] == 3
    
    def test_get_failed_jobs(self):
        """测试获取失败任务"""
        with patch('sbo_core.tasks_framework.get_queue') as mock_get_queue:
            mock_queue = MagicMock()
            mock_queue.failed_job_registry.get_job_ids.return_value = ["job1", "job2"]
            mock_queue.connection = MagicMock()
            mock_get_queue.return_value = mock_queue
            
            with patch('sbo_core.tasks_framework.Job') as MockJob:
                mock_job = MagicMock()
                mock_job.func_name = "test_task"
                mock_job.created_at = datetime.now(timezone.utc)
                mock_job.exc_info = "Error info"
                MockJob.fetch.return_value = mock_job
                
                failed_jobs = TaskMonitor.get_failed_jobs("test_queue", limit=10)
                
                assert len(failed_jobs) == 2
                assert failed_jobs[0]["job_id"] == "job1"


class TestRetryStrategy:
    """测试重试策略"""
    
    def test_retry_intervals(self):
        """测试重试间隔配置"""
        from sbo_core.tasks_framework import get_retry_strategy
        
        with patch('sbo_core.tasks_framework.Retry') as MockRetry:
            mock_retry = MagicMock()
            MockRetry.return_value = mock_retry
            
            retry = get_retry_strategy(max_retries=3, intervals=[30, 60, 120])
            
            MockRetry.assert_called_once_with(max=3, interval=[30, 60, 120])
            assert retry == mock_retry


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
