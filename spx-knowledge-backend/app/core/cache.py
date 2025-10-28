"""
Cache Module
"""

from typing import Any, Optional
import json
import redis
from app.config.settings import settings

class CacheManager:
    """缓存管理器"""
    
    def __init__(self):
        self.redis_client = redis.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True
        )
    
    async def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        try:
            value = self.redis_client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            print(f"缓存获取错误: {e}")
            return None
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        expire: Optional[int] = None
    ) -> bool:
        """设置缓存"""
        try:
            if expire:
                self.redis_client.setex(key, expire, json.dumps(value))
            else:
                self.redis_client.set(key, json.dumps(value))
            return True
        except Exception as e:
            print(f"缓存设置错误: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """删除缓存"""
        try:
            self.redis_client.delete(key)
            return True
        except Exception as e:
            print(f"缓存删除错误: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """检查缓存是否存在"""
        try:
            return bool(self.redis_client.exists(key))
        except Exception as e:
            print(f"缓存检查错误: {e}")
            return False

# 全局缓存管理器实例
cache_manager = CacheManager()
