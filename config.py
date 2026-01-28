from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """应用配置"""
    
    # Gemini 配置
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-3-flash-preview"
    
    # Suno 配置
    SUNO_API_TOKEN: str
    SUNO_API_URL: str = "https://api.sunoapi.org/api/v1/generate"
    SUNO_MODEL: str = "V5"
    
    # 应用配置
    TASK_TIMEOUT: int = 180
    MAX_IMAGE_SIZE: int = 10 * 1024 * 1024  # 10MB
    ENV: str = "development"
    
    class Config:
        env_file = ".env"


@lru_cache()
def get_settings():
    """获取配置单例"""
    return Settings()
