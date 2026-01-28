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
- **AI 模型**: Gemini 3 Pro Preview
- **音乐生成**: Suno V5
- **异步处理**: asyncio + BackgroundTasks
- **图片处理**: Pillow
- **HTTP 客户端**: httpx

## 性能优化

- 使用异步 I/O 处理并发请求
- BackgroundTasks 避免阻塞主线程
- 图片大小限制（10MB）
- 合理的超时设置（180秒）

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
A: Gemini 分析约 5-10 秒，Suno 生成约 30-60 秒，总计 1-2 分钟

### Q: 服务重启后任务丢失
A: 当前使用内存存储，生产环境建议使用 Redis 或数据库

### Q: 如何限制并发请求
A: 添加速率限制中间件（如 slowapi）

## 许可证

MIT License

## 维护者

GitHub Copilot
