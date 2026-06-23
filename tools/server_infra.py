#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fashion 穿搭助手 — 基础设施层
- TaskManager: 线程安全任务状态追踪（内存 + 磁盘写穿 + watchdog）
- 日志系统
- 线程安全装饰器
- 全局异常钩子
- 信号处理（优雅关闭）
- 共享状态管理（线程安全）
"""

import json
import os
import signal
import sys
import threading
import time
import traceback as _tb_module

# ── 路径常量 ──
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(_BASE_DIR)
LOG_FILE = os.path.join(PROJECT_DIR, 'tools', 'wechat_control.log')

# ── 进程启动时间 ──
_server_start_time = time.time()


def get_uptime_seconds():
    return int(time.time() - _server_start_time)


# ═══════════════════════════════════════════════════════════
# 日志
# ═══════════════════════════════════════════════════════════

def log(msg, level='INFO'):
    """线程安全写日志到文件 + stdout"""
    ts = time.strftime('%H:%M:%S')
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, 'a') as f:
            f.write(line + '\n')
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════
# 全局异常钩子：守护线程崩溃不静默消失
# ═══════════════════════════════════════════════════════════

_original_excepthook = sys.excepthook


def _global_excepthook(exc_type, exc_value, exc_tb):
    """捕获所有线程中的未处理异常，写日志 + stderr"""
    err = ''.join(_tb_module.format_exception(exc_type, exc_value, exc_tb))
    try:
        log(f"未捕获异常: {err}", "CRITICAL")
    except Exception:
        pass
    sys.stderr.write(f"[CRASH] {time.strftime('%Y-%m-%d %H:%M:%S')} {err}\n")
    sys.stderr.flush()
    _original_excepthook(exc_type, exc_value, exc_tb)


def install_excepthook():
    """安装全局异常钩子（应在模块导入后立即调用）"""
    sys.excepthook = _global_excepthook


# ═══════════════════════════════════════════════════════════
# 线程安全装饰器
# ═══════════════════════════════════════════════════════════

def safe_daemon(name, task_manager=None):
    """装饰器：包裹守护线程目标，自动捕获异常并标记关联任务为 error

    Args:
        name: 线程名称（用于日志）
        task_manager: TaskManager 实例（可选，用于标记任务状态）
    """
    def decorator(fn):
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                err = _tb_module.format_exc()
                log(f"后台线程 [{name}] 崩溃: {err}", "CRITICAL")
                # 尝试标记关联任务为 error（首个参数通常是 task_id）
                tm = task_manager
                if tm and args and isinstance(args[0], str) and len(args[0]) >= 13:
                    # task_id 格式: 13位时间戳 或 13位时间戳_N
                    try:
                        tm.update(args[0], status='error',
                                  message=f'后台任务崩溃: {str(e)[:100]}')
                    except Exception:
                        pass
        return wrapper
    return decorator


# ═══════════════════════════════════════════════════════════
# 共享状态（线程安全）
# ═══════════════════════════════════════════════════════════

class SharedState:
    """线程安全的全局共享状态管理器。

    所有对 _pipeline_running 和 _pipeline_status 的读写都走同一个锁，
    防止竞态条件导致的状态不一致。
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._pipeline_running = False
        self._pipeline_status = {
            'last_run': None,
            'last_error': None,
            'total_runs': 0
        }
        self._proto_rebuild_lock = threading.Lock()

    # ── pipeline_running ──
    @property
    def pipeline_running(self):
        with self._lock:
            return self._pipeline_running

    def try_start_pipeline(self):
        """尝试获取管线执行权。返回 True 表示可以开始，False 表示已在运行。"""
        with self._lock:
            if self._pipeline_running:
                return False
            self._pipeline_running = True
            return True

    def end_pipeline(self):
        """释放管线执行权。"""
        with self._lock:
            self._pipeline_running = False

    # ── pipeline_status ──
    def update_pipeline_status(self, **kwargs):
        """线程安全更新管线状态。"""
        with self._lock:
            self._pipeline_status.update(kwargs)

    def get_pipeline_status(self):
        """线程安全读取管线状态（返回副本）。"""
        with self._lock:
            return dict(self._pipeline_status)

    # ── proto_rebuild_lock ──
    @property
    def proto_rebuild_lock(self):
        return self._proto_rebuild_lock


# 全局共享状态实例
state = SharedState()


# ═══════════════════════════════════════════════════════════
# TaskManager — 线程安全任务状态追踪
# ═══════════════════════════════════════════════════════════

class TaskManager:
    """线程安全的任务状态追踪（内存 + 磁盘写穿，重启不丢）。

    特性:
    - write-through: create/update 同时写入内存和磁盘
    - disk fallback: get() 内存未命中时自动读取磁盘
    - watchdog: 后台线程自动将超时 running 任务标记为 error
    - cleanup: 定期清理过期任务（内存 + 磁盘）
    """

    def __init__(self, disk_dir=None, ttl=3600, watchdog_timeout=300):
        self._tasks = {}
        self._lock = threading.Lock()
        self._ttl = ttl
        self._watchdog_timeout = watchdog_timeout
        self._disk_dir = disk_dir or os.path.join(PROJECT_DIR, 'outfits', '_tasks')
        self._watchdog_thread = None
        self._watchdog_stop = threading.Event()
        os.makedirs(self._disk_dir, exist_ok=True)

    # ── 磁盘 I/O ──
    def _write_disk(self, tid):
        """写穿磁盘：内存任务 → outfits/_tasks/{tid}.json"""
        try:
            t = self._tasks.get(tid)
            if t:
                disk_path = os.path.join(self._disk_dir, f'{tid}.json')
                with open(disk_path, 'w') as tf:
                    json.dump(t, tf, ensure_ascii=False, indent=2)
        except Exception:
            pass  # 磁盘写入失败不影响内存运行

    # ── CRUD ──
    def create(self):
        """创建新任务，返回 task_id（保证唯一，即使同毫秒内多次调用）"""
        base = str(int(time.time() * 1000))
        with self._lock:
            # 防止同毫秒内多次调用产生 ID 碰撞
            tid = base
            seq = 0
            while tid in self._tasks:
                seq += 1
                tid = f'{base}_{seq}'
            self._tasks[tid] = {
                'id': tid,
                'status': 'queued',
                'message': '排队中...',
                'result': '',
                'image_path': '',
                'image_url': '',
                'log': '',
                'created_at': time.time()
            }
        self._write_disk(tid)
        return tid

    def update(self, tid, **kwargs):
        """更新任务状态（自动落盘）"""
        with self._lock:
            if tid in self._tasks:
                self._tasks[tid].update(kwargs)
            else:
                # 从磁盘恢复后再更新
                disk_path = os.path.join(self._disk_dir, f'{tid}.json')
                if os.path.exists(disk_path):
                    try:
                        with open(disk_path, 'r') as tf:
                            t = json.load(tf)
                        t.update(kwargs)
                        self._tasks[tid] = t
                    except Exception:
                        return
                else:
                    return
        self._write_disk(tid)

    def get(self, tid, allow_disk_fallback=True):
        """获取任务状态。内存 miss → 磁盘回退。"""
        with self._lock:
            task = self._tasks.get(tid)
            if task:
                return dict(task)
        # 磁盘回退
        if allow_disk_fallback:
            disk_path = os.path.join(self._disk_dir, f'{tid}.json')
            if os.path.exists(disk_path):
                try:
                    with open(disk_path, 'r') as tf:
                        return json.load(tf)
                except Exception:
                    pass
        return None

    def get_active_count(self):
        """返回当前活跃任务数（queued + running）"""
        with self._lock:
            return sum(1 for t in self._tasks.values()
                      if t.get('status') in ('queued', 'running'))

    # ── 清理 ──
    def cleanup(self):
        """清理过期任务（内存 + 磁盘）"""
        now = time.time()
        with self._lock:
            expired = [tid for tid, t in self._tasks.items()
                      if now - t.get('created_at', now) > self._ttl]
            for tid in expired:
                del self._tasks[tid]
        # 同步清理过期磁盘文件
        try:
            if os.path.isdir(self._disk_dir):
                for fn in os.listdir(self._disk_dir):
                    if not fn.endswith('.json'):
                        continue
                    fpath = os.path.join(self._disk_dir, fn)
                    if now - os.path.getmtime(fpath) > self._ttl:
                        try:
                            os.remove(fpath)
                        except OSError:
                            pass
        except Exception:
            pass

    # ── Watchdog（任务超时自动失败）──
    def start_watchdog(self, interval=30):
        """启动 watchdog 后台线程。

        每 interval 秒扫描一次，将 running 超过 watchdog_timeout 秒的任务
        自动标记为 error，防止任务永远卡在 running 状态。
        """
        if self._watchdog_thread is not None:
            return  # 已经启动

        tm = self  # 闭包引用

        def _watchdog_loop():
            log(f"🔄 Watchdog 已启动（超时={self._watchdog_timeout}s，间隔={interval}s）")
            while not self._watchdog_stop.is_set():
                self._watchdog_stop.wait(interval)
                if self._watchdog_stop.is_set():
                    break
                now = time.time()
                with self._lock:
                    for tid, t in list(self._tasks.items()):
                        if t.get('status') == 'running':
                            started = t.get('started_at', t.get('created_at', now))
                            elapsed = now - started
                            if elapsed > self._watchdog_timeout:
                                t['status'] = 'error'
                                t['message'] = f'任务超时（运行 {int(elapsed)}s > {self._watchdog_timeout}s）'
                                tm._write_disk(tid)
                                log(f"⏰ Watchdog: 任务 {tid} 超时自动标记为 error（{int(elapsed)}s）")
            log("Watchdog 已停止")

        self._watchdog_thread = threading.Thread(target=_watchdog_loop, daemon=True)
        self._watchdog_thread.start()

    def stop_watchdog(self):
        """停止 watchdog 线程"""
        self._watchdog_stop.set()

    # ── 启动恢复 ──
    def recover_on_startup(self):
        """启动时扫描磁盘任务，标记中断并尝试自动重试分析任务。

        Returns:
            (interrupted_count, retried_count, retry_queue):
            - interrupted_count: 无可恢复数据的中断任务数
            - retried_count: 找到可恢复图片、已重新排队的任务数
            - retry_queue: [(tid, uid, image_paths), ...] 可直接提交重试
        """
        interrupted = 0
        retried = 0
        retry_queue = []  # [(tid, uid, image_paths), ...]

        if not os.path.isdir(self._disk_dir):
            return 0, 0, []

        for fn in os.listdir(self._disk_dir):
            if not fn.endswith('.json'):
                continue
            fpath = os.path.join(self._disk_dir, fn)
            try:
                with open(fpath, 'r') as tf:
                    t = json.load(tf)
            except Exception:
                continue

            status = t.get('status', '')
            if status not in ('queued', 'running', ''):
                continue

            tid = t.get('id', fn.replace('.json', ''))

            # 检查是否有可恢复的分析图片
            can_retry = False
            incoming_dirs = []
            for uid_dir in ['wardrobe/_incoming']:
                d = os.path.join(PROJECT_DIR, uid_dir)
                if os.path.isdir(d):
                    incoming_dirs.append(d)
            # 也检查用户目录
            users_dir = os.path.join(PROJECT_DIR, 'users')
            if os.path.isdir(users_dir):
                for ud in os.listdir(users_dir):
                    inc = os.path.join(users_dir, ud, 'wardrobe', '_incoming')
                    if os.path.isdir(inc):
                        incoming_dirs.append(inc)

            for inc_dir in incoming_dirs:
                img_pattern = f'img_{tid}_'
                matches = [f for f in os.listdir(inc_dir) if f.startswith(img_pattern)]
                if matches:
                    can_retry = True
                    img_paths = [os.path.join(inc_dir, m) for m in sorted(matches)]
                    uid = t.get('_user_id', 'default')
                    # 将图片路径写入任务，供重试使用
                    t['_retry_image_dir'] = inc_dir
                    t['_retry_images'] = img_paths
                    retry_queue.append((tid, uid, img_paths))
                    break

            if can_retry:
                t['status'] = 'queued'
                t['message'] = '服务已恢复，自动重新排队'
                retried += 1
            else:
                t['status'] = 'interrupted'
                t['message'] = '服务已重启，任务中断（无可恢复数据）'
                interrupted += 1

            # 写回磁盘
            try:
                with open(fpath, 'w') as tf:
                    json.dump(t, tf, ensure_ascii=False, indent=2)
            except Exception:
                pass

        if interrupted or retried:
            log(f"♻️ 启动恢复: {interrupted} 个中断, {retried} 个自动重试")

        return interrupted, retried, retry_queue


# ═══════════════════════════════════════════════════════════
# 信号处理（优雅关闭）
# ═══════════════════════════════════════════════════════════

def setup_signal_handlers(http_server, task_manager, shutdown_event,
                         graceful_timeout=15):
    """注册 SIGTERM/SIGHUP/SIGINT 处理器，实现优雅关闭。

    关闭流程:
    1. 停止接受新连接（server.shutdown()）
    2. 将所有 in-flight 任务标记为 interrupted（落盘）
    3. 等待活跃任务完成（最多 graceful_timeout 秒）
    4. 清理资源

    Args:
        http_server: ThreadingHTTPServer 实例
        task_manager: TaskManager 实例
        shutdown_event: threading.Event，通知主循环退出
        graceful_timeout: 等待活跃任务完成的最大秒数
    """

    def _handle_signal(signum, frame):
        sig_name = {signal.SIGTERM: 'SIGTERM', signal.SIGHUP: 'SIGHUP',
                    signal.SIGINT: 'SIGINT'}.get(signum, str(signum))
        log(f"收到信号 {sig_name}，优雅关闭中...")

        # Step 1: 停止 watchdog
        task_manager.stop_watchdog()

        # Step 2: 将进行中的任务标记为 interrupted（落盘）
        with task_manager._lock:
            for tid, tsk in list(task_manager._tasks.items()):
                if tsk.get('status') in ('queued', 'running'):
                    task_manager.update(tid, status='interrupted',
                                       message=f'服务重启中 (signal {sig_name})')

        # Step 3: 等待活跃任务完成（最多 graceful_timeout 秒）
        waited = 0
        while waited < graceful_timeout:
            active = task_manager.get_active_count()
            if active == 0:
                log(f"所有任务已结束（等待 {waited}s）")
                break
            time.sleep(0.5)
            waited += 0.5
        else:
            log(f"⚠️ 等待超时（{graceful_timeout}s），仍有 {task_manager.get_active_count()} 个活跃任务，强制关闭")

        # Step 4: 停止 HTTP 服务器
        shutdown_event.set()
        http_server.shutdown()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGHUP, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    log("🛡️ 信号处理已注册 (SIGTERM/SIGHUP/SIGINT → 优雅关闭)")


# ═══════════════════════════════════════════════════════════
# 健康检查数据收集
# ═══════════════════════════════════════════════════════════

def collect_health_data(task_manager, outfits_base=None):
    """收集系统健康数据（供 /health 端点使用）。

    Returns:
        dict: 健康数据字典
    """
    import resource as _resource

    today_str = time.strftime('%Y-%m-%d')
    today_ok = False

    if outfits_base and os.path.isdir(outfits_base):
        for d in sorted(os.listdir(outfits_base), reverse=True):
            if d.startswith(today_str):
                md = os.path.join(outfits_base, d, 'outfit.md')
                if os.path.exists(md) and os.path.getsize(md) > 50:
                    today_ok = True
                break

    # 系统资源
    mem_bytes = _resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss
    mem_mb = round(mem_bytes / (1024 * 1024), 1)
    disk_stat = os.statvfs(PROJECT_DIR)
    disk_free_gb = round((disk_stat.f_bavail * disk_stat.f_frsize) / (1024**3), 1)

    active_tasks = task_manager.get_active_count() if task_manager else 0
    uptime_seconds = get_uptime_seconds()

    # 检查 Tailscale Funnel 状态
    funnel_active = False
    try:
        import subprocess as _sp
        result = _sp.run(['tailscale', 'funnel', 'status'],
                        capture_output=True, text=True, timeout=5)
        if 'Funnel on' in (result.stdout or '') and ('http://localhost:' in (result.stdout or '') or 'http://127.0.0.1:' in (result.stdout or '')):
            funnel_active = True
    except Exception:
        pass

    pipeline_status = state.get_pipeline_status()

    return {
        "status": "ok",
        "service": "Fashion 穿搭助手",
        "time": time.strftime("%H:%M:%S"),
        "uptime_seconds": uptime_seconds,
        "memory_mb": mem_mb,
        "disk_free_gb": disk_free_gb,
        "active_tasks": active_tasks,
        "today_ok": today_ok,
        "running": state.pipeline_running,
        "funnel_active": funnel_active,
        "latest_date": (today_str if today_ok else
                       (pipeline_status.get('last_run', '')[:10]
                        if pipeline_status.get('last_run') else None))
    }
