#!/usr/bin/env python3
"""
穿搭效果图标注合成工具
将 AI 生成的效果图与原始单品图片合成，在身体对应位置贴上缩略图+标签
"""
import os, sys, re, glob
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

# ===== 路径配置 =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTFIT_BASE = os.path.join(BASE_DIR, '..', 'outfits')

# ===== 中文系统字体查找 =====
FONT_CANDIDATES = [
    '/System/Library/Fonts/STHeiti Medium.ttc',
    '/System/Library/Fonts/STHeiti Light.ttc',
    '/System/Library/Fonts/Hiragino Sans GB.ttc',
]

def find_font(size=16):
    """查找可用中文字体，返回 ImageFont 对象"""
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    print("⚠️  未找到中文字体，使用默认字体（中文可能显示为方块）")
    return ImageFont.load_default()

# ===== 品类→边缘布局映射 =====
# edge: 贴靠哪条边; order: 越小越靠上/左(-1=最高优先级)
# size: 缩略图基准像素; 权重越大的品类占用空间越多
CATEGORY_CONFIG = {
    # 头部配饰 → 两侧，不挡脸
    "HAT-":   {"edge": "left",   "size": 240, "order": -1},
    "SUN-":   {"edge": "right",  "size": 160, "order": -1},
    # 核心大件 → 左侧，按穿着顺序排列
    "JK-":    {"edge": "left",   "size": 340, "order": 0},
    "TS-":    {"edge": "left",   "size": 320, "order": 1},
    "LS-":    {"edge": "left",   "size": 320, "order": 1},
    "SHIRT-": {"edge": "left",   "size": 320, "order": 1},
    "TANK-":  {"edge": "left",   "size": 320, "order": 1},
    "SH-":    {"edge": "left",   "size": 320, "order": 2},
    "PT-":    {"edge": "left",   "size": 320, "order": 2},
    # 配件
    "ACC-":   {"edge": "left",   "size": 160, "order": 3},
    # 包 → 右侧
    "BAG-":   {"edge": "right",  "size": 280, "order": 1},
    # 鞋袜 → 底部
    "SHOE-":  {"edge": "bottom", "size": 320, "order": 0},
    "SOCK-":  {"edge": "bottom", "size": 200, "order": 1},
}

# 页面边距
EDGE_PAD = 16
TITLE_H = 50


def find_latest_outfit():
    """自动找到最新的穿搭目录"""
    dirs = sorted([d for d in os.listdir(OUTFIT_BASE)
                   if os.path.isdir(os.path.join(OUTFIT_BASE, d)) and not d.startswith('.')])
    return os.path.join(OUTFIT_BASE, dirs[-1]) if dirs else None


def parse_outfit_md(outfit_dir):
    """
    解析 outfit.md 的「穿搭方案」表格
    返回: [{id, name, category, prefix}]
    """
    md_path = os.path.join(outfit_dir, 'outfit.md')
    if not os.path.exists(md_path):
        print(f"❌ 未找到 {md_path}")
        return []

    with open(md_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # 找到「穿搭方案」区块
    in_section = False
    items = []

    for line in lines:
        if '穿搭方案' in line:
            in_section = True
            continue
        if in_section and line.strip().startswith('##') and '穿搭方案' not in line:
            break
        if not in_section:
            continue

        # 跳过非表格行
        stripped = line.strip()
        if not stripped.startswith('|') or '---' in stripped:
            continue

        cells = [c.strip() for c in stripped.split('|')]
        # 有效数据行：至少4列（品类 | ID | 名称 | 理由）
        if len(cells) < 4:
            continue

        category_raw = cells[1]  # 含 emoji
        item_id = cells[2].replace('**', '').strip()
        item_name = cells[3].strip()

        # 跳过表头行
        if item_id in ('单品ID', 'ID', ''):
            continue
        # 验证 ID 格式
        if not re.match(r'^[A-Z]+-\d+', item_id):
            continue

        # 去掉品类中的 emoji
        category = re.sub(r'[^一-鿿\w]', '', category_raw).strip()

        # 提取 ID 前缀
        prefix = item_id.split('-')[0] + '-'

        items.append({
            'id': item_id,
            'name': item_name,
            'category': category,
            'prefix': prefix,
        })

    return items


def find_ai_image(outfit_dir):
    """
    找到 AI 生成的效果图
    优先 generated/ → 上身效果/，优先 _1 编号的图
    """
    candidates = []

    for sub in ['generated', '上身效果']:
        sub_dir = os.path.join(outfit_dir, sub)
        if not os.path.exists(sub_dir):
            continue
        for f in sorted(os.listdir(sub_dir)):
            if f.lower().endswith(('.jpg', '.jpeg', '.png')) and not f.startswith('.'):
                candidates.append(os.path.join(sub_dir, f))

    if not candidates:
        return None

    # 优先选 _1 或 不带编号的
    preferred = [p for p in candidates if '_1.' in os.path.basename(p) or '_标注版' not in os.path.basename(p)]
    if preferred:
        # 进一步优先非标注版
        non_annotated = [p for p in preferred if '标注版' not in p]
        return non_annotated[0] if non_annotated else preferred[0]
    return candidates[0]


def find_item_image(items_dir, item):
    """
    在 items/ 目录中匹配单品图片
    匹配规则：文件名包含 {ID}_ 前缀
    """
    item_id = item['id']
    name = item['name']

    # 精确匹配：ID_名称.jpg
    exact_pattern = f"{item_id}_*"
    matches = glob.glob(os.path.join(items_dir, exact_pattern))
    if matches:
        # 选第一个匹配的（排除 .DS_Store）
        for m in matches:
            if os.path.isfile(m) and not os.path.basename(m).startswith('.'):
                return m

    # 模糊匹配：只匹配 ID 前缀
    for f in sorted(os.listdir(items_dir)):
        if f.startswith(item_id + '_') and f.lower().endswith(('.jpg', '.jpeg', '.png')):
            return os.path.join(items_dir, f)

    # 关键词匹配：匹配名称中的关键词
    name_keywords = re.split(r'[/、]', name)[0][:4]
    for f in sorted(os.listdir(items_dir)):
        if name_keywords in f and f.lower().endswith(('.jpg', '.jpeg', '.png')):
            return os.path.join(items_dir, f)

    return None


def get_item_config(prefix):
    """获取品类的布局配置"""
    if prefix in CATEGORY_CONFIG:
        return CATEGORY_CONFIG[prefix]
    for key, val in CATEGORY_CONFIG.items():
        if key.startswith(prefix[:2]):
            return val
    return {"edge": "left", "size": 240, "order": 99}


def create_thumbnail(img_path, thumb_size):
    """
    创建圆角缩略图，带白边框和阴影
    - 自动校正 EXIF 旋转
    - 保持原始宽高比（衣物已在衣橱中统一为正向）
    返回 RGBA PIL Image
    """
    img = Image.open(img_path)

    # EXIF 自动旋转（衣物已经 auto_orient.py 处理过方向）
    img = ImageOps.exif_transpose(img)

    if img.mode not in ('RGB', 'RGBA'):
        img = img.convert('RGBA')

    # 缩放保持宽高比（长边适配 thumb_size）
    w, h = img.size
    ratio = thumb_size / max(w, h)
    new_w, new_h = int(w * ratio), int(h * ratio)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    # 转为 RGBA
    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    # 创建圆角遮罩
    mask = Image.new('L', (new_w, new_h), 0)
    mask_draw = ImageDraw.Draw(mask)
    radius = 12
    mask_draw.rounded_rectangle([(0, 0), (new_w - 1, new_h - 1)], radius=radius, fill=255)
    img.putalpha(mask)

    # 阴影层（比缩略图大一圈）
    shadow_pad = 6
    shadow_size = (new_w + shadow_pad * 2, new_h + shadow_pad * 2)
    shadow = Image.new('RGBA', shadow_size, (0, 0, 0, 0))
    shadow_mask = Image.new('L', shadow_size, 0)
    shadow_draw = ImageDraw.Draw(shadow_mask)
    shadow_draw.rounded_rectangle(
        [(shadow_pad, shadow_pad), (shadow_size[0] - shadow_pad - 1, shadow_size[1] - shadow_pad - 1)],
        radius=radius, fill=80
    )
    shadow.putalpha(shadow_mask)
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=5))

    # 白边框层
    border_pad = 3
    final_size = (new_w + border_pad * 2, new_h + border_pad * 2)
    result = Image.new('RGBA', final_size, (0, 0, 0, 0))

    # 粘贴阴影
    shadow_offset_x = (final_size[0] - shadow_size[0]) // 2 + 3
    shadow_offset_y = (final_size[1] - shadow_size[1]) // 2 + 3
    result.paste(shadow, (shadow_offset_x, shadow_offset_y), shadow)

    # 白边框
    border = Image.new('RGBA', final_size, (0, 0, 0, 0))
    border_mask = Image.new('L', final_size, 0)
    border_draw = ImageDraw.Draw(border_mask)
    border_draw.rounded_rectangle(
        [(0, 0), (final_size[0] - 1, final_size[1] - 1)],
        radius=radius + border_pad, fill=255
    )
    border.putalpha(border_mask)

    # 白色填充
    white_bg = Image.new('RGBA', final_size, (255, 255, 255, 255))
    white_bg.putalpha(border_mask)
    result = Image.alpha_composite(result, white_bg)

    # 粘贴缩略图到白边框内部
    result.paste(img, (border_pad, border_pad), img)

    return result


def assign_positions(items, ai_width, ai_height):
    """
    边缘布局：利用人物四周空间展示服装
    - 帽子 → 左侧最上（头部左侧）
    - 外套/上衣/下装 → 左侧垂直排列（核心大件）
    - 墨镜 → 右侧最上（头部右侧）
    - 包 → 右侧
    - 鞋袜 → 底部水平排列
    """
    edges = {"left": [], "right": [], "bottom": []}

    for item in items:
        cfg = get_item_config(item['prefix'])
        edge = cfg['edge']
        edges[edge].append({
            'item': item,
            'size': cfg['size'],
            'order': cfg['order'],
        })

    for edge in edges:
        edges[edge].sort(key=lambda x: (x['order'], x['item']['id']))

    placed = []
    usable_top = TITLE_H + EDGE_PAD
    usable_bottom = ai_height - EDGE_PAD
    usable_height = usable_bottom - usable_top
    usable_width = ai_width - EDGE_PAD * 2

    # 标签估算高度（根据字号动态）
    label_est = 60

    def layout_vertical(items_list, edge_name, usable_h):
        """垂直排列：均匀分布 + 自动压缩"""
        if not items_list:
            return []
        result = []
        est_heights = [it['size'] + label_est for it in items_list]
        total = sum(est_heights)
        if total > usable_h:
            scale = usable_h / total
            for i, it in enumerate(items_list):
                it['size'] = max(120, int(it['size'] * scale))
                est_heights[i] = it['size'] + label_est
            total = sum(est_heights)
        spacing = max(8, (usable_h - total) / (len(items_list) + 1))
        cur_y = usable_top + spacing

        for it in items_list:
            if edge_name == 'left':
                px = EDGE_PAD
            else:
                # 右边缘：预估宽度 ≈ 高度的 60%（衣物竖图通常 3:4~2:3）
                est_w = int(it['size'] * 0.65)
                px = ai_width - EDGE_PAD - est_w
            py = int(cur_y)
            result.append({
                'item': it['item'], 'thumb_size': it['size'],
                'paste_x': px, 'paste_y': py, 'edge': edge_name,
            })
            cur_y += it['size'] + label_est + spacing
        return result

    def layout_horizontal(items_list, usable_w):
        """底部水平排列"""
        if not items_list:
            return []
        result = []
        est_widths = [it['size'] + label_est for it in items_list]
        total = sum(est_widths)
        if total > usable_w:
            scale = usable_w / total
            for i, it in enumerate(items_list):
                it['size'] = max(120, int(it['size'] * scale))
                est_widths[i] = it['size'] + label_est
            total = sum(est_widths)
        spacing = max(8, (usable_w - total) / (len(items_list) + 1))
        cur_x = EDGE_PAD + spacing

        for it in items_list:
            py = usable_bottom - it['size']
            result.append({
                'item': it['item'], 'thumb_size': it['size'],
                'paste_x': int(cur_x), 'paste_y': py, 'edge': 'bottom',
            })
            cur_x += it['size'] + label_est + spacing
        return result

    placed.extend(layout_vertical(edges['left'], 'left', usable_height))
    placed.extend(layout_vertical(edges['right'], 'right', usable_height))
    placed.extend(layout_horizontal(edges['bottom'], usable_width))

    return placed


def draw_label(text, x, y, font_id, font_name, anchor="below"):
    """
    绘制半透明标签 pill
    anchor: "below"=标签在点下方, "above"=标签在点上方,
            "right"=在点右侧, "left"=在点左侧
    返回: (label_image, (paste_x, paste_y))
    """
    bbox_id = ImageDraw.Draw(Image.new('RGBA', (1, 1))).textbbox((0, 0), text['id'], font=font_id)
    tw_id = bbox_id[2] - bbox_id[0]
    th_id = bbox_id[3] - bbox_id[1]

    bbox_name = ImageDraw.Draw(Image.new('RGBA', (1, 1))).textbbox((0, 0), text['name'], font=font_name)
    tw_name = bbox_name[2] - bbox_name[0]
    th_name = bbox_name[3] - bbox_name[1]

    gap = 2
    text_w = max(tw_id, tw_name)
    text_h = th_id + th_name + gap
    pad_x, pad_y = 12, 7
    pill_w = text_w + pad_x * 2
    pill_h = text_h + pad_y * 2

    overlay = Image.new('RGBA', (pill_w, pill_h), (0, 0, 0, 0))
    pill_draw = ImageDraw.Draw(overlay)
    pill_draw.rounded_rectangle(
        [(0, 0), (pill_w - 1, pill_h - 1)],
        radius=8, fill=(0, 0, 0, 180)
    )
    id_x = pill_w // 2 - tw_id // 2
    pill_draw.text((id_x, pad_y), text['id'], font=font_id, fill=(255, 255, 255, 255))
    name_x = pill_w // 2 - tw_name // 2
    pill_draw.text((name_x, pad_y + th_id + gap), text['name'], font=font_name, fill=(220, 220, 220, 255))

    # 计算标签放置位置
    if anchor == "below":
        lx, ly = x - pill_w // 2, y
    elif anchor == "above":
        lx, ly = x - pill_w // 2, y - pill_h
    elif anchor == "right":
        lx, ly = x, y - pill_h // 2
    elif anchor == "left":
        lx, ly = x - pill_w, y - pill_h // 2
    else:
        lx, ly = x - pill_w // 2, y

    return overlay, (lx, ly)


def composite(ai_path, placed_items, output_path):
    """主合成函数：边缘布局 + 缩略图 + 标签"""
    print(f"\n🖼️  加载 AI 效果图: {os.path.basename(ai_path)}")
    ai_img = Image.open(ai_path)
    if ai_img.mode != 'RGBA':
        ai_img = ai_img.convert('RGBA')
    ai_w, ai_h = ai_img.size
    print(f"   尺寸: {ai_w}x{ai_h}")

    # 准备字体（放大以适应更大的缩略图）
    font_id = find_font(18)
    font_name = find_font(14)
    font_title = find_font(24)

    # 创建标注层
    overlay = Image.new('RGBA', (ai_w, ai_h), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    # ===== 标题栏 =====
    title_bg = Image.new('RGBA', (ai_w, TITLE_H), (0, 0, 0, 160))
    overlay.paste(title_bg, (0, 0), title_bg)
    overlay_draw.text((24, 10), '单品标注', font=font_title, fill=(255, 255, 255, 240))

    # ===== 确定 items 目录 =====
    items_dir = os.path.join(os.path.dirname(ai_path), '..', 'items')
    if not os.path.exists(items_dir):
        items_dir = os.path.join(os.path.dirname(os.path.dirname(ai_path)), 'items')

    print(f"📦 单品目录: {items_dir}")

    for placed in placed_items:
        item = placed['item']
        thumb_size = placed['thumb_size']
        paste_x = placed['paste_x']
        paste_y = placed['paste_y']
        edge = placed['edge']

        # 查找单品图片
        img_path = find_item_image(items_dir, item)
        if not img_path:
            print(f"   ⚠️  未找到 {item['id']} 的图片，跳过")
            continue

        print(f"   ✅ {item['id']} {item['name'][:15]} → {os.path.basename(img_path)} ({thumb_size}px)")

        # 创建缩略图
        thumb = create_thumbnail(img_path, thumb_size)
        tw, th = thumb.size

        # 粘贴缩略图
        px = max(2, min(ai_w - tw - 2, paste_x))
        py = max(2, min(ai_h - th - 2, paste_y))
        overlay.paste(thumb, (px, py), thumb)

        # 标签文本
        label_data = {'id': item['id'], 'name': item['name'][:14]}

        # 根据边缘决定标签位置
        if edge == 'left':
            # 标签在缩略图右侧（指向人物）
            label_img, (lx, ly) = draw_label(
                label_data, px + tw + 8, py + th // 2, font_id, font_name, anchor="right"
            )
        elif edge == 'right':
            # 标签在缩略图左侧（指向人物）
            label_img, (lx, ly) = draw_label(
                label_data, px - 8, py + th // 2, font_id, font_name, anchor="left"
            )
        elif edge == 'bottom':
            # 标签在缩略图上方
            label_img, (lx, ly) = draw_label(
                label_data, px + tw // 2, py - 6, font_id, font_name, anchor="above"
            )
        else:
            label_img, (lx, ly) = draw_label(
                label_data, px + tw // 2, py + th + 6, font_id, font_name, anchor="below"
            )

        # 边界钳制
        lx = max(2, min(ai_w - label_img.width - 2, lx))
        ly = max(2, min(ai_h - label_img.height - 2, ly))
        overlay.paste(label_img, (lx, ly), label_img)

        # 连接线：从缩略图边缘到标签
        line_color = (255, 255, 255, 100)
        if edge == 'left':
            start = (px + tw, py + th // 2)
            end = (lx, ly + label_img.height // 2)
        elif edge == 'right':
            start = (px, py + th // 2)
            end = (lx + label_img.width, ly + label_img.height // 2)
        elif edge == 'bottom':
            start = (px + tw // 2, py)
            end = (lx + label_img.width // 2, ly + label_img.height)
        else:
            start = (px + tw // 2, py + th)
            end = (lx + label_img.width // 2, ly)
        overlay_draw.line([start, end], fill=line_color, width=1)

    # ===== 合成 =====
    result = Image.alpha_composite(ai_img, overlay)
    result_rgb = result.convert('RGB')

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    result_rgb.save(output_path, 'JPEG', quality=92)

    file_size = os.path.getsize(output_path) // 1024
    print(f"\n💾 已保存: {output_path} ({file_size}KB)")
    return output_path


def main():
    print("=" * 60)
    print("🏷️  穿搭效果图单品标注合成")
    print("=" * 60)

    # 确定穿搭目录
    if len(sys.argv) > 1:
        outfit_dir = sys.argv[1]
        if not os.path.isabs(outfit_dir):
            outfit_dir = os.path.join(BASE_DIR, '..', outfit_dir)
        outfit_dir = os.path.abspath(outfit_dir)
    else:
        outfit_dir = find_latest_outfit()

    if not outfit_dir or not os.path.exists(outfit_dir):
        print("❌ 未找到穿搭目录")
        sys.exit(1)

    print(f"\n📁 穿搭目录: {os.path.basename(outfit_dir)}")

    # 解析 outfit.md
    items = parse_outfit_md(outfit_dir)
    if not items:
        print("❌ 未能从 outfit.md 解析到单品信息")
        sys.exit(1)

    print(f"📋 解析到 {len(items)} 件单品:")
    for item in items:
        print(f"   ▸ {item['id']} [{item['category']}] {item['name']}")

    # 查找 AI 效果图
    ai_path = find_ai_image(outfit_dir)
    if not ai_path:
        print("❌ 未找到 AI 生成的效果图（generated/ 或 上身效果/）")
        sys.exit(1)

    print(f"\n🖼️  AI 效果图: {os.path.basename(ai_path)}")

    # 加载 AI 图获取尺寸
    ai_img = Image.open(ai_path)
    ai_w, ai_h = ai_img.size
    ai_img.close()

    # 计算位置
    placed = assign_positions(items, ai_w, ai_h)
    print(f"\n📍 位置分配（共 {len(placed)} 件）:")
    for p in placed:
        item = p['item']
        print(f"   ▸ {item['id']} [{item['category']}] → {p['edge']}边 ({p['paste_x']}, {p['paste_y']}) {p['thumb_size']}px")

    # 确定输出路径
    ai_dir = os.path.dirname(ai_path)
    ai_basename = os.path.splitext(os.path.basename(ai_path))[0]
    output_path = os.path.join(ai_dir, f"{ai_basename}_标注版.jpg")

    # 合成
    composite(ai_path, placed, output_path)

    print(f"\n{'=' * 60}")
    print(f"✅ 标注图生成完成！")
    print(f"📁 {output_path}")


if __name__ == '__main__':
    main()
