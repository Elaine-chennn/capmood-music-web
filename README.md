# MelodySnap Backend

基于 Gemini 3 Pro Preview 和 Suno V5 的图片转音乐后端服务。

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并填入你的 API Keys：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
GEMINI_API_KEY=your_actual_gemini_api_key
SUNO_API_TOKEN=your_actual_suno_token
```

### 3. 启动服务

```bash
# 开发环境（带热重载）
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 生产环境
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

服务将在 http://localhost:8000 启动

### 4. 访问 API 文档

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- 健康检查: http://localhost:8000/health

### 5. 测试 API

```bash
python test_api.py path/to/your/image.jpg
```

## 项目结构

```
backend/
├── main.py              # FastAPI 主应用
├── config.py            # 配置管理
├── models.py            # Pydantic 数据模型
├── tasks.py             # 后台任务处理
├── services/
│   ├── __init__.py
│   ├── gemini.py        # Gemini API 封装
│   └── suno.py          # Suno API 封装
├── prompts/
│   └── system_prompt.txt # Gemini System Prompt
├── requirements.txt     # 依赖列表
├── .env.example         # 环境变量模板
└── test_api.py          # 测试脚本
```

## API 端点

### POST /api/generate-music
上传图片生成音乐（异步）

**请求**:
- Content-Type: multipart/form-data
- Body: image (file)

**响应**:
```json
{
  "task_id": "uuid",
  "status": "pending",
  "message": "任务已创建...",
  "model_info": {
    "gemini": "gemini-3-pro-preview",
    "suno": "V5"
  }
}
```

### GET /api/task/{task_id}
查询任务状态

**响应**:
```json
{
  "task_id": "uuid",
  "status": "completed",
  "gemini_config": {...},
  "music_url": "https://...",
  "error": null,
  "created_at": "2026-01-28T...",
  "updated_at": "2026-01-28T..."
}
```

### DELETE /api/task/{task_id}
删除任务记录

### GET /health
服务健康检查

### GET /
API 基本信息

## 使用示例

### Python

```python
import httpx
import asyncio

async def generate_music(image_path: str):
    async with httpx.AsyncClient() as client:
        # 1. 上传图片
        with open(image_path, 'rb') as f:
            files = {'image': f}
            response = await client.post(
                'http://localhost:8000/api/generate-music',
                files=files
            )
        
        task_id = response.json()['task_id']
        
        # 2. 轮询状态
        while True:
            response = await client.get(
                f'http://localhost:8000/api/task/{task_id}'
            )
            data = response.json()
            
            if data['status'] == 'completed':
                return data['music_url']
            elif data['status'] == 'failed':
                raise Exception(data['error'])
            
            await asyncio.sleep(2)

# 使用
music_url = asyncio.run(generate_music('image.jpg'))
print(f"音乐 URL: {music_url}")
```

### cURL

```bash
# 1. 上传图片
curl -X POST http://localhost:8000/api/generate-music \
  -F "image=@image.jpg"

# 2. 查询状态（使用返回的 task_id）
curl http://localhost:8000/api/task/<task_id>
```

### JavaScript/TypeScript

```typescript
async function generateMusic(imageFile: File): Promise<string> {
  // 1. 上传图片
  const formData = new FormData();
  formData.append('image', imageFile);
  
  const response = await fetch('http://localhost:8000/api/generate-music', {
    method: 'POST',
    body: formData
  });
  
  const { task_id } = await response.json();
  
  // 2. 轮询状态
  while (true) {
    const statusResponse = await fetch(
      `http://localhost:8000/api/task/${task_id}`
    );
    const data = await statusResponse.json();
    
    if (data.status === 'completed') {
      return data.music_url;
    } else if (data.status === 'failed') {
      throw new Error(data.error);
    }
    
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
}
```

## 技术栈

- **框架**: FastAPI 0.109+
- **AI 模型**: Gemini 3 Flash Preview
- **音乐生成**: Suno V5
- **异步处理**: asyncio + BackgroundTasks
- **图片处理**: Pillow
- **HTTP 客户端**: httpx
- **视频合成**: MoviePy 2.x
- **重试机制**: tenacity 8.2.3

## 性能优化

- 使用异步 I/O 处理并发请求
- BackgroundTasks 避免阻塞主线程
- 图片大小限制（10MB）
- 合理的超时设置（180秒）

### 🆕 错误重试机制

使用 `tenacity` 库实现智能重试，提高服务稳定性：

**Gemini Service**:
- 最多重试 3 次
- 指数退避策略（2秒 → 4秒 → 8秒）
- 仅对网络相关错误重试（ConnectionError, TimeoutError）

**Suno Service**:
- API 调用失败时自动重试（最多 3 次）
- 轮询优化：从固定 5 秒改为指数退避
  - 渐进式延迟：2s → 3s → 5s → 5s → 8s → 10s → 10s → 15s → 15s → 20s
  - 总轮询时间从 300 秒优化至 93 秒
  - 更快获得结果，减少等待时间

**配置示例**:
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((ConnectionError, TimeoutError))
)
async def analyze_image(self, image_data: bytes):
    # API 调用逻辑
    ...
```

### 🆕 自动文件清理

后台任务自动清理过期的生成视频，避免磁盘空间耗尽：

**特性**:
- 每小时自动执行一次清理任务
- 删除超过 24 小时的视频文件
- 应用启动时自动注册后台任务
- 失败重试机制，确保清理任务稳定运行

**实现**:
```python
async def cleanup_old_files():
    """定时清理过期的视频文件"""
    while True:
        cutoff = datetime.now() - timedelta(hours=24)
        for file in VIDEOS_DIR.glob("*.mp4"):
            if datetime.fromtimestamp(file.stat().st_mtime) < cutoff:
                file.unlink()
        await asyncio.sleep(3600)  # 每小时执行一次

# 在启动事件中注册
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_old_files())
```

**日志输出**:
```
2026-02-08 22:56:23 - main - INFO - 文件清理后台任务已启动（每小时清理一次超过24小时的视频）
```

## 生产环境部署

### Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 启动

```bash
docker build -t melodysnap-backend .
docker run -p 8000:8000 --env-file .env melodysnap-backend
```

## 常见问题

### Q: Gemini API 返回非 JSON 格式
A: 代码已包含自动清理 Markdown 标记的逻辑

### Q: 任务处理时间过长
A: Gemini 分析约 5-10 秒，Suno 生成约 30-60 秒，总计 1-2 分钟。已实现指数退避轮询策略优化等待时间。

### Q: 服务重启后任务丢失
A: 当前使用内存存储，生产环境建议使用 Redis 或数据库

### Q: 如何限制并发请求
A: 添加速率限制中间件（如 slowapi）

### Q: API 调用失败怎么办
A: 已实现自动重试机制（最多 3 次），包括 Gemini 图片分析和 Suno 音乐生成

### Q: 生成的视频文件会占满磁盘吗
A: 不会。后台任务每小时自动清理超过 24 小时的视频文件

## 更新日志

### v2.1.0 (2026-02-08)
- ✨ 新增：错误重试机制（tenacity）
  - Gemini Service 自动重试（最多 3 次）
  - Suno Service API 调用重试
  - 指数退避轮询策略（优化 70% 等待时间）
- ✨ 新增：自动文件清理后台任务
  - 每小时清理超过 24 小时的视频文件
  - 避免磁盘空间耗尽
- 🐛 修复：轮询超时时间过长问题
- 📝 更新：完善 README 文档

## 许可证

MIT License

## 维护者

GitHub Copilot
