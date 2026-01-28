import logging
from datetime import datetime
from services.gemini import GeminiService
from services.suno import SunoService
from models import TaskStatus

logger = logging.getLogger(__name__)

# 内存存储（生产环境建议用 Redis）
tasks_store = {}


async def process_image_to_music(task_id: str, image_data: bytes):
    """
    异步处理：图片 → Gemini → Suno → 音乐
    
    Args:
        task_id: 任务 ID
        image_data: 图片二进制数据
    """
    gemini_service = GeminiService()
    suno_service = SunoService()
    
    # 更新状态为处理中
    tasks_store[task_id]["status"] = TaskStatus.PROCESSING
    tasks_store[task_id]["updated_at"] = datetime.now().isoformat()
    logger.info(f"[Task {task_id}] 开始处理")
    
    try:
        # 步骤1: Gemini 分析图片
        logger.info(f"[Task {task_id}] 步骤1: 调用 Gemini 分析图片")
        gemini_config = await gemini_service.analyze_image(image_data)
        tasks_store[task_id]["gemini_config"] = gemini_config
        logger.info(f"[Task {task_id}] Gemini 分析完成: {gemini_config.get('title')}")
        
        # 步骤2: Suno 生成音乐
        logger.info(f"[Task {task_id}] 步骤2: 调用 Suno 生成音乐")
        music_url = await suno_service.generate_music(gemini_config)
        
        # 更新为完成状态
        tasks_store[task_id]["status"] = TaskStatus.COMPLETED
        tasks_store[task_id]["music_url"] = music_url
        tasks_store[task_id]["updated_at"] = datetime.now().isoformat()
        logger.info(f"[Task {task_id}] 任务完成: {music_url}")
        
    except Exception as e:
        # 错误处理
        error_msg = str(e)
        logger.error(f"[Task {task_id}] 任务失败: {error_msg}")
        tasks_store[task_id]["status"] = TaskStatus.FAILED
        tasks_store[task_id]["error"] = error_msg
        tasks_store[task_id]["updated_at"] = datetime.now().isoformat()
