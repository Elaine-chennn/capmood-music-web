"""
错误追踪和日志记录
"""
import traceback
import logging
import json
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class ErrorTracker:
    """错误追踪器"""
    
    @staticmethod
    def log_error(
        task_id: str,
        error: Exception,
        context: str,
        retry_count: int = 0,
        extra_info: Optional[dict] = None
    ):
        """记录详细错误信息"""
        error_data = {
            "task_id": task_id,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
            "context": context,
            "timestamp": datetime.now().isoformat(),
            "retry_count": retry_count,
            "extra_info": extra_info or {}
        }
        
        # 记录到日志
        logger.error(f"任务错误详情: {json.dumps(error_data, ensure_ascii=False, indent=2)}")
        
        return error_data
    
    @staticmethod
    def get_user_friendly_message(error: Exception) -> str:
        """获取用户友好的错误消息"""
        error_messages = {
            "FileNotFoundError": "文件不存在，请重新上传",
            "ValueError": "参数错误，请检查输入",
            "TimeoutError": "处理超时，请稍后重试",
            "ConnectionError": "网络连接失败，请检查网络",
            "PermissionError": "权限不足，请联系管理员",
        }
        
        error_type = type(error).__name__
        return error_messages.get(error_type, "处理失败，请稍后重试")
