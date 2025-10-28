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
        model: str = settings.OLLAMA_MODEL
    ) -> str:
        """生成文本"""
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False
                }
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
