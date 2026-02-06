import logging
import time
import os
from datetime import datetime
from pathlib import Path
from services.gemini import GeminiService
from services.lyria import LyriaService
from models import TaskStatus

logger = logging.getLogger(__name__)

# 内存存储（生产环境建议用 Redis）
tasks_store = {}


async def process_image_to_music(task_id: str, image_data: bytes):
    """
    异步处理：图片 → Gemini → Lyria → 音乐
    
    Args:
        task_id: 任务 ID
        image_data: 图片二进制数据
    """
    gemini_service = GeminiService()
    lyria_service = LyriaService()
    
    # 更新状态为处理中
    tasks_store[task_id]["status"] = TaskStatus.PROCESSING
    tasks_store[task_id]["updated_at"] = datetime.now().isoformat()
    task_start_time = time.time()
    logger.info(f"[Task {task_id}] 开始处理")
    
    try:
        # 步骤0: 保存上传的照片
        static_dir = Path("static")
        static_dir.mkdir(exist_ok=True)
        image_filename = f"{task_id}.jpg"
        image_path = static_dir / image_filename
        
        with open(image_path, 'wb') as f:
            f.write(image_data)
        
        image_url = f"/static/{image_filename}"
        tasks_store[task_id]["image_url"] = image_url
        logger.info(f"[Task {task_id}] 照片已保存: {image_path}")
        
        # 步骤1: Gemini 分析图片
        logger.info(f"[Task {task_id}] 步骤1: 调用 Gemini 分析图片")
        gemini_step_start = time.time()
        gemini_config = await gemini_service.analyze_image(image_data)
        gemini_step_time = time.time() - gemini_step_start
        # 只保存 title 到任务存储
        tasks_store[task_id]["title"] = gemini_config.get('title', 'Untitled')
        logger.info(f"[Task {task_id}] ⏱️  步骤1完成，用时: {gemini_step_time:.2f} 秒")
        logger.info(f"[Task {task_id}] Gemini 分析完成: {gemini_config.get('title')}")
        
        # 步骤2: Lyria 生成音乐
        logger.info(f"[Task {task_id}] 步骤2: 调用 Lyria 生成音乐")
        lyria_step_start = time.time()
        audio_base64 = await lyria_service.generate_music(gemini_config)
        lyria_step_time = time.time() - lyria_step_start
        logger.info(f"[Task {task_id}] ⏱️  步骤2完成，用时: {lyria_step_time:.2f} 秒")
        
        # 保存音频文件到 static 目录
        static_dir = Path("static")
        static_dir.mkdir(exist_ok=True)
        audio_filename = f"{task_id}.wav"
        audio_path = static_dir / audio_filename
        lyria_service.save_audio_to_file(audio_base64, str(audio_path))
        logger.info(f"[Task {task_id}] 音频已保存: {audio_path}")
        
        # 生成访问 URL
        music_url = f"/static/{audio_filename}"
        
        # 更新为完成状态
        total_time = time.time() - task_start_time
        tasks_store[task_id]["status"] = TaskStatus.COMPLETED
        tasks_store[task_id]["music_url"] = music_url
        tasks_store[task_id]["updated_at"] = datetime.now().isoformat()
        logger.info(f"[Task {task_id}] ✅ 任务完成")
        logger.info(f"[Task {task_id}] ⏱️  总用时: {total_time:.2f} 秒 (Gemini: {gemini_step_time:.2f}s + Lyria: {lyria_step_time:.2f}s)")
        
    except Exception as e:
        # 错误处理
        error_msg = str(e)
        logger.error(f"[Task {task_id}] 任务失败: {error_msg}")
        tasks_store[task_id]["status"] = TaskStatus.FAILED
        tasks_store[task_id]["error"] = error_msg
        tasks_store[task_id]["updated_at"] = datetime.now().isoformat()
