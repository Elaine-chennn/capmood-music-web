from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uuid
import logging
import json
import redis
from datetime import datetime, timedelta
from pathlib import Path
from models import TaskResponse, TaskDetail, TaskStatus
from tasks import process_image_to_music, tasks_store
from config import get_settings

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

settings = get_settings()

# 初始化 Redis
try:
    redis_client = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        decode_responses=True
    )
    redis_client.ping()
    logger.info("Redis 连接成功")
except Exception as e:
    logger.warning(f"Redis 连接失败: {e}，分享功能将不可用")
    redis_client = None

app = FastAPI(
    title="MelodySnap API",
    description="图片转音乐 API 服务 (Gemini 3 Pro Preview + Google Lyria)",
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

# 创建 static 目录并挂载静态文件服务
static_dir = Path("static")
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
async def startup_event():
    """启动时显示配置信息"""
    logger.info("=" * 50)
    logger.info(f"MelodySnap API 启动")
    logger.info(f"Gemini 模型: {settings.GEMINI_MODEL}")
    logger.info(f"Lyria 模型: lyria-realtime-exp")
    logger.info(f"环境: {settings.ENV}")
    logger.info("=" * 50)


@app.post("/api/generate-music", response_model=TaskResponse)
async def generate_music(
    background_tasks: BackgroundTasks,
    image: UploadFile = File(...)
):
    """
    上传图片，使用 Gemini 3 Pro Preview 分析并通过 Google Lyria 生成音乐
    
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
        "image_url": None,
        "error": None,
        "created_at": now,
        "updated_at": now,
        "model_info": {
            "gemini": settings.GEMINI_MODEL,
            "lyria": "lyria-realtime-exp"
        }
    }
    
    logger.info(f"创建任务 {task_id}，图片大小: {len(image_data)} bytes")
    
    # 添加到后台任务
    background_tasks.add_task(process_image_to_music, task_id, image_data)
    
    return TaskResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        message="任务已创建，正在使用 Gemini 3 Pro Preview 和 Google Lyria 处理中",
        model_info={
            "gemini": settings.GEMINI_MODEL,
            "lyria": "lyria-realtime-exp"
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


@app.post("/api/share/{task_id}")
async def create_share(task_id: str):
    """
    创建分享链接
    
    - **task_id**: 任务 ID
    
    将音乐数据保存到 Redis，返回分享 URL（有效期 7 天）
    """
    if redis_client is None:
        raise HTTPException(status_code=503, detail="分享功能暂时不可用")
    
    if task_id not in tasks_store:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    task = tasks_store[task_id]
    
    if task["status"] != TaskStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="任务还未完成")
    
    # 准备分享数据
    share_data = {
        "music_url": task["music_url"],
        "music_info": task.get("gemini_config", {}),
        "model_info": task.get("model_info", {}),
        "created_at": datetime.now().isoformat(),
        "task_id": task_id
    }
    
    # 存储到 Redis（7天过期）
    expire_seconds = settings.SHARE_EXPIRE_DAYS * 24 * 3600
    redis_client.setex(
        f"share:{task_id}",
        expire_seconds,
        json.dumps(share_data)
    )
    
    logger.info(f"创建分享链接: {task_id}")
    
    return {
        "share_id": task_id,
        "share_url": f"/share/{task_id}",
        "expires_in_days": settings.SHARE_EXPIRE_DAYS,
        "expires_at": (datetime.now() + timedelta(days=settings.SHARE_EXPIRE_DAYS)).isoformat()
    }


@app.get("/api/share/{share_id}")
async def get_share_data(share_id: str):
    """
    获取分享的音乐数据
    
    - **share_id**: 分享 ID（即 task_id）
    """
    if redis_client is None:
        raise HTTPException(status_code=503, detail="分享功能暂时不可用")
    
    # 从 Redis 获取数据
    data = redis_client.get(f"share:{share_id}")
    
    if not data:
        raise HTTPException(status_code=404, detail="分享不存在或已过期")
    
    share_data = json.loads(data)
    
    # 记录访问（可选：统计播放次数）
    redis_client.incr(f"share:views:{share_id}")
    
    logger.info(f"访问分享: {share_id}")
    
    return share_data


@app.get("/health")
async def health_check():
    """健康检查"""
    redis_status = "ok" if redis_client else "unavailable"
    try:
        if redis_client:
            redis_client.ping()
    except:
        redis_status = "error"
    
    return {
        "status": "ok",
        "tasks_count": len(tasks_store),
        "redis_status": redis_status,
        "models": {
            "gemini": settings.GEMINI_MODEL,
            "lyria": "lyria-realtime-exp"
        },
        "configuration": {
            "gemini_configured": bool(settings.GEMINI_API_KEY),
            "google_api_configured": bool(settings.GOOGLE_API_KEY),
            "redis_configured": bool(redis_client)
        }
    }


@app.get("/")
async def root():
    """API 信息"""
    return {
        "service": "MelodySnap API",
        "version": "2.0.0",
        "models": {
            "gemini": settings.GEMINI_MODEL,
            "lyria": "lyria-realtime-exp"
        },
        "docs": "/docs",
        "health": "/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
