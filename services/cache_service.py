"""
缓存服务 - 提升重复图片处理速度
"""
import hashlib
import logging
import json
from typing import Optional, Dict
from pathlib import Path

logger = logging.getLogger(__name__)


class CacheService:
    """缓存管理服务"""
    
    def __init__(self, redis_client):
        self.redis = redis_client
        self.cache_prefix = "cache:gemini:"
        self.cache_ttl = 7 * 86400  # 7天缓存
    
    @staticmethod
    def get_image_hash(image_path: str) -> str:
        """计算图片的 MD5 哈希值"""
        try:
            with open(image_path, "rb") as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception as e:
            logger.error(f"计算图片哈希失败: {e}")
            return None
    
    async def get_cached_analysis(self, image_hash: str) -> Optional[Dict]:
        """获取缓存的 Gemini 分析结果"""
        try:
            key = f"{self.cache_prefix}{image_hash}"
            cached_data = self.redis.get(key)
            
            if cached_data:
                logger.info(f"✅ 缓存命中: {image_hash[:8]}...")
                return json.loads(cached_data)
            
            logger.info(f"❌ 缓存未命中: {image_hash[:8]}...")
            return None
        except Exception as e:
            logger.error(f"获取缓存失败: {e}")
            return None
    
    async def save_analysis_to_cache(self, image_hash: str, analysis_result: Dict) -> bool:
        """保存 Gemini 分析结果到缓存"""
        try:
            key = f"{self.cache_prefix}{image_hash}"
            self.redis.set(
                key,
                json.dumps(analysis_result),
                ex=self.cache_ttl
            )
            logger.info(f"💾 分析结果已缓存: {image_hash[:8]}...")
            return True
        except Exception as e:
            logger.error(f"保存缓存失败: {e}")
            return False
    
    async def invalidate_cache(self, image_hash: str) -> bool:
        """使缓存失效"""
        try:
            key = f"{self.cache_prefix}{image_hash}"
            self.redis.delete(key)
            logger.info(f"🗑️ 缓存已清除: {image_hash[:8]}...")
            return True
        except Exception as e:
            logger.error(f"清除缓存失败: {e}")
            return False
    
    async def get_cache_stats(self) -> Dict:
        """获取缓存统计信息"""
        try:
            keys = self.redis.keys(f"{self.cache_prefix}*")
            return {
                "total_entries": len(keys),
                "ttl_days": self.cache_ttl // 86400
            }
        except Exception as e:
            logger.error(f"获取缓存统计失败: {e}")
            return {"error": str(e)}
