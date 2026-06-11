#!/usr/bin/env python3
"""
穿搭效果图标注合成工具
将 AI 生成的效果图与原始单品图片合成，在身体对应位置贴上缩略图+标签
"""
import os, sys, re, glob
from PIL import Image, ImageDraw, ImageFont, ImageFilter

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

# ===== 品类→身体区域映射 =====
# zone_name -> (anchor_x%, anchor_y%, thumb_size_px, label_side)
# label_side: 'left'=标签在缩略图左侧, 'bottom'=标签在下方
CATEGORY_ZONE = {
    "HAT-":   {"zone": "head",        "cx": 0.50, "cy": 0.08, "size": 140},
    "SUN-":   {"zone": "head",        "cx": 0.50, "cy": 0.06, "size": 130},
    "JK-":    {"zone": "upper_top",   "cx": 0.24, "cy": 0.20, "size": 180},
    "TS-":    {"zone": "upper_body",  "cx": 0.24, "cy": 0.33, "size": 180},
    "LS-":    {"zone": "upper_body",  "cx": 0.24, "cy": 0.33, "size": 180},
    "SHIRT-": {"zone": "upper_body",  "cx": 0.24, "cy": 0.33, "size": 180},
    "TANK-":  {"zone": "upper_body",  "cx": 0.24, "cy": 0.33, "size": 180},
    "SH-":    {"zone": "lower_body",  "cx": 0.24, "cy": 0.58, "size": 180},
    "PT-":    {"zone": "lower_body",  "cx": 0.24, "cy": 0.58, "size": 180},
    "SHOE-":  {"zone": "feet",       "cx": 0.26, "cy": 0.87, "size": 160},
    "SOCK-":  {"zone": "feet",       "cx": 0.26, "cy": 0.83, "size": 140},
    "BAG-":   {"zone": "side_right", "cx": 0.82, "cy": 0.40, "size": 160},
    "ACC-":   {"zone": "wrist",      "cx": 0.16, "cy": 0.45, "size": 120},
}


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


def get_zone_info(prefix):
    """获取品类的区域信息"""
    if prefix in CATEGORY_ZONE:
        return CATEGORY_ZONE[prefix]
    # 回退查找
    for key, val in CATEGORY_ZONE.items():
        if key.startswith(prefix[:2]):
            return val
    return {"zone": "unknown", "cx": 0.50, "cy": 0.50, "size": 140}


def create_thumbnail(img_path, thumb_size):
    """
    创建圆角缩略图，带白边框和阴影
    返回 RGBA PIL Image
    """
    img = Image.open(img_path)
    if img.mode not in ('RGB', 'RGBA'):
        img = img.convert('RGBA')

    # 缩放保持宽高比
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
    为每个单品计算在 AI 图上的锚点位置
    同区域多件物品自动错开

    返回: [{item, thumb_img, anchor_x, anchor_y, label_x, label_y}]
    """
    # 按区域分组
    zones = {}
    for item in items:
        zone_info = get_zone_info(item['prefix'])
        zone_name = zone_info['zone']
        if zone_name not in zones:
            zones[zone_name] = {'items': [], 'info': zone_info}
        zones[zone_name]['items'].append(item)
        zones[zone_name]['info'] = zone_info  # 用最后一个的配置

    placed = []

    # 同区域多 item 偏移策略
    for zone_name, group in zones.items():
        zone_items = group['items']
        info = group['info']
        base_cx = int(ai_width * info['cx'])
        base_cy = int(ai_height * info['cy'])

        n = len(zone_items)

        for i, item in enumerate(zone_items):
            item_info = get_zone_info(item['prefix'])
            thumb_size = item_info['size']

            # 多件时垂直偏移
            if n > 1:
                spacing = thumb_size + 20
                offset_y = (i - (n - 1) / 2) * spacing
            else:
                offset_y = 0

            anchor_x = base_cx
            anchor_y = base_cy + int(offset_y)

            # 确保不超出图片边界
            half = thumb_size // 2 + 6  # 含边距
            anchor_x = max(half, min(ai_width - half, anchor_x))
            anchor_y = max(half, min(ai_height - half, anchor_y))

            placed.append({
                'item': item,
                'thumb_size': thumb_size,
                'anchor_x': anchor_x,
                'anchor_y': anchor_y,
            })

    return placed


def draw_label(draw, text, x, y, font_id, font_name, max_width=200):
    """
    绘制半透明标签：黑底白字圆角 pill
    返回标签底部 y 坐标
    """
    # 测量文字大小
    bbox_id = draw.textbbox((0, 0), text['id'], font=font_id)
    tw_id = bbox_id[2] - bbox_id[0]
    th_id = bbox_id[3] - bbox_id[1]

    bbox_name = draw.textbbox((0, 0), text['name'], font=font_name)
    tw_name = bbox_name[2] - bbox_name[0]
    th_name = bbox_name[3] - bbox_name[1]

    # 两行之间的间距
    gap = 2
    text_w = max(tw_id, tw_name)
    text_h = th_id + th_name + gap

    # Pill 背景尺寸
    pad_x, pad_y = 10, 6
    pill_w = text_w + pad_x * 2
    pill_h = text_h + pad_y * 2

    pill_x = x - pill_w // 2
    pill_y = y

    # 绘制半透明黑底
    overlay = Image.new('RGBA', (pill_w, pill_h), (0, 0, 0, 0))
    pill_draw = ImageDraw.Draw(overlay)
    pill_draw.rounded_rectangle(
        [(0, 0), (pill_w - 1, pill_h - 1)],
        radius=8, fill=(0, 0, 0, 170)
    )

    # ID 行（白色加粗效果通过大字号实现）
    id_x = pill_w // 2 - tw_id // 2
    pill_draw.text((id_x, pad_y), text['id'], font=font_id, fill=(255, 255, 255, 255))

    # 名称行
    name_x = pill_w // 2 - tw_name // 2
    pill_draw.text((name_x, pad_y + th_id + gap), text['name'], font=font_name, fill=(220, 220, 220, 255))

    # 合成到主 draw
    # 这里需要返回 overlay 和位置，因为 draw 不能直接 alpha composite
    return overlay, (pill_x, pill_y), pill_h


def composite(ai_path, placed_items, output_path):
    """主合成函数"""
    print(f"\n🖼️  加载 AI 效果图: {os.path.basename(ai_path)}")
    ai_img = Image.open(ai_path)
    if ai_img.mode != 'RGBA':
        ai_img = ai_img.convert('RGBA')
    ai_w, ai_h = ai_img.size
    print(f"   尺寸: {ai_w}x{ai_h}")

    # 准备字体
    font_id = find_font(15)
    font_name = find_font(12)
    font_title = find_font(22)

    # 创建标注层
    overlay = Image.new('RGBA', (ai_w, ai_h), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    # ===== 绘制标题栏 =====
    title_h = 50
    title_bg = Image.new('RGBA', (ai_w, title_h), (0, 0, 0, 150))
    overlay.paste(title_bg, (0, 0), title_bg)
    overlay_draw.text((24, 12), '单品标注', font=font_title, fill=(255, 255, 255, 240))

    # ===== 处理每个单品 =====
    items_dir = os.path.join(os.path.dirname(ai_path), '..', 'items')
    if not os.path.exists(items_dir):
        # ai_path 可能在 generated/ 下，items/ 在上层
        items_dir = os.path.join(os.path.dirname(os.path.dirname(ai_path)), 'items')

    print(f"📦 单品目录: {items_dir}")

    for i, placed in enumerate(placed_items):
        item = placed['item']
        thumb_size = placed['thumb_size']
        anchor_x = placed['anchor_x']
        anchor_y = placed['anchor_y']

        # 查找单品图片
        img_path = find_item_image(items_dir, item)
        if not img_path:
            print(f"   ⚠️  未找到 {item['id']} 的图片，跳过")
            continue

        print(f"   ✅ {item['id']} {item['name']} → {os.path.basename(img_path)}")

        # 创建缩略图
        thumb = create_thumbnail(img_path, thumb_size)
        tw, th = thumb.size

        # 粘贴缩略图（锚点为中心）
        paste_x = anchor_x - tw // 2
        paste_y = anchor_y - th // 2

        # 边界检查
        paste_x = max(0, min(ai_w - tw, paste_x))
        paste_y = max(0, min(ai_h - th, paste_y))

        overlay.paste(thumb, (paste_x, paste_y), thumb)

        # 绘制标签（在缩略图下方）
        label_data = {
            'id': item['id'],
            'name': item['name'][:12]  # 限制长度
        }
        label_img, (lx, ly), label_h = draw_label(
            overlay_draw, label_data,
            anchor_x, paste_y + th + 6,
            font_id, font_name
        )
        # 标签边界检查
        lx = max(2, min(ai_w - label_img.width - 2, lx))
        ly = max(2, min(ai_h - label_img.height - 2, ly))
        overlay.paste(label_img, (lx, ly), label_img)

        # 绘制标注小圆点（连接缩略图和标签的视觉锚点）
        dot_r = 5
        dot_x, dot_y = anchor_x, paste_y + th + 3
        overlay_draw.ellipse(
            [(dot_x - dot_r, dot_y - dot_r), (dot_x + dot_r, dot_y + dot_r)],
            fill=(255, 255, 255, 180)
        )

    # ===== 合成 =====
    result = Image.alpha_composite(ai_img, overlay)
    result_rgb = result.convert('RGB')

    # 确保输出目录存在
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
        print(f"   ▸ {item['id']} [{item['category']}] → ({p['anchor_x']}, {p['anchor_y']}) size={p['thumb_size']}")

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
