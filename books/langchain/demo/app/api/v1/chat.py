from fastapi import APIRouter
from app.models.schemas import ChatRequest

router = APIRouter()


@router.post("/chat/stream")
async def chat_endpoint(request: ChatRequest):
    """流式对话"""
    pass


@router.get("/chat/messages")
async def get_chat_messages(thread_id: str):
    """获取历史消息"""
    pass


@router.delete("/chat/messages")
async def clear_chat_messages(thread_id: str):
    """清空历史消息"""
    pass