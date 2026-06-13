#!/usr/bin/env python3
"""
百科 HTML 生成器 — 将 encyclopedia.md 转为小红书风格的移动端阅读页面

用法:
  python3 tools/generate_encyclopedia_html.py              # 生成全部
  python3 tools/generate_encyclopedia_html.py <style_id>   # 单个风格
"""

import os, sys, json, re, glob

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.join(BASE_DIR, '..')
STYLES_DIR = os.path.join(PROJ_DIR, 'styles_universal')
CATEGORIES = os.path.join(STYLES_DIR, 'categories.json')

CSS = '''
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#fff;color:#333;line-height:1.8;max-width:680px;margin:0 auto;padding:0 16px 40px}
.cover{padding:40px 0 24px;border-bottom:1px solid #f0f0f0;margin-bottom:24px}
.cover h1{font-size:26px;font-weight:700;letter-spacing:1px;margin-bottom:8px}
.cover .en{font-size:14px;color:#999;margin-bottom:12px}
.cover .tags{display:flex;flex-wrap:wrap;gap:6px}
.cover .tag{background:#f5f0eb;color:#8b7355;padding:3px 10px;border-radius:12px;font-size:12px}
.cover .meta{font-size:12px;color:#bbb;margin-top:12px}
h2{font-size:18px;font-weight:700;margin:32px 0 12px;padding-left:8px;border-left:3px solid #d4a574}
h3{font-size:15px;font-weight:700;margin:20px 0 8px;color:#555}
p,li{font-size:15px;margin:6px 0}
ul,ol{padding-left:18px}
table{width:100%;border-collapse:collapse;margin:12px 0;font-size:13px}
th,td{border:1px solid #eee;padding:8px 10px;text-align:left}
th{background:#faf8f5;font-weight:600}
tr:nth-child(even){background:#fdfcf9}
blockquote{background:#fdf8f3;border-left:3px solid #d4a574;margin:12px 0;padding:10px 14px;color:#8b7355;font-style:italic;border-radius:0 6px 6px 0}
a{color:#8b7355;text-decoration:none;border-bottom:1px dotted #d4a574}
a:hover{color:#6b5535}
strong{color:#444}
code{background:#f5f0eb;padding:1px 6px;border-radius:3px;font-size:13px}
img{max-width:100%;border-radius:8px;margin:12px 0}
.sep{text-align:center;color:#ddd;margin:32px 0;font-size:20px;letter-spacing:8px}
.footer{text-align:center;color:#ccc;font-size:11px;margin-top:40px;padding-top:20px;border-top:1px solid #f0f0f0}
'''

HTML_TPL = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{name_zh} — 风格百科</title>
<style>{css}</style>
</head>
<body>
<div class="cover">
  <h1>{name_zh}</h1>
  <div class="en">{name_en}</div>
  <div class="tags">{tags}</div>
  <div class="meta">Fashion Style Advisor · {update_date}</div>
</div>
{body}
<div class="sep">· · ·</div>
<div class="footer">Fashion Style Advisor · 风格百科 · AI 辅助生成</div>
</body>
</html>'''


def md_to_html(text):
    """简易 Markdown → HTML"""
    lines = text.split('\n')
    html = []
    in_table = False
    in_list = False
    in_quote = False

    for line in lines:
        s = line.strip()

        # Skip frontmatter
        if s.startswith('> **状态') or s.startswith('> **分类'):
            continue
        if s.startswith('# ') and '#' not in s[2:]:
            continue  # skip main h1 (handled by cover)

        # Headers
        if s.startswith('## '):
            html.append(f'<h2>{escape(s[3:])}</h2>')
            continue
        if s.startswith('### '):
            html.append(f'<h3>{escape(s[4:])}</h3>')
            continue
        if s.startswith('#### '):
            html.append(f'<h4>{escape(s[5:])}</h4>')
            continue

        # Code blocks
        if s.startswith('```'):
            if in_quote:
                html.append('</pre>')
                in_quote = False
            else:
                html.append('<pre style="background:#f5f0eb;padding:12px;border-radius:6px;font-size:13px;overflow-x:auto">')
                in_quote = True
            continue
        if in_quote:
            html.append(escape(line))
            continue

        # Blockquote
        if s.startswith('> '):
            html.append(f'<blockquote>{inline_md(s[2:])}</blockquote>')
            continue

        # Tables
        if s.startswith('|') and '---' in s:
            continue
        if s.startswith('|'):
            cells = [c.strip() for c in s.split('|')[1:-1]]
            if not in_table:
                html.append('<table>')
                in_table = True
                tag = 'th'
            else:
                tag = 'td'
            html.append('<tr>' + ''.join(f'<{tag}>{inline_md(c)}</{tag}>' for c in cells) + '</tr>')
            continue
        elif in_table:
            html.append('</table>')
            in_table = False

        # Lists
        if re.match(r'^- ', s):
            html.append(f'<li>{inline_md(s[2:])}</li>')
            continue
        if re.match(r'^\d+\. ', s):
            _numless = re.sub(r'^\d+\.\s*', '', s)
            html.append(f'<li>{inline_md(_numless)}</li>')
            continue

        # Empty line
        if not s:
            html.append('<br>')
            continue

        # Paragraph
        html.append(f'<p>{inline_md(s)}</p>')

    if in_table:
        html.append('</table>')
    if in_quote:
        html.append('</pre>')

    return '\n'.join(html)


def inline_md(text):
    """行内 Markdown"""
    text = escape(text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    text = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', text)
    return text


def escape(text):
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def generate_one(style_id, dry_run=False):
    """为单个风格生成 HTML"""
    md_path = os.path.join(STYLES_DIR, style_id, 'encyclopedia.md')
    if not os.path.exists(md_path):
        return None

    with open(md_path, 'r', encoding='utf-8') as f:
        text = f.read()

    # Extract metadata
    name_zh = style_id
    name_en = ''
    for line in text.split('\n'):
        if line.startswith('# ') and '（' in line:
            m = re.match(r'# (.+?)（(.+?)）', line)
            if m:
                name_zh = m.group(1).strip()
                name_en = m.group(2).strip()
            break
        elif line.startswith('# '):
            name_zh = line[2:].strip()
            break

    # Extract update date
    update_date = '2026-06-13'
    m = re.search(r'最后更新[：:]\s*(.+)', text)
    if m:
        update_date = m.group(1).strip()

    # Extract category tags
    with open(CATEGORIES, 'r') as f:
        cats = json.load(f)
    registry = cats.get('style_registry', {})
    info = registry.get(style_id, {})
    name_zh = info.get('name_zh', name_zh)
    name_en = info.get('name_en', name_en)
    tags = []
    for dim in ['parent', 'era', 'formality', 'scene', 'aesthetic']:
        v = info.get(dim, '')
        if v:
            tags.append(v.replace('_', ' '))
    tags_html = ''.join(f'<span class="tag">{t}</span>' for t in tags[:5])

    body = md_to_html(text)
    html = HTML_TPL.format(
        name_zh=name_zh, name_en=name_en, tags=tags_html,
        update_date=update_date, body=body, css=CSS
    )

    if dry_run:
        return html

    out_path = os.path.join(STYLES_DIR, style_id, 'encyclopedia.html')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return out_path


def main():
    if len(sys.argv) > 1:
        sid = sys.argv[1]
        out = generate_one(sid)
        if out:
            print(f'✅ {sid} → {out}')
        else:
            print(f'❌ {sid} 无百科文件')
    else:
        # Generate all
        registry = json.load(open(CATEGORIES))['style_registry']
        count = 0
        for sid in registry:
            out = generate_one(sid)
            if out:
                count += 1
        print(f'✅ 生成 {count} 个百科 HTML 页面')


if __name__ == '__main__':
    main()
