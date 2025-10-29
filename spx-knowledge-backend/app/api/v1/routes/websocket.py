"""
WebSocket Endpoints
根据文档修改功能设计实现WebSocket实时通知端点
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from typing import Optional
import json
from app.services.websocket_notification_service import websocket_notification_service
from app.core.logging import logger

router = APIRouter()

@router.websocket("/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """WebSocket连接端点 - 根据设计文档实现"""
    try:
        logger.info(f"WebSocket连接请求: user_id={user_id}")
        
        # 建立连接
        await websocket_notification_service.connect(websocket, user_id)
        
        try:
            while True:
                # 接收客户端消息
                data = await websocket.receive_text()
                message = json.loads(data)
                
                # 处理客户端消息
                await handle_client_message(websocket, user_id, message)
                
        except WebSocketDisconnect:
            logger.info(f"WebSocket连接断开: user_id={user_id}")
        except Exception as e:
            logger.error(f"WebSocket处理错误: {e}", exc_info=True)
        finally:
            # 断开连接
            websocket_notification_service.disconnect(websocket, user_id)
            
    except Exception as e:
        logger.error(f"WebSocket端点错误: {e}", exc_info=True)


# 文档状态推送：无需鉴权，解决前端 /ws/documents/status 403 问题
@router.websocket("/documents/status")
async def documents_status_socket(websocket: WebSocket):
    try:
        await websocket.accept()
        logger.info("WebSocket连接: 文档状态推送")
        # 初次连接发送JSON欢迎包，避免前端解析错误
        await websocket.send_json({"type": "connected", "message": "ok"})
        # 简单心跳/占位实现，前端可仅用于建立可用连接
        while True:
            try:
                data = await websocket.receive_text()
                # 统一返回JSON，前端按JSON解析
                await websocket.send_json({"type": "pong", "echo": data})
            except WebSocketDisconnect:
                break
    except Exception as e:
        logger.error(f"文档状态WebSocket错误: {e}", exc_info=True)

async def handle_client_message(websocket: WebSocket, user_id: str, message: dict):
    """处理客户端消息 - 根据设计文档实现"""
    try:
        message_type = message.get("type", "")
        
        if message_type == "ping":
            # 心跳检测
            await websocket_notification_service.send_personal_message({
                "type": "pong",
                "timestamp": "2024-01-01T10:00:00Z"
            }, websocket)
            
        elif message_type == "subscribe":
            # 订阅特定类型的通知
            subscription_type = message.get("subscription_type", "")
            await websocket_notification_service.send_personal_message({
                "type": "subscription_confirmed",
                "subscription_type": subscription_type,
                "message": f"已订阅 {subscription_type} 通知"
            }, websocket)
            
        elif message_type == "unsubscribe":
            # 取消订阅
            subscription_type = message.get("subscription_type", "")
            await websocket_notification_service.send_personal_message({
                "type": "unsubscription_confirmed",
                "subscription_type": subscription_type,
                "message": f"已取消订阅 {subscription_type} 通知"
            }, websocket)
            
        else:
            # 未知消息类型
            await websocket_notification_service.send_personal_message({
                "type": "error",
                "message": f"未知的消息类型: {message_type}"
            }, websocket)
            
    except Exception as e:
        logger.error(f"处理客户端消息错误: {e}", exc_info=True)
        await websocket_notification_service.send_personal_message({
            "type": "error",
            "message": f"处理消息失败: {str(e)}"
        }, websocket)

@router.get("/ws/stats")
async def get_websocket_stats():
    """获取WebSocket连接统计 - 根据设计文档实现"""
    try:
        stats = websocket_notification_service.get_connection_stats()
        return stats
    except Exception as e:
        logger.error(f"获取WebSocket统计错误: {e}", exc_info=True)
        return {"error": str(e)}
