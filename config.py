from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """应用配置"""
    
    # Gemini 配置
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-3-flash-preview"
    
    # Google API Key (用于 Lyria)
    GOOGLE_API_KEY: str
    
    # Redis 配置
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    SHARE_EXPIRE_DAYS: int = 7
    
    # 应用配置
    TASK_TIMEOUT: int = 180
    MAX_IMAGE_SIZE: int = 10 * 1024 * 1024  # 10MB（上传限制）
    IMAGE_RESIZE_MAX: int = 2048  # 后端处理的图片最大边长（前端已压缩到1920px，这里放宽到2048px）
    ENV: str = "development"
    
    class Config:
        env_file = ".env"


@lru_cache()
def get_settings():
    """获取配置单例"""
    return Settings()
