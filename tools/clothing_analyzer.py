#!/usr/bin/env python3
"""
服装智能分析工具 — AI 视觉三引擎
===================================
整合三个免费本地 AI 模型进行服装识别分析：

A. YOLOv8       → 服装检测（位置 + 品类边界框）
B. HuggingFace  → 服装分类（45 类精细品类）
C. OpenClip     → 图文匹配（给图打标签/文字搜图）

用法:
    # 分析单张图片（三引擎全开）
    python3 tools/clothing_analyzer.py --image path/to/shirt.jpg

    # 只检测品类和位置（YOLO 模式）
    python3 tools/clothing_analyzer.py --image outfit.jpg --mode detect

    # 只分类（HuggingFace 模式）
    python3 tools/clothing_analyzer.py --image shirt.jpg --mode classify

    # 给图片打文字标签（OpenClip 模式）
    python3 tools/clothing_analyzer.py --image outfit.jpg --mode tag

    # 批量分析整个目录
    python3 tools/clothing_analyzer.py --dir ./wardrobe/items --output ./analysis_results

    # 自定义标签列表（OpenClip）
    python3 tools/clothing_analyzer.py --image shirt.jpg --mode tag \\
        --labels "T恤,衬衫,卫衣,外套,Polo衫,背心"

    # 搜索匹配度最高的图片（用文字搜图）
    python3 tools/clothing_analyzer.py --search "蓝色条纹衬衫" --dir ./wardrobe

    # 可视化检测结果
    python3 tools/clothing_analyzer.py --image outfit.jpg --visualize
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from collections import Counter

# ============================================================
# 配置
# ============================================================

BASE_DIR = Path(__file__).parent.parent
DEFAULT_OUTPUT = BASE_DIR / "analysis_results"

# ============================================================
# 引擎 A: YOLOv8 — 服装检测
# ============================================================

YOLO_MODEL = "yolov8n.pt"  # 轻量版，~6MB

def detect_clothing(image_path, model_name=YOLO_MODEL, conf=0.25):
    """
    YOLOv8 通用物体检测（含服装品类）
    返回检测到的物品列表：位置 + 品类 + 置信度
    """
    try:
        from ultralytics import YOLO
    except ImportError:
        return {"error": "请先安装: pip install ultralytics"}

    if not os.path.exists(image_path):
        return {"error": f"图片不存在: {image_path}"}

    try:
        model = YOLO(model_name)
        results = model(image_path, conf=conf)

        detections = []
        for r in results:
            boxes = r.boxes
            if boxes is None:
                continue

            for i in range(len(boxes)):
                cls_id = int(boxes.cls[i].item())
                conf_score = float(boxes.conf[i].item())
                x1, y1, x2, y2 = [float(v) for v in boxes.xyxy[i].tolist()]

                # YOLO COCO 数据集中与服装相关的品类
                class_name = r.names[cls_id]

                detections.append({
                    "class": class_name,
                    "confidence": round(conf_score, 3),
                    "bbox": {
                        "x1": round(x1, 1),
                        "y1": round(y1, 1),
                        "x2": round(x2, 1),
                        "y2": round(y2, 1),
                        "width": round(x2 - x1, 1),
                        "height": round(y2 - y1, 1),
                    },
                    "area_ratio": round((x2 - x1) * (y2 - y1) / (r.orig_shape[1] * r.orig_shape[0]), 4),
                })

        return {
            "engine": "YOLOv8",
            "image": os.path.basename(image_path),
            "detections": detections,
            "count": len(detections),
            "clothing_items": [d for d in detections if d["class"] in _CLOTHING_CLASSES],
        }
    except Exception as e:
        return {"error": f"YOLO 检测失败: {e}"}


# YOLO COCO 中与服装相关的品类
_CLOTHING_CLASSES = {
    "shirt", "tee", "tshirt", "t-shirt", "T-shirt",
    "pants", "jeans", "shorts", "skirt", "dress",
    "jacket", "coat", "blazer", "hoodie", "sweater",
    "shoe", "sneakers", "boots", "sandals", "hat", "cap",
    "backpack", "bag", "tie", "belt", "scarf", "gloves",
    "sunglasses", "watch", "bracelet", "necklace",
    "suitcase", "umbrella",
    # COCO 标准品类
    "person", "tie", "suitcase", "frisbee", "skis",
    "snowboard", "sports ball", "kite", "baseball bat",
    "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "wine glass", "cup",
    "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog",
    "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet",
    "tv", "laptop", "mouse", "remote", "keyboard",
    "cell phone", "microwave", "oven", "toaster",
    "sink", "refrigerator", "book", "clock", "vase",
    "scissors", "teddy bear", "hair drier", "toothbrush",
}

# ============================================================
# 引擎 B: HuggingFace — 服装精细分类
# ============================================================

def classify_clothing(image_path):
    """
    HuggingFace nateraw/fashion-clothes 模型
    45 种服装品类分类
    """
    try:
        from transformers import pipeline
    except ImportError:
        return {"error": "请先安装: pip install transformers torch"}

    if not os.path.exists(image_path):
        return {"error": f"图片不存在: {image_path}"}

    try:
        classifier = pipeline(
            "image-classification",
            model="tzhao3/vit-FashionMNIST",
            top_k=10,
        )
        results = classifier(image_path)

        classifications = []
        for r in results:
            classifications.append({
                "label": r["label"],
                "confidence": round(r["score"], 4),
            })

        return {
            "engine": "HuggingFace Fashion",
            "image": os.path.basename(image_path),
            "top_prediction": classifications[0] if classifications else None,
            "classifications": classifications,
            "all_labels": [c["label"] for c in classifications],
        }
    except Exception as e:
        return {"error": f"分类失败: {e}"}


# ============================================================
# 引擎 C: OpenClip — 图文匹配
# ============================================================

def tag_image(image_path, candidate_labels=None):
    """
    OpenClip 图文匹配：给图片打标签
    默认使用服装相关的标签列表
    """
    try:
        import torch
        import clip
    except ImportError:
        try:
            import open_clip
        except ImportError:
            return {"error": "请先安装: pip install open-clip-torch"}

    if not os.path.exists(image_path):
        return {"error": f"图片不存在: {image_path}"}

    # 默认服装标签
    if candidate_labels is None:
        candidate_labels = [
            "T恤", "衬衫", "Polo衫", "卫衣", "毛衣", "背心",
            "外套", "夹克", "风衣", "西装", "牛仔外套",
            "短裤", "长裤", "牛仔裤", "休闲裤", "运动裤",
            "裙子", "连衣裙", "半身裙",
            "运动鞋", "帆布鞋", "靴子", "凉鞋", "皮鞋",
            "帽子", "背包", "手表", "项链", "腰带",
            "黑色", "白色", "蓝色", "红色", "绿色", "灰色",
            "条纹", "格纹", "纯色", "印花", "牛仔布",
            "棉", "亚麻", "丝绸", "羊毛", "皮革",
            "正式", "休闲", "运动", "通勤", "度假",
            "日系", "韩系", "美式", "英式", "简约",
        ]

    try:
        # 尝试 open_clip
        import open_clip
        model, _, preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained="laion2b_s34b_b79k"
        )
        tokenizer = open_clip.get_tokenizer("ViT-B-32")

        from PIL import Image
        img = Image.open(image_path).convert("RGB")
        image_input = preprocess(img).unsqueeze(0)
        text_inputs = tokenizer(candidate_labels)

        with torch.no_grad():
            image_features = model.encode_image(image_input)
            text_features = model.encode_text(text_inputs)
            image_features /= image_features.norm(dim=-1, keepdim=True)
            text_features /= text_features.norm(dim=-1, keepdim=True)
            similarity = (100.0 * image_features @ text_features.T).softmax(dim=-1)

        scores = similarity[0].tolist()
        results = sorted(
            zip(candidate_labels, scores),
            key=lambda x: x[1],
            reverse=True,
        )

        tags = []
        for label, score in results[:15]:
            if score > 0.01:  # 过滤低置信度
                tags.append({
                    "label": label,
                    "score": round(score, 4),
                })

        return {
            "engine": "OpenClip",
            "image": os.path.basename(image_path),
            "top_tags": tags[:5],
            "all_tags": tags,
            "candidates_count": len(candidate_labels),
        }
    except Exception as e:
        return {"error": f"OpenClip 分析失败: {e}"}


def search_by_text(query, image_dir, top_k=5):
    """
    OpenClip 文字搜图：用文字描述搜索图片目录
    """
    try:
        import torch
        import open_clip
    except ImportError:
        return {"error": "请先安装: pip install open-clip-torch"}

    image_dir = Path(image_dir)
    if not image_dir.exists():
        return {"error": f"目录不存在: {image_dir}"}

    # 收集图片
    extensions = {".jpg", ".jpeg", ".png", ".webp"}
    images = sorted([f for f in image_dir.iterdir() if f.suffix.lower() in extensions])
    if not images:
        return {"error": f"目录中没有图片: {image_dir}"}

    try:
        import open_clip
        import torch
        from PIL import Image

        model, _, preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained="laion2b_s34b_b79k"
        )
        tokenizer = open_clip.get_tokenizer("ViT-B-32")

        # 编码查询文字
        text = tokenizer([query])
        with torch.no_grad():
            text_features = model.encode_text(text)
            text_features /= text_features.norm(dim=-1, keepdim=True)

        results = []
        for img_path in images:
            try:
                img = Image.open(img_path).convert("RGB")
                image_input = preprocess(img).unsqueeze(0)

                with torch.no_grad():
                    image_features = model.encode_image(image_input)
                    image_features /= image_features.norm(dim=-1, keepdim=True)
                    similarity = (image_features @ text_features.T).item()

                results.append({
                    "file": img_path.name,
                    "path": str(img_path),
                    "similarity": round(similarity, 4),
                })
            except Exception:
                continue

        results.sort(key=lambda x: x["similarity"], reverse=True)

        return {
            "engine": "OpenClip 文字搜图",
            "query": query,
            "total_images": len(results),
            "results": results[:top_k],
            "top_result": results[0] if results else None,
        }
    except Exception as e:
        return {"error": f"搜索失败: {e}"}


# ============================================================
# 可视化（YOLO 检测结果标注）
# ============================================================

def visualize_detection(image_path, output_path=None):
    """运行 YOLO 检测并保存标注图片"""
    try:
        from ultralytics import YOLO
    except ImportError:
        return {"error": "请先安装: pip install ultralytics"}

    if not os.path.exists(image_path):
        return {"error": f"图片不存在: {image_path}"}

    if output_path is None:
        output_dir = DEFAULT_OUTPUT
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / f"detected_{Path(image_path).name}")

    try:
        model = YOLO(YOLO_MODEL)
        results = model(image_path)
        for r in results:
            r.save(filename=output_path)

        return {
            "engine": "YOLOv8 可视化",
            "input": image_path,
            "output": output_path,
        }
    except Exception as e:
        return {"error": f"可视化失败: {e}"}


# ============================================================
# 综合分析（三引擎全开）
# ============================================================

def analyze_full(image_path):
    """三引擎综合分析一张图片"""
    print(f"\n{'='*60}")
    print(f"  🔍 综合分析: {Path(image_path).name}")
    print(f"{'='*60}")

    result = {
        "image": os.path.basename(image_path),
        "path": image_path,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    # 引擎 A: YOLOv8 检测
    print(f"\n🅰️  YOLOv8 检测...")
    detect = detect_clothing(image_path)
    result["yolo_detection"] = detect
    if "error" not in detect:
        clothes = detect.get("clothing_items", [])
        print(f"   检测到 {detect['count']} 个物品，其中服装相关: {len(clothes)}")
        for c in clothes:
            print(f"   - {c['class']} (置信度: {c['confidence']})")
    else:
        print(f"   ❌ {detect['error']}")

    # 引擎 B: HuggingFace 分类
    print(f"\n🅱️  HuggingFace 服装分类...")
    classify = classify_clothing(image_path)
    result["hf_classification"] = classify
    if "error" not in classify:
        print(f"   最可能: {classify['top_prediction']['label']} ({classify['top_prediction']['confidence']})")
        for c in classify["classifications"][:5]:
            print(f"   - {c['label']}: {c['confidence']}")
    else:
        print(f"   ❌ {classify['error']}")

    # 引擎 C: OpenClip 标签
    print(f"\n🅲  OpenClip 标签匹配...")
    tags = tag_image(image_path)
    result["openclip_tags"] = tags
    if "error" not in tags:
        print(f"   前5标签:")
        for t in tags["top_tags"]:
            print(f"   - {t['label']}: {t['score']}")
    else:
        print(f"   ❌ {tags['error']}")

    # 综合分析结论
    print(f"\n{'='*60}")
    print(f"  📋 分析结论")
    print(f"{'='*60}")

    conclusions = []

    # 从 YOLO 看品类
    if "error" not in detect and detect["clothing_items"]:
        main_item = detect["clothing_items"][0]["class"]
        conclusions.append(f"主要品类: {main_item}")

    # 从 HuggingFace 看精细分类
    if "error" not in classify and classify["top_prediction"]:
        conclusions.append(f"精细分类: {classify['top_prediction']['label']}")

    # 从 OpenClip 看风格/颜色
    if "error" not in tags and tags["top_tags"]:
        style_tags = [t["label"] for t in tags["top_tags"][:3]]
        conclusions.append(f"特征标签: {' / '.join(style_tags)}")

    for c in conclusions:
        print(f"   ✅ {c}")

    print()
    return result


# ============================================================
# 批量处理
# ============================================================

def batch_analyze(directory, output_dir=None):
    """批量分析目录中的所有图片"""
    directory = Path(directory)
    if not directory.exists():
        print(f"❌ 目录不存在: {directory}")
        return

    if output_dir:
        output_dir = Path(output_dir)
    else:
        output_dir = DEFAULT_OUTPUT
    output_dir.mkdir(parents=True, exist_ok=True)

    extensions = {".jpg", ".jpeg", ".png", ".webp"}
    images = sorted([f for f in directory.iterdir() if f.suffix.lower() in extensions])

    if not images:
        print(f"❌ 目录中没有图片: {directory}")
        return

    print(f"\n📂 批量分析 {len(images)} 张图片...\n")

    all_results = {}
    for i, img_path in enumerate(images, 1):
        print(f"[{i}/{len(images)}] {img_path.name}")
        result = analyze_full(str(img_path))
        all_results[img_path.name] = result
        print()

    # 保存汇总
    summary_file = output_dir / "analysis_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"📄 汇总已保存: {summary_file}")

    # 生成文本报告
    report_file = output_dir / "analysis_report.txt"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("服装分析报告\n")
        f.write(f"{'='*60}\n")
        f.write(f"分析时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"图片总数: {len(images)}\n\n")

        for name, result in all_results.items():
            f.write(f"\n--- {name} ---\n")
            yolo = result.get("yolo_detection", {})
            hf = result.get("hf_classification", {})
            clip = result.get("openclip_tags", {})

            if "error" not in yolo and yolo.get("clothing_items"):
                for c in yolo["clothing_items"]:
                    f.write(f"  YOLO: {c['class']} ({c['confidence']})\n")
            if "error" not in hf and hf.get("top_prediction"):
                f.write(f"  HF: {hf['top_prediction']['label']} ({hf['top_prediction']['confidence']})\n")
            if "error" not in clip and clip.get("top_tags"):
                tags_str = " / ".join([t["label"] for t in clip["top_tags"]])
                f.write(f"  CLIP: {tags_str}\n")

    print(f"📄 报告已保存: {report_file}")

    return all_results


# ============================================================
# CLI 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="👕 服装智能分析工具（YOLOv8 + HuggingFace + OpenClip）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 tools/clothing_analyzer.py --image shirt.jpg
  python3 tools/clothing_analyzer.py --image outfit.jpg --mode detect
  python3 tools/clothing_analyzer.py --dir ./wardrobe/items --output ./results
  python3 tools/clothing_analyzer.py --search "蓝色条纹衬衫" --dir ./wardrobe
  python3 tools/clothing_analyzer.py --image outfit.jpg --visualize
        """,
    )
    parser.add_argument("--image", "-i", type=str, help="单张图片路径")
    parser.add_argument("--dir", "-d", type=str, help="批量分析目录")
    parser.add_argument("--mode", "-m", type=str,
                        choices=["full", "detect", "classify", "tag"],
                        default="full", help="分析模式（默认 full=三引擎全开）")
    parser.add_argument("--output", "-o", type=str, help="输出目录")
    parser.add_argument("--labels", type=str, help="自定义标签（逗号分隔，仅 tag 模式）")
    parser.add_argument("--search", "-s", type=str, help="文字搜图关键词")
    parser.add_argument("--visualize", "-v", action="store_true", help="可视化检测结果")
    parser.add_argument("--top-k", type=int, default=5, help="搜索/显示前 N 个结果")

    args = parser.parse_args()

    if args.search and args.dir:
        result = search_by_text(args.search, args.dir, args.top_k)
        print(f"\n🔍 文字搜图: \"{args.search}\"")
        print(f"{'='*50}")
        if "error" in result:
            print(f"❌ {result['error']}")
        else:
            print(f"📊 共搜索 {result['total_images']} 张图片")
            for i, r in enumerate(result["results"], 1):
                print(f"\n  #{i} {r['file']}")
                print(f"     匹配度: {r['similarity']}")
        return

    if args.visualize and args.image:
        result = visualize_detection(args.image, args.output)
        if "error" in result:
            print(f"❌ {result['error']}")
        else:
            print(f"✅ 标注图已保存: {result['output']}")
        return

    if args.dir:
        batch_analyze(args.dir, args.output)
        return

    if args.image:
        if args.mode == "detect":
            result = detect_clothing(args.image)
        elif args.mode == "classify":
            result = classify_clothing(args.image)
        elif args.mode == "tag":
            labels = args.labels.split(",") if args.labels else None
            result = tag_image(args.image, labels)
        else:
            result = analyze_full(args.image)
            return

        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    parser.print_help()
    print("\n❌ 请指定 --image 或 --dir")


if __name__ == "__main__":
    main()
