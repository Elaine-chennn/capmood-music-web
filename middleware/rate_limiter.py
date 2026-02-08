"""
并发控制和速率限制中间件
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict

logger = logging.getLogger(__name__)


class TaskLimiter:
    """任务并发控制器"""
    
    def __init__(self, max_concurrent: int = 10):
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.active_tasks = 0
        self._lock = asyncio.Lock()
    
    async def acquire(self, task_id: str):
        """获取处理权限"""
        async with self._lock:
            self.active_tasks += 1
            logger.info(f"任务开始 {task_id}, 当前活跃: {self.active_tasks}/{self.max_concurrent}")
        
        await self.semaphore.acquire()
    
    async def release(self, task_id: str):
        """释放处理权限"""
        self.semaphore.release()
        
        async with self._lock:
            self.active_tasks -= 1
            logger.info(f"任务完成 {task_id}, 当前活跃: {self.active_tasks}/{self.max_concurrent}")
    
    def is_available(self) -> bool:
        """检查是否可以接受新任务"""
        return self.active_tasks < self.max_concurrent
    
    def get_status(self) -> Dict:
        """获取当前状态"""
        return {
            "active_tasks": self.active_tasks,
            "max_concurrent": self.max_concurrent,
            "available_slots": self.max_concurrent - self.active_tasks
        }


class RateLimiter:
    """IP 速率限制器"""
    
    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, list] = {}
    
    async def check_rate_limit(self, client_ip: str) -> bool:
        """检查是否超过速率限制"""
        now = datetime.now()
        
        if client_ip not in self.requests:
            self.requests[client_ip] = []
        
        # 清理过期请求
        self.requests[client_ip] = [
            req_time for req_time in self.requests[client_ip]
            if now - req_time < timedelta(seconds=self.window_seconds)
        ]
        
        # 检查是否超限
        if len(self.requests[client_ip]) >= self.max_requests:
            logger.warning(f"速率限制触发: {client_ip}")
            return False
        
        # 记录本次请求
        self.requests[client_ip].append(now)
        return True
    
    def get_remaining(self, client_ip: str) -> int:
        """获取剩余请求次数"""
        if client_ip not in self.requests:
            return self.max_requests
        return max(0, self.max_requests - len(self.requests[client_ip]))
