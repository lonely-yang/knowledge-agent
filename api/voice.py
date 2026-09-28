# -*- coding: utf-8 -*-
"""语音接口：TTS(HTTP 旁路 + WS 逐句合成)、STT(WS 实时识别桥)。

浏览器 WebSocket 不能自定义 header，WS 鉴权统一走 query token，
复用 utils.auth.decode_token 校验，与 core.security.get_current_user 同源。
"""
import json

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from clients.tencent_speech import SpeechNotConfigured, run_asr_bridge, tts_stream
from core.config import settings
from core.security import get_current_user
from utils.auth import decode_token

voice_router = APIRouter(prefix="/voice", tags=["语音"])

WS_CLOSE_UNAUTHORIZED = 4401
WS_CLOSE_NOT_CONFIGURED = 4400
WS_CLOSE_UPSTREAM_ERROR = 4500


@voice_router.get("/tts", response_class=StreamingResponse)
async def tts_http(
    text: str = Query(..., description="待合成文本，支持长文本"),
    user=Depends(get_current_user),
):
    """HTTP 流式合成旁路：直接产 mp3，便于验证与简单场景播放。"""
    try:
        if not settings.speech_ready:
            raise SpeechNotConfigured()
        return StreamingResponse(tts_stream(text), media_type="audio/mpeg")
    except SpeechNotConfigured as e:
        raise HTTPException(status_code=400, detail=str(e))


async def _ws_auth_or_close(ws: WebSocket, token: str) -> bool:
    """accept 后校验 query token；失败按约定 close code 断开。"""
    await ws.accept()
    if not decode_token(token, "access"):
        await ws.close(code=WS_CLOSE_UNAUTHORIZED, reason="unauthorized")
        return False
    if not settings.speech_ready:
        await ws.close(code=WS_CLOSE_NOT_CONFIGURED, reason="speech service not configured")
        return False
    return True


@voice_router.websocket("/stt/ws")
async def ws_stt(ws: WebSocket, token: str = Query("")):
    """按住说话：上行 16k pcm 二进制帧 + {"type":"stop"} 控制帧；
    下行 ready / asr_partial / asr_end / error。"""
    if not await _ws_auth_or_close(ws, token):
        return
    await run_asr_bridge(ws)


@voice_router.websocket("/tts/ws")
async def ws_tts(ws: WebSocket, token: str = Query("")):
    """边生成边播报：前端逐句发 {"type":"tts_fragment","seq":n,"text":...}，
    服务端串行合成，推二进制 mp3 分片，每句完发 {"event":"fragment_end","seq":n}。"""
    if not await _ws_auth_or_close(ws, token):
        return
    await ws.send_json({"event": "connected"})
    try:
        while True:
            try:
                payload = json.loads(await ws.receive_text())
            except WebSocketDisconnect:
                break
            msg_type = payload.get("type")
            if msg_type == "tts_fragment":
                text = (payload.get("text") or "").strip()
                if not text:
                    continue
                try:
                    async for audio in tts_stream(text):
                        await ws.send_bytes(audio)
                except Exception:
                    await ws.send_json({"event": "error", "seq": payload.get("seq"), "message": "TTS合成失败"})
                    continue
                await ws.send_json({"event": "fragment_end", "seq": payload.get("seq")})
            elif msg_type == "tts_done":
                await ws.send_json({"event": "end"})
                break
            else:
                await ws.send_json({"event": "error", "message": "未知消息类型"})
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await ws.close(code=WS_CLOSE_UPSTREAM_ERROR, reason="tts upstream error")
        except Exception:
            pass
