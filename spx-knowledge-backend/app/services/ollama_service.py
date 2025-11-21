"""
Ollama Service
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
import requests
import json
from app.config.settings import settings

class OllamaService:
    """Ollama服务"""
    
    def __init__(self, db: Session):
        self.db = db
        self.base_url = settings.OLLAMA_BASE_URL
    
    async def generate_text(
        self, 
        prompt: str, 
        model: str = settings.OLLAMA_MODEL,
        format: Optional[str] = None
    ) -> str:
        """生成文本
        
        Args:
            prompt: 提示词
            model: 模型名称
            format: 输出格式，如 "json" 用于强制 JSON 输出（Ollama 支持）
        """
        try:
            request_data = {
                "model": model,
                "prompt": prompt,
                "stream": False
            }
            # 如果指定了 format，添加到请求中（Ollama 支持 format 参数强制 JSON 输出）
            if format:
                request_data["format"] = format
            
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=request_data
            )
            response.raise_for_status()
            result = response.json()
            return result.get("response", "")
        except Exception as e:
            print(f"Ollama文本生成错误: {e}")
            return ""
    
    async def generate_embedding(
        self, 
        text: str, 
        model: str = settings.OLLAMA_EMBEDDING_MODEL
    ) -> List[float]:
        """生成嵌入向量"""
        try:
            response = requests.post(
                f"{self.base_url}/api/embeddings",
                json={
                    "model": model,
                    "prompt": text
                }
            )
            response.raise_for_status()
            result = response.json()
            return result.get("embedding", [])
        except Exception as e:
            print(f"Ollama向量生成错误: {e}")
            return []
    
    async def chat_completion(
        self, 
        messages: List[Dict[str, str]], 
        model: str = settings.OLLAMA_MODEL
    ) -> str:
        """聊天完成"""
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": False
                }
            )
            response.raise_for_status()
            result = response.json()
            return result.get("message", {}).get("content", "")
        except Exception as e:
            print(f"Ollama聊天完成错误: {e}")
            return ""
    
    async def generate_answer(self, prompt: str, model: str = settings.OLLAMA_MODEL) -> str:
        """生成答案（generate_text的别名，用于兼容）"""
        try:
            return await self.generate_text(prompt, model)
        except Exception as e:
            print(f"Ollama生成答案错误: {e}")
            return ""
    
    async def stream_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = settings.OLLAMA_MODEL
    ):
        """流式聊天完成"""
        import asyncio
        from typing import AsyncGenerator
        
        try:
            # 在线程池中执行同步请求，避免阻塞事件循环
            loop = asyncio.get_event_loop()
            
            def _make_stream_request():
                """在线程池中执行的同步请求"""
                response = requests.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": model,
                        "messages": messages,
                        "stream": True
                    },
                    stream=True,
                    timeout=300
                )
                response.raise_for_status()
                return response
            
            # 在线程池中执行请求
            response = await loop.run_in_executor(None, _make_stream_request)
            
            # 在线程池中读取流式响应
            def _read_stream():
                """在线程池中读取流式数据"""
                chunks = []
                for line in response.iter_lines():
                    if line:
                        try:
                            data = json.loads(line.decode('utf-8'))
                            content = data.get("message", {}).get("content", "")
                            done = data.get("done", False)
                            chunks.append((content, done))
                            if done:
                                break
                        except json.JSONDecodeError:
                            continue
                return chunks
            
            # 在线程池中读取流
            chunks = await loop.run_in_executor(None, _read_stream)
            
            # 异步yield结果
            for content, done in chunks:
                if content:
                    yield content
                if done:
                    break
                    
        except Exception as e:
            import traceback
            print(f"Ollama流式聊天完成错误: {e}")
            print(traceback.format_exc())
            yield f"错误: {str(e)}"