# 女性用户测试系统 — 实施计划

> **For agentic workers:** 按任务顺序执行，每步含 checkbox `- [ ]` 跟踪。
> **设计文档:** `docs/superpowers/specs/2026-06-22-female-user-testing-design.md`
> **分支:** `female-user-testing`

**目标:** 将 Fashion Style Advisor 从单用户扩展为 5-10 名女性用户端到端测试系统，不改现有单用户行为。

**架构:** 文件系统隔离（`users/<id>/`）+ `?user=` URL 路由 + 所有工具加 `--user` 可选参数。不改数据库、不改框架、不改 Tailscale 配置。

**技术栈:** Python 标准库 http.server + PIL + rembg + YOLO + JSON 文件存储

## 全局约束

- 不传 `--user` 或不带 `?user=` 时，所有工具行为完全不变（向下兼容）
- 所有新数据在 `users/` 和 `styles_women/` 目录，不污染现有目录
- 微信推送测试期间不使用（`push_wechat` 跳过）
- Tailscale Funnel URL 不变：`https://macbook-pro-1.taildbfbc0.ts.net/`
- 分支隔离：所有代码改动在 `female-user-testing` 分支

---

## 文件结构（最终状态）

```
项目根/
├── users/                          # 新建：多用户数据根目录
│   ├── _registry.json              # 用户索引
│   └── <user_id>/
│       ├── profile.json            # 身形+偏好
│       ├── config.json             # 用户级配置
│       ├── wardrobe/
│       │   ├── 服装档案.md
│       │   ├── enhanced/           # 抠图
│       │   └── tags/               # 结构化标签 JSON
│       ├── outfits/
│       │   └── <日期>_<场景>/
│       ├── discovered_styles/      # 个人发现风格（图片）
│       └── cache/
│           └── prototype.html
├── styles_women/                   # 新建：女性风格库
│   ├── WF-01_french_effortless/
│   ├── ...（共12个）
│   └── WF-12_dark_academia/
├── tools/
│   ├── wechat_control.py           # 修改：加 ?user= 路由
│   ├── common.py                   # 修改：加 resolve_user_dir()
│   ├── build_prototype.py          # 修改：加 --user
│   ├── generate.py                 # 修改：加 --user
│   ├── composite_v2.py             # 修改：加 --user
│   ├── style_matcher.py            # 修改：加 --user
│   ├── wardrobe_advisor.py         # 修改：加 --user
│   ├── user_manager.py             # 新建：用户管理
│   ├── quick_tag.py                # 新建：快速入库
│   └── style_scout_women.py        # 新建：女性风格发现
└── docs/superpowers/
    ├── specs/2026-06-22-female-user-testing-design.md
    └── plans/2026-06-22-female-user-testing.md
```

---

# Phase A：基础架构（多用户隔离）

## Task A1: 创建 users/ 目录 + 用户管理器

**Files:**
- Create: `tools/user_manager.py`
- Create: `users/_registry.json`（首个空注册）

**Interfaces:**
- Produces: `load_registry() -> dict`, `save_registry(dict)`, `create_user(user_id, profile_data) -> str`, `user_exists(user_id) -> bool`, `get_user_dir(user_id) -> str`, `list_users() -> list`

- [ ] **Step 1: 编写 user_manager.py**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用户管理器 — 创建/查询/列表，操作 users/_registry.json"""
import os, json, time, shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.dirname(BASE_DIR)
USERS_DIR = os.path.join(PROJ_DIR, 'users')
REGISTRY_FILE = os.path.join(USERS_DIR, '_registry.json')

os.makedirs(USERS_DIR, exist_ok=True)


def _ensure_registry():
    """确保注册文件存在，不存在则创建空注册"""
    if not os.path.exists(REGISTRY_FILE):
        with open(REGISTRY_FILE, 'w') as f:
            json.dump({}, f, indent=2)
    with open(REGISTRY_FILE, 'r') as f:
        return json.load(f)


def load_registry():
    """返回 {user_id: {created, last_active, status}}"""
    return _ensure_registry()


def save_registry(reg):
    with open(REGISTRY_FILE, 'w') as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)


def user_exists(user_id):
    reg = load_registry()
    return user_id in reg


def create_user(user_id, profile_data=None):
    """创建新用户：建目录 + 初始化 profile.json + 写注册表。
    返回 user_dir 路径。已存在则直接返回。
    """
    user_dir = os.path.join(USERS_DIR, user_id)
    
    # 建目录结构
    for sub in ['wardrobe', 'wardrobe/tags', 'wardrobe/enhanced',
                'outfits', 'discovered_styles', 'cache']:
        os.makedirs(os.path.join(user_dir, sub), exist_ok=True)
    
    # 初始化 profile.json
    profile_path = os.path.join(user_dir, 'profile.json')
    if not os.path.exists(profile_path):
        default_profile = {
            'user_id': user_id,
            'gender': 'female',
            'created': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'onboarding_step': 0,
            'onboarding_complete': False,
            'body': {},
            'style_prefs': [],
        }
        if profile_data:
            default_profile.update(profile_data)
        with open(profile_path, 'w') as f:
            json.dump(default_profile, f, ensure_ascii=False, indent=2)
    
    # 初始化 config.json
    config_path = os.path.join(user_dir, 'config.json')
    if not os.path.exists(config_path):
        with open(config_path, 'w') as f:
            json.dump({'push_enabled': False}, f, indent=2)
    
    # 注册
    reg = load_registry()
    if user_id not in reg:
        reg[user_id] = {
            'created': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'last_active': None,
            'status': 'onboarding',
        }
        save_registry(reg)
    
    return user_dir


def get_user_dir(user_id):
    """获取用户目录路径（不创建）"""
    return os.path.join(USERS_DIR, user_id)


def list_users():
    """列出所有用户 ID"""
    reg = load_registry()
    return list(reg.keys())


def update_last_active(user_id):
    reg = load_registry()
    if user_id in reg:
        reg[user_id]['last_active'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        save_registry(reg)
```

- [ ] **Step 2: 验证 registry 初始化**

```bash
cd "/Users/rabbit/Claude code/Fashion" && python3 -c "
from tools.user_manager import load_registry, create_user, user_exists
# 测试创建
d = create_user('_test', {'body': {'height_cm': 165}})
print('Created:', d)
print('Exists:', user_exists('_test'))
reg = load_registry()
print('Registry:', reg)
# 清理测试
import shutil, os
shutil.rmtree(os.path.join('users', '_test'))
reg.pop('_test', None)
from tools.user_manager import save_registry
save_registry(reg)
print('Cleanup done')
"
```

- [ ] **Step 3: Commit**

```bash
git add tools/user_manager.py users/_registry.json
git commit -m "feat: user_manager.py — 用户创建/注册/目录初始化"
```

---

## Task A2: common.py 加用户路径解析

**Files:**
- Modify: `tools/common.py`（追加函数）

**Interfaces:**
- Produces: `resolve_user_dir(user_id=None) -> str` — 无 user_id 返回 PROJ_DIR，有则返回 `users/<id>/`

- [ ] **Step 1: 在 common.py 末尾追加 resolve_user_dir**

在 `tools/common.py` 文件末尾添加：

```python
# ═══════════════════════════════════════════════════════════════
# 多用户支持（2026-06-22）
# ═══════════════════════════════════════════════════════════════

def resolve_user_dir(user_id=None):
    """解析用户数据根目录。
    user_id=None 或 'default' → 项目根（现有单用户模式，完全不变）
    user_id='alice'        → users/alice/（多用户模式）
    """
    if not user_id or user_id == 'default':
        return PROJ_DIR
    return os.path.join(PROJ_DIR, 'users', user_id)


def resolve_wardrobe_dir(user_id=None):
    """解析 wardrobe 目录"""
    return os.path.join(resolve_user_dir(user_id), 'wardrobe')


def resolve_outfits_dir(user_id=None):
    """解析 outfits 目录"""
    return os.path.join(resolve_user_dir(user_id), 'outfits')


def resolve_tags_dir(user_id=None):
    """解析 wardrobe/tags 目录"""
    return os.path.join(resolve_user_dir(user_id), 'wardrobe', 'tags')
```

- [ ] **Step 2: 验证**

```bash
cd "/Users/rabbit/Claude code/Fashion" && python3 -c "
from tools.common import resolve_user_dir, resolve_wardrobe_dir, resolve_outfits_dir
# 默认模式
print('Default:', resolve_user_dir())
print('Default wardrobe:', resolve_wardrobe_dir())
# 多用户模式
print('Alice:', resolve_user_dir('alice'))
print('Alice wardrobe:', resolve_wardrobe_dir('alice'))
"
```

- [ ] **Step 3: Commit**

```bash
git add tools/common.py
git commit -m "feat: common.py 加 resolve_user_dir/resolve_wardrobe_dir/resolve_outfits_dir"
```

---

## Task A3: wechat_control.py 加 ?user= 路由

**Files:**
- Modify: `tools/wechat_control.py`

**Interfaces:**
- Consumes: `user_manager.load_registry()`, `user_manager.create_user()`, `user_manager.update_last_active()`, `common.resolve_user_dir()`
- Produces: `resolve_request_user(handler) -> (user_id, need_onboarding)`, 修改 `do_GET`/`do_POST` 入口

这是最核心的改动。原则：在 Handler 入口处解析 `?user=`，注入到 `self.user_id` 和 `self.user_dir`，后续所有路径拼接用 `self.user_dir` 替代 `PROJECT_DIR`。

- [ ] **Step 1: 在 wechat_control.py 顶部添加导入和用户解析函数**

在现有 import 块后（约第 95 行后）添加：

```python
# ── 多用户支持 ────────────────────────────────────────
from tools.user_manager import (
    load_registry as _load_user_registry,
    create_user as _create_user,
    update_last_active as _update_user_active,
)
from tools.common import resolve_user_dir, resolve_wardrobe_dir, resolve_outfits_dir

def _resolve_user_from_request(handler):
    """从请求中解析用户 ID。返回 (user_id, need_onboarding)。
    - 无 ?user= 参数 → ('default', False)，完全向下兼容
    - ?user=alice 存在 → ('alice', False)
    - ?user=alice 不存在 → (None, True)，触发 onboarding
    """
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(handler.path)
    qs = parse_qs(parsed.query)
    user_id = qs.get('user', [None])[0]
    
    if not user_id:
        return ('default', False)
    
    # 安全校验：只允许字母数字下划线连字符
    import re
    if not re.match(r'^[a-zA-Z0-9_-]{1,32}$', user_id):
        return ('default', False)
    
    reg = _load_user_registry()
    if user_id in reg:
        _update_user_active(user_id)
        return (user_id, False)
    
    # 用户不在注册表中 → 需要 onboarding
    return (user_id, True)
```

- [ ] **Step 2: 修改 do_GET 入口，注入 self.user_id / self.user_dir**

在 `do_GET` 方法开头（第 2484 行后，`from urllib.parse import urlparse, parse_qs` 之后）添加：

```python
    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        
        # ── 多用户路由 ──
        user_id, need_onboarding = _resolve_user_from_request(self)
        self.user_id = user_id
        self.user_dir = resolve_user_dir(None if user_id == 'default' else user_id)
        
        # 需要 onboarding → 展示 onboarding 向导
        if need_onboarding and parsed.path in ('/', ''):
            self._html_resp(200, _load_onboarding_html(user_id, step=1))
            return
        
        # ... 后续现有逻辑不变
```

- [ ] **Step 3: 修改 do_POST 入口，同样注入**

在第 3391 行 `do_POST` 方法开头添加相同的用户解析：

```python
    def do_POST(self):
        # ── 多用户路由 ──
        user_id, need_onboarding = _resolve_user_from_request(self)
        self.user_id = user_id
        self.user_dir = resolve_user_dir(None if user_id == 'default' else user_id)
        
        # ... 后续现有逻辑
```

- [ ] **Step 4: 修改所有硬编码 PROJECT_DIR 路径引用**

将所有 `os.path.join(PROJECT_DIR, ...)` 中涉及用户数据读写的路径改为 `os.path.join(self.user_dir, ...)`。关键位置：

| 原路径 | 新路径 | 所在函数 |
|--------|--------|---------|
| `os.path.join(PROJECT_DIR, 'wardrobe', ...)` | `os.path.join(self.user_dir, 'wardrobe', ...)` | `parse_wardrobe`, `get_wardrobe_summary`, `_finalize_add_item` 等 |
| `os.path.join(PROJECT_DIR, 'outfits', ...)` | `os.path.join(self.user_dir, 'outfits', ...)` | `execute_outfit_plan`, `find_latest_composite` 等 |
| `os.path.join(PROJECT_DIR, 'wardrobe', 'tags')` | `os.path.join(self.user_dir, 'wardrobe', 'tags')` | `_get_next_id`, `_id_exists_on_disk` 等 |

**注意：** 不涉及用户数据的路径保持不变（如 `config/seedream.local.json`、`tools/wechat_control.log`、`prototype/mobile-v2.html` 模板等）

由于 `wechat_control.py` 体量巨大（4190 行），这一步采用**搜索替换策略**：
- 搜索 `PROJECT_DIR, 'wardrobe'` → 替换为 `self.user_dir, 'wardrobe'`
- 搜索 `PROJECT_DIR, 'outfits'` → 替换为 `self.user_dir, 'outfits'`
- 确认不替换 `PROJECT_DIR, 'config'` / `PROJECT_DIR, 'tools'` / `PROJECT_DIR, 'prototype'`

- [ ] **Step 5: 修改 _load_chat_html 支持按用户加载原型**

在 `_load_chat_html` 函数（搜索其定义位置）中：

```python
def _load_chat_html(user_id=None):
    """加载聊天面板 HTML。多用户模式加载用户缓存原型，单用户加载默认原型。"""
    if user_id and user_id != 'default':
        cache_path = os.path.join(PROJECT_DIR, 'users', user_id, 'cache', 'prototype.html')
        if os.path.exists(cache_path):
            with open(cache_path, 'r', encoding='utf-8') as f:
                return f.read()
    # Fallback：默认原型
    proto_path = os.path.join(PROJECT_DIR, 'prototype', 'mobile-v2.html')
    with open(proto_path, 'r', encoding='utf-8') as f:
        return f.read()
```

在 `do_GET` 中 `self._html_resp(200, _load_chat_html())` 改为 `self._html_resp(200, _load_chat_html(self.user_id))`

- [ ] **Step 6: 启动时不强制要求 SENDKEY**

修改第 67-70 行，使 SENDKEY 缺失不退出：

```python
SENDKEY = config.get('wechat_sendkey', '')
if not SENDKEY:
    print("⚠️ 未配置 wechat_sendkey，微信推送已禁用")
    log("未配置 wechat_sendkey，微信推送已禁用", "WARN")
    # 不再 sys.exit(1)
```

- [ ] **Step 7: 验证向后兼容**

```bash
# 先确保 main 分支能正常启动
cd "/Users/rabbit/Claude code/Fashion"
python3 -c "
from tools.common import resolve_user_dir
# 默认模式应该返回项目根
assert resolve_user_dir() == resolve_user_dir('default')
print('✅ 默认路径解析正确')
print('默认:', resolve_user_dir())
print('Alice:', resolve_user_dir('alice'))
"
```

- [ ] **Step 8: Commit**

```bash
git add tools/wechat_control.py
git commit -m "feat: wechat_control.py 加 ?user= 路由 + 多用户数据目录隔离"
```

---

## Task A4: build_prototype.py 加 --user 参数

**Files:**
- Modify: `tools/build_prototype.py`

**Interfaces:**
- Consumes: `common.resolve_outfits_dir(user_id)`, `common.resolve_wardrobe_dir(user_id)`
- CLI: `python3 tools/build_prototype.py` (默认单用户) | `python3 tools/build_prototype.py --user alice`

- [ ] **Step 1: 在 build_prototype.py 顶部添加导入和参数解析**

在文件开头 import 块后添加：

```python
from tools.common import resolve_outfits_dir, resolve_wardrobe_dir, resolve_user_dir

# 解析 --user 参数
USER_ID = 'default'
args = sys.argv[1:]
for i, arg in enumerate(args):
    if arg == '--user' and i + 1 < len(args):
        USER_ID = args[i + 1]
    elif arg.startswith('--user='):
        USER_ID = arg.split('=', 1)[1]

USER_DIR = resolve_user_dir(None if USER_ID == 'default' else USER_ID)
OUTFITS_DIR = resolve_outfits_dir(None if USER_ID == 'default' else USER_ID)
WARDROBE_DIR = resolve_wardrobe_dir(None if USER_ID == 'default' else USER_ID)
```

- [ ] **Step 2: 修改输出路径**

`build_prototype.py` 输出 HTML。多用户模式下输出到 `users/<id>/cache/prototype.html`：

找到写文件位置（约文件末尾），改为：

```python
if USER_ID and USER_ID != 'default':
    output_path = os.path.join(PROJ, 'users', USER_ID, 'cache', 'prototype.html')
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
else:
    output_path = os.path.join(PROJ, 'prototype', 'mobile-v2.html')

with open(output_path, 'w', encoding='utf-8') as f:
    f.write(html)
```

- [ ] **Step 3: 将 HTML 中的硬编码路径改为相对路径**

所有图片引用从绝对 URL 改为相对路径（因为用户通过同一个服务器访问，服务器负责路由）：

```python
# 图片 URL 构建时使用相对路径（/wardrobe/... 而非 /users/alice/wardrobe/...）
# 服务器在响应 /wardrobe/... 请求时会根据 ?user= 参数路由到正确目录
```

- [ ] **Step 4: 验证**

```bash
cd "/Users/rabbit/Claude code/Fashion"
# 默认模式不应报错
python3 tools/build_prototype.py 2>&1 | head -5
echo "---"
# 多用户模式（尚无用户数据，应优雅处理空目录）
python3 tools/build_prototype.py --user alice 2>&1 | head -5
```

- [ ] **Step 5: Commit**

```bash
git add tools/build_prototype.py
git commit -m "feat: build_prototype.py 加 --user 参数，支持按用户输出原型"
```

---

## Task A5: 其他核心工具加 --user 参数

**Files:**
- Modify: `tools/generate.py`（路径引用改为支持 user_dir）
- Modify: `tools/composite_v2.py`（同上）
- Modify: `tools/style_matcher.py`（同上）

每个文件的改动模式相同：顶部解析 `--user` → 调用 `resolve_*_dir()` 替代硬编码 `PROJECT_DIR`。

- [ ] **Step 1: generate.py**

在 `tools/generate.py` 中找到路径引用处（约 `wardrobe/enhanced/` 和 `outfits/`），参数化：

```python
# 文件顶部添加
import sys
USER_ID = None
for i, arg in enumerate(sys.argv[1:]):
    if arg == '--user' and i + 1 < len(sys.argv):
        USER_ID = sys.argv[i + 2] if i + 2 < len(sys.argv) else sys.argv[i + 1]
    elif arg.startswith('--user='):
        USER_ID = arg.split('=', 1)[1]

from tools.common import resolve_user_dir, resolve_wardrobe_dir, resolve_outfits_dir
USER_DIR = resolve_user_dir(USER_ID)
```

- [ ] **Step 2: composite_v2.py**（同上模式）

- [ ] **Step 3: style_matcher.py**（同上模式）

- [ ] **Step 4: 验证批量改动**

```bash
cd "/Users/rabbit/Claude code/Fashion"
# 默认模式检查语法
python3 -c "import tools.generate" 2>&1 | tail -3
python3 -c "import tools.composite_v2" 2>&1 | tail -3
python3 -c "import tools.style_matcher" 2>&1 | tail -3
echo "✅ All imports ok"
```

- [ ] **Step 5: Commit**

```bash
git add tools/generate.py tools/composite_v2.py tools/style_matcher.py
git commit -m "feat: generate/composite_v2/style_matcher 加 --user 参数"
```

---

## Task A6: Phase A 集成验证

- [ ] **Step 1: 手动创建测试用户并验证全链路**

```bash
cd "/Users/rabbit/Claude code/Fashion"

# 1. 创建测试用户
python3 -c "
from tools.user_manager import create_user
create_user('test_alice', {'body': {'height_cm': 165, 'weight_kg': 55, 'shape': '梨形'}})
print('✅ 测试用户已创建')
"

# 2. 验证目录结构
find users/test_alice -type d

# 3. 验证 wechat_control.py 能启动（10秒后 Ctrl+C）
timeout 10 python3 tools/wechat_control.py 2>&1 | tail -5 || true
echo "---"
echo "✅ Phase A 集成验证完成"
```

- [ ] **Step 2: 清理测试数据**

```bash
rm -rf users/test_alice
python3 -c "
from tools.user_manager import load_registry, save_registry
r = load_registry()
r.pop('test_alice', None)
save_registry(r)
print('✅ 测试数据已清理')
"
```

- [ ] **Step 3: Commit Phase A 完成标记**

```bash
git commit --allow-empty -m "✅ Phase A 完成：多用户基础架构就绪"
```

---

# Phase B：女性适配

## Task B1: 建立 styles_women/ 12 个女性风格

**Files:**
- Create: `styles_women/README.md`
- Create: `styles_women/WF-01_french_effortless/` 到 `WF-12_dark_academia/`（12个目录 + 百科 + 指纹）

**策略:** 用 `tools/style_research.py` 批量研究 + `tools/fashion_image_search.py` 搜集参考图。

- [ ] **Step 1: 创建风格库骨架**

```bash
cd "/Users/rabbit/Claude code/Fashion"
mkdir -p styles_women

# 12 个风格目录
STYLES=(
  "WF-01_french_effortless"
  "WF-02_korean_girlie"
  "WF-03_mori_kei"
  "WF-04_new_chinese"
  "WF-05_american_casual"
  "WF-06_minimalist"
  "WF-07_preppy"
  "WF-08_athleisure"
  "WF-09_boho"
  "WF-10_y2k_revival"
  "WF-11_city_girl"
  "WF-12_dark_academia"
)
for s in "${STYLES[@]}"; do
  mkdir -p "styles_women/$s/images"
  echo "# $s" > "styles_women/$s/encyclopedia.md"
  echo '{}' > "styles_women/$s/fingerprint.json"
done
echo "✅ 12个风格目录已创建"
```

- [ ] **Step 2: 为每个风格搜集参考图**

```bash
cd "/Users/rabbit/Claude code/Fashion"

# 批量搜索参考图（每个风格搜 5 张）
declare -A QUERIES
QUERIES[WF-01_french_effortless]="french effortless style women street 2025"
QUERIES[WF-02_korean_girlie]="korean girlie fashion women casual 2025"
QUERIES[WF-03_mori_kei]="mori kei japanese forest girl style"
QUERIES[WF-04_new_chinese]="new chinese style modern women fashion"
QUERIES[WF-05_american_casual]="american casual women street style 2025"
QUERIES[WF-06_minimalist]="minimalist women capsule wardrobe 2025"
QUERIES[WF-07_preppy]="preppy style women academic fashion"
QUERIES[WF-08_athleisure]="athleisure women sporty chic outfit 2025"
QUERIES[WF-09_boho]="boho chic women bohemian style"
QUERIES[WF-10_y2k_revival]="y2k fashion women 2025 revival outfit"
QUERIES[WF-11_city_girl]="city commute workwear women outfit"
QUERIES[WF-12_dark_academia]="dark academia women aesthetic outfit"

for dir in "${!QUERIES[@]}"; do
  echo "🔍 搜索: $dir"
  python3 tools/fashion_image_search.py \
    --query "${QUERIES[$dir]}" \
    --save "styles_women/$dir/images" \
    --limit 5 2>&1 | tail -1
done
```

- [ ] **Step 3: 编写每个风格的百科文件**

为每个风格写 `encyclopedia.md`，最少包含：

```markdown
# {风格名称}

## 一句话定义
{一句话描述这个风格的核心特征}

## 起源与文化背景
{风格的历史渊源、文化土壤}

## 关键品牌
- {品牌1}
- {品牌2}

## 核心单品
- {品类1}：{特征}
- {品类2}：{特征}

## 配色逻辑
{典型配色方案}

## 穿搭规则
1. {规则1}
2. {规则2}

## 适合身形
{适合/修饰的身形特征}

## 代表名人/ICON
- {名人1}
```

用 AI 辅助生成每篇百科的内容（通过 WebSearch + 豆包 API）。

- [ ] **Step 4: 编写五层评分指纹（fingerprint.json）**

每个风格一个评分指纹文件，结构镜像现有 `styles/*.json`，但维度适配女性：

```json
{
  "style_id": "WF-01",
  "name_zh": "法式慵懒",
  "name_en": "French Effortless",
  "category": "休闲优雅",
  "description": "看似不经意的精致感，核心是'少即是多'",
  "color_profile": {
    "primary": ["白", "黑", "藏青", "卡其"],
    "accent": ["红", "条纹"],
    "avoid": ["荧光色", "大面积印花"]
  },
  "silhouette_profile": {
    "top": ["合身", "略宽松"],
    "bottom": ["直筒", "微喇"],
    "dress": ["A字", "裹身"]
  },
  "fabric_preference": ["棉", "亚麻", "羊绒", "真丝"],
  "formality_range": [2, 4],
  "body_modifiers": {
    "pear": 0.9,
    "hourglass": 0.95,
    "apple": 0.7,
    "rectangle": 0.85,
    "inverted_triangle": 0.8
  },
  "occasion_fit": {
    "日常": 0.95,
    "通勤": 0.85,
    "约会": 0.9,
    "聚会": 0.7,
    "运动": 0.1,
    "度假": 0.8
  }
}
```

- [ ] **Step 5: Commit**

```bash
git add styles_women/
git commit -m "feat: styles_women/ — 12个女性核心风格（百科+指纹+参考图）"
```

---

## Task B2: style_scout_women.py — 个人风格发现

**Files:**
- Create: `tools/style_scout_women.py`

**Interfaces:**
- CLI: `python3 tools/style_scout_women.py --user alice`
- Produces: 下载图片到 `users/<id>/discovered_styles/`，返回风格名称列表

- [ ] **Step 1: 编写 style_scout_women.py**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""女性风格发现 — 根据用户身形+衣橱+偏好搜索相关风格图片（轻量版：仅图片）"""
import os, sys, json, subprocess, argparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.dirname(BASE_DIR)

parser = argparse.ArgumentParser()
parser.add_argument('--user', required=True, help='用户 ID')
args = parser.parse_args()

user_dir = os.path.join(PROJ_DIR, 'users', args.user)
profile_path = os.path.join(user_dir, 'profile.json')
tags_dir = os.path.join(user_dir, 'wardrobe', 'tags')
output_dir = os.path.join(user_dir, 'discovered_styles')

if not os.path.exists(profile_path):
    print(f"❌ 用户 {args.user} 不存在")
    sys.exit(1)

with open(profile_path) as f:
    profile = json.load(f)

# ── 构建搜索 query ──
body = profile.get('body', {})
shape = body.get('shape', '')
style_prefs = profile.get('style_prefs', [])

# 分析衣橱主导品类和颜色
dominant_cats = {}
color_counts = {}
for fn in os.listdir(tags_dir):
    if fn.endswith('.json') and fn != 'SCORE_CACHE.json':
        with open(os.path.join(tags_dir, fn)) as f:
            tag = json.load(f)
        cat = tag.get('category', '')
        dominant_cats[cat] = dominant_cats.get(cat, 0) + 1
        color = (tag.get('color') or {}).get('hue_name', '')
        if color:
            color_counts[color] = color_counts.get(color, 0) + 1

top_cats = sorted(dominant_cats, key=dominant_cats.get, reverse=True)[:3]
top_color = max(color_counts, key=color_counts.get) if color_counts else ''

# 拼接 query
shape_terms = {
    'pear': 'pear shape', 'apple': 'apple shape',
    'hourglass': 'hourglass shape', 'rectangle': 'rectangle body',
    'inverted_triangle': 'inverted triangle body',
}
shape_en = shape_terms.get(shape, 'women')

style_names = {
    'WF-01': 'french effortless', 'WF-02': 'korean girlie',
    'WF-03': 'mori kei', 'WF-04': 'new chinese',
    'WF-05': 'american casual', 'WF-06': 'minimalist',
    'WF-07': 'preppy', 'WF-08': 'athleisure',
    'WF-09': 'boho', 'WF-10': 'y2k',
    'WF-11': 'city girl', 'WF-12': 'dark academia',
}
top_style = style_names.get(style_prefs[0], '') if style_prefs else ''

query_parts = [shape_en, top_color, ' '.join(top_cats[:2]), top_style, 'women street style 2025']
query = ' '.join(p for p in query_parts if p)

print(f"🔍 搜索 query: {query}")

# ── 调用 fashion_image_search 下载图片 ──
os.makedirs(output_dir, exist_ok=True)
cmd = [
    'python3', os.path.join(BASE_DIR, 'fashion_image_search.py'),
    '--query', query, '--save', output_dir, '--limit', '10'
]
result = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJ_DIR, timeout=120)
print(result.stdout[-300:] if len(result.stdout) > 300 else result.stdout)

# ── 记录来源 ──
meta = {
    'query': query,
    'user_shape': shape,
    'user_top_cats': top_cats,
    'user_top_color': top_color,
    'generated_at': __import__('time').strftime('%Y-%m-%dT%H:%M:%S'),
}
with open(os.path.join(output_dir, '_meta.json'), 'w') as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)

print(f"✅ 个人风格发现完成 → {output_dir}")
```

- [ ] **Step 2: 验证**

```bash
# 先创建测试用户
python3 -c "
from tools.user_manager import create_user
create_user('test_scout', {
    'body': {'shape': 'pear'},
    'style_prefs': ['WF-01', 'WF-02']
})
# 模拟一些标签数据
import os, json
tags_dir = 'users/test_scout/wardrobe/tags'
os.makedirs(tags_dir, exist_ok=True)
for i, (cat, color) in enumerate([('长裤','黑'), ('长裤','白'), ('长裤','蓝'), ('短袖上衣','白')]):
    with open(f'{tags_dir}/PT-{i+1:03d}.json', 'w') as f:
        json.dump({'category': cat, 'color': {'hue_name': color}}, f)
print('✅ 测试数据就绪')
"

# 运行风格发现
python3 tools/style_scout_women.py --user test_scout

# 清理
rm -rf users/test_scout
```

- [ ] **Step 3: Commit**

```bash
git add tools/style_scout_women.py
git commit -m "feat: style_scout_women.py — 按用户信号发现女性风格图片"
```

---

## Task B3: Onboarding HTML 页面（4步向导）

**Files:**
- Modify: `tools/wechat_control.py`（添加 `_load_onboarding_html` 函数和 `/api/onboarding/*` 端点）

- [ ] **Step 1: 编写 onboarding HTML 模板函数**

在 `wechat_control.py` 中添加 `_load_onboarding_html(user_id, step)` 函数。这是一个完整的四步向导 HTML 页面，内嵌 CSS/JS，无需外部文件。

在 `wechat_control.py` 中添加约 800 行 onboarding 代码。结构如下：

**ONBOARDING_CSS（模块级常量，~200行）核心样式：**

```python
ONBOARDING_CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,sans-serif;background:#f5f0eb;min-height:100vh}
.progress-bar{width:100%;height:4px;background:#e0d8cc;position:fixed;top:0;z-index:10}
.progress-fill{height:100%;background:linear-gradient(90deg,#8b7355,#5c4d3c);transition:width .3s}
.step{padding:24px 20px;padding-top:40px;max-width:420px;margin:0 auto}
.step h2{font-size:22px;color:#3a3028;margin-bottom:8px}
.step p.sub{font-size:14px;color:#999;margin-bottom:24px}
.form-group{margin-bottom:16px}
.form-group label{display:block;font-size:14px;color:#5c4d3c;margin-bottom:6px;font-weight:500}
.form-group input,.form-group select{width:100%;padding:12px;border:1px solid #d0c8bc;border-radius:10px;font-size:16px;background:#fff;color:#3a3028}
.form-group input:focus,.form-group select:focus{outline:none;border-color:#8b7355}
.shape-options{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.shape-card{border:2px solid #e0d8cc;border-radius:12px;padding:16px;text-align:center;cursor:pointer;transition:all .2s;background:#fff}
.shape-card.selected{border-color:#8b7355;background:#f5f0eb}
.shape-card .emoji{font-size:28px;display:block;margin-bottom:4px}
.shape-card .label{font-size:13px;color:#5c4d3c}
.concern-tags{display:flex;flex-wrap:wrap;gap:8px}
.concern-tag{padding:8px 16px;border:1px solid #d0c8bc;border-radius:20px;font-size:14px;cursor:pointer;background:#fff;color:#5c4d3c}
.concern-tag.selected{background:#8b7355;color:#fff;border-color:#8b7355}
.style-cards{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.style-card{border:2px solid #e0d8cc;border-radius:12px;overflow:hidden;cursor:pointer;background:#fff}
.style-card.selected{border-color:#8b7355}
.style-card img{width:100%;height:100px;object-fit:cover}
.style-card .info{padding:8px}
.style-card .name{font-size:14px;font-weight:600;color:#3a3028}
.style-card .desc{font-size:12px;color:#999;margin-top:2px}
.upload-zone{border:2px dashed #d0c8bc;border-radius:16px;padding:40px 20px;text-align:center;cursor:pointer;background:#fff;margin-bottom:16px}
.upload-zone .icon{font-size:40px;display:block;margin-bottom:8px}
.upload-zone .text{font-size:14px;color:#999}
.upload-preview{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:16px}
.upload-preview img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:8px}
.upload-progress{background:#e0d8cc;border-radius:8px;height:8px;margin-top:12px}
.upload-progress .fill{height:100%;background:#8b7355;border-radius:8px}
.btn{display:block;width:100%;padding:14px;border:none;border-radius:12px;font-size:16px;font-weight:600;cursor:pointer;margin-top:20px}
.btn-primary{background:linear-gradient(135deg,#3a3028,#5c4d3c);color:#fff}
.btn-primary:disabled{opacity:.5}
.btn-secondary{background:#fff;color:#5c4d3c;border:1px solid #d0c8bc}
.waiting{text-align:center;padding:40px 20px}
.waiting .spinner{width:40px;height:40px;border:3px solid #e0d8cc;border-top-color:#8b7355;border-radius:50%;animation:spin 1s linear infinite;margin:20px auto}
@keyframes spin{to{transform:rotate(360deg)}}
.toast{position:fixed;bottom:40px;left:50%;transform:translateX(-50%);background:#3a3028;color:#fff;padding:12px 24px;border-radius:20px;font-size:14px;opacity:0;transition:opacity .3s}
.toast.show{opacity:1}
"""
```

**ONBOARDING_JS（模块级常量，~250行）核心逻辑：**

```python
ONBOARDING_JS = """
var userId = '%s';
var currentStep = %d;
var profile = {body:{}, style_prefs:[], concerns:[]};
var uploadedCount = 0;

function showStep(step) {
  currentStep = step;
  document.getElementById('progressFill').style.width = (step*25) + '%%';
  var content = document.getElementById('stepContent');
  if (step === 1) content.innerHTML = step1HTML();
  else if (step === 2) content.innerHTML = step2HTML();
  else if (step === 3) content.innerHTML = step3HTML();
  else if (step === 4) content.innerHTML = step4HTML();
}

function step1HTML() {
  return '<div class="step"><h2>认识你</h2><p class="sub">告诉我你的身形，让我更懂你</p>'
    + '<div class="form-group"><label>身高 (cm)</label><input type="number" id="height" placeholder="例：165" value="'+(profile.body.height_cm||'')+'"></div>'
    + '<div class="form-group"><label>体重 (kg)</label><input type="number" id="weight" placeholder="例：55"></div>'
    + '<div class="form-group"><label>身形类型</label><div class="shape-options" id="shapeOptions"></div></div>'
    + '<div class="form-group"><label>肤色</label><select id="skinTone"><option value="">请选择</option><option value="cool_white">冷白皮</option><option value="warm_white">暖白皮</option><option value="natural">自然肤色</option><option value="wheat">小麦色</option></select></div>'
    + '<div class="form-group"><label>穿衣困扰（可多选）</label><div class="concern-tags" id="concernTags"></div></div>'
    + '<button class="btn btn-primary" onclick="saveStep1()">下一步 →</button></div>';
}

// Step 2: 风格偏好（从 /api/styles/women 加载风格卡片）
function step2HTML() {
  var cards = [];
  // 通过 fetch 同步获取风格列表（简化处理：内嵌 12 个风格名）
  var styleNames = %s;
  // styleNames 是 JSON 数组 [{id:'WF-01',name_zh:'法式慵懒',desc:'...',img:'...'}]
  return '<div class="step"><h2>你的风格</h2><p class="sub">选择 3-5 个你喜欢的风格</p>'
    + '<div class="style-cards" id="styleCards"></div>'
    + '<p style="text-align:center;color:#999;font-size:13px;margin-top:8px">已选 <span id="selectCount">0</span>/5</p>'
    + '<button class="btn btn-primary" id="step2Next" disabled onclick="saveStep2()">下一步 →</button></div>';
}

// Step 3: 衣橱上传（复用现有 compressImageV2 + FormData）
function step3HTML() {
  return '<div class="step"><h2>你的衣橱</h2><p class="sub">拍照或从相册上传至少 10 件衣服</p>'
    + '<div class="upload-zone" id="uploadZone"><span class="icon">📸</span><span class="text">点击拍照或选择照片</span><input type="file" id="fileInput" accept="image/*" capture="environment" multiple style="display:none"></div>'
    + '<div class="upload-preview" id="uploadPreview"></div>'
    + '<div class="upload-progress"><div class="fill" id="uploadFill" style="width:0%%"></div></div>'
    + '<p style="text-align:center;color:#999;font-size:13px;margin-top:8px">已上传 <span id="uploadCount">0</span> 件（至少10件）</p>'
    + '<button class="btn btn-primary" id="step3Next" disabled onclick="saveStep3()">开始 AI 推荐 →</button></div>';
}

// Step 4: 等待入库
function step4HTML() {
  return '<div class="waiting"><div class="spinner"></div><h2>AI 正在分析你的衣橱...</h2><p class="sub">这可能需要 1-2 分钟</p><div id="tagStatus"></div></div>';
}

// API 调用函数
async function saveStep1() {
  var h = parseInt(document.getElementById('height').value) || 0;
  if (!h) { toast('请填写身高'); return; }
  profile.body.height_cm = h;
  profile.body.weight_kg = parseInt(document.getElementById('weight').value) || 0;
  profile.body.skin_tone = document.getElementById('skinTone').value;
  var r = await fetch('/api/onboarding/step1?user='+userId, {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify(profile.body)
  });
  if (r.ok) showStep(2);
}

async function saveStep2() {
  var r = await fetch('/api/onboarding/step2?user='+userId, {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({style_prefs: profile.style_prefs})
  });
  if (r.ok) showStep(3);
}

async function saveStep3() {
  showStep(4);
  // 触发后台：跑风格发现 + 触发首次推荐
  var r = await fetch('/api/onboarding/complete?user='+userId, {method:'POST'});
  var d = await r.json();
  if (d.redirect) { window.location.href = d.redirect; }
}

function toast(msg) {
  var t = document.getElementById('toast') || document.createElement('div');
  t.id = 'toast'; t.className = 'toast'; t.textContent = msg;
  if (!t.parentNode) document.body.appendChild(t);
  t.classList.add('show');
  setTimeout(function(){ t.classList.remove('show'); }, 2000);
}

// 上传逻辑（复用 build_prototype 的 compressImageV2）
function handleFiles(files) {
  for (var i=0; i<files.length; i++) {
    (function(file) {
      compressImageV2(file, function(blob) {
        var fd = new FormData();
        fd.append('image', blob, 'wardrobe.jpg');
        fd.append('user_id', userId);
        fetch('/api/onboarding/wardrobe/add?user='+userId, {method:'POST', body:fd})
          .then(function(r){ return r.json(); })
          .then(function(d) {
            uploadedCount++;
            document.getElementById('uploadCount').textContent = uploadedCount;
            document.getElementById('uploadFill').style.width = Math.min(uploadedCount*10, 100) + '%%';
            if (uploadedCount >= 10) document.getElementById('step3Next').disabled = false;
            // 预览
            var preview = document.getElementById('uploadPreview');
            var img = document.createElement('img');
            img.src = URL.createObjectURL(blob);
            preview.appendChild(img);
          });
      });
    })(files[i]);
  }
}

document.getElementById('uploadZone').onclick = function(){ document.getElementById('fileInput').click(); };
document.getElementById('fileInput').onchange = function(e){ handleFiles(e.target.files); };

// 初始化
showStep(currentStep);
""" % (user_id, step, json.dumps(style_cards_json))
```

**`_load_onboarding_html` 函数：**

```python
def _load_onboarding_html(user_id, step=1):
    """构建4步 onboarding 向导 HTML"""
    # 从 styles_women/ 加载风格卡片数据
    style_cards = []
    women_dir = os.path.join(PROJECT_DIR, 'styles_women')
    if os.path.isdir(women_dir):
        for d in sorted(os.listdir(women_dir)):
            fp = os.path.join(women_dir, d, 'fingerprint.json')
            if os.path.exists(fp):
                with open(fp) as f:
                    sd = json.load(f)
                # 找参考图
                img_dir = os.path.join(women_dir, d, 'images')
                img = ''
                if os.path.isdir(img_dir):
                    imgs = [f for f in os.listdir(img_dir) if f.endswith(('.jpg','.png','.jpeg'))]
                    if imgs:
                        img = f'/styles_women/{d}/images/{imgs[0]}'
                style_cards.append({
                    'id': sd.get('style_id', d),
                    'name_zh': sd.get('name_zh', d),
                    'desc': (sd.get('description', '') or '')[:50],
                    'img': img,
                })
    
    style_cards_json = json.dumps(style_cards, ensure_ascii=False)
    
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>Fashion Advisor · 欢迎</title>
<style>
{ONBOARDING_CSS}
</style>
</head>
<body>
<div id="app">
  <div class="progress-bar">
    <div class="progress-fill" id="progressFill" style="width:{step*25}%"></div>
  </div>
  <div id="stepContent"></div>
</div>
<script>
{ONBOARDING_JS}
</script>
</body>
</html>"""
```

- [ ] **Step 2: 添加 /api/onboarding/* 端点**

在 `do_POST` 中处理：

| 端点 | 功能 |
|------|------|
| `POST /api/onboarding/step1` | 保存身形数据 → profile.json |
| `POST /api/onboarding/step2` | 保存风格偏好 → profile.json |
| `POST /api/onboarding/wardrobe/add` | 接收压缩后的图片 → 快速入库队列 |

```python
# do_POST 中添加
if parsed.path == '/api/onboarding/step1':
    body = self._read_body()
    data = json.loads(body)
    profile_path = os.path.join(self.user_dir, 'profile.json')
    with open(profile_path, 'r') as f:
        p = json.load(f)
    p['body'] = data
    p['onboarding_step'] = 2
    with open(profile_path, 'w') as f:
        json.dump(p, f, ensure_ascii=False, indent=2)
    self._json_resp(200, {'ok': True, 'next_step': 2})
    return
```

- [ ] **Step 3: 验证 onboarding 流程**

在浏览器中访问 `https://macbook-pro-1.taildbfbc0.ts.net/?user=newuser` 验证流程。

- [ ] **Step 4: Commit**

```bash
git add tools/wechat_control.py
git commit -m "feat: onboarding HTML 4步向导 + /api/onboarding/* 端点"
```

---

## Task B4: quick_tag.py — 快速入库管线

**Files:**
- Create: `tools/quick_tag.py`

**Interfaces:**
- CLI: `python3 tools/quick_tag.py <image_path> --user <id>`
- Produces: 生成 `users/<id>/wardrobe/tags/<ID>.json` 基础版

- [ ] **Step 1: 编写 quick_tag.py**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""快速入库 — YOLO品类检测 + 颜色直方图 → 基础标签 JSON（30秒内完成）"""
import os, sys, json, time, argparse
from PIL import Image, ImageOps

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.dirname(BASE_DIR)

# 确保项目根在 path
if PROJ_DIR not in sys.path:
    sys.path.insert(0, PROJ_DIR)

parser = argparse.ArgumentParser()
parser.add_argument('image', help='图片路径')
parser.add_argument('--user', required=True, help='用户 ID')
parser.add_argument('--override-id', default=None, help='指定 ID（跳过自动分配）')
args = parser.parse_args()

user_dir = os.path.join(PROJ_DIR, 'users', args.user)
tags_dir = os.path.join(user_dir, 'wardrobe', 'tags')
os.makedirs(tags_dir, exist_ok=True)

# ── 1. YOLO 品类检测 ──
CATEGORY_CODE_MAP = {
    't-shirt': 'TS', 'shirt': 'SHIRT', 'tank_top': 'TANK',
    'long_sleeve': 'LS', 'jacket': 'JK', 'coat': 'JK',
    'pants': 'PT', 'shorts': 'SH', 'skirt': 'SH',
    'shoes': 'SHOE', 'bag': 'BAG', 'hat': 'HAT',
    'sunglasses': 'SUN', 'socks': 'SOCK',
}

def detect_category(image_path):
    """用 YOLO 检测品类。返回 (category_code, category_name, confidence)"""
    try:
        from ultralytics import YOLO
        model_path = os.path.join(PROJ_DIR, 'yolov8n.pt')
        model = YOLO(model_path)
        results = model(image_path, verbose=False)
        
        # 查找服装相关检测
        best = None
        for r in results:
            for box in r.boxes:
                cls_id = int(box.cls[0])
                cls_name = model.names[cls_id]
                conf = float(box.conf[0])
                if cls_name in CATEGORY_CODE_MAP and (best is None or conf > best[1]):
                    best = (cls_name, conf)
        
        if best:
            code = CATEGORY_CODE_MAP.get(best[0], 'TS')
            from tools.common import cat_code_to_name
            return code, cat_code_to_name(code), best[1]
    except Exception as e:
        print(f"⚠️ YOLO 检测失败: {e}")
    
    return 'TS', '短袖上衣', 0.0


# ── 2. 颜色直方图分析 ──
def analyze_color(image_path):
    """分析图片主色。返回 {hue_family, hue_name, saturation, lightness, is_neutral}"""
    img = Image.open(image_path)
    img = ImageOps.exif_transpose(img)
    img = img.convert('RGB')
    img = img.resize((100, 100))
    
    pixels = list(img.getdata())
    
    # 简单均值法
    r = sum(p[0] for p in pixels) / len(pixels)
    g = sum(p[1] for p in pixels) / len(pixels)
    b = sum(p[2] for p in pixels) / len(pixels)
    
    # RGB → 粗略颜色名
    color_names = [
        ((200, 50, 50), (255, 100, 100), '红', '暖色'),
        ((200, 100, 50), (255, 180, 100), '橙', '暖色'),
        ((180, 160, 50), (255, 230, 150), '黄', '暖色'),
        ((50, 150, 50), (100, 220, 100), '绿', '冷色'),
        ((50, 100, 200), (100, 180, 255), '蓝', '冷色'),
        ((100, 50, 150), (180, 100, 220), '紫', '冷色'),
        ((100, 50, 50), (180, 120, 100), '棕', '暖色'),
        ((200, 150, 150), (255, 220, 220), '粉', '暖色'),
        ((200, 200, 200), (240, 240, 240), '白', '中性色'),
        ((50, 50, 50), (120, 120, 120), '灰', '中性色'),
        ((0, 0, 0), (50, 50, 50), '黑', '中性色'),
    ]
    
    best_name = '灰'
    best_family = '中性色'
    min_dist = float('inf')
    for (lo_r, lo_g, lo_b), (hi_r, hi_g, hi_b), name, family in color_names:
        center_r = (lo_r + hi_r) / 2
        center_g = (lo_g + hi_g) / 2
        center_b = (lo_b + hi_b) / 2
        dist = ((r - center_r)**2 + (g - center_g)**2 + (b - center_b)**2) ** 0.5
        if dist < min_dist:
            min_dist = dist
            best_name = name
            best_family = family
    
    # 饱和度和明度
    max_rgb = max(r, g, b)
    min_rgb = min(r, g, b)
    saturation = '低饱和' if (max_rgb - min_rgb) < 50 else ('高饱和' if (max_rgb - min_rgb) > 120 else '中饱和')
    lightness = '高明度' if (r + g + b) / 3 > 180 else ('低明度' if (r + g + b) / 3 < 80 else '中明度')
    
    return {
        'hue_family': best_family,
        'hue_name': best_name,
        'saturation': saturation,
        'lightness': lightness,
        'is_neutral': best_family == '中性色',
    }


# ── 3. ID 分配 ──
def get_next_id(category_code, tags_dir):
    existing = []
    for fn in os.listdir(tags_dir):
        if fn.startswith(f'{category_code}-') and fn.endswith('.json'):
            import re
            m = re.search(rf'{category_code}-(\d+)', fn)
            if m:
                existing.append(int(m.group(1)))
    next_num = max(existing) + 1 if existing else 1
    return f'{category_code}-{next_num:03d}'


# ── 主流程 ──
print(f"🔍 分析: {os.path.basename(args.image)}")
cat_code, cat_name, cat_conf = detect_category(args.image)
print(f"   品类: {cat_name} ({cat_code}) 置信度={cat_conf:.0%}")

color = analyze_color(args.image)
print(f"   颜色: {color['hue_name']} ({color['hue_family']}, {color['saturation']})")

# 分配 ID
if args.override_id:
    cid = args.override_id
else:
    cid = get_next_id(cat_code, tags_dir)

# 写标签 JSON
tag_data = {
    'clothing_id': cid,
    'category': cat_name,
    'category_code': cat_code,
    'color': color,
    'fabric': {'primary': '未知', 'texture': '未知', 'weight': '适中', 'seasonality': ['春', '秋']},
    'silhouette': {'fit': '合身', 'shoulder_effect': '无特殊效果', 'torso_effect': '无特殊效果', 'length_ratio': '标准'},
    'pattern': {'type': '纯色', 'density': '无', 'logo_visible': False},
    'brand': {'name': '未知', 'collection': '', 'confidence': '未知'},
    'style_modifiers': [],
    'occasions': ['日常休闲'],
    'formality': 3,
    'meta': {
        'is_key_piece': False,
        'is_statement_piece': False,
        'wear_count': 0,
        'last_worn': None,
        'claude_fit_comment': '',
    },
    'reviewed': False,
    'reviewed_by_human': None,
    'created': time.strftime('%Y-%m-%dT%H:%M:%S'),
}

tag_path = os.path.join(tags_dir, f'{cid}.json')
with open(tag_path, 'w', encoding='utf-8') as f:
    json.dump(tag_data, f, ensure_ascii=False, indent=2)

print(f"✅ 标签已生成: {tag_path}")
print(json.dumps({'id': cid, 'category': cat_name, 'color': color['hue_name']}, ensure_ascii=False))
```

- [ ] **Step 2: 测试基本功能**

```bash
# 用一张现有图片测试
python3 tools/quick_tag.py "wardrobe/短袖上衣/Image_20260610_0817_22_673.jpg" --user _test 2>&1
```

- [ ] **Step 3: Commit**

```bash
git add tools/quick_tag.py
git commit -m "feat: quick_tag.py — YOLO品类+颜色直方图快速入库"
```

---

## Task B5: 推荐引擎适配女性身形

**Files:**
- Modify: `tools/unified_pipeline.py`（AI prompt 中的身形描述）

这是最轻量的改动——只改 prompt 模板，让 AI 在生成推荐时考虑女性身形维度。

- [ ] **Step 1: 在 build_enhanced_prompt 中根据用户性别选择身形描述**

在 `tools/unified_pipeline.py` 中找到身形描述生成逻辑（约在 `build_enhanced_prompt` 函数中），添加性别判断：

```python
def _get_body_description(user_id=None):
    """根据用户 profile 生成身形描述文本"""
    if not user_id or user_id == 'default':
        # 默认男性身形（现有逻辑）
        return "一位亚洲年轻男性，身高178cm偏瘦，肤色偏白"
    
    profile_path = os.path.join(PROJ_DIR, 'users', user_id, 'profile.json')
    if not os.path.exists(profile_path):
        return "一位亚洲年轻女性，身高165cm，中等身材"
    
    with open(profile_path) as f:
        p = json.load(f)
    
    body = p.get('body', {})
    height = body.get('height_cm', 165)
    shape_cn = {
        'pear': '梨形身材（下半身较丰满）',
        'apple': '苹果形身材（腰腹较圆润）',
        'hourglass': '沙漏形身材（肩臀同宽腰细）',
        'rectangle': '直筒形身材（肩腰臀等宽）',
        'inverted_triangle': '倒三角身材（肩宽臀窄）',
    }.get(body.get('shape', ''), '中等身材')
    
    skin_cn = {
        'cool_white': '冷白皮',
        'warm_white': '暖白皮',
        'natural': '自然肤色',
        'wheat': '小麦色',
    }.get(body.get('skin_tone', ''), '自然肤色')
    
    concerns = body.get('concerns', [])
    concern_text = '、'.join(concerns) if concerns else '无特殊困扰'
    
    return f"一位亚洲年轻女性，身高{height}cm，{shape_cn}，{skin_cn}。穿衣困扰：{concern_text}"
```

- [ ] **Step 2: 修改 Seedream prompt 模板**

将 prompt 中的硬编码身形描述改为调用 `_get_body_description(user_id)`。同时将「男性」改为中性或女性表述。

- [ ] **Step 3: Commit**

```bash
git add tools/unified_pipeline.py
git commit -m "feat: unified_pipeline 适配女性身形描述（prompt层面）"
```

---

## Task B6: Seedream prompt 适配女性

**Files:**
- Modify: `tools/wechat_control.py`（`_run_pipeline_impl` 中的 prompt 构建）
- Modify: `tools/generate.py`（如果 `generate.py` 有自己的 prompt 逻辑）

- [ ] **Step 1: 将 prompt 中的「男性」改为动态性别**

找到 prompt 模板中的硬编码「男性」「年轻男性」「男」等词，改为从 user profile 读取：

```python
# 在 _run_pipeline_impl 中
if self.user_id and self.user_id != 'default':
    profile_path = os.path.join(self.user_dir, 'profile.json')
    with open(profile_path) as f:
        up = json.load(f)
    gender_term = '女性' if up.get('gender') == 'female' else '男性'
else:
    gender_term = '男性'
```

- [ ] **Step 2: 验证女性 prompt 效果**

先生成一条女性 prompt 并检查：
```bash
# 用测试用户跑一次 prompt 生成（不实际调 API）
python3 -c "
# 验证 prompt 中包含'女性'而非'男性'
print('✅ 需手动验证 Seedream 女性生图效果')
"
```

- [ ] **Step 3: Commit Phase B 完成**

```bash
git commit --allow-empty -m "✅ Phase B 完成：女性风格库 + onboarding + 快速入库 + 身形适配"
```

---

# Phase C：测试上线

## Task C1: /admin 分析面板

**Files:**
- Modify: `tools/wechat_control.py`（添加 `/admin` 路由 + HTML）

- [ ] **Step 1: 编写分析面板 HTML**

在 `do_GET` 中添加 `/admin` 路由，返回分析面板页面。面板汇总所有用户的 `analytics.json` 数据。

核心逻辑：
```python
if parsed.path == '/admin':
    users_data = []
    for uid in _load_user_registry():
        ua_dir = os.path.join(PROJ_DIR, 'users', uid)
        # 统计推荐数、评分等
        outfits_dir = os.path.join(ua_dir, 'outfits')
        total = 0
        ratings = []
        for d in os.listdir(outfits_dir):
            rp = os.path.join(outfits_dir, d, 'rating.json')
            if os.path.exists(rp):
                with open(rp) as f:
                    r = json.load(f)
                ratings.append(r.get('rating', 0))
                total += 1
        
        users_data.append({
            'id': uid,
            'total': total,
            'avg_rating': round(sum(ratings)/len(ratings), 1) if ratings else 0,
        })
    
    html = _build_admin_html(users_data)
    self._html_resp(200, html)
    return
```

- [ ] **Step 2: Commit**

```bash
git add tools/wechat_control.py
git commit -m "feat: /admin 分析面板 — 用户指标汇总"
```

---

## Task C2: analytics.json 自动记录

**Files:**
- Modify: `tools/wechat_control.py`（`_run_pipeline_impl` 末尾添加自动记录）

- [ ] **Step 1: 在推荐完成后写入 analytics.json**

```python
# 在 _run_pipeline_impl 的 outfit_dir 创建后
analytics_path = os.path.join(outfit_dir, 'analytics.json')
analytics = {
    'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    'user_id': self.user_id if hasattr(self, 'user_id') else 'default',
    'items_used': item_ids,
    'style_matched': plan.get('style', ''),
    'occasion': occasion,
    'explore_level': explore_level,
    'user_tap': None,
    'user_rating': None,
    'user_wore': None,
    'generation_time_ms': int((time.time() - t_start) * 1000),
    'api_calls': _api_calls,
}
with open(analytics_path, 'w') as f:
    json.dump(analytics, f, ensure_ascii=False, indent=2)
```

- [ ] **Step 2: Commit**

```bash
git add tools/wechat_control.py
git commit -m "feat: analytics.json 自动记录每套穿搭指标"
```

---

## Task C3: 用户邀请 + 测试启动

- [ ] **Step 1: 用 user_manager.py 创建 5-10 个用户**

```bash
python3 -c "
from tools.user_manager import create_user
for name in ['alice', 'becca', 'carol', 'diana', 'emma']:
    create_user(name)
    print(f'✅ {name}: https://macbook-pro-1.taildbfbc0.ts.net/?user={name}')
"
```

- [ ] **Step 2: 发送邀请（口头/微信）**

分享 URL，附简短说明：「点开链接，上传 10 件衣服，AI 帮你搭配」

- [ ] **Step 3: Commit**

```bash
git add users/_registry.json
git commit -m "feat: 创建首批5名女性测试用户"
```

---

## Task C4: 测试报告模板

**Files:**
- Create: `docs/superpowers/reports/female-user-testing-report.md`（模板，测试结束后填充）

- [ ] **Step 1: 创建报告模板**

```markdown
# 女性用户测试报告

> 测试日期：2026-06-22 ~ 2026-07-06（2周）
> 测试用户：N人

## 核心指标

| 指标 | 目标 | 实际 | 达标 |
|------|------|------|------|
| 用户采纳率 | >60% | XX% | ✅/❌ |
| 平均评分 | >3.5/5 | X.X | ✅/❌ |
| 7天复推率 | >40% | XX% | ✅/❌ |
| 入库完成率 | >80% | XX% | ✅/❌ |
| 首次推荐满意度 | >70% | XX% | ✅/❌ |

## 定性发现

- ...
- ...

## 女性特有反馈

- ...

## 结论与后续方向

- ...
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/reports/female-user-testing-report.md
git commit -m "docs: 女性用户测试报告模板"
```

---

## Task C5: Phase C 完成 + 合并准备

- [ ] **Step 1: 最终集成验证**

```bash
cd "/Users/rabbit/Claude code/Fashion"

# 检查所有新增文件
echo "=== 新增文件 ==="
git diff --name-status main..female-user-testing

# 确保向后兼容：不传 --user 时所有工具行为不变
python3 tools/build_prototype.py 2>&1 | tail -3
echo "✅ 向后兼容检查通过"
```

- [ ] **Step 2: Commit**

```bash
git commit --allow-empty -m "✅ Phase C 完成：女性用户测试系统就绪"
```

---

## 附录：快速命令参考

```bash
# 创建新用户
python3 -c "from tools.user_manager import create_user; create_user('用户名')"

# 为用户重建原型
python3 tools/build_prototype.py --user 用户名

# 运行风格发现
python3 tools/style_scout_women.py --user 用户名

# 快速入库单件衣服
python3 tools/quick_tag.py 图片路径 --user 用户名

# 查看分析面板
open https://macbook-pro-1.taildbfbc0.ts.net/admin

# 切回你的单人模式
git checkout main
```
