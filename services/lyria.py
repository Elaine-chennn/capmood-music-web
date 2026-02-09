import asyncio
import logging
import base64
import time
import struct
from typing import Dict, Any
from google import genai
from google.genai import types
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class LyriaService:
    """Google Lyria 实时音乐生成服务封装"""
    
    def __init__(self):
        self.api_key = settings.GOOGLE_API_KEY
        self.model = "models/lyria-realtime-exp"
        self.client = genai.Client(
            api_key=self.api_key,
            http_options={'api_version': 'v1alpha'}
        )
        logger.info(f"初始化 Lyria 服务，模型: {self.model}")
    
    async def generate_music(self, config: Dict[str, Any]) -> str:
        """
        调用 Google Lyria 实时 API 生成音乐
        
        Args:
            config: Gemini 生成的配置，包含以下字段：
                - prompt/title: 音乐描述文本
                - tags: 标签
                - moods: 情绪
                - instruments: 乐器
                - tempo: 节奏
                
        Returns:
            str: 音乐文件的 base64 编码数据（WAV 格式）
            
        Raises:
            Exception: API 调用失败
        """
        max_retries = 2
        retry_delay = 3  # 秒
        
        for attempt in range(max_retries):
            try:
                # 从配置中构建 prompt
                prompt = self._build_prompt_from_config(config)
                bpm = self._extract_bpm_from_config(config)
                temperature = config.get("temperature", 1.0)
                vocalization = config.get("vocalization", False)
                lyrics = config.get("lyrics", "")
                
                logger.info(f"开始调用 Lyria 实时 API (尝试 {attempt + 1}/{max_retries})")
                logger.info(f"Prompt: {prompt}")
                logger.info(f"BPM: {bpm}, Temperature: {temperature}")
                logger.info(f"Vocalization: {vocalization}")
                if vocalization and lyrics:
                    logger.info(f"Lyrics: {lyrics}")
                
                # 收集生成的音频数据
                audio_chunks = []
                lyria_start_time = time.time()
                
                # 使用 wait_for 设置超时（Python 3.10 兼容）
                try:
                    await asyncio.wait_for(
                        self._generate_music_stream(prompt, bpm, temperature, vocalization, lyrics, audio_chunks),
                        timeout=45.0  # 45秒总超时
                    )
                except asyncio.TimeoutError:
                    raise asyncio.TimeoutError("Lyria API 生成超时")
                
                if not audio_chunks:
                    raise Exception("未接收到音频数据")
                
                # 合并所有音频块
                audio_data = b''.join(audio_chunks)
                lyria_time = time.time() - lyria_start_time
                logger.info(f"⏱️  Lyria API 生成时间: {lyria_time:.2f} 秒")
                logger.info(f"✓ 音乐生成成功，音频大小: {len(audio_data)} bytes")
                
                # 返回 base64 编码
                audio_base64 = base64.b64encode(audio_data).decode('utf-8')
                return audio_base64
                    
            except asyncio.TimeoutError:
                logger.error(f"Lyria API 超时 (尝试 {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    logger.info(f"等待 {retry_delay} 秒后重试...")
                    await asyncio.sleep(retry_delay)
                    continue
                else:
                    raise Exception("Lyria API 连接超时，请稍后重试")
            except Exception as e:
                logger.error(f"Lyria 服务错误 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1 and "handshake" in str(e).lower():
                    logger.info(f"等待 {retry_delay} 秒后重试...")
                    await asyncio.sleep(retry_delay)
                    continue
                else:
                    raise
    
    async def _generate_music_stream(self, prompt: str, bpm: int, temperature: float, 
                                      vocalization: bool, lyrics: str, audio_chunks: list):
        """
        生成音乐流的辅助方法
        
        Args:
            prompt: 音乐风格描述
            bpm: 节拍速度
            temperature: 随机性
            vocalization: 是否使用人声
            lyrics: 歌词（如果有）
            audio_chunks: 音频块列表
        """
        async with (
            self.client.aio.live.music.connect(model=self.model) as session,
        ):
            # 构建完整的 prompt（如果有歌词，附加到 prompt 中）
            full_prompt = prompt
            if vocalization and lyrics:
                full_prompt = f"{prompt}\n\nLyrics:\n{lyrics}"
            
            # 设置音乐生成配置
            await session.set_weighted_prompts(
                prompts=[
                    types.WeightedPrompt(text=full_prompt, weight=1.0),
                ]
            )
            
            # 根据是否需要人声设置生成模式
            music_mode = types.MusicGenerationMode.VOCALIZATION if vocalization else types.MusicGenerationMode.QUALITY
            
            await session.set_music_generation_config(
                config=types.LiveMusicGenerationConfig(
                    bpm=bpm,
                    temperature=temperature,
                    musicGenerationMode=music_mode
                )
            )
            
            # 开始生成音乐
            await session.play()
            logger.info("开始接收音频流...")
            
            # 接收音频流（限制时间为 30 秒）
            start_time = asyncio.get_event_loop().time()
            max_duration = 30  # 30秒
            
            async for message in session.receive():
                if hasattr(message, 'server_content') and message.server_content:
                    if hasattr(message.server_content, 'audio_chunks'):
                        for chunk in message.server_content.audio_chunks:
                            if hasattr(chunk, 'data'):
                                audio_chunks.append(chunk.data)
                
                # 检查是否超过最大时长
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed >= max_duration:
                    logger.info(f"达到最大生成时长 {max_duration} 秒，停止接收")
                    break
            
            # 停止生成
            await session.stop()
    
    def _build_prompt_from_config(self, config: Dict[str, Any]) -> str:
        """
        从 Gemini 配置构建 Lyria prompt
        
        Lyria 需要详细的英文描述，包括：流派、曲调、乐器、节奏等
        
        Args:
            config: Gemini 生成的配置
            
        Returns:
            str: Lyria prompt 文本
        """
        # 优先使用 Gemini 返回的完整 style 字段
        style = config.get("style", "")
        
        if style:
            # style 已经包含完整的音乐描述，直接使用
            # 例如: "Cinematic Post-Rock, Dream Pop, Ethereal, 75 BPM, Electric Guitar"
            logger.info(f"使用完整 style 作为 prompt: {style}")
            return style
        
        # 回退逻辑：如果没有 style 字段（旧版本兼容）
        title = config.get("title", "")
        tags = config.get("tags", "")
        moods = config.get("moods", [])
        instruments = config.get("instruments", [])
        
        parts = []
        if tags:
            parts.append(tags)
        elif title:
            parts.append(title)
        
        if moods:
            if isinstance(moods, list):
                parts.extend(moods[:2])
            else:
                parts.append(moods)
        
        if instruments:
            if isinstance(instruments, list):
                parts.extend(instruments[:2])
            else:
                parts.append(instruments)
        
        prompt = ", ".join(parts) if parts else "ambient instrumental"
        logger.info(f"使用回退逻辑构建的 prompt: {prompt}")
        return prompt
    
    def _extract_bpm_from_config(self, config: Dict[str, Any]) -> int:
        """
        从配置中提取 BPM（每分钟节拍数）
        
        Args:
            config: Gemini 生成的配置
            
        Returns:
            int: BPM 值（默认 120）
        """
        # 优先从 style 字段中提取 BPM（例如 "75 BPM"）
        style = config.get("style", "")
        if style:
            import re
            # 匹配 "数字 BPM" 模式
            bpm_match = re.search(r'(\d+)\s*BPM', style, re.IGNORECASE)
            if bpm_match:
                bpm = int(bpm_match.group(1))
                logger.info(f"从 style 中提取 BPM: {bpm}")
                return bpm
        
        # 尝试从配置中获取 BPM
        if "bpm" in config:
            return int(config["bpm"])
        
        # 从 tempo 描述推断 BPM
        tempo = config.get("tempo", "").lower()
        
        bpm_map = {
            "very slow": 60,
            "slow": 80,
            "moderate": 100,
            "medium": 120,
            "fast": 140,
            "very fast": 160,
            "energetic": 140,
            "calm": 80,
            "relaxed": 90,
        }
        
        for key, value in bpm_map.items():
            if key in tempo:
                logger.info(f"从 tempo '{tempo}' 推断 BPM: {value}")
                return value
        
        # 默认 BPM
        default_bpm = 120
        logger.info(f"使用默认 BPM: {default_bpm}")
        return default_bpm
    
    def get_audio_data_url(self, audio_base64: str) -> str:
        """
        将 base64 音频数据转换为 data URL
        
        Args:
            audio_base64: base64 编码的音频数据
            
        Returns:
            str: data URL 格式的音频数据
        """
        return f"data:audio/wav;base64,{audio_base64}"
    
    def save_audio_to_file(self, audio_base64: str, output_path: str) -> str:
        """
        将 base64 编码的音频保存为 WAV 文件
        
        Args:
            audio_base64: base64 编码的音频数据（原始 PCM）
            output_path: 输出文件路径
            
        Returns:
            str: 保存的文件路径
        """
        try:
            # 解码 base64 得到原始 PCM 数据
            pcm_data = base64.b64decode(audio_base64)
            
            # Lyria 返回的音频参数（根据 Lyria 文档）
            # 采样率: 24000 Hz, 单声道, 16位
            sample_rate = 24000
            num_channels = 1
            bits_per_sample = 16
            
            # 构建 WAV 文件头
            wav_data = self._create_wav_header(
                pcm_data, 
                sample_rate, 
                num_channels, 
                bits_per_sample
            )
            
            # 写入文件
            with open(output_path, 'wb') as f:
                f.write(wav_data)
            
            logger.info(f"音频已保存至: {output_path}, 大小: {len(wav_data)} bytes")
            return output_path
        except Exception as e:
            logger.error(f"保存音频文件失败: {str(e)}")
            raise Exception(f"保存音频文件失败: {str(e)}")
    
    def _create_wav_header(self, pcm_data: bytes, sample_rate: int, 
                           num_channels: int, bits_per_sample: int) -> bytes:
        """
        为 PCM 数据创建 WAV 文件头
        
        Args:
            pcm_data: 原始 PCM 音频数据
            sample_rate: 采样率（Hz）
            num_channels: 声道数
            bits_per_sample: 每个样本的位数
            
        Returns:
            bytes: 完整的 WAV 文件数据（包含头部）
        """
        byte_rate = sample_rate * num_channels * bits_per_sample // 8
        block_align = num_channels * bits_per_sample // 8
        data_size = len(pcm_data)
        
        # 构建 WAV 文件头（44 字节）
        header = struct.pack('<4sI4s',
            b'RIFF',                          # ChunkID
            data_size + 36,                   # ChunkSize
            b'WAVE'                           # Format
        )
        
        # fmt 子块
        header += struct.pack('<4sIHHIIHH',
            b'fmt ',                          # Subchunk1ID
            16,                               # Subchunk1Size (PCM)
            1,                                # AudioFormat (PCM)
            num_channels,                     # NumChannels
            sample_rate,                      # SampleRate
            byte_rate,                        # ByteRate
            block_align,                      # BlockAlign
            bits_per_sample                   # BitsPerSample
        )
        
        # data 子块
        header += struct.pack('<4sI',
            b'data',                          # Subchunk2ID
            data_size                         # Subchunk2Size
        )
        
        return header + pcm_data
