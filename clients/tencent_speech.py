# -*- coding: utf-8 -*-
"""腾讯云实时语音识别(ASR V2)与流式语音合成(TTS stream_ws)客户端。

移植自 aiagent-end/models/tts_say/tts_ws_client.py，改造点：
- 配置改读 core.config.settings（.env 未填密钥时接口返回明确错误而非启动失败）
- ASR 桥接收尾重写：前端 stop 控制帧 -> 向腾讯云发结束信令 -> drain 到最终结果，
  修复参考实现「cancel 丢最终结果 / 见第一个 final 就退出」的缺陷
"""
import asyncio
import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import AsyncGenerator
from urllib.parse import urlencode

import websockets
from fastapi import WebSocket, WebSocketDisconnect

from core.config import settings

ASR_HOST = "asr.cloud.tencent.com"
ASR_DRAIN_TIMEOUT = 5  # 收到结束信令后等待腾讯云最终结果的最长秒数


class SpeechNotConfigured(RuntimeError):
    pass


def _ensure_configured() -> None:
    if not settings.speech_ready:
        raise SpeechNotConfigured("腾讯云语音密钥未配置，请在 .env 填写 TENCENT_SECRET_ID/TENCENT_SECRET_KEY/TENCENT_APP_ID")


# ---------------------------------------------------------------- TTS

def _tts_generate_signature(sign_str: str) -> str:
    """腾讯TTS websocket签名: HMAC-SHA1 + base64"""
    hmac_obj = hmac.new(settings.TENCENT_SECRET_KEY.encode(), sign_str.encode(), hashlib.sha1)
    return base64.b64encode(hmac_obj.digest()).decode()


def _tts_build_ws_url(text: str, session_id: str) -> str:
    """stream_ws 请求URL：Text 放 URL 参数，签名原文为 GETtts.cloud.tencent.com/stream_ws?参数ASCII升序"""
    timestamp = int(time.time())
    params = {
        "Action": "TextToStreamAudioWS",
        "AppId": settings.TENCENT_APP_ID,
        "SecretId": settings.TENCENT_SECRET_ID,
        "Timestamp": str(timestamp),
        "Expired": str(timestamp + 24 * 3600),
        "SessionId": session_id,
        "Text": text,
        "VoiceType": str(settings.TTS_VOICE_TYPE),
        "SampleRate": str(settings.TTS_SAMPLE_RATE),
        "Codec": settings.TTS_CODEC,
        "Speed": "0",
        "Volume": "0",
    }
    sign_str = "GETtts.cloud.tencent.com/stream_ws?" + "&".join(
        f"{k}={v}" for k, v in sorted(params.items())
    )
    params["Signature"] = _tts_generate_signature(sign_str)
    return f"{settings.TTS_WS_URL}?{urlencode(params)}"


def split_long_text(text: str, chunk_size: int = 120):
    """长文本分片，每片最多120汉字，优先按标点切"""
    start = 0
    text_len = len(text)
    while start < text_len:
        end = min(start + chunk_size, text_len)
        punc = ["。", "，", "！", "？", "\n"]
        pos = -1
        for p in punc:
            idx = text.find(p, start, end)
            if idx != -1:
                pos = idx + 1
                break
        if pos != -1:
            chunk = text[start:pos]
            start = pos
        else:
            chunk = text[start:end]
            start = end
        yield chunk


async def tts_stream(text: str) -> AsyncGenerator[bytes, None]:
    """逐片流式调用腾讯TTS，yield mp3 二进制分片。每片一个 stream_ws 连接。"""
    _ensure_configured()
    for chunk in split_long_text(text):
        session_id = str(uuid.uuid4())
        url = _tts_build_ws_url(chunk, session_id)
        async with websockets.connect(url, max_size=10 * 1024 * 1024) as upstream:
            try:
                while True:
                    msg = await upstream.recv()
                    if isinstance(msg, bytes):
                        yield msg
                        continue
                    j = json.loads(msg)
                    if j.get("code", 0) != 0:
                        raise RuntimeError(f"腾讯TTS错误: {j}")
                    if j.get("final") == 1:
                        break
            finally:
                try:
                    await upstream.close()
                except Exception:
                    pass


# ---------------------------------------------------------------- ASR

def _asr_build_ws_url(voice_id: str) -> str:
    """按腾讯云签名规则生成 ASR V2 带签名的 WebSocket 地址。"""
    timestamp = int(time.time())
    expired = timestamp + 24 * 3600
    params = {
        "secretid": settings.TENCENT_SECRET_ID,
        "timestamp": timestamp,
        "expired": expired,
        "nonce": int(time.time() * 1000) % 1000000000,
        "engine_model_type": settings.ASR_ENGINE_MODEL_TYPE,
        "voice_id": voice_id,
        "voice_format": settings.ASR_VOICE_FORMAT,
        "needvad": settings.ASR_NEED_VAD,
    }
    # 签名原文: host/path?参数ASCII升序(值用原始值)，HMAC-SHA1->Base64
    source = "{}?{}".format(
        "{}/asr/v2/{}".format(ASR_HOST, settings.TENCENT_APP_ID),
        "&".join("{}={}".format(k, params[k]) for k in sorted(params)),
    )
    digest = hmac.new(settings.TENCENT_SECRET_KEY.encode(), source.encode(), hashlib.sha1).digest()
    params["signature"] = base64.b64encode(digest).decode()
    return "wss://{}/asr/v2/{}?{}".format(ASR_HOST, settings.TENCENT_APP_ID, urlencode(params))


def _extract_asr_text(payload: dict) -> str:
    result = payload.get("result") or {}
    return result.get("voice_text") or result.get("text") or ""


def _is_sentence_final(payload: dict) -> bool:
    """句末标记：整场 final=1，或 slice_type=1（本句最后一个切片）"""
    if payload.get("final") == 1:
        return True
    result = payload.get("result") or {}
    return result.get("slice_type") == 1


async def run_asr_bridge(client_ws: WebSocket) -> None:
    """前端<->腾讯云 ASR 桥。

    上行：二进制帧=音频原样转发；文本帧 {"type":"stop"}=松手结束。
    下行归一化：ready / asr_partial(累计全文) / asr_end(最终全文) / error。
    """
    _ensure_configured()
    voice_id = str(uuid.uuid4())
    url = _asr_build_ws_url(voice_id)

    segments: list[str] = []  # 已定稿的整句
    current = ""              # 当前未定稿半句
    stop_requested = asyncio.Event()

    def full_text() -> str:
        return "".join(segments) + current

    try:
        async with websockets.connect(url, max_size=2 * 1024 * 1024, ping_interval=None) as upstream:
            await client_ws.send_json({"type": "ready"})

            async def client_to_upstream() -> None:
                while True:
                    try:
                        msg = await client_ws.receive()
                    except WebSocketDisconnect:
                        return
                    if msg["type"] == "websocket.disconnect":
                        return
                    if msg.get("bytes"):
                        await upstream.send(msg["bytes"])
                    elif msg.get("text"):
                        try:
                            if json.loads(msg["text"]).get("type") == "stop":
                                # 空二进制帧 = ASR V2 结束信令，触发服务端吐最终结果
                                await upstream.send(b"")
                                stop_requested.set()
                                return
                        except json.JSONDecodeError:
                            pass

            async def upstream_to_client() -> None:
                nonlocal current
                async for msg in upstream:
                    if isinstance(msg, (bytes, bytearray)):
                        continue  # ASR 正常只回 JSON
                    try:
                        payload = json.loads(msg)
                    except json.JSONDecodeError:
                        continue
                    if payload.get("code", 0) != 0:
                        await client_ws.send_json({"type": "error", "message": payload.get("message", "识别失败")})
                        return
                    text = _extract_asr_text(payload)
                    if _is_sentence_final(payload):
                        if text:
                            segments.append(text)
                        current = ""
                    elif text:
                        current = text
                    if stop_requested.is_set() and payload.get("final") == 1:
                        break
                    await client_ws.send_json({"type": "asr_partial", "text": full_text()})

            pump = asyncio.create_task(client_to_upstream())
            drain = asyncio.create_task(upstream_to_client())
            try:
                # 等前端 stop/断开
                await pump
                # 给上游最多 ASR_DRAIN_TIMEOUT 秒吐出最终结果；超时用已累计文本兜底
                try:
                    await asyncio.wait_for(drain, ASR_DRAIN_TIMEOUT)
                except (TimeoutError, asyncio.TimeoutError):
                    drain.cancel()
                except WebSocketDisconnect:
                    pass
                await client_ws.send_json({"type": "asr_end", "text": full_text()})
            finally:
                pump.cancel()
                drain.cancel()
    except Exception as e:
        try:
            await client_ws.send_json({"type": "error", "message": f"ASR桥接异常: {e}"})
        except Exception:
            pass
    finally:
        try:
            await client_ws.close()
        except Exception:
            pass
