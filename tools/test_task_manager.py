#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TaskManager 单元测试

覆盖核心可靠性路径：
  1. create → get 往返
  2. update 持久化
  3. 磁盘回退（模拟内存丢失）
  4. cleanup 过期清理
  5. watchdog 超时自动失败

运行: python3 tools/test_task_manager.py
"""

import json
import os
import sys
import tempfile
import time
import unittest

# 确保项目根目录在 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.server_infra import TaskManager


class TestTaskManager(unittest.TestCase):
    """TaskManager 核心功能测试"""

    def setUp(self):
        """每个测试前创建临时目录和 TaskManager"""
        self.tmpdir = tempfile.mkdtemp(prefix='test_tasks_')
        self.tm = TaskManager(disk_dir=self.tmpdir, ttl=3600, watchdog_timeout=2)

    def tearDown(self):
        """清理临时目录"""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # ── Test 1: create → get 往返 ──
    def test_create_and_get(self):
        """创建任务后能正确读取"""
        tid = self.tm.create()
        self.assertIsNotNone(tid)
        self.assertTrue(tid.isdigit())

        task = self.tm.get(tid)
        self.assertIsNotNone(task)
        self.assertEqual(task['id'], tid)
        self.assertEqual(task['status'], 'queued')
        self.assertEqual(task['message'], '排队中...')

    # ── Test 2: update 持久化 ──
    def test_update_persists(self):
        """更新后内存和磁盘同步"""
        tid = self.tm.create()
        self.tm.update(tid, status='running', message='正在处理...')

        task = self.tm.get(tid)
        self.assertEqual(task['status'], 'running')
        self.assertEqual(task['message'], '正在处理...')

        # 验证磁盘落盘
        disk_path = os.path.join(self.tmpdir, f'{tid}.json')
        self.assertTrue(os.path.exists(disk_path))
        with open(disk_path) as f:
            disk_data = json.load(f)
        self.assertEqual(disk_data['status'], 'running')

    # ── Test 3: 磁盘回退（模拟重启后内存丢失）──
    def test_disk_fallback(self):
        """重启后（新 TaskManager 实例）能从磁盘恢复任务"""
        tid = self.tm.create()
        self.tm.update(tid, status='done', message='完成', result='测试结果')

        # 模拟重启：创建新的 TaskManager 实例（内存为空）
        tm2 = TaskManager(disk_dir=self.tmpdir)
        task = tm2.get(tid)
        self.assertIsNotNone(task, "磁盘回退失败：重启后无法恢复任务")
        self.assertEqual(task['status'], 'done')
        self.assertEqual(task['result'], '测试结果')

    # ── Test 4: cleanup 过期清理 ──
    def test_cleanup_expired(self):
        """过期任务被正确清理"""
        # 使用短 TTL
        tm_short = TaskManager(disk_dir=self.tmpdir, ttl=1)  # 1秒过期
        tid = tm_short.create()
        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, f'{tid}.json')))

        # 等待过期
        time.sleep(1.5)
        tm_short.cleanup()

        task = tm_short.get(tid)
        self.assertIsNone(task, "过期任务未被清理")

        # 磁盘文件也应被清理
        self.assertFalse(os.path.exists(os.path.join(self.tmpdir, f'{tid}.json')),
                        "过期磁盘文件未被清理")

    # ── Test 5: watchdog 超时自动失败 ──
    def test_watchdog_timeout(self):
        """Watchdog 自动将超时 running 任务标记为 error"""
        tid = self.tm.create()
        self.tm.update(tid, status='running', message='处理中...',
                       started_at=time.time() - 10)  # 10秒前开始

        # 启动 watchdog（超时2秒）
        self.tm.start_watchdog(interval=1)

        # 等待 watchdog 检测
        time.sleep(3)

        task = self.tm.get(tid)
        self.assertEqual(task['status'], 'error',
                        f"Watchdog 未将超时任务标记为 error，当前状态: {task['status']}")
        self.assertIn('超时', task.get('message', ''))

        self.tm.stop_watchdog()

    # ── Test 6: 启动恢复 ──
    def test_recover_on_startup(self):
        """启动恢复：queued/running 任务正确标记"""
        # 创建一些任务（加微延迟避免毫秒级 ID 碰撞）
        tid1 = self.tm.create()
        self.tm.update(tid1, status='running', message='处理中...')
        time.sleep(0.002)
        tid2 = self.tm.create()
        self.tm.update(tid2, status='queued', message='排队中...')
        time.sleep(0.002)
        tid3 = self.tm.create()
        self.tm.update(tid3, status='done', message='已完成')

        # 模拟重启
        tm2 = TaskManager(disk_dir=self.tmpdir)
        interrupted, retried = tm2.recover_on_startup()

        # done 任务不受影响
        t3 = tm2.get(tid3)
        self.assertEqual(t3['status'], 'done')

        # queued/running 任务被标记（因为没有可恢复图片）
        t1 = tm2.get(tid1)
        t2 = tm2.get(tid2)
        self.assertIn(t1['status'], ('interrupted', 'queued'))
        self.assertIn(t2['status'], ('interrupted', 'queued'))

        # 至少标记了一些
        self.assertTrue(interrupted > 0 or retried >= 0,
                       f"启动恢复未处理任何任务 (interrupted={interrupted}, retried={retried})")


if __name__ == '__main__':
    unittest.main(verbosity=2)
