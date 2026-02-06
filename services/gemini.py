import google.generativeai as genai
from PIL import Image
import json
import io
import logging
import time
from pathlib import Path
from datetime import datetime
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# 配置 Gemini
genai.configure(api_key=settings.GEMINI_API_KEY)


class GeminiService:
    """Gemini API 服务封装"""
    
    def __init__(self):
        self.model = genai.GenerativeModel(settings.GEMINI_MODEL)
        self.system_prompt = self._load_prompt()
        logger.info(f"初始化 Gemini 服务，模型: {settings.GEMINI_MODEL}")
    
    def _load_prompt(self) -> str:
        """加载 System Prompt"""
        prompt_path = Path(__file__).parent.parent / "prompts" / "system_prompt.txt"
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    async def analyze_image(self, image_data: bytes) -> dict:
        """
        使用 Gemini 3 Pro Preview 分析图片并生成音乐配置
        
        Args:
            image_data: 图片二进制数据
            
        Returns:
            dict: 音乐生成配置
            
        Raises:
            ValueError: JSON 解析失败
            Exception: Gemini API 调用失败
        """
        try:
            # 打开图片
            image = Image.open(io.BytesIO(image_data))
            original_size = image.size
            logger.info(f"原始图片尺寸: {original_size}, 格式: {image.format}")
            
            # 智能 Resize 图片以优化 API 调用
            # Gemini 推荐的图片尺寸为 768-2048 像素之间
            max_size = settings.IMAGE_RESIZE_MAX
            
            # 只有当图片超过最大尺寸时才缩放
            if max(image.size) > max_size:
                # 保持宽高比进行缩放
                ratio = max_size / max(image.size)
                new_size = tuple(int(dim * ratio) for dim in image.size)
                image = image.resize(new_size, Image.Resampling.LANCZOS)
                logger.info(f"图片已缩放: {original_size} → {new_size}")
                
                # 计算缩放后的图片大小
                resized_buffer = io.BytesIO()
                image.save(resized_buffer, format=image.format or 'JPEG', quality=85)
                resized_size = len(resized_buffer.getvalue())
                logger.info(f"缩放后图片大小: {resized_size} bytes ({resized_size/1024:.2f} KB)")
            else:
                logger.info(f"图片尺寸合适，无需缩放 (最大边: {max(image.size)}px <= {max_size}px)")
            
            # 调用 Gemini 3 Pro Preview
            logger.info(f"调用 {settings.GEMINI_MODEL} 分析图片...")
            start_time = time.time()
            
            # 设置生成配置
            generation_config = genai.types.GenerationConfig(
                temperature=0.8,
            )
            
            response = self.model.generate_content(
                [self.system_prompt, image],
                generation_config=generation_config
            )
            gemini_time = time.time() - start_time
            logger.info(f"⏱️  Gemini API 响应时间: {gemini_time:.2f} 秒")
            
            # 清理 Markdown 标记
            text = response.text.strip()
            logger.debug(f"Gemini 原始响应: {text[:200]}...")
            
            # 移除可能的代码块标记
            if text.startswith("```json"):
                text = text[7:]
            elif text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            
            text = text.strip()
            
            # 解析 JSON
            config = json.loads(text)
            
            # 保存完整的 Gemini 返回内容到单独的日志文件
            gemini_log_path = Path("logs/gemini_responses.log")
            gemini_log_path.parent.mkdir(exist_ok=True)
            
            with open(gemini_log_path, 'a', encoding='utf-8') as f:
                f.write("\n" + "="*80 + "\n")
                f.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("="*80 + "\n")
                f.write(json.dumps(config, indent=2, ensure_ascii=False))
                f.write("\n" + "="*80 + "\n\n")
            
            logger.info(f"Gemini 返回内容已保存至: {gemini_log_path}")
            
            # 打印详细的分析结果
            logger.info("="*60)
            logger.info("Gemini 3 分析结果详情")
            logger.info("="*60)
            logger.info(f"标题 (title): {config.get('title', 'N/A')}")
            logger.info(f"人声性别 (vocalGender): {config.get('vocalGender', 'N/A')}")
            
            # 解析 style 字段
            style = config.get('style', '')
            logger.info(f"\n音乐风格 (style):")
            logger.info(f"  完整内容: {style}")
            if style:
                components = style.split(", ")
                logger.info(f"  包含元素:")
                for comp in components:
                    if "BPM" in comp:
                        logger.info(f"    - {comp:30s} ← 节奏速度")
                    elif "Vocal" in comp:
                        logger.info(f"    - {comp:30s} ← 人声风格")
                    elif any(word in comp for word in ["Guitar", "Piano", "Synth", "Strings", "Pad", "Drum"]):
                        logger.info(f"    - {comp:30s} ← 乐器")
                    elif any(word in comp for word in ["Pop", "Rock", "Jazz", "Electronic", "Cinematic", "Ambient"]):
                        logger.info(f"    - {comp:30s} ← 音乐流派")
                    else:
                        logger.info(f"    - {comp:30s} ← 情绪/氛围")
            
            # 打印歌词结构
            prompt = config.get('prompt', '')
            logger.info(f"\n歌词内容 (prompt):")
            if prompt:
                lines = prompt.split('\n')
                verse_count = prompt.count('[Verse]')
                chorus_count = prompt.count('[Chorus]')
                logger.info(f"  结构: {verse_count} 个 [Verse], {chorus_count} 个 [Chorus]")
                logger.info(f"  总行数: {len([l for l in lines if l.strip()])}")
                logger.info(f"  前3行预览: {' / '.join(lines[:3])}")
            
            # 打印可选参数
            logger.info(f"\n可选参数:")
            logger.info(f"  styleWeight: {config.get('styleWeight', 0.65)}")
            logger.info(f"  weirdnessConstraint: {config.get('weirdnessConstraint', 0.65)}")
            logger.info(f"  audioWeight: {config.get('audioWeight', 0.65)}")
            logger.info("="*60)
            
            logger.info(f"✓ Gemini 分析完成 - 标题: {config.get('title')}")
            return config
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {str(e)}\n原始文本: {text}")
            raise ValueError(f"Gemini 返回的 JSON 格式错误: {str(e)}")
        except Exception as e:
            logger.error(f"Gemini API 调用失败: {str(e)}")
            raise Exception(f"图片分析失败: {str(e)}")
