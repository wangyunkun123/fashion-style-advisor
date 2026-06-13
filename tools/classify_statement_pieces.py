#!/usr/bin/env python3
"""
单品表现力分类器 — 一次性脚本

遍历 76 件单品标签，计算表现力分数，写入 meta.is_statement_piece。

用法:
  python3 tools/classify_statement_pieces.py              # 使用默认阈值 0.30
  python3 tools/classify_statement_pieces.py --threshold 0.35  # 自定义阈值
  python3 tools/classify_statement_pieces.py --dry-run    # 仅预览，不写入
"""

import os, sys, json, glob

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.join(BASE_DIR, '..')
TAGS_DIR = os.path.join(PROJ_DIR, 'wardrobe', 'tags')

# 导入风格实验室的计算函数
sys.path.insert(0, BASE_DIR)
from style_lab import compute_statement_score


def main():
    dry_run = '--dry-run' in sys.argv
    threshold = 0.30
    for arg in sys.argv[1:]:
        if arg.startswith('--threshold'):
            if '=' in arg:
                threshold = float(arg.split('=')[1])
            else:
                idx = sys.argv.index(arg)
                if idx + 1 < len(sys.argv):
                    threshold = float(sys.argv[idx + 1])

    tag_files = sorted(glob.glob(os.path.join(TAGS_DIR, '*.json')))
    tag_files = [f for f in tag_files if not os.path.basename(f).startswith('SCORE_CACHE')]
    tag_files = [f for f in tag_files if not os.path.basename(f).startswith('.id_to_cutout')]

    print(f"🔍 扫描 {len(tag_files)} 件单品（阈值: {threshold}）...\n")

    statement_count = 0
    results = []

    for fpath in tag_files:
        with open(fpath, 'r', encoding='utf-8') as f:
            item = json.load(f)

        score = compute_statement_score(item)
        is_statement = score >= threshold

        item['meta']['is_statement_piece'] = is_statement
        item['meta']['_statement_score'] = round(score, 2)

        if is_statement:
            statement_count += 1

        results.append({
            'id': item['clothing_id'],
            'category': item.get('category', ''),
            'color': item['color']['hue_name'],
            'score': round(score, 2),
            'is_statement': is_statement,
        })

        if not dry_run:
            with open(fpath, 'w', encoding='utf-8') as f:
                json.dump(item, f, ensure_ascii=False, indent=2)

    # 打印结果
    results.sort(key=lambda x: -x['score'])

    print(f"{'ID':12s} {'品类':10s} {'颜色':10s} {'表现力':>6s} {'判定':>6s}")
    print("-" * 55)
    for r in results:
        status = '⭐ 锚点' if r['is_statement'] else '基础'
        print(f"{r['id']:12s} {r['category']:10s} {r['color']:10s} {r['score']:>6.2f}  {status:>6s}")

    print(f"\n📊 共 {statement_count}/{len(results)} 件标注为锚点单品（阈值 {threshold}）")

    if dry_run:
        print("⚠️ 预览模式，未写入文件。移除 --dry-run 以执行。")
    else:
        print("✅ 已写入所有标签文件。")


if __name__ == '__main__':
    main()
