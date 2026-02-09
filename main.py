from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Request, Form  # pyright: ignore[reportMissingImports]
from fastapi.middleware.cors import CORSMiddleware  # pyright: ignore[reportMissingImports]
from fastapi.staticfiles import StaticFiles  # pyright: ignore[reportMissingImports]
from fastapi.responses import Response  # pyright: ignore[reportMissingImports]
import uuid
import logging
import json
import os
import redis  # pyright: ignore[reportMissingImports]
from datetime import datetime, timedelta
from pathlib import Path
from models import TaskResponse, TaskDetail, TaskStatus
from tasks import process_image_to_music, tasks_store
from services.video_service import VideoService
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
# 创建 videos 子目录
videos_dir = Path("static/videos")
videos_dir.mkdir(parents=True, exist_ok=True)
@app.api_route("/static/{filename:path}", methods=["GET", "HEAD"])
async def serve_static_with_range(filename: str, request: Request):
    """
    自定义静态文件服务，支持 HTTP Range 请求（iOS AVPlayer 需要）
    Starlette 0.35.x 的 StaticFiles 不支持 Range，手动实现
    """
    file_path = static_dir / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    file_size = file_path.stat().st_size

    # 根据扩展名确定 Content-Type
    ext = file_path.suffix.lower()
    content_types = {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".mp4": "video/mp4",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
    }
    content_type = content_types.get(ext, "application/octet-stream")

    # 处理 Range 请求
    range_header = request.headers.get("range")
    if range_header:
        # 解析 Range: bytes=start-end
        range_str = range_header.replace("bytes=", "")
        parts = range_str.split("-")
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if parts[1] else file_size - 1
        end = min(end, file_size - 1)
        content_length = end - start + 1

        with open(file_path, "rb") as f:
            f.seek(start)
            data = f.read(content_length)

        return Response(
            content=data,
            status_code=206,
            headers={
                "Content-Type": content_type,
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Content-Length": str(content_length),
                "Accept-Ranges": "bytes",
            },
        )

    # HEAD 请求：只返回头部
    if request.method == "HEAD":
        return Response(
            content=b"",
            status_code=200,
            headers={
                "Content-Type": content_type,
                "Content-Length": str(file_size),
                "Accept-Ranges": "bytes",
            },
        )

    # 普通 GET 请求：返回完整文件
    with open(file_path, "rb") as f:
        data = f.read()

    return Response(
        content=data,
        status_code=200,
        headers={
            "Content-Type": content_type,
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes",
        },
    )


# 保留 StaticFiles 作为后备（自定义路由优先匹配）
# app.mount("/static", StaticFiles(directory="static"), name="static")

# 初始化视频服务
video_service = VideoService()


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
        "title": None,
        "gemini_config": None,
        "music_url": None,
        "image_url": None,
        "error": None,
        "message": "Analyzing your photo...",
        "analysis_result": None,
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
async def get_task_status(task_id: str, request: Request):
    """
    查询任务状态
    
    - **task_id**: 任务 ID

    返回的 music_url 和 image_url 为绝对路径（前端移动端需要完整 URL）
    """
    if task_id not in tasks_store:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # 复制任务数据，避免修改原始存储
    task = dict(tasks_store[task_id])

    # 将相对路径转换为绝对 URL（移动端 App 需要完整 URL 才能访问资源）
    base_url = str(request.base_url).rstrip('/')
    if task.get("music_url") and task["music_url"].startswith("/"):
        task["music_url"] = f"{base_url}{task['music_url']}"
    if task.get("image_url") and task["image_url"].startswith("/"):
        task["image_url"] = f"{base_url}{task['image_url']}"

    return task


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


@app.post("/api/generate-share-video")
async def generate_share_video(
    request: Request,
    image: UploadFile = File(...),
    audio_url: str = Form(...),
    title: str = Form("Melody Snap"),
    duration: str = Form("15"),
):
    """
    生成分享视频：卡片图片 + Ken Burns 缩放动画 + 音频叠加 → MP4

    使用 MoviePy 2.x 进行视频合成，支持 Ken Burns 缓慢缩放效果。

    - **image**: 卡片截图（PNG/JPG）
    - **audio_url**: 音频文件 URL（绝对路径或相对路径）
    - **title**: 歌曲标题
    - **duration**: 视频时长（秒，默认 15）
    """
    try:
        video_id = str(uuid.uuid4())[:8]

        # 保存上传的卡片图片到临时位置
        card_image_data = await image.read()
        card_image_path = static_dir / f"card_{video_id}.png"
        with open(card_image_path, 'wb') as f:
            f.write(card_image_data)

        # 解析音频文件的本地路径（前端可能传入绝对 URL 或相对路径）
        base_url = str(request.base_url).rstrip('/')
        if audio_url.startswith(base_url):
            audio_relative = audio_url[len(base_url):]
        elif audio_url.startswith("http"):
            raise HTTPException(status_code=400, detail="仅支持本服务器上的音频文件")
        else:
            audio_relative = audio_url

        audio_local_path = Path(audio_relative.lstrip("/"))
        if not audio_local_path.exists():
            raise HTTPException(status_code=404, detail=f"音频文件不存在: {audio_relative}")

        # 使用 VideoService (MoviePy + Ken Burns) 生成视频
        video_filename = f"share_{video_id}.mp4"
        video_path = str(videos_dir / video_filename)
        dur = int(duration)

        await video_service.generate_share_video(
            card_image_path=str(card_image_path),
            audio_path=str(audio_local_path),
            output_path=video_path,
            duration=dur,
            title=title,
        )

        # 清理临时卡片图片
        card_image_path.unlink(missing_ok=True)

        return {
            "video_url": f"/static/videos/{video_filename}",
            "duration": dur,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"生成分享视频失败: {str(e)}", exc_info=True)
        # 清理临时文件
        temp_card = static_dir / f"card_{video_id}.png"
        temp_card.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"视频生成失败: {str(e)}")


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
    import uvicorn  # pyright: ignore[reportMissingImports]
    uvicorn.run(app, host="0.0.0.0", port=8000)
