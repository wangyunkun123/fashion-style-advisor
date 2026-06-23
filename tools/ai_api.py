# -*- coding: utf-8 -*-
"""豆包 AI API 调用 — Doubao Chat + JSON 提取 + 图片预处理"""

import io
import json
import os
import re
import urllib.request
import urllib.error
from PIL import Image as PILImage, ImageOps

_PROJ_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_FILE = os.path.join(_PROJ_DIR, 'config', 'seedream.local.json')

with open(_CONFIG_FILE, 'r') as f:
    _config = json.load(f)

API_KEY = _config.get('api_key', '')
API_CHAT_URL = 'https://ark.cn-beijing.volces.com/api/plan/v3/chat/completions'
CHAT_MODEL = 'doubao-seed-2.0-code'


def call_doubao_chat(messages, max_tokens=16384, timeout=120):
    """调用 doubao-seed-2.0-code 聊天 API
    自动检测 finish_reason=length 并用更大 max_tokens 重试
    """
    _max_tokens = max_tokens
    for _attempt in range(2):
        payload = json.dumps({
            'model': CHAT_MODEL,
            'messages': messages,
            'max_tokens': _max_tokens,
            'temperature': 0.7,
        }).encode('utf-8')
        req = urllib.request.Request(API_CHAT_URL, data=payload, headers={
            'Content-Type': 'application/json; charset=utf-8',
            'Authorization': f'Bearer {API_KEY}',
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode('utf-8'))
            choice = result['choices'][0]
            msg = choice.get('message', {})
            content = msg.get('content', '')
            finish_reason = choice.get('finish_reason', '')
            if not content:
                reasoning = msg.get('reasoning_content', '')
                if reasoning:
                    content = reasoning
            if finish_reason == 'length' and _max_tokens < 16384:
                _max_tokens = 16384
                continue
            return content
        except urllib.error.HTTPError as e:
            # 捕获 HTTP 错误详情（如 400 Bad Request），方便诊断
            err_body = ''
            try:
                err_body = e.read().decode('utf-8')[:500]
            except Exception:
                pass
            raise RuntimeError(f'API HTTP {e.code}: {err_body}') from e
        except Exception:
            raise


def extract_json(text):
    """从 AI 回复中提取 JSON 对象"""
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return None


def resize_image_for_api(image_path, max_size=1024):
    """将图片缩放到 max_size px，返回 JPEG bytes"""
    img = PILImage.open(image_path)
    img = ImageOps.exif_transpose(img)
    if img.mode in ('RGBA', 'P', 'LA'):
        rgb = PILImage.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'P':
            img = img.convert('RGBA')
        rgb.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
        img = rgb
    elif img.mode != 'RGB':
        img = img.convert('RGB')
    w, h = img.size
    if max(w, h) > max_size:
        ratio = max_size / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), PILImage.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=80)
    return buf.getvalue()
