import os
import sys
import time
import random
import asyncio
import threading
import re
import json
import requests
import shutil
import winreg
from concurrent.futures import ThreadPoolExecutor
from playwright.async_api import async_playwright

# ================= 终端颜色配置 =================
class Colors:
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREY = "\033[90m"

def cprint(msg, level="info"):
    """默认的 CLI 日志回调"""
    ts = time.strftime('%H:%M:%S')
    if level == "info": color = Colors.BLUE
    elif level == "success": color = Colors.GREEN
    elif level == "warning": color = Colors.YELLOW
    elif level == "danger": color = Colors.RED
    elif level == "secondary": color = Colors.GREY
    else: color = Colors.RESET
    print(f"{Colors.GREY}[{ts}]{Colors.RESET} {color}{msg}{Colors.RESET}")

# ================= 浏览器路径自动寻找工具 =================
def find_system_browser(browser_type="edge"):
    browser_type = browser_type.lower()
    reg_key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe" if browser_type == "edge" else r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_key) as key:
            exe_path, _ = winreg.QueryValueEx(key, "")
            if os.path.exists(exe_path): return exe_path
    except:
        pass
    which_path = shutil.which(browser_type)
    if which_path: return which_path
    
    edge_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.expanduser(r"~\AppData\Local\Microsoft\Edge\Application\msedge.exe"),
    ]
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
    ]
    target_paths = edge_paths if browser_type == "edge" else chrome_paths
    for path in target_paths:
        if os.path.exists(path): return path
    return None

# ================= 配置文件管理 =================
class ConfigManager:
    def __init__(self):
        self.config_file = "spider_config.json"
        self.default_config = {
            "save_path": os.path.join(os.getcwd(), "Download"), 
            "concurrency": 3,
            "download_threads": 16,
            "max_scrolls": 1000,
            "stop_thresh": 300,      # 旧图阈值默认 300
            "max_video_size": 5,
            "dl_images": True,
            "dl_gifs": True,
            "browser_type": "Edge",
            "create_link_file": True,
            "custom_likes_id": "",
            "deep_scan": False,
            "headless": False,
            "theme": "system",        # UI 主题: system, light, dark
            "timeout": 60,          # 超时时间(秒)
            "use_tmp_files": True   # 是否使用临时文件下载
        }
        self.data = self.load()

    def load(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "auto_phoenix_restart" in data: del data["auto_phoenix_restart"]
                    # 补全可能缺失的配置
                    if "stop_thresh" not in data: data["stop_thresh"] = 300
                    if "timeout" not in data: data["timeout"] = 60
                    if "use_tmp_files" not in data: data["use_tmp_files"] = True
                    if "create_link_file" not in data: data["create_link_file"] = True
                    return {**self.default_config, **data}
            except:
                return self.default_config
        return self.default_config

    def save(self):
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Config Save Error: {e}")

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value):
        self.data[key] = value
        self.save()

CFG = ConfigManager()

# ================= 高性能异步并发下载管理器 (支持毫秒级中断 + 尸体清理) =================
class DownloadManager:
    def __init__(self, callbacks=None, max_threads=16):
        self.queue = asyncio.Queue()
        self.executor = ThreadPoolExecutor(max_workers=max_threads)
        self.active_task_ids = set()
        self.session_counters = {}
        self.pending_tasks_map = {}
        self.is_running = False
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        self.active_workers = []
        self.cbs = callbacks if callbacks else {}

    def _emit_log(self, msg, level="info"):
        if 'on_log' in self.cbs and self.cbs['on_log']:
            self.cbs['on_log'](msg, level)
        else:
            cprint(msg, level)

    async def start_workers(self, count=10):
        self.is_running = True
        self.active_workers = [asyncio.create_task(self._worker_logic()) for _ in range(count)]
        self._emit_log(f"🚀 下载调度中枢已就位 (下载线程: {self.executor._max_workers})", "info")

    async def stop_workers(self):
        self.is_running = False
        for _ in range(len(self.active_workers)):
            await self.queue.put(None)
        if self.active_workers:
            await asyncio.gather(*self.active_workers, return_exceptions=True)
        self.active_workers = []

    def register_task(self, tid):
        self.active_task_ids.add(tid)
        if tid not in self.session_counters: self.session_counters[tid] = 0
        if tid not in self.pending_tasks_map: self.pending_tasks_map[tid] = 0

    def deregister_task(self, tid):
        self.active_task_ids.discard(tid)
        self.pending_tasks_map[tid] = 0

    def get_pending_count(self, tid):
        return self.pending_tasks_map.get(tid, 0)

    async def submit_job(self, url, path, tid, label, f_type, clean_url, tweet_url):
        if tid not in self.active_task_ids: return
        self.pending_tasks_map[tid] = self.pending_tasks_map.get(tid, 0) + 1
        await self.queue.put({
            'url': url, 'path': path, 'tid': tid,
            'label': label, 'type': f_type,
            'clean_url': clean_url, 
            'tweet_url': tweet_url,
            'retry': 0
        })

    async def _worker_logic(self):
        while True:
            try:
                if not self.is_running and self.queue.empty(): break
                
                try:
                    item = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    if not self.is_running: break
                    continue

                if item is None:
                    self.queue.task_done()
                    break

                tid = item['tid']
                if not self.is_running or tid not in self.active_task_ids:
                    self.pending_tasks_map[tid] = max(0, self.pending_tasks_map.get(tid, 0) - 1)
                    self.queue.task_done()
                    continue

                if item['type'] == 'vid':
                    try:
                        loop = asyncio.get_event_loop()
                        timeout = int(CFG.get('timeout'))
                        res = await loop.run_in_executor(self.executor, lambda: self.session.head(item['url'], timeout=timeout))
                        content_size = int(res.headers.get('Content-Length', 0))
                        limit_mb = float(CFG.get('max_video_size'))
                        if limit_mb > 0:
                            limit_bytes = limit_mb * 1024 * 1024
                            if content_size > limit_bytes: 
                                self.pending_tasks_map[tid] = max(0, self.pending_tasks_map.get(tid, 0) - 1)
                                self.queue.task_done()
                                continue
                    except:
                        self.pending_tasks_map[tid] = max(0, self.pending_tasks_map.get(tid, 0) - 1)
                        self.queue.task_done()
                        continue

                path = item['path']
                if os.path.exists(path) and os.path.getsize(path) > 1024:
                    self.pending_tasks_map[tid] = max(0, self.pending_tasks_map.get(tid, 0) - 1)
                    self.queue.task_done()
                    continue

                try:
                    loop = asyncio.get_event_loop()
                    success = await loop.run_in_executor(self.executor, self._sync_download, item['url'], path, tid)
                    if success:
                        self._record_history(item['clean_url'], tid, item.get('tweet_url'))
                        self.session_counters[tid] = self.session_counters.get(tid, 0) + 1
                        if 'on_progress' in self.cbs and self.cbs['on_progress']:
                            self.cbs['on_progress'](tid, self.session_counters[tid])
                    elif item['retry'] < 2 and self.is_running and tid in self.active_task_ids:
                        item['retry'] += 1
                        await self.queue.put(item)
                        continue
                except Exception:
                    pass
                finally:
                    self.pending_tasks_map[tid] = max(0, self.pending_tasks_map.get(tid, 0) - 1)
                    self.queue.task_done()
            except Exception:
                pass

    def _sync_download(self, url, path, tid):
        use_tmp = CFG.get("use_tmp_files")
        download_target = path + ".tmp" if use_tmp else path
        timeout = int(CFG.get('timeout'))
        
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with self.session.get(url, timeout=timeout, stream=True) as r:
                if r.status_code == 200:
                    with open(download_target, "wb") as f:
                        for chunk in r.iter_content(chunk_size=16384):
                            if not self.is_running or tid not in self.active_task_ids:
                                f.close()
                                r.close()
                                if os.path.exists(download_target):
                                    try: os.remove(download_target)
                                    except: pass
                                return False
                            if chunk: f.write(chunk)
                    
                    if use_tmp and os.path.exists(download_target):
                        if os.path.exists(path):
                            try: os.remove(path)
                            except: pass
                        # 尝试移动文件（带重试机制以应对杀毒软件锁定）
                        move_success = False
                        for _ in range(3):
                            try:
                                shutil.move(download_target, path)
                                move_success = True
                                break
                            except Exception:
                                import time
                                time.sleep(0.5)
                        
                        if not move_success:
                             # 如果最终移动失败，手动抛出异常以触发外部清理逻辑
                             raise Exception("File move failed after retries")
                    return True
            return False
        except:
            if os.path.exists(download_target):
                try: os.remove(download_target)
                except: pass
            return False

    def _record_history(self, url, tid, tweet_url=None):
        root = CFG.get('save_path')
        if not root: return
        p = os.path.join(root, "我的喜欢" if tid == "MY_LIKES" else "我的书签" if tid == "MY_BOOKMARKS" else f"博主图集/{tid}")
        try:
            os.makedirs(p, exist_ok=True)
            raw_fname = url.split('/')[-1].split('?')[0]
            f_id = raw_fname.rsplit(".", 1)[0] if "." in raw_fname else raw_fname
            with open(os.path.join(p, "history.txt"), "a", encoding="utf-8") as f:
                f.write(f_id + "\n")
            if CFG.get("create_link_file") and tweet_url:
                with open(os.path.join(p, "link.txt"), "a", encoding="utf-8") as f:
                    f.write(f"{tweet_url}\t{f_id}\n")
        except: pass

# ================= 核心爬虫引擎 =================
class CrawlerEngine:
    def __init__(self, callbacks=None):
        self.loop = None
        self.pw_instance = None
        self.browser_context = None
        self.queue = asyncio.Queue()
        self.running_tasks = {}
        self.semaphore = None
        self.is_running = False
        self.manual_shutdown = False
        self.engine_ready_event = asyncio.Event()
        self.is_ctx_alive = False
        self.cbs = callbacks if callbacks else {}
        self.dl_manager = DownloadManager(callbacks)
        # 暂停状态管理
        self.paused_tasks = set()  # 暂停的任务 ID
        self.suspended_tasks = {}  # 挂起的任务（释放了槽位，等待恢复）
        self.global_paused = False
        self.completed_tasks = []  # 本次启动完成的任务
        self.failed_tasks = {}     # 失败的任务 {tid: error_msg}
        self.transitioning_tasks = {} # 正在等待信号量的任务 {tid: launcher_task}
        self.tid_to_page = {}      # 任务 ID 到 Page 对象的映射，防止幽灵页面

    def _emit_log(self, msg, level="info"):
        """推送日志到前端"""
        if 'on_log' in self.cbs and self.cbs['on_log']:
            self.cbs['on_log'](msg, level)
        else:
            cprint(msg, level)

    def _broadcast_status(self):
        """主动推送最新状态到前端"""
        if 'on_task_update' in self.cbs and self.cbs['on_task_update']:
            try:
                self.cbs['on_task_update'](self.get_queue_status())
            except: pass

    def start(self):
        if self.is_running: return
        self.is_running = True
        self.manual_shutdown = False
        threading.Thread(target=self._run_loop, daemon=True).start()

    def add_task_to_queue(self, tid):
        if self.is_running and self.loop:
            # 查重：如果在运行中、挂起中或已在队列中，则拒绝
            if tid in self.running_tasks or tid in self.suspended_tasks or tid in self.paused_tasks:
                self._emit_log(f"⚠️ 任务 [{tid}] 已经在处理中，请勿重复添加", "warning")
                return False
                
            # 检查队列内部
            queue_items = []
            try:
                queue_items = list(self.queue._queue)
            except: pass
            if tid in queue_items:
                self._emit_log(f"⚠️ 任务 [{tid}] 已在排队，请勿重复添加", "warning")
                return False

            self.loop.call_soon_threadsafe(self.queue.put_nowait, tid)
            # 添加到队列时，清除错误状态
            self.failed_tasks.pop(tid, None)
            self._emit_log(f"➕ 任务 [{tid}] 已添加至队列", "info")
            return True
        else:
            self._emit_log("⚠️ 引擎尚未就绪", "warning")
            return False

    def stop(self):
        self.manual_shutdown = True
        self.is_running = False
        if self.loop:
             asyncio.run_coroutine_threadsafe(self._shutdown_sequence(), self.loop)

    def _run_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._engine_lifecycle())

    async def _engine_lifecycle(self):
        self._emit_log(f"🚀 初始化核心 (页面并发: {int(CFG.get('concurrency'))})", "info")
        
        dl_threads = int(CFG.get('download_threads'))
        self.dl_manager = DownloadManager(self.cbs, max_threads=dl_threads)
        await self.dl_manager.start_workers(count=12)
        
        self.semaphore = asyncio.Semaphore(int(CFG.get('concurrency')))

        await self._launch_context()
        if not self.browser_context: 
            self.is_running = False
            return

        self._emit_log("✅ 物理链路开启，环境预热中...", "success")
        if CFG.get("deep_scan"):
             self._emit_log("⛏️ 注意：穿透模式 (Deep Scan) 已开启，将强制扫描至底部", "warning")

        await asyncio.sleep(3)
        self.engine_ready_event.set()

        scheduler_task = asyncio.create_task(self._task_dispatcher())

        self.is_ctx_alive = True
        def on_close(_): 
            if self.is_running and not self.manual_shutdown:
                self._emit_log("⚠️ 浏览器已关闭，引擎停止。", "warning")
            self.is_ctx_alive = False
            self.is_running = False

        self.browser_context.on("close", on_close)

        while self.is_running and self.is_ctx_alive:
            if not self.browser_context.pages: await self.browser_context.new_page()
            await asyncio.sleep(2)

        if scheduler_task: scheduler_task.cancel()
        self.engine_ready_event.clear()
        
        await self._shutdown_sequence()

    async def _launch_context(self):
        # 严格检查复用条件：变量存在 且 仍在连接中
        if self.browser_context and self.pw_instance:
            try:
                # 尝试访问属性，如果已经断开会抛异常或返回 False
                if self.browser_context.browser and self.browser_context.browser.is_connected():
                    self._emit_log("🔗 正在连通已有的浏览器实例", "success")
                    return self.browser_context
            except:
                pass
            
            # 如果走到这里，说明注入的实例已失效，需要重置
            self._emit_log("⚠️ 浏览器实例已丢失，正在重新初始化...", "warning")
            self.browser_context = None

        user_data_path = os.path.abspath("my_browser_data")
        bt = CFG.get("browser_type")
        exe = find_system_browser(bt)
        if not exe:
            self._emit_log(f"❌ 寻址失败: 未找到 {bt} 内核路径", "danger")
            return None
        
        is_headless = CFG.get("headless")
        timeout = int(CFG.get("timeout")) * 1000 # Playwright 使用毫秒

        if not self.pw_instance:
            self.pw_instance = await async_playwright().start()
            
        self.browser_context = await self.pw_instance.chromium.launch_persistent_context(
            user_data_dir=user_data_path, executable_path=exe,
            headless=is_headless,
            channel="msedge" if bt.lower() == "edge" else "chrome",
            args=["--disable-blink-features=AutomationControlled"], no_viewport=True,
            timeout=timeout
        )
        
        # 【新增】强制清理非正常关闭留下的冗余标签页
        try:
            pages = self.browser_context.pages
            if len(pages) > 1:
                # 保留第一个，关闭其余所有
                for p in pages[1:]:
                    await p.close()
        except:
            pass

        return self.browser_context

    async def _shutdown_sequence(self):
        """完全关闭引擎（软件退出时调用）"""
        if not self.browser_context and (not self.dl_manager or not self.dl_manager.is_running): return

        self._emit_log("🛑 正在停止全链路采集...", "danger")
        if self.dl_manager: await self.dl_manager.stop_workers()
        
        for t in self.running_tasks.values(): t.cancel()
        self.running_tasks.clear()
        self.suspended_tasks.clear()
        self.paused_tasks.clear()

        # 只有完全退出时才关闭浏览器
        if self.manual_shutdown:
            if self.browser_context:
                try: await self.browser_context.close()
                except: pass
            if hasattr(self, 'pw_instance') and self.pw_instance:
                try: await self.pw_instance.stop()
                except: pass
            self.browser_context = None
        
        self.is_running = False
        self._emit_log("🏁 引擎已安全停机。", "success")

    def stop_crawling_only(self):
        """仅停止爬取逻辑，不关闭浏览器（新需求）"""
        self._emit_log("⏹️ 正在停止爬取...", "warning")
        self.is_running = False
        
        # 强制关闭下载管理器总闸，触发即时中断检查
        if self.dl_manager:
            self.dl_manager.is_running = False
        
        # 取消所有运行中的任务
        for tid, task in list(self.running_tasks.items()):
            task.cancel()
            if self.dl_manager:
                self.dl_manager.deregister_task(tid)
        self.running_tasks.clear()
        self.suspended_tasks.clear()
        
        # 清空队列
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except:
                break
        
        self._emit_log("⏹️ 爬取已停止 (后台下载已强制中断并清理)", "success")

    # ================= 任务控制方法 =================
    async def delete_task(self, tid):
        """删除任务（强制关闭对应 Page）"""
        deleted = False
        
        # 如果任务正在运行，取消并关闭 Page
        if tid in self.running_tasks:
            task = self.running_tasks[tid]
            task.cancel()
            deleted = True
            self._emit_log(f"🗑️ 已删除运行中任务: [{tid}]", "warning")
        
        # 同样需要清理正在过渡中（已出队但未进入 running）的任务
        if hasattr(self, 'transitioning_tasks') and tid in self.transitioning_tasks:
            task = self.transitioning_tasks[tid]
            task.cancel()
            self.transitioning_tasks.pop(tid, None)
            deleted = True
            self._emit_log(f"🗑️ 已删除过渡中任务: [{tid}]", "warning")
        
        # 从队列中移除
        try:
            new_queue = asyncio.Queue()
            while not self.queue.empty():
                item = self.queue.get_nowait()
                if item != tid:
                    new_queue.put_nowait(item)
                else:
                    deleted = True
                    self._emit_log(f"🗑️ 已从队列移除: [{tid}]", "warning")
            self.queue = new_queue
        except:
            pass
        
        # 从下载管理器注销
        if self.dl_manager:
            self.dl_manager.deregister_task(tid)
        
        # 从任务中移除
        self.running_tasks.pop(tid, None)
        self.failed_tasks.pop(tid, None)
        
        # 任务状态更新回调
        if 'on_task_update' in self.cbs and self.cbs['on_task_update']:
            self.cbs['on_task_update'](self.get_queue_status())

    def pause_task(self, tid):
        """暂停单个任务"""
        if hasattr(self, 'paused_tasks'):
            self.paused_tasks.add(tid)
        else:
            self.paused_tasks = {tid}
        self._emit_log(f"⏸️ 任务已暂停: [{tid}]", "info")

    def resume_task(self, tid):
        """恢复单个任务"""
        # 如果在失败列表中，则重新加入队列
        if tid in self.failed_tasks:
            self.add_task_to_queue(tid)
            return

        if hasattr(self, 'paused_tasks') and tid in self.paused_tasks:
            self.paused_tasks.discard(tid)
            self._emit_log(f"▶️ 任务已恢复: [{tid}]", "info")

    def pause_all(self):
        """全局暂停"""
        self.global_paused = True
        self._emit_log("⏸️ 全局暂停", "warning")

    def resume_all(self):
        """全局恢复"""
        self.global_paused = False
        if hasattr(self, 'paused_tasks'):
            self.paused_tasks.clear()
        self._emit_log("▶️ 全局恢复", "success")

    async def clear_all_tasks(self):
        """清空所有任务"""
        self._emit_log("🗑️ 正在清空任务列表...", "warning")
        
        # 1. 取消所有运行中的任务
        for tid, task in list(self.running_tasks.items()):
            task.cancel()
        self.running_tasks.clear()
        
        # 2. 取消所有过渡中的任务（启动器）
        for tid, task in list(self.transitioning_tasks.items()):
            task.cancel()
        self.transitioning_tasks.clear()
        
        # 3. 清空各种状态集合
        self.paused_tasks.clear()
        self.failed_tasks.clear()
        self.suspended_tasks.clear()
        
        # 4. 清空队列
        while not self.queue.empty():
            try: self.queue.get_nowait()
            except: break
            
        # 5. 清理下载项与注销 ID
        if self.dl_manager:
            for tid in list(self.dl_manager.active_task_ids):
                self.dl_manager.deregister_task(tid)
            self.dl_manager.session_counters.clear()
        
        # 6. 重置信号量 (防止死锁)
        if self.semaphore:
            self.semaphore = asyncio.Semaphore(int(CFG.get('concurrency')))
            
        # 7. 推送状态
        self._emit_log("🗓️ 任务列表已完全重置 (后台下载已强制中断)", "success")
        self._broadcast_status()

    def get_queue_status(self):
        """获取任务队列状态"""
        status_list = []
        
        # 运行中的任务
        for tid in self.running_tasks.keys():
            is_paused = hasattr(self, 'paused_tasks') and tid in self.paused_tasks
            status_list.append({
                "id": tid,
                "status": "paused" if is_paused else "running",
                "progress": self.dl_manager.session_counters.get(tid, 0) if self.dl_manager else 0
            })
        
        # 队列中等待的任务（通过遍历队列副本）
        try:
            queue_items = list(self.queue._queue)
            for tid in queue_items:
                if tid not in self.running_tasks:
                    status_list.append({
                        "id": tid,
                        "status": "queued",
                        "progress": 0
                    })
        except:
            pass
        
        # 正在等待槽位的任务（即调度器已取走但尚未开始执行）
        for tid in list(self.transitioning_tasks.keys()):
            if tid in self.running_tasks: continue # 如果已进入运行字典，则由下方循环渲染
            is_paused = tid in self.paused_tasks or self.global_paused
            status_list.append({
                "id": tid,
                "status": "paused" if is_paused else "queued",
                "progress": 0
            })

        # 失败的任务
        for tid, err in self.failed_tasks.items():
            status_list.append({
                "id": tid,
                "status": "error",
                "progress": self.dl_manager.session_counters.get(tid, 0) if self.dl_manager else 0,
                "error": err
            })
        
        return status_list

    def get_completed_tasks(self):
        """获取本次启动完成的任务列表"""
        return self.completed_tasks[:50]  # 最多返回 50 条

    async def _task_dispatcher(self):
        while self.is_running:
            try:
                tid = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                # 产生一个非阻塞启动器，防止 acquire 导致 dispatcher 暂停工作
                launcher = asyncio.create_task(self._task_launcher(tid))
                self.transitioning_tasks[tid] = launcher
            except:
                pass

    async def _task_launcher(self, tid):
        """负责等待信号量并启动执行器的中间层"""
        try:
            while self.is_running:
                # 1. 如果在等待期间被暂停，则一直等直到恢复或引擎停止
                while (tid in self.paused_tasks or self.global_paused) and self.is_running:
                    await asyncio.sleep(1)
                
                if not self.is_running: return

                # 2. 获取信号量（此时如果排在前面的任务没暂停，它会在这里阻塞）
                self._emit_log(f"⏳ 任务 [{tid}] 正在等待可用槽位...", "secondary")
                await self.semaphore.acquire()
                
                # 3. 拿到信号量后，再次检查是否在等待期间又变为了暂停状态
                if (tid in self.paused_tasks or self.global_paused) and self.is_running:
                    self.semaphore.release()
                    continue
                
                # 4. 正式进入执行
                await self._wrapped_executor(tid)
                break
        except asyncio.CancelledError:
            pass
        finally:
            self.transitioning_tasks.pop(tid, None)

    async def _wrapped_executor(self, tid):
        """任务执行器：支持暂停释放槽位"""
        try:
            self.dl_manager.register_task(tid)
            self._emit_log(f"▶ 启动任务: [{tid}]", "info")
            
            root = CFG.get('save_path')
            p = os.path.join(root, "我的喜欢" if tid == "MY_LIKES" else "我的书签" if tid == "MY_BOOKMARKS" else f"博主图集/{tid}")
            self._archaeology_healing(p, tid)

            mission = asyncio.create_task(self._mission_body_logic(tid))
            self.running_tasks[tid] = mission
            
            try:
                status = await mission
            except asyncio.CancelledError:
                # 任务被取消（删除时）
                self._emit_log(f"🗑️ 任务 [{tid}] 已被删除", "warning")
                status = "CANCELLED"

            if status == "FINISHED":
                while self.dl_manager.get_pending_count(tid) > 0 and self.is_running:
                    await asyncio.sleep(2)
                self._emit_log(f"✅ 任务 [{tid}] 完成", "success")
                # 记录完成的任务
                self.completed_tasks.insert(0, {
                    "id": tid,
                    "time": __import__('datetime').datetime.now().strftime("%H:%M:%S")
                })
                # 任务完成，且成功移除
                if 'on_task_finished' in self.cbs and self.cbs['on_task_finished']:
                    self.cbs['on_task_finished'](tid)

            elif status == "PAUSED":
                # 任务被暂停，释放槽位等待恢复
                self._emit_log(f"⏸️ 任务 [{tid}] 已挂起，等待恢复", "info")
            elif status == "FAILED":
                # 任务显式返回失败状态
                self.failed_tasks[tid] = "任务执行失败"
                self._emit_log(f"❌ 任务 [{tid}] 执行失败", "danger")
            elif status != "CANCELLED":
                self._emit_log(f"⚠️ 任务 [{tid}] 结束状态: {status}", "warning")
        except Exception as e:
            self.failed_tasks[tid] = str(e)
            self._emit_log(f"❌ 任务 [{tid}] 执行异常: {e}", "danger")
        finally:
            self.semaphore.release()
            self.running_tasks.pop(tid, None)
            try:
                self.queue.task_done()
            except:
                pass

    async def _sniff_and_save_id(self, page):
        """主动嗅探用户 ID 并保存"""
        self._emit_log(f"🔍 正在核实当前账号身份...", "info")
        try:
            # 1. 回到主页
            await page.goto("https://x.com/home", timeout=30000)
            
            # 2. 定位 Profile 按钮
            profile_btn = page.locator('a[data-testid="AppTabBar_Profile_Link"]')
            await profile_btn.wait_for(state="attached", timeout=10000)
            
            # 3. 读取 href
            href_attr = await profile_btn.get_attribute("href")
            
            if href_attr:
                real_user_id = href_attr.strip("/")
                CFG.set("custom_likes_id", real_user_id)
                self._emit_log(f"✅ 身份确认: @{real_user_id}", "success")
                return real_user_id
            return None
        except Exception as e:
            self._emit_log(f"❌ 无法识别账号身份: {e}", "danger")
            return None

    def _archaeology_healing(self, path, tid):
        h_file = os.path.join(path, "history.txt")
        if not os.path.exists(h_file) and os.path.exists(path):
            ids = []
            for sub in ["图片", "Gif"]:
                p = os.path.join(path, sub)
                if os.path.exists(p):
                    for f in os.listdir(p): ids.append(os.path.splitext(f)[0])
            if ids:
                with open(h_file, "w", encoding="utf-8") as f:
                    for rid in set(ids): f.write(rid + "\n")
                self._emit_log(f"🧠 [{tid}] 考古完成，恢复记录 {len(ids)} 条", "secondary")

    async def resilient_goto(self, page, url, tid):
        timeout = int(CFG.get('timeout')) * 1000
        for i in range(3):
            try:
                await self.engine_ready_event.wait()
                await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
                return True
            except Exception as e:
                if "ERR_ABORTED" in str(e):
                    await asyncio.sleep(2)
                    continue
                raise e
        return False

    async def _mission_body_logic(self, tid):
        if not self.is_running or not self.browser_context: return "FAILED"
        save_root = CFG.get('save_path')
        target_url = f"https://x.com/{tid}/media"
        task_label = tid
        save_dir = os.path.join(save_root, "博主图集", tid)

        if tid == "MY_BOOKMARKS":
            target_url = "https://x.com/i/bookmarks"
            task_label = "书签"
            save_dir = os.path.join(save_root, "我的书签")
        elif tid == "MY_LIKES":
            my_id = CFG.get("custom_likes_id")
            if not my_id: 
                # 尝试主动嗅探
                # 此时页面可能还没打开，需要先创建页面
                # 但 logic 内部会创建页面，所以我们在 logic 获取页面后做一次嗅探
                pass 
            else:
                target_url = f"https://x.com/{my_id}/likes"
            
            task_label = "喜欢"
            save_dir = os.path.join(save_root, "我的喜欢")

        state = {"active": False, "streak": 0}
        history = self._get_local_history(save_dir)

        def get_tweet_url(item_data):
            try:
                core_data = item_data.get("itemContent", item_data)
                if "tweet_results" in core_data and "result" in core_data["tweet_results"]:
                    res = core_data["tweet_results"]["result"]
                    legacy = res.get("legacy") or res.get("tweet", {}).get("legacy")
                    core = res.get("core") or res.get("tweet", {}).get("core")
                    
                    if legacy:
                        t_id = legacy.get("id_str")
                        u_name = "i"
                        try: u_name = core["user_results"]["result"]["legacy"]["screen_name"]
                        except: pass
                        if t_id: return f"https://x.com/{u_name}/status/{t_id}"
            except: pass
            return None

        def pinpoint_extract(data):
            found = []
            if isinstance(data, dict):
                if "itemContent" in data or "tweet_results" in data:
                    t_url = get_tweet_url(data)
                    
                    def find_media(d, link):
                        res = []
                        if isinstance(d, dict):
                            if "media_url_https" in d:
                                u = d["media_url_https"]
                                if "/media/" in u and "profile_images" not in u: 
                                    res.append({'type': 'img', 'url': u, 'link': link})
                            if "video_info" in d and "variants" in d["video_info"]:
                                mp4s = [v for v in d["video_info"]["variants"] if v.get("content_type") == "video/mp4"]
                                if mp4s: 
                                    best = max(mp4s, key=lambda x: x.get("bitrate", 0))["url"]
                                    res.append({'type': 'vid', 'url': best, 'link': link})
                            for v in d.values(): res.extend(find_media(v, link))
                        elif isinstance(d, list):
                            for i in d: res.extend(find_media(i, link))
                        return res
                    
                    found.extend(find_media(data, t_url))
                    return found
                
                for v in data.values(): found.extend(pinpoint_extract(v))
            elif isinstance(data, list):
                for i in data: found.extend(pinpoint_extract(i))
            return found

        async def api_handler(res):
            markers = ["UserMedia", "UserTweets", "Bookmarks", "Likes", "Timeline"]
            if not any(m in res.url for m in markers) or not state["active"]: return
            try:
                json_data = await res.json()
                media_list = pinpoint_extract(json_data)
                
                for item in media_list:
                    raw_url = item['url']
                    t_link = item['link']
                    clean = raw_url.split("?")[0]
                    
                    raw_fname = clean.split('/')[-1]
                    if "." in raw_fname:
                         f_id = raw_fname.rsplit(".", 1)[0]
                    else:
                         f_id = raw_fname
                    
                    if f_id in history:
                        state["streak"] += 1
                        continue
                    state["streak"] = 0
                    
                    if item['type'] == 'img' and CFG.get("dl_images"):
                        dest = os.path.join(save_dir, "图片", f_id + ".jpg")
                        await self.dl_manager.submit_job(f"{clean}?format=jpg&name=orig", dest, tid, task_label, 'img', clean, t_link)
                        history.add(f_id)
                    elif item['type'] == 'vid' and CFG.get("dl_gifs"):
                        dest = os.path.join(save_dir, "Gif", f_id + ".mp4")
                        await self.dl_manager.submit_job(clean, dest, tid, task_label, 'vid', clean, t_link)
                        history.add(f_id)
            except:
                pass

        try:
            # 【幽灵页面查重】检查是否已有该任务对应的页面
            page = None
            if tid in self.tid_to_page:
                old_page = self.tid_to_page[tid]
                try:
                    if not old_page.is_closed():
                        page = old_page
                        self._emit_log(f"🧠 [{task_label}] 检测到已有页面，正在复用进行同步", "secondary")
                    else:
                        del self.tid_to_page[tid]
                except:
                    del self.tid_to_page[tid]

            if not page:
                page = await self.browser_context.new_page()
                self.tid_to_page[tid] = page

            page.on("response", lambda r: asyncio.create_task(api_handler(r)))
            state["active"] = True

            # 【ID 缓存机制】
            if tid == "MY_LIKES" and not CFG.get("custom_likes_id"):
                sniffed_id = await self._sniff_and_save_id(page)
                if sniffed_id:
                     target_url = f"https://x.com/{sniffed_id}/likes"
                else:
                     return "FAILED"

            if not await self.resilient_goto(page, target_url, task_label): return "FAILED"

            try: await page.wait_for_selector('[data-testid="tweet"]', timeout=20000)
            except: pass
            
            self._emit_log(f"✅ [{task_label}] 页面加载完毕，开始采集", "success")
            await asyncio.sleep(5)

            shake_retry = 0
            for i in range(int(CFG.get('max_scrolls'))):
                if not self.is_running or not self.is_ctx_alive: return "FAILED"
                
                # 【暂停检查与信号量交接】
                if tid in self.paused_tasks or self.global_paused:
                    self._emit_log(f"⏸️ 任务 [{tid}] 正在暂停并释放资源...", "info")
                    self.semaphore.release() # 释放槽位给别人
                    try:
                        while (tid in self.paused_tasks or self.global_paused) and self.is_running:
                            await asyncio.sleep(1)
                        
                        if not self.is_running: return "FAILED"
                        
                        self._emit_log(f"⏳ 任务 [{tid}] 正在尝试恢复并重新排队...", "info")
                        await self.semaphore.acquire() # 重新排队
                        self._emit_log(f"▶️ 任务 [{tid}] 已成功恢复运行", "success")
                    except Exception as e:
                        self._emit_log(f"❌ 任务 [{tid}] 恢复失败: {e}", "danger")
                        return "FAILED"

                # 【核心修改】读取配置中的阈值
                stop_limit = int(CFG.get('stop_thresh'))
                if not CFG.get("deep_scan") and state["streak"] >= stop_limit: 
                    self._emit_log(f"🛑 [{task_label}] 连续 {stop_limit} 张旧图，停止", "success")
                    break
                elif CFG.get("deep_scan") and state["streak"] > 0 and state["streak"] % 100 == 0:
                    self._emit_log(f"⛏️ [{task_label}] 穿透模式运行中... 已忽略 {state['streak']} 张旧图", "secondary")

                prev_h = await page.evaluate("document.body.scrollHeight")
                await page.keyboard.press("End")
                
                # 滚动后的等待也要分片，以便快速响应暂停/停止
                wait_time = random.uniform(5, 8)
                for _ in range(int(wait_time)):
                     if not self.is_running or tid in self.paused_tasks or self.global_paused: break
                     await asyncio.sleep(1)
                
                new_h = await page.evaluate("document.body.scrollHeight")

                if new_h == prev_h:
                    shake_retry += 1
                    
                    is_rate_limited = await page.get_by_text("Rate limit exceeded").count() > 0 or \
                                      await page.get_by_text("Cannot retrieve tweets").count() > 0
                    if is_rate_limited:
                         self._emit_log(f"⛔ [{task_label}] 触发推特限流，停止账号保护！", "danger")
                         return "FAILED"

                    retry_btn = page.get_by_role("button", name=re.compile(r"Retry|Try again", re.I))
                    if await retry_btn.count() > 0:
                         self._emit_log(f"🔄 [{task_label}] 检测到重试按钮，尝试点击...", "warning")
                         await retry_btn.click()
                         await asyncio.sleep(5)
                         shake_retry = 0
                         continue

                    if shake_retry < 3:
                        self._emit_log(f"⏳ [{task_label}] 页面未滚动，重试 {shake_retry}...", "warning")
                        await page.evaluate("window.scrollBy(0, -600)")
                        await asyncio.sleep(3)
                        await page.keyboard.press("End")
                        await asyncio.sleep(shake_retry * 5)
                        continue
                    else:
                        self._emit_log(f"🛑 [{task_label}] 页面到底", "success")
                        break
                else:
                    shake_retry = 0
            return "FINISHED"
        except Exception as e:
            self._emit_log(f"❌ [{task_label}] 任务异常: {e}", "danger")
            return "FAILED"
        finally:
            try: 
                if tid in self.tid_to_page:
                    self.tid_to_page.pop(tid)
                await page.close()
            except: pass

    def _get_local_history(self, path):
        s = set()
        h = os.path.join(path, "history.txt")
        if os.path.exists(h):
            try:
                with open(h, "r", encoding="utf-8") as f:
                    for line in f: s.add(line.strip())
            except: pass
        return s

    async def run_login(self):
        bt = CFG.get("browser_type")
        exe = find_system_browser(bt)
        if not exe: 
            self._emit_log("未找到浏览器内核", "danger")
            return
        self._emit_log("🔑 正在开启独立登录环境授权向导...", "warning")
        async with async_playwright() as p:
            ctx = await p.chromium.launch_persistent_context(
                user_data_dir=os.path.abspath("my_browser_data"), executable_path=exe,
                headless=False, channel="msedge" if bt.lower() == "edge" else "chrome",
                args=["--disable-blink-features=AutomationControlled"], no_viewport=True
            )
            page = ctx.pages[0]
            await page.goto("https://x.com/i/flow/login", timeout=0)
            self._emit_log("请在弹出的浏览器中登录 Twitter，完成后关闭浏览器窗口。", "info")
            while True:
                if not ctx.pages: break
                await asyncio.sleep(1)
            self._emit_log("✅ 授权环境已更新并落盘", "success")

    # 【新增】导出 Cookie 逻辑
    def export_cookies(self):
        src = os.path.abspath("my_browser_data")
        if not os.path.exists(src):
            cprint("❌ 未找到登录数据，无法导出", "danger")
            return
        
        dest = os.path.join(os.getcwd(), "cookies_backup.json")
        async def extract():
            async with async_playwright() as p:
                bt = CFG.get("browser_type")
                exe = find_system_browser(bt)
                ctx = await p.chromium.launch_persistent_context(
                    user_data_dir=src, executable_path=exe, headless=True,
                    channel="msedge" if bt.lower() == "edge" else "chrome"
                )
                storage = await ctx.storage_state(path=dest)
                await ctx.close()
                cprint(f"✅ Cookie 已导出至: {dest}", "success")
        
        asyncio.run(extract())

# ================= 新增：历史统计功能 =================
def print_stats():
    root = CFG.get("save_path")
    if not root or not os.path.exists(root):
        cprint("❌ 存储路径不存在，无法统计", "danger")
        return

    def count_lines(folder_name, sub_folder=None):
        if sub_folder:
            path = os.path.join(root, folder_name, sub_folder, "history.txt")
        else:
            path = os.path.join(root, folder_name, "history.txt")
        
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return sum(1 for line in f if line.strip())
            except: return 0
        return 0

    cprint("\n📊 本地历史记录统计:", "info")
    print("-" * 30)

    likes = count_lines("我的喜欢")
    marks = count_lines("我的书签")
    
    if os.path.exists(os.path.join(root, "我的喜欢")):
        print(f"❤️  我的喜欢    : {likes} 张")
    if os.path.exists(os.path.join(root, "我的书签")):
        print(f"🔖 我的书签    : {marks} 张")

    users_root = os.path.join(root, "博主图集")
    if os.path.exists(users_root):
        print("-" * 30)
        for user_dir in os.listdir(users_root):
            full_path = os.path.join(users_root, user_dir)
            if os.path.isdir(full_path):
                cnt = count_lines("博主图集", user_dir)
                print(f"👤 {user_dir:<12} : {cnt} 张")
    
    print("-" * 30)


# ================= 命令行接口 =================
def main():
    os.system('cls' if os.name == 'nt' else 'clear')
    cprint("========================================", "info")
    cprint("   X-Spider CLI (Ultimate v9.0)", "info")
    cprint("========================================", "info")
    
    if not os.path.exists("my_browser_data"):
        cprint("⚠️ 未检测到登录信息，请先执行 'login' 命令", "warning")
    else:
        cprint("✅ 登录凭证就绪", "success")

    engine = CrawlerEngine()
    engine.start()

    cprint("\n指令列表:", "secondary")
    cprint("  add <id>    : 添加博主", "secondary")
    cprint("  likes       : 下载喜欢", "secondary")
    cprint("  marks       : 下载书签", "secondary")
    cprint("  path <dir>  : 修改路径", "secondary")
    cprint("  threads <n> : 下载线程", "secondary")
    cprint("  pages <n>   : 页面并发", "secondary")
    cprint("  limit <MB>  : 视频限制", "secondary")
    cprint("  thresh <n>  : 旧图阈值", "secondary")
    cprint("  timeout <n> : 超时设置", "secondary")
    cprint("  browser <t> : 内核切换(edge/chrome)", "secondary")
    cprint("  img on/off  : 图片开关", "secondary")
    cprint("  vid on/off  : 视频开关", "secondary")
    cprint("  deep on/off : 穿透开关", "secondary")
    cprint("  head on/off : 无头开关", "secondary")
    cprint("  stats       : 历史统计", "secondary")
    cprint("  export      : 导出Cookie", "secondary")
    cprint("  config      : 查看配置", "secondary")
    cprint("  login       : 启动登录", "secondary")
    cprint("  exit        : 退出", "secondary")
    print("")

    try:
        while True:
            cmd_raw = input(f"{Colors.CYAN}X-Spider>{Colors.RESET} ").strip()
            if not cmd_raw: continue
            
            if 'path ' in cmd_raw:
                parts = ['path', cmd_raw[5:].strip('"')]
            else:
                parts = cmd_raw.split()
                
            cmd = parts[0].lower()
            
            if cmd == "exit" or cmd == "stop" or cmd == "quit":
                engine.stop()
                break
            
            elif cmd == "add":
                if len(parts) > 1:
                    raw_args = parts[1]
                    ids = re.findall(r'@?([a-zA-Z0-9_]+)', raw_args)
                    final_ids = set()
                    for i in ids:
                        if i.lower() not in ['x', 'com', 'https', 'http', 'twitter', 'www']: final_ids.add(i)
                    for tid in final_ids: engine.add_task_to_queue(tid)
                else: cprint("用法: add <id/url>", "warning")
            
            elif cmd == "likes": engine.add_task_to_queue("MY_LIKES")
            elif cmd == "marks": engine.add_task_to_queue("MY_BOOKMARKS")

            elif cmd == "path":
                if len(parts) > 1:
                    new_path = parts[1]
                    if os.path.isdir(new_path) or not os.path.exists(new_path):
                        try:
                            if not os.path.exists(new_path): os.makedirs(new_path)
                            CFG.set("save_path", new_path)
                            cprint(f"📂 路径已更新: {new_path}", "success")
                        except: cprint("❌ 路径无效", "danger")
                    else: cprint("❌ 路径无效", "danger")
                else: cprint(f"当前路径: {CFG.get('save_path')}", "info")

            elif cmd == "limit":
                if len(parts) > 1 and parts[1].isdigit():
                    v = int(parts[1])
                    CFG.set("max_video_size", v)
                    cprint(f"🎞️ 视频限制: {v}MB", "success")

            elif cmd == "threads":
                if len(parts) > 1 and parts[1].isdigit():
                    n = int(parts[1])
                    if 1 <= n <= 64:
                        CFG.set("download_threads", n)
                        cprint(f"⚙️ 下载线程: {n}", "success")
                    else: cprint("范围: 1-64", "danger")

            elif cmd == "pages":
                if len(parts) > 1 and parts[1].isdigit():
                    n = int(parts[1])
                    if 1 <= n <= 10:
                        CFG.set("concurrency", n)
                        cprint(f"📄 页面并发: {n}", "success")
                    else: cprint("范围: 1-10", "danger")

            elif cmd == "thresh":
                if len(parts) > 1 and parts[1].isdigit():
                    n = int(parts[1])
                    CFG.set("stop_thresh", n)
                    cprint(f"🛑 阈值更新: {n} 张", "success")
                else: cprint(f"当前阈值: {CFG.get('stop_thresh')}", "info")
            
            elif cmd == "timeout":
                if len(parts) > 1 and parts[1].isdigit():
                    n = int(parts[1])
                    CFG.set("timeout", n)
                    cprint(f"⏱️ 超时设置: {n} 秒", "success")
                else: cprint(f"当前超时: {CFG.get('timeout')}秒", "info")

            elif cmd == "browser":
                if len(parts) > 1:
                    b_type = parts[1].lower()
                    if b_type in ["edge", "chrome"]:
                        CFG.set("browser_type", b_type.title())
                        cprint(f"🌐 内核切换: {b_type.title()}", "success")
                    else: cprint("仅支持 edge/chrome", "danger")
                else: cprint(f"当前内核: {CFG.get('browser_type')}", "info")

            elif cmd == "img":
                if len(parts) > 1:
                    mode = parts[1].lower() == "on"
                    CFG.set("dl_images", mode)
                    cprint(f"🖼️ 图片下载: {'ON' if mode else 'OFF'}", "success")

            elif cmd == "vid":
                if len(parts) > 1:
                    mode = parts[1].lower() == "on"
                    CFG.set("dl_videos", mode)
                    cprint(f"🎬 视频下载: {'ON' if mode else 'OFF'}", "success")

            elif cmd == "deep":
                if len(parts) > 1:
                    mode = parts[1].lower() == "on"
                    CFG.set("deep_scan", mode)
                    cprint(f"⛏️ 穿透模式: {'ON' if mode else 'OFF'}", "success")

            elif cmd == "head" or cmd == "headless":
                if len(parts) > 1:
                    mode = parts[1].lower() == "on"
                    CFG.set("headless", mode)
                    cprint(f"👻 无头模式: {'ON' if mode else 'OFF'}", "success")

            elif cmd == "stats":
                print_stats()

            elif cmd == "export":
                engine.export_cookies()

            elif cmd == "config":
                cprint(json.dumps(CFG.data, indent=2, ensure_ascii=False), "secondary")

            elif cmd == "login":
                if engine.is_running: cprint("请先 exit 停止引擎", "warning")
                else: asyncio.run(engine.run_login())
            
            else: cprint("未知指令 (输入 help 查看说明)", "secondary")

    except KeyboardInterrupt:
        engine.stop()
        cprint("\n强制退出...", "danger")

if __name__ == "__main__":
    main()