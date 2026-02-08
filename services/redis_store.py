"""
Redis 任务存储服务
提供任务数据的持久化存储和管理
"""
import json
import logging
from typing import Optional, Dict
from datetime import datetime

logger = logging.getLogger(__name__)


class RedisTaskStore:
    """Redis 任务存储管理器"""
    
    def __init__(self, redis_client):
        self.redis = redis_client
        self.task_prefix = "task:"
        self.task_ttl = 86400  # 24小时过期
    
    async def save_task(self, task_id: str, task_data: dict) -> bool:
        """保存任务数据"""
        try:
            key = f"{self.task_prefix}{task_id}"
            # 添加更新时间
            task_data["updated_at"] = datetime.now().isoformat()
            
            # 同步 Redis 不需要 await
            self.redis.set(
                key,
                json.dumps(task_data),
                ex=self.task_ttl
            )
            logger.info(f"任务已保存到 Redis: {task_id}")
            return True
        except Exception as e:
            logger.error(f"保存任务失败 {task_id}: {e}")
            return False
    
    async def get_task(self, task_id: str) -> Optional[Dict]:
        """获取任务数据"""
        try:
            key = f"{self.task_prefix}{task_id}"
            data = self.redis.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"获取任务失败 {task_id}: {e}")
            return None
    
    async def update_task_status(self, task_id: str, status: str, **kwargs) -> bool:
        """更新任务状态"""
        try:
            task_data = await self.get_task(task_id)
            if not task_data:
                logger.warning(f"任务不存在: {task_id}")
                return False
            
            task_data["status"] = status
            task_data.update(kwargs)
            
            return await self.save_task(task_id, task_data)
        except Exception as e:
            logger.error(f"更新任务状态失败 {task_id}: {e}")
            return False
    
    async def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        try:
            key = f"{self.task_prefix}{task_id}"
            self.redis.delete(key)
            logger.info(f"任务已删除: {task_id}")
            return True
        except Exception as e:
            logger.error(f"删除任务失败 {task_id}: {e}")
            return False
    
    async def get_all_tasks(self) -> list:
        """获取所有任务（用于调试）"""
        try:
            keys = self.redis.keys(f"{self.task_prefix}*")
            tasks = []
            for key in keys:
                data = self.redis.get(key)
                if data:
                    tasks.append(json.loads(data))
            return tasks
        except Exception as e:
            logger.error(f"获取所有任务失败: {e}")
            return []
