"""
RQ Worker 入口点

支持多个专用队列：
- sbo_high: 高优先级任务（Cross-Encoder 重排、对话归档）
- sbo_default: 默认优先级任务（一般巩固任务）
- sbo_low: 低优先级任务（生命周期更新）
- sbo_archive: 对话归档专用队列
- sbo_lifecycle: 生命周期任务队列
- sbo_rerank: 重排任务队列
"""

from __future__ import annotations

import logging
import sys

from sbo_core.tasks_framework import run_worker, QUEUE_HIGH, QUEUE_DEFAULT, QUEUE_LOW
from sbo_core.tasks_framework import QUEUE_ARCHIVE, QUEUE_LIFECYCLE, QUEUE_RERANK

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

_logger = logging.getLogger("sbo_core.worker")


def main():
    """主入口点"""
    import argparse
    
    parser = argparse.ArgumentParser(description="SecondBrainOS RQ Worker")
    parser.add_argument(
        "--queues",
        nargs="+",
        default=None,
        help=f"队列名称列表，默认全部。可用: {QUEUE_HIGH}, {QUEUE_DEFAULT}, {QUEUE_LOW}, {QUEUE_ARCHIVE}, {QUEUE_LIFECYCLE}, {QUEUE_RERANK}"
    )
    parser.add_argument(
        "--no-scheduler",
        action="store_true",
        help="禁用调度器"
    )
    parser.add_argument(
        "--burst",
        action="store_true",
        help="Burst 模式（处理完当前任务后退出）"
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Worker 名称"
    )
    
    args = parser.parse_args()
    
    queues = args.queues
    with_scheduler = not args.no_scheduler
    burst = args.burst
    name = args.name
    
    _logger.info(f"Starting worker with queues={queues or 'all'}, scheduler={with_scheduler}, burst={burst}")
    
    run_worker(
        queues=queues,
        with_scheduler=with_scheduler,
        burst=burst,
        name=name,
    )


if __name__ == "__main__":
    main()
