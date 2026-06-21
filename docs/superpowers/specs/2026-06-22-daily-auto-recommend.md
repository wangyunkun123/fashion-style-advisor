# 每日自动推荐穿搭 — 设计文档

> 2026-06-22 | 状态：设计完成，待实施

## 目标

每天早上 5:57 自动生成今日穿搭（完整管线含 AI 生图），结果显示在手机端首页。

## 约束

- Mac 24h 不睡眠，本地调度
- 完整管线：Seedream 生图 + 排版 + 原型重建
- 手机网页为主要展示面，不推微信
- 失败时手机端显示警告卡片，点击自动重试

## 架构

```
Claude Cron (5:57) → GET localhost:8765/recommend → run_pipeline() → build_prototype.py
                                                          ↓
手机页面 JS 调 /health → 判断 today_ok → 正常展示 / 警告卡片+重试按钮
```

## 改动清单

| 组件 | 改动 | 文件 |
|------|------|------|
| Cron 调度 | 新增每日 5:57 定时任务 | `.claude/scheduled_tasks.json` |
| 健康端点 | 新增 `/health` 返回今日推荐状态 | `tools/wechat_control.py` |
| 状态端点 | 新增 `/api/status` 返回运行历史 | `tools/wechat_control.py` |
| 管线锁 | `run_pipeline()` 入口防并发 | `tools/wechat_control.py` |
| 手机端检测 | JS 启动时调 `/health`，按状态展示 | `tools/build_prototype.py` |

## 关键决策

- Cron 选 5:57 而非 6:00 — 避开舰队整点高峰
- Durable cron — 持久化到磁盘，Claude 重启后恢复
- 失败自动重试一次（60s 后）
- 管线入口加锁防并发，你点了「立即生成」不会再启一个
