import httpx
import logging
import asyncio
from typing import Dict, Any
from config import get_settings
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)
settings = get_settings()


class SunoService:
    """Suno API 服务封装"""
    
    def __init__(self):
        self.api_url = settings.SUNO_API_URL
        self.api_token = settings.SUNO_API_TOKEN
        self.model = settings.SUNO_MODEL
        logger.info(f"初始化 Suno 服务，模型: {self.model}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.RequestError, ConnectionError)),
        reraise=True
    )
    async def generate_music(self, config: Dict[str, Any]) -> str:
        """
        调用 Suno V5 API 生成音乐
        
        Args:
            config: Gemini 生成的配置
            
        Returns:
            str: 音乐文件 URL
            
        Raises:
            Exception: API 调用失败
        """
        try:
            logger.info(f"尝试调用 Suno API（重试机制已启用）")
            # 确保使用 V5 模型
            config['model'] = self.model
            
            # 提供 callBackUrl（即使使用轮询模式）
            # 实际生产环境应该提供真实的回调URL
            if 'callBackUrl' not in config:
                config['callBackUrl'] = "http://localhost:8000/api/suno-callback"
            
            logger.info(f"开始调用 Suno {self.model} API: {config.get('title')}")
            logger.debug(f"请求配置: {config}")
            
            # 禁用 SSL 验证（仅开发环境）
            # 降低超时时间避免长时间等待
            async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
                response = await client.post(
                    self.api_url,
                    json=config,
                    headers={
                        "Authorization": f"Bearer {self.api_token}",
                        "Content-Type": "application/json"
                    }
                )
                
                logger.info(f"Suno API 响应状态: {response.status_code}")
                
                if response.status_code == 504:
                    raise Exception(
                        "Suno API 网关超时。可能原因：\n"
                        "1. Suno API 服务暂时不可用\n"
                        "2. API Token 无效或配额已用尽\n"
                        "3. 网络连接问题\n"
                        "请稍后重试或检查您的 API Token 状态"
                    )
                
                if response.status_code != 200:
                    error_detail = response.text
                    logger.error(f"Suno API 错误: {error_detail}")
                    raise Exception(
                        f"Suno API 返回错误 (状态码 {response.status_code}): {error_detail}"
                    )
                
                data = response.json()
                logger.debug(f"Suno API 响应: {data}")
                
                # 根据文档，成功响应返回 taskId
                if data.get("code") != 200:
                    raise Exception(f"Suno API 错误: {data.get('msg', '未知错误')}")
                
                task_id = data.get("data", {}).get("taskId")
                if not task_id:
                    raise Exception("Suno API 未返回 taskId")
                
                logger.info(f"✓ 任务创建成功，taskId: {task_id}")
                
                # 轮询获取结果
                music_url = await self._poll_task_result(task_id)
                
                logger.info(f"✓ 音乐生成成功 ({self.model}): {music_url}")
                return music_url
                
        except httpx.TimeoutException:
            logger.error("Suno API 请求超时")
            raise Exception("音乐生成超时，请稍后重试")
        except httpx.RequestError as e:
            logger.error(f"Suno API 请求错误: {str(e)}")
            raise Exception(f"网络请求失败: {str(e)}")
        except Exception as e:
            logger.error(f"Suno 服务错误: {str(e)}")
            raise
    
    async def _poll_task_result(self, task_id: str) -> str:
        """
        轮询任务结果（使用指数退避策略）
        
        Args:
            task_id: 任务 ID
            
        Returns:
            str: 音乐文件 URL
        """
        # 根据文档，正确的查询端点是 GET /api/v1/generate/record-info
        base_url = self.api_url.replace('/generate', '')
        detail_url = f"{base_url}/generate/record-info"
        
        # 指数退避策略：2s, 3s, 5s, 5s, 8s, 10s, 10s, 15s, 15s, 20s (总共约95秒)
        delays = [2, 3, 5, 5, 8, 10, 10, 15, 15, 20]
        
        logger.info(f"开始轮询任务: {task_id}（使用指数退避策略）")
        logger.debug(f"查询端点: {detail_url}")
        
        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            for i, delay in enumerate(delays):
                try:
                    logger.debug(f"发送查询请求 [第{i+1}/{len(delays)}次]: taskId={task_id}")
                    
                    # 使用 GET 方法，taskId 作为查询参数
                    response = await client.get(
                        f"{detail_url}?taskId={task_id}",
                        headers={
                            "Authorization": f"Bearer {self.api_token}"
                        }
                    )
                    
                    logger.debug(f"响应状态: {response.status_code}")
                    
                    if response.status_code == 200:
                        data = response.json()
                        logger.info(f"API响应: {data}")
                        
                        if data.get("code") == 200:
                            task_data = data.get("data", {})
                            status = task_data.get("status")
                            
                            logger.info(f"任务状态: {status}")
                            
                            if status == "SUCCESS":
                                # 根据实际响应结构，数据在 response.sunoData 中
                                response_data = task_data.get("response", {})
                                tracks = response_data.get("sunoData", [])
                                
                                if tracks and len(tracks) > 0:
                                    # 返回第一首歌的 URL（字段名是 audioUrl，驼峰命名）
                                    audio_url = tracks[0].get("audioUrl")
                                    if audio_url:
                                        logger.info(f"✓ 获取到音频URL: {audio_url}")
                                        return audio_url
                                    else:
                                        logger.warning("音频URL为空")
                                else:
                                    logger.warning("响应中没有音频数据")
                            
                            elif status == "FAILED":
                                error_msg = task_data.get("errorMessage", "未知错误")
                                raise Exception(f"音乐生成失败: {error_msg}")
                            
                            elif status == "GENERATING" or status == "PENDING":
                                logger.info(f"任务仍在处理中... [{i+1}/{max_attempts}]")
                        else:
                            logger.warning(f"API返回错误代码: {data.get('code')}, 消息: {data.get('msg')}")
                    else:
                        logger.warning(f"HTTP状态码: {response.status_code}, 响应: {response.text[:200]}")
                    
                    # 使用指数退避延迟
                    logger.debug(f"等待 {delay} 秒后重试...")
                    await asyncio.sleep(delay)
                    
                except Exception as e:
                    logger.warning(f"轮询失败 [{i+1}/{len(delays)}]: {str(e)}")
                    await asyncio.sleep(delay)
            
            total_time = sum(delays)
            raise Exception(f"轮询超时：任务 {task_id} 在 {total_time} 秒内未完成")
