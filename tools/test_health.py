#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
/health 端点 Smoke Test

验证：
  1. 基础设施模块可直接导入（无循环依赖）
  2. SharedState 线程安全
  3. collect_health_data 返回结构完整
  4. TaskManager 实例可正常创建

运行: python3 tools/test_health.py
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestInfraModule(unittest.TestCase):
    """基础设施模块导入和基本功能测试"""

    def test_import_server_infra(self):
        """server_infra 模块可正常导入（无循环依赖）"""
        from tools.server_infra import (
            log, safe_daemon, install_excepthook,
            TaskManager, SharedState, state,
            setup_signal_handlers, collect_health_data,
            PROJECT_DIR, LOG_FILE,
        )
        self.assertTrue(PROJECT_DIR.endswith('Fashion'))
        self.assertTrue(LOG_FILE.endswith('wechat_control.log'))

    def test_shared_state_thread_safety(self):
        """SharedState 基本线程安全操作"""
        from tools.server_infra import SharedState
        s = SharedState()

        # 初始状态
        self.assertFalse(s.pipeline_running)

        # try_start / end
        self.assertTrue(s.try_start_pipeline())
        self.assertTrue(s.pipeline_running)
        self.assertFalse(s.try_start_pipeline())  # 已运行，拒绝
        s.end_pipeline()
        self.assertFalse(s.pipeline_running)

        # pipeline_status
        s.update_pipeline_status(last_run='2026-06-23T12:00:00', total_runs=5)
        st = s.get_pipeline_status()
        self.assertEqual(st['last_run'], '2026-06-23T12:00:00')
        self.assertEqual(st['total_runs'], 5)

        # proto_rebuild_lock 可获取
        lock = s.proto_rebuild_lock
        self.assertTrue(lock.acquire(blocking=False))
        lock.release()

    def test_collect_health_data_structure(self):
        """collect_health_data 返回完整结构"""
        from tools.server_infra import TaskManager, collect_health_data
        tm = TaskManager()
        health = collect_health_data(tm)

        required_fields = [
            'status', 'service', 'time', 'uptime_seconds',
            'memory_mb', 'disk_free_gb', 'active_tasks',
            'today_ok', 'running', 'funnel_active', 'latest_date'
        ]
        for field in required_fields:
            self.assertIn(field, health, f"health 缺少字段: {field}")

        self.assertEqual(health['status'], 'ok')
        self.assertIsInstance(health['uptime_seconds'], int)
        self.assertIsInstance(health['memory_mb'], float)
        self.assertIsInstance(health['disk_free_gb'], float)
        self.assertIsInstance(health['active_tasks'], int)
        self.assertIsInstance(health['funnel_active'], bool)

    def test_task_manager_singleton(self):
        """多个 TaskManager 实例互不干扰"""
        import time
        from tools.server_infra import TaskManager
        tm1 = TaskManager()
        tm2 = TaskManager()

        tid1 = tm1.create()
        time.sleep(0.002)  # 避免毫秒级 ID 碰撞
        tid2 = tm2.create()

        self.assertNotEqual(tid1, tid2)
        self.assertIsNotNone(tm1.get(tid1))
        self.assertIsNotNone(tm2.get(tid2))
        # tm1 不应看到 tm2 的任务
        self.assertIsNone(tm1.get(tid2, allow_disk_fallback=False))


if __name__ == '__main__':
    unittest.main(verbosity=2)
