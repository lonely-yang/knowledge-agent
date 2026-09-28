# -*- coding: utf-8 -*-
"""语音链路自检脚本（不依赖浏览器）：
1) 检查 /voice 与 /api/voice 路由是否已注册
2) 用 JWT 密钥签一个 token，直连 WS /voice/tts/ws 合成一句话，保存 mp3
用法：python scripts/test_voice.py [要合成的文本]
前提：后端已在 127.0.0.1:8000 运行
"""
import asyncio
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import websockets  # noqa: E402

from utils.auth import create_access_token  # noqa: E402

TEXT = sys.argv[1] if len(sys.argv) > 1 else "你好，这是一段语音合成链路自检。"


def check_http_routes() -> None:
    for path in ("/voice/tts", "/api/voice/tts"):
        url = f"http://127.0.0.1:8000{path}?text=hi"
        try:
            urllib.request.urlopen(url, timeout=5)
            print(f"[FAIL] {path} 无鉴权竟然 200？")
        except urllib.error.HTTPError as e:
            print(f"[OK]   {path} -> HTTP {e.code}（401=已注册缺token，404=路由未注册）")
        except Exception as e:
            print(f"[FAIL] {path} -> {e}")


async def test_tts_ws() -> None:
    token = create_access_token(1, "voice-selftest")
    uri = f"ws://127.0.0.1:8000/voice/tts/ws?token={token}"
    audio = bytearray()
    try:
        async with websockets.connect(uri, max_size=10 * 1024 * 1024) as ws:
            first = json.loads(await ws.recv())
            print(f"[OK]   WS 已连接, 首帧: {first}")
            if first.get("event") == "error" or "connected" not in str(first):
                print("[FAIL] 服务端拒绝了连接（多为密钥未配置或 token 无效）")
                return
            await ws.send(json.dumps({"type": "tts_fragment", "seq": 1, "text": TEXT}))
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=30)
                if isinstance(msg, (bytes, bytearray)):
                    audio.extend(msg)
                    continue
                j = json.loads(msg)
                if j.get("event") == "fragment_end":
                    break
                if j.get("event") == "error":
                    print(f"[FAIL] 合成报错: {j}")
                    return
    except Exception as e:
        print(f"[FAIL] WS 测试异常: {e!r}")
        return
    out = Path(__file__).parent / "test_voice_output.mp3"
    out.write_bytes(bytes(audio))
    print(f"[{'OK' if audio else 'FAIL'}] 收到音频 {len(audio)} bytes -> {out}（能播放=腾讯TTS链路通）")


if __name__ == "__main__":
    check_http_routes()
    asyncio.run(test_tts_ws())
