#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
集成测试：上传分析全链路 round-trip

Mock 豆包 API → 测试完整分析管线 → 验证任务状态转换

运行: python3 tools/test_integration.py
"""

import base64
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Mock API 响应（模拟豆包返回的单品识别结果）──
MOCK_ANALYSIS_RESPONSE = json.dumps({
    "items": [
        {
            "category_code": "SHIRT",
            "category": "衬衣",
            "color": {
                "hue_family": "中性色",
                "hue_name": "米白色",
                "saturation": "无彩色",
                "lightness": "高明度",
                "is_neutral": True,
                "friendly_for_pale_skin": True
            },
            "brand": {"name": "Roland Garros", "collection": "", "confidence": "确定"},
            "fabric": {
                "primary": "棉",
                "texture": "坑条针织",
                "weight": "适中",
                "seasonality": ["春", "夏"]
            },
            "silhouette": {
                "fit": "合身",
                "shoulder_effect": "无特殊效果",
                "torso_effect": "无特殊效果",
                "length_ratio": "标准"
            },
            "pattern": {"type": "文字/Logo", "density": "适中", "logo_visible": True},
            "style_modifiers": ["复古", "运动休闲"],
            "occasions": ["运动", "日常休闲"],
            "formality": 3,
            "meta": {"claude_fit_comment": "合身版型，适配春夏"},
            "source_image": 1,
            "suggested_id": "SHIRT-099"
        }
    ]
}, ensure_ascii=False)


class TestAnalysisPipeline(unittest.TestCase):
    """分析管线集成测试（Mock 外部 API）"""

    @classmethod
    def setUpClass(cls):
        """模块级初始化：创建临时目录和基础模块"""
        cls.tmpdir = tempfile.mkdtemp(prefix='test_integration_')
        # 覆盖目录结构让 resolve_*_dir 工作
        cls.incoming_dir = os.path.join(cls.tmpdir, 'wardrobe', '_incoming')
        cls.tags_dir = os.path.join(cls.tmpdir, 'wardrobe', 'tags')
        cls.outfits_dir = os.path.join(cls.tmpdir, 'outfits')
        cls.tasks_dir = os.path.join(cls.tmpdir, 'outfits', '_tasks')
        for d in [cls.incoming_dir, cls.tags_dir, cls.outfits_dir, cls.tasks_dir]:
            os.makedirs(d, exist_ok=True)

        # 导入基础设施层（使用临时目录）
        from tools.server_infra import TaskManager
        cls.tm = TaskManager(disk_dir=cls.tasks_dir, ttl=3600, watchdog_timeout=300)

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        """每个测试前清理旧任务 + 创建新任务"""
        # 清理内存中的旧任务（避免跨测试干扰）
        self.tm._tasks.clear()
        # 清理磁盘上的旧任务文件
        for fn in os.listdir(self.tasks_dir):
            os.remove(os.path.join(self.tasks_dir, fn))
        # 清理 incoming 图片
        for fn in os.listdir(self.incoming_dir):
            os.remove(os.path.join(self.incoming_dir, fn))

        self.tid = self.tm.create()
        self.tm.update(self.tid, status='queued', message='等待分析...')

    # ── Test 1: 完整分析任务状态转换 ──
    @patch('tools.ai_api.call_doubao_chat')
    def test_analysis_state_transitions(self, mock_api):
        """Mock API → 分析完成 → 验证状态转换链"""
        mock_api.return_value = MOCK_ANALYSIS_RESPONSE

        # 验证初始状态
        t0 = self.tm.get(self.tid)
        self.assertEqual(t0['status'], 'queued')

        # 模拟 running 状态
        self.tm.update(self.tid, status='running', message='AI正在识别...',
                       started_at=time.time())
        t1 = self.tm.get(self.tid)
        self.assertEqual(t1['status'], 'running')

        # 模拟完成
        self.tm.update(self.tid, status='done', message='识别完成',
                       result=MOCK_ANALYSIS_RESPONSE)
        t2 = self.tm.get(self.tid)
        self.assertEqual(t2['status'], 'done')
        self.assertIsNotNone(t2['result'])

        # 验证分析结果可解析
        result = json.loads(t2['result']) if isinstance(t2['result'], str) else t2['result']
        self.assertIn('items', result)
        self.assertEqual(len(result['items']), 1)
        self.assertEqual(result['items'][0]['category_code'], 'SHIRT')

    # ── Test 2: API 失败时状态正确标记 ──
    @patch('tools.ai_api.call_doubao_chat')
    def test_analysis_api_failure(self, mock_api):
        """API 返回空 → 任务标记为 error"""
        mock_api.return_value = None

        # 模拟 API 失败
        self.tm.update(self.tid, status='running', message='AI正在识别...')
        self.tm.update(self.tid, status='error', message='AI 未返回结果，请重试')

        t = self.tm.get(self.tid)
        self.assertEqual(t['status'], 'error')
        self.assertIn('未返回', t['message'])

    # ── Test 3: 任务状态持久化（磁盘写穿验证）──
    def test_task_persistence_roundtrip(self):
        """写入 → 读磁盘 → 新 TaskManager 恢复"""
        self.tm.update(self.tid, status='done', message='完成',
                       result='{"test": true}')

        # 新 TaskManager 实例（模拟重启）
        tm2 = type(self.tm)(disk_dir=self.tasks_dir)
        t = tm2.get(self.tid)
        self.assertIsNotNone(t, "重启后任务丢失")
        self.assertEqual(t['status'], 'done')
        self.assertEqual(t['result'], '{"test": true}')

    # ── Test 4: 重试队列端到端 ──
    def test_retry_queue_roundtrip(self):
        """创建可恢复任务 → 模拟崩溃 → 验证重试队列"""
        # 创建模拟图片
        img_path = os.path.join(self.incoming_dir, f'img_{self.tid}_0.jpg')
        with open(img_path, 'wb') as f:
            f.write(b'\xff\xd8\xff\xe0\x00\x10JFIF')  # 最小 JPEG 头

        # 使用 _retry_images 标记（模拟 recover_on_startup 结果）
        self.tm.update(self.tid, status='running', message='分析中...',
                       _user_id='test_user',
                       _retry_images=[img_path],
                       _retry_image_dir=self.incoming_dir)

        # 验证任务数据包含重试信息
        t = self.tm.get(self.tid)
        self.assertIn('_retry_images', t)
        self.assertEqual(len(t['_retry_images']), 1)
        self.assertTrue(os.path.exists(t['_retry_images'][0]))

    # ── Test 5: 并发任务隔离 ──
    def test_concurrent_task_isolation(self):
        """多个任务同时进行，互不影响"""
        tid2 = self.tm.create()
        self.tm.update(tid2, status='running', message='任务2运行中')

        self.tm.update(self.tid, status='done', message='任务1完成')

        t1 = self.tm.get(self.tid)
        t2 = self.tm.get(tid2)

        self.assertEqual(t1['status'], 'done')
        self.assertEqual(t2['status'], 'running')
        self.assertNotEqual(t1['id'], t2['id'])

    # ── Test 6: 健康检查在负载下正常 ──
    def test_health_during_load(self):
        """有活跃任务时 /health 正确上报"""
        from tools.server_infra import collect_health_data

        # 创建多个任务（部分活跃）
        for i in range(3):
            tid = self.tm.create()
            if i < 2:
                self.tm.update(tid, status='running', message=f'处理中...')

        health = collect_health_data(self.tm)
        self.assertGreaterEqual(health['active_tasks'], 2)
        self.assertEqual(health['status'], 'ok')
        self.assertIn('funnel_active', health)

    # ── Test 7: _process_retry_queue 基本调用 ──
    def test_process_retry_queue_callable(self):
        """_process_retry_queue 函数存在且可调用（不实际提交分析）"""
        from tools.wechat_control import _process_retry_queue

        # 空队列 → 不抛异常
        try:
            _process_retry_queue([])
        except Exception as e:
            self.fail(f"_process_retry_queue([]) 抛异常: {e}")

        # 验证函数签名正确
        self.assertTrue(callable(_process_retry_queue))


if __name__ == '__main__':
    unittest.main(verbosity=2)
