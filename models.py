from pydantic import BaseModel, Field
from typing import Optional, Literal
from enum import Enum


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class LyriaConfig(BaseModel):
    """Google Lyria API 音乐生成配置"""
    vocalization: bool = Field(..., description="是否使用人声演唱")
    style: str = Field(..., description="音乐风格描述（包含流派、情绪、BPM、乐器、人声风格等）")
    lyrics: Optional[str] = Field(default="", description="歌词（仅当 vocalization=true 时）")
    title: str = Field(..., description="歌曲标题")
    bpm: int = Field(..., description="节拍速度（40-180）", ge=40, le=180)


class SunoConfig(BaseModel):
    """Suno V5 API 请求配置（已弃用，保留用于兼容性）"""
    customMode: bool = True
    instrumental: bool = False  # 包含歌词
    model: Literal["V5"] = "V5"  # 强制使用 V5 模型
    prompt: str = Field(..., description="歌词内容（含标签）")
    style: str = Field(..., description="音乐风格描述")
    title: str = Field(..., description="歌曲标题")
    vocalGender: Literal["m", "f"] = Field(..., description="人声性别: m(男)/f(女)")
    
    # V5 模型支持的可选字段
    callBackUrl: Optional[str] = None
    personaId: Optional[str] = None
    negativeTags: Optional[str] = None
    styleWeight: float = Field(default=0.65, ge=0, le=1)
    weirdnessConstraint: float = Field(default=0.65, ge=0, le=1)
    audioWeight: float = Field(default=0.65, ge=0, le=1)


class TaskResponse(BaseModel):
    """任务创建响应"""
    task_id: str
    status: TaskStatus
    message: str
    model_info: dict = Field(
        default={
            "gemini": "gemini-3-flash-preview",
            "lyria": "lyria-realtime-exp"
        }
    )


class TaskDetail(BaseModel):
    """任务详情"""
    task_id: str
    status: TaskStatus
    title: Optional[str] = None  # 只返回歌曲标题
    music_url: Optional[str] = None
    image_url: Optional[str] = None  # 添加照片URL字段
    error: Optional[str] = None
    created_at: str
    updated_at: str
    model_info: dict = Field(
        default={
            "gemini": "gemini-3-flash-preview",
            "lyria": "lyria-realtime-exp"
        }
    )
