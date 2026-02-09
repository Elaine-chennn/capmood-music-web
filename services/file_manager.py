"""
文件管理和清理服务
"""
import os
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict

logger = logging.getLogger(__name__)


class FileManager:
    """文件管理器"""
    
    def __init__(self, static_dir: str = "static"):
        self.static_dir = Path(static_dir)
        self.images_dir = self.static_dir / "images"
        self.music_dir = self.static_dir / "music"
        
        # 确保目录存在
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.music_dir.mkdir(parents=True, exist_ok=True)
    
    async def cleanup_old_files(self, days: int = 7) -> Dict[str, int]:
        """清理指定天数前的文件"""
        cutoff_time = datetime.now() - timedelta(days=days)
        cutoff_timestamp = cutoff_time.timestamp()
        
        stats = {
            "images_deleted": 0,
            "music_deleted": 0,
            "total_size_freed": 0
        }
        
        # 清理图片
        for file_path in self.images_dir.iterdir():
            if file_path.is_file() and file_path.stat().st_mtime < cutoff_timestamp:
                size = file_path.stat().st_size
                file_path.unlink()
                stats["images_deleted"] += 1
                stats["total_size_freed"] += size
                logger.info(f"已清理图片: {file_path.name}")
        
        # 清理音频
        for file_path in self.music_dir.iterdir():
            if file_path.is_file() and file_path.stat().st_mtime < cutoff_timestamp:
                size = file_path.stat().st_size
                file_path.unlink()
                stats["music_deleted"] += 1
                stats["total_size_freed"] += size
                logger.info(f"已清理音频: {file_path.name}")
        
        # 转换为 MB
        stats["total_size_freed_mb"] = round(stats["total_size_freed"] / 1024 / 1024, 2)
        
        logger.info(f"清理完成: {stats}")
        return stats
    
    def get_storage_stats(self) -> Dict:
        """获取存储统计信息"""
        def get_dir_size(path: Path) -> int:
            return sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
        
        images_size = get_dir_size(self.images_dir)
        music_size = get_dir_size(self.music_dir)
        
        return {
            "images": {
                "count": len(list(self.images_dir.glob('*'))),
                "size_mb": round(images_size / 1024 / 1024, 2)
            },
            "music": {
                "count": len(list(self.music_dir.glob('*'))),
                "size_mb": round(music_size / 1024 / 1024, 2)
            },
            "total_size_mb": round((images_size + music_size) / 1024 / 1024, 2)
        }
    
    def delete_task_files(self, task_id: str) -> bool:
        """删除特定任务的所有文件"""
        try:
            deleted = False
            
            # 删除图片
            for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                image_path = self.images_dir / f"{task_id}{ext}"
                if image_path.exists():
                    image_path.unlink()
                    deleted = True
                    logger.info(f"已删除图片: {image_path.name}")
            
            # 删除音频
            music_path = self.music_dir / f"{task_id}.wav"
            if music_path.exists():
                music_path.unlink()
                deleted = True
                logger.info(f"已删除音频: {music_path.name}")
            
            return deleted
        except Exception as e:
            logger.error(f"删除任务文件失败 {task_id}: {e}")
            return False
