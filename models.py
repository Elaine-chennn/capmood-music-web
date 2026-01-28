from pydantic import BaseModel, Field
from typing import Optional, Literal
from enum import Enum


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class SunoConfig(BaseModel):
    """Suno V5 API 请求配置"""
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
            "suno": "V5"
        }
    )


class TaskDetail(BaseModel):
    """任务详情"""
    task_id: str
    status: TaskStatus
    gemini_config: Optional[SunoConfig] = None
    music_url: Optional[str] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str
    model_info: dict = Field(
        default={
            "gemini": "gemini-3-flash-preview",
            "suno": "V5"
        }
    )
