#!/usr/bin/env python3
"""
Server酱微信推送 - 将穿搭效果图推送到微信
"""
import json, urllib.request, sys, os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, '..', 'config', 'seedream.json')
LOCAL_CONFIG_FILE = os.path.join(BASE_DIR, '..', 'config', 'seedream.local.json')

with open(CONFIG_FILE, 'r') as f:
    config = json.load(f)

# 合并本地密钥（不提交Git）
if os.path.exists(LOCAL_CONFIG_FILE):
    with open(LOCAL_CONFIG_FILE, 'r') as f:
        local = json.load(f)
    config.update(local)

SENDKEY = config.get('wechat_sendkey', '')
if not SENDKEY:
    print("❌ 未配置 wechat_sendkey")
    sys.exit(1)

def send_wechat(title, content=""):
    """发送微信推送"""
    url = f"https://sctapi.ftqq.com/{SENDKEY}.send"
    data = json.dumps({
        "title": title,
        "desp": content
    }).encode('utf-8')

    req = urllib.request.Request(url, data=data, headers={
        'Content-Type': 'application/json;charset=utf-8'
    })

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            if result.get('code') == 0:
                print(f"✅ 微信推送成功")
                return True
            else:
                print(f"⚠️  推送返回: {result.get('message', 'unknown')}")
                return False
    except Exception as e:
        print(f"❌ 推送失败: {e}")
        return False

def send_outfit_image(outfit_name, items, github_image_url):
    """发送穿搭效果图推送"""
    # 构建单品列表
    item_lines = ""
    for item in items:
        item_lines += f"- {item}\n"

    content = f"""![穿搭效果图]({github_image_url})

---
**单品清单**
{item_lines}
🔗 [查看项目](https://github.com/wangyunkun123/fashion-style-advisor)
"""

    title = f"👔 {outfit_name}"
    return send_wechat(title, content)

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("用法: python3 notify.py <穿搭名称> <GitHub图片URL> [单品1] [单品2] ...")
        print("示例: python3 notify.py '6月11日 日系轻熟' 'https://...jpg' 'TS-011 杏色短袖' 'SH-008 棕色短裤'")
        sys.exit(1)

    outfit_name = sys.argv[1]
    image_url = sys.argv[2]
    items = sys.argv[3:]

    send_outfit_image(outfit_name, items, image_url)
