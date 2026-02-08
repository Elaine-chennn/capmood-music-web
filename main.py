from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Form  # pyright: ignore[reportMissingImports]
from fastapi.middleware.cors import CORSMiddleware  # pyright: ignore[reportMissingImports]
from fastapi.staticfiles import StaticFiles  # pyright: ignore[reportMissingImports]
from fastapi.responses import FileResponse  # pyright: ignore[reportMissingImports]
import uuid
import os
import logging
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from models import TaskResponse, TaskDetail, TaskStatus
from tasks import process_image_to_music, tasks_store
from services.video import VideoService
from config import get_settings

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title="MelodySnap API",
    description="图片转音乐 API 服务 (Gemini 3 Pro Preview + Suno V5)",
    version="2.0.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境改为具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def cleanup_old_files():
    """
    定时清理过期的视频文件
    
    - 默认清理超过24小时的视频文件
    - 每小时执行一次清理
    """
    while True:
        try:
            cutoff = datetime.now() - timedelta(hours=24)
            deleted_count = 0
            
            if VIDEOS_DIR.exists():
                for file in VIDEOS_DIR.glob("*.mp4"):
                    try:
                        file_time = datetime.fromtimestamp(file.stat().st_mtime)
                        if file_time < cutoff:
                            file.unlink()
                            deleted_count += 1
                            logger.info(f"已删除过期视频: {file.name}")
                    except Exception as e:
                        logger.error(f"删除文件失败 {file.name}: {str(e)}")
            
            if deleted_count > 0:
                logger.info(f"文件清理完成，共删除 {deleted_count} 个过期视频")
            
        except Exception as e:
            logger.error(f"文件清理任务出错: {str(e)}")
        
        # 每小时执行一次
        await asyncio.sleep(3600)


@app.on_event("startup")
async def startup_event():
    """启动时显示配置信息并启动后台清理任务"""
    logger.info("=" * 50)
    logger.info(f"MelodySnap API 启动")
    logger.info(f"Gemini 模型: {settings.GEMINI_MODEL}")
    logger.info(f"Suno 模型: {settings.SUNO_MODEL}")
    logger.info(f"环境: {settings.ENV}")
    logger.info("=" * 50)
    
    # 启动文件清理后台任务
    asyncio.create_task(cleanup_old_files())
    logger.info("文件清理后台任务已启动（每小时清理一次超过24小时的视频）")


@app.post("/api/generate-music", response_model=TaskResponse)
async def generate_music(
    background_tasks: BackgroundTasks,
    image: UploadFile = File(...)
):
    """
    上传图片，使用 Gemini 3 Pro Preview 分析并通过 Suno V5 生成音乐
    
    - **image**: 图片文件（支持 jpg, png, webp）
    
    返回 task_id 用于查询生成状态
    """
    try:
        logger.info(f"收到图片上传请求: filename={image.filename}, content_type={image.content_type}")
        
        # 验证文件类型
        if not image.content_type or not image.content_type.startswith('image/'):
            logger.error(f"无效的文件类型: {image.content_type}")
            raise HTTPException(status_code=400, detail="只支持图片文件")
        
        # 读取图片数据
        image_data = await image.read()
        logger.info(f"图片大小: {len(image_data)} bytes")
        
        # 验证文件大小
        if len(image_data) > settings.MAX_IMAGE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"图片文件过大（最大 {settings.MAX_IMAGE_SIZE / 1024 / 1024}MB）"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理图片上传时出错: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"处理图片时出错: {str(e)}")
    
    # 生成任务 ID
    task_id = str(uuid.uuid4())
    
    # 初始化任务
    now = datetime.now().isoformat()
    tasks_store[task_id] = {
        "task_id": task_id,
        "status": TaskStatus.PENDING,
        "gemini_config": None,
        "music_url": None,
        "error": None,
        "created_at": now,
        "updated_at": now,
        "model_info": {
            "gemini": settings.GEMINI_MODEL,
            "suno": settings.SUNO_MODEL
        }
    }
    
    logger.info(f"创建任务 {task_id}，图片大小: {len(image_data)} bytes")
    
    # 添加到后台任务
    background_tasks.add_task(process_image_to_music, task_id, image_data)
    
    return TaskResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        message="任务已创建，正在使用 Gemini 3 Pro Preview 和 Suno V5 处理中",
        model_info={
            "gemini": settings.GEMINI_MODEL,
            "suno": settings.SUNO_MODEL
        }
    )


@app.get("/api/task/{task_id}", response_model=TaskDetail)
async def get_task_status(task_id: str):
    """
    查询任务状态
    
    - **task_id**: 任务 ID
    """
    if task_id not in tasks_store:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return tasks_store[task_id]


@app.delete("/api/task/{task_id}")
async def delete_task(task_id: str):
    """删除任务记录"""
    if task_id not in tasks_store:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    del tasks_store[task_id]
    logger.info(f"删除任务 {task_id}")
    return {"message": "任务已删除"}


@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "ok",
        "tasks_count": len(tasks_store),
        "models": {
            "gemini": settings.GEMINI_MODEL,
            "suno": settings.SUNO_MODEL
        },
        "configuration": {
            "gemini_configured": bool(settings.GEMINI_API_KEY),
            "suno_configured": bool(settings.SUNO_API_TOKEN)
        }
    }


@app.post("/api/generate-share-video")
async def generate_share_video(
    image: UploadFile = File(...),
    audio_url: str = Form(...),
    title: str = Form("Melody Snap Song"),
    duration: int = Form(15),
):
    """
    Generate a share video by composing an image with audio.
    
    - **image**: Card image (PNG from ViewShot)
    - **audio_url**: URL to the music file
    - **title**: Song title
    - **duration**: Video duration in seconds (max 30)
    
    Returns the video file URL.
    """
    try:
        logger.info(f"收到视频生成请求: title={title}, duration={duration}s")
        
        # Read image data
        image_data = await image.read()
        if len(image_data) > settings.MAX_IMAGE_SIZE:
            raise HTTPException(status_code=400, detail="Image too large")
        
        # Clamp duration
        duration = min(max(duration, 5), 30)
        
        # Generate video
        video_service = VideoService()
        video_path = await video_service.create_share_video(
            image_data=image_data,
            audio_url=audio_url,
            title=title,
            duration=duration,
        )
        
        # Return video as a downloadable file
        video_filename = os.path.basename(video_path)
        video_url = f"/static/videos/{video_filename}"
        
        logger.info(f"视频生成完成: {video_url}")
        return {
            "status": "completed",
            "video_url": video_url,
            "video_filename": video_filename,
        }
        
    except Exception as e:
        logger.error(f"视频生成失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Video generation failed: {str(e)}")


# Serve generated video files
VIDEOS_DIR = Path(__file__).parent / "generated_videos"
VIDEOS_DIR.mkdir(exist_ok=True)
app.mount("/static/videos", StaticFiles(directory=str(VIDEOS_DIR)), name="videos")


@app.get("/")
async def root():
    """API 信息"""
    return {
        "service": "MelodySnap API",
        "version": "2.1.0",
        "models": {
            "gemini": settings.GEMINI_MODEL,
            "suno": settings.SUNO_MODEL
        },
        "docs": "/docs",
        "health": "/health"
    }


if __name__ == "__main__":
    import uvicorn  # pyright: ignore[reportMissingImports]
    uvicorn.run(app, host="0.0.0.0", port=8000)
