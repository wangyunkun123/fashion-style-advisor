#!/usr/bin/env python3
"""
月度回访 — 检查是否需要向用户发送模式切换提醒

用法:
  python3 tools/monthly_checkin.py              # 检查并发送回访（自动判断）
  python3 tools/monthly_checkin.py --dry-run    # 仅显示会发什么，不实际发送
"""

import os, sys, json
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.join(BASE_DIR, '..')
PREF_FILE = os.path.join(PROJ_DIR, 'config', 'push_preference.json')

def load_prefs():
    if not os.path.exists(PREF_FILE):
        return {'mode': 'both', 'switched_at': datetime.now().strftime('%Y-%m-%d'), 'checkin_done': []}
    with open(PREF_FILE, 'r') as f:
        return json.load(f)

def save_prefs(prefs):
    with open(PREF_FILE, 'w') as f:
        json.dump(prefs, f, ensure_ascii=False, indent=2)

def days_since_switch(prefs):
    switched = prefs.get('switched_at', datetime.now().strftime('%Y-%m-%d'))
    dt = datetime.strptime(switched, '%Y-%m-%d')
    return (datetime.now() - dt).days

def check_and_send(dry_run=False):
    prefs = load_prefs()
    mode = prefs.get('mode', 'both')
    days = days_since_switch(prefs)
    done = set(prefs.get('checkin_done', []))

    # 首次选择(both→simple/rich)当天不算，等待30天
    if mode == 'both' or days < 30:
        return None

    sys.path.insert(0, os.path.join(BASE_DIR))
    from wechat_control import push_wechat

    base = get_base_url()
    msg = None

    # 30-59天：第一次回访
    if 30 <= days < 60:
        if 'day30' not in done:
            if mode == 'simple':
                msg = ("📊 30天穿搭服务报告\n\n"
                       "想继续躺平还是换个玩法？\n\n"
                       f"[🔄 切换百科版，让AI学着你的喜好来]({base}/setpref?mode=rich)")
            else:
                msg = ("📝 你已经给AI上了一月课了\n\n"
                       "它现在挺懂你的。要不要让它自己发挥，你只管穿？\n\n"
                       f"[🎯 切换简洁版，AI直接推]({base}/setpref?mode=simple)")
            if not dry_run:
                prefs.setdefault('checkin_done', []).append('day30')
                save_prefs(prefs)

    # 31天额外请求：后悔了提醒
    if 31 <= days < 60 and 'day31' not in done and 'day60' not in done:
        other = 'rich' if mode == 'simple' else 'simple'
        other_name = '百科版' if other == 'rich' else '简洁版'
        msg = ("🤔 后悔了？想改回上一版？\n\n"
               f"点一下就能切回{other_name} 📦\n\n"
               f"[🔄 切回{other_name}]({base}/setpref?mode={other})")
        if not dry_run:
            prefs.setdefault('checkin_done', []).append('day31')
            save_prefs(prefs)

    # 60天+：第二次回访
    if days >= 60 and 'day60' not in done:
        msg = ("💫 60天穿搭陪伴\n\n"
               "还是喜欢现在的方式？还是想试试另一种？\n\n"
               f"[🔄 切换模式]({base}/setpref)")
        if not dry_run:
            prefs.setdefault('checkin_done', []).append('day60')
            save_prefs(prefs)

    if msg:
        if dry_run:
            print(f"[DRY RUN] 会发送: {msg[:80]}...")
        else:
            push_wechat('🤖 穿搭助手月度回访', msg)
            return msg
    return None

def get_base_url():
    cfg = os.path.join(PROJ_DIR, 'config', 'seedream.local.json')
    if os.path.exists(cfg):
        with open(cfg) as f:
            return json.load(f).get('push_base_url', 'http://localhost:8765')
    return 'http://localhost:8765'

if __name__ == '__main__':
    dry = '--dry-run' in sys.argv
    result = check_and_send(dry_run=dry)
    if result:
        print('✅ 回访消息已发送')
    else:
        days = days_since_switch(load_prefs())
        print(f'📅 已过{days}天，无需回访')
