import google.generativeai as genai
from PIL import Image
import json
import io
import logging
from pathlib import Path
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
        使用 Gemini 3 Pro Preview 分析图片并生成 Suno V5 配置
        
        Args:
            image_data: 图片二进制数据
            
        Returns:
            dict: Suno V5 API 所需的配置
            
        Raises:
            ValueError: JSON 解析失败
            Exception: Gemini API 调用失败
        """
        try:
            # 打开图片
            image = Image.open(io.BytesIO(image_data))
            logger.info(f"图片尺寸: {image.size}, 格式: {image.format}")
            
            # 调用 Gemini 3 Pro Preview
            logger.info(f"调用 {settings.GEMINI_MODEL} 分析图片...")
            response = self.model.generate_content([
                self.system_prompt,
                image
            ])
            
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
            
            # 验证必需字段
            required_fields = ['prompt', 'style', 'title', 'vocalGender']
            missing_fields = [f for f in required_fields if f not in config]
            if missing_fields:
                raise ValueError(f"缺少必需字段: {', '.join(missing_fields)}")
            
            # 强制设置为 V5 模型
            config['customMode'] = True
            config['instrumental'] = False
            config['model'] = settings.SUNO_MODEL  # 确保是 V5
            
            # 验证并标准化 vocalGender 格式为 m/f
            if config['vocalGender'] not in ['male', 'female', 'm', 'f']:
                config['vocalGender'] = 'f'  # 默认值
            
            # 标准化为 m/f 格式（Suno API 要求）
            if config['vocalGender'] == 'male':
                config['vocalGender'] = 'm'
            elif config['vocalGender'] == 'female':
                config['vocalGender'] = 'f'
            
            logger.info(f"✓ Gemini 分析完成 - 标题: {config.get('title')}, 模型: {config.get('model')}")
            return config
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {str(e)}\n原始文本: {text}")
            raise ValueError(f"Gemini 返回的 JSON 格式错误: {str(e)}")
        except Exception as e:
            logger.error(f"Gemini API 调用失败: {str(e)}")
            raise Exception(f"图片分析失败: {str(e)}")
