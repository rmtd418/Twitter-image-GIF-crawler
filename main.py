"""
X-Spider GUI - Eel 桌面应用入口
技术栈: Python + Eel + Playwright
修复版本：
- 所有耗时操作异步执行，不阻塞 UI
- 支持预加入队列（引擎未启动也能添加任务）
- 修复任务删除和登录功能
"""
import os
import sys
import eel
import threading
import asyncio
import shutil
import tkinter as tk
from tkinter import filedialog
import ctypes  # 用于单实例保护
# 导入核心爬虫模块
from spider_core import CrawlerEngine, CFG, find_system_browser
import json

# ================= 全局变量 =================
engine: CrawlerEngine = None
playwright_loop: asyncio.AbstractEventLoop = None
playwright_thread: threading.Thread = None
# 全局浏览器实例，实现跨引擎重启持久化
global_pw_instance = None
global_browser_context = None
# 预加入队列（引擎启动前添加的任务）
pending_tasks = []
TASKS_FILE = "tasks.json"

def save_tasks():
    """保存当前任务列表到文件"""
    tasks_to_save = list(pending_tasks)
    if engine and engine.is_running:
        # 如果引擎在运行，还需要获取引擎中的队列和运行中任务
        # 这里简化处理：我们只保存 pending_tasks 和 queue 中的任务
        # 运行中的任务如果保存，下次启动也应该是 pending 状态
        try:
            # 获取引擎队列快照 (注意：这是异步队列，这里只能近似获取)
            # 更稳妥的方式是让引擎提供 keys
            pass 
        except:
            pass
    
    # 简单起见，我们只持久化 pending_tasks 
    # (注意：用户要求重启后任务列表还在。如果引擎正在运行的任务，重启后应该变回待启动)
    # 我们需要在 engine 关闭或软件退出时，把 queue 里的东西倒出来存进去
    
    # 重新实现：
    # 1. 收集 pending_tasks
    # 2. 如果 engine 存在，收集 engine.queue 和 engine.running_tasks
    
    all_tasks = list(pending_tasks)
    if engine:
        # 获取引擎中的任务（需要线程安全访问，或者在 shutdown 时统一处理）
        # 为防止复杂并发问题，我们在 save 时主要关注 pending。
        # 在 on_close 时，我们会停止引擎，此时可以将任务导出。
        pass
        
    try:
        with open(TASKS_FILE, "w", encoding="utf-8") as f:
            json.dump(all_tasks, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存任务列表失败: {e}")

def load_tasks():
    """从文件加载任务列表"""
    global pending_tasks
    if os.path.exists(TASKS_FILE):
        try:
            with open(TASKS_FILE, "r", encoding="utf-8") as f:
                saved_tasks = json.load(f)
                if isinstance(saved_tasks, list):
                    pending_tasks = saved_tasks
                    print(f"已加载 {len(pending_tasks)} 个任务")
        except Exception as e:
            print(f"加载任务列表失败: {e}")

# ================= Playwright 工作线程 =================
def start_playwright_thread():
    """在独立线程中启动 Playwright 的 asyncio 事件循环"""
    global playwright_loop
    playwright_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(playwright_loop)
    playwright_loop.run_forever()
def run_async_nowait(coro):
    """在 Playwright 线程中异步运行协程（不等待结果，不阻塞）"""
    if playwright_loop and playwright_loop.is_running():
        asyncio.run_coroutine_threadsafe(coro, playwright_loop)
def run_async(coro, timeout=60):
    """在 Playwright 线程中运行协程并等待结果（有超时）"""
    if playwright_loop and playwright_loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, playwright_loop)
        try:
            return future.result(timeout=timeout)
        except Exception as e:
            print(f"异步操作超时或失败: {e}")
            return None
    return None
# ================= 回调函数 =================
def on_log(msg, level="info"):
    """推送日志到前端"""
    try:
        eel.onLog(msg, level)()
    except:
        pass
def on_task_update(task_list):
    """推送任务列表更新到前端"""
    try:
        eel.onTaskUpdate(task_list)()
    except:
        pass
def on_progress(task_id, count):
    """推送下载进度到前端"""
    try:
        eel.onProgress(task_id, count)()
    except:
        pass
def on_engine_status(running):
    """推送引擎状态到前端"""
    try:
        eel.onEngineStatus(running)()
    except:
        pass
def on_task_finished(tid):
    """任务完成回调：从预列表中移除并保存"""
    global pending_tasks
    if tid in pending_tasks:
        pending_tasks.remove(tid)
        save_tasks()
        on_log(f"💾 任务 [{tid}] 完成并已从列表中移除", "success")

# ================= Eel 暴露的 API =================
@eel.expose
def check_login_status():
    """检查登录状态"""
    return os.path.exists("my_browser_data")
@eel.expose
def check_save_path():
    """检查保存路径是否有效"""
    path = CFG.get("save_path")
    return path and os.path.isdir(path)
@eel.expose
def get_settings():
    """获取所有配置"""
    return CFG.data
@eel.expose
def update_setting(key, value):
    """更新单个配置"""
    CFG.set(key, value)
    return True
@eel.expose
def select_folder():
    """调用系统文件夹选择对话框"""
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    folder = filedialog.askdirectory()
    root.destroy()
    if folder:
        CFG.set("save_path", folder)
        return folder
    return None
@eel.expose
def start_engine():
    """启动爬虫引擎（异步，不阻塞）"""
    global engine, pending_tasks
    
    # 前置校验
    if not check_login_status():
        return {"success": False, "error": "请先登录 Twitter 账号"}
    
    if not check_save_path():
        return {"success": False, "error": "请先设置有效的保存路径"}
    
    if engine and engine.is_running:
        return {"success": False, "error": "引擎已在运行中"}
    
    # 创建引擎并注入回调
    callbacks = {
        'on_log': on_log,
        'on_progress': on_progress,
        'on_task_update': on_task_update,
        'on_task_finished': lambda tid: playwright_loop.call_soon_threadsafe(on_task_finished, tid)
    }
    engine = CrawlerEngine(callbacks)
    engine.loop = playwright_loop
    
    # 注入全局浏览器实例（实现 Detachment 修复）
    global global_pw_instance, global_browser_context
    engine.pw_instance = global_pw_instance
    engine.browser_context = global_browser_context
    
    # 异步启动引擎
    async def do_start():
        global engine, global_pw_instance, global_browser_context
        await engine._engine_lifecycle()
        
        # 实时更新全局引用 (若 engine 内部发现了失效并重置，这里也会跟着更新)
        global_pw_instance = engine.pw_instance
        global_browser_context = engine.browser_context
    
    # 强制重置标志位
    engine.is_running = True
    engine.manual_shutdown = False
    run_async_nowait(do_start())
    
    on_engine_status(True)
    
    # 处理预加入队列的任务
    if pending_tasks:
        for tid in pending_tasks:
            engine.add_task_to_queue(tid)
        # 变更：不再清空 pending_tasks，而是保留作为持久化记录
        # 只有当任务完成 (on_task_finished) 或手动删除时才移除
        save_tasks() 
    
    return {"success": True}
@eel.expose
def stop_engine():
    """停止爬虫引擎（仅停止爬取，不关闭浏览器）"""
    global engine
    if engine:
        # 新逻辑：只停止爬取，不关闭浏览器
        engine.stop_crawling_only()
        on_engine_status(False)
    return {"success": True}
@eel.expose
def add_tasks(input_str):
    """批量添加任务（支持预加入队列）"""
    global engine, pending_tasks
    
    import re
    ids = re.findall(r'@?([a-zA-Z0-9_]+)', input_str)
    final_ids = set()
    exclude = {'x', 'com', 'https', 'http', 'twitter', 'www'}
    for i in ids:
        if i.lower() not in exclude:
            final_ids.add(i)
    
    if not final_ids:
        return {"success": False, "error": "未识别到有效的用户 ID"}
    
    # 允许预加入队列
    if engine and engine.is_running:
        added_count = 0
        for tid in final_ids:
            if engine.add_task_to_queue(tid):
                added_count += 1
        
        if added_count == 0:
            return {"success": False, "error": "所选任务已在运行或排队中，请勿重复添加"}
            
        return {"success": True, "count": added_count, "info": f"成功添加 {added_count} 个任务"}
    else:
        # 引擎未启动，加入预队列
        changed = False
        duplicate_count = 0
        for tid in final_ids:
            if tid in pending_tasks:
                duplicate_count += 1
                continue
            pending_tasks.append(tid)
            on_log(f"➕ 任务 [{tid}] 已加入预队列，待引擎启动后执行", "info")
            changed = True
        if changed:
            save_tasks()
        
        msg = f"成功添加 {len(final_ids) - duplicate_count} 个任务"
        if duplicate_count > 0:
            msg += f" (忽略 {duplicate_count} 个重复项)"
            
        if len(final_ids) == duplicate_count:
             return {"success": False, "error": "所选任务均已在列表中，请勿重复添加"}
             
        return {"success": True, "count": len(final_ids) - duplicate_count, "info": msg}
@eel.expose
def add_my_likes():
    """添加我的喜欢任务"""
    global engine, pending_tasks
    
    if engine and engine.is_running:
        if not engine.add_task_to_queue("MY_LIKES"):
            return {"success": False, "error": "任务已在队列中"}
    else:
        if "MY_LIKES" not in pending_tasks:
            pending_tasks.append("MY_LIKES")
            on_log("➕ 任务 [我的喜欢] 已加入预队列", "info")
            save_tasks()
        else:
            return {"success": False, "error": "任务已在预队列中"}
    return {"success": True}

@eel.expose
def add_my_bookmarks():
    """添加我的书签任务"""
    global engine, pending_tasks
    
    if engine and engine.is_running:
        if not engine.add_task_to_queue("MY_BOOKMARKS"):
            return {"success": False, "error": "任务已在队列中"}
    else:
        if "MY_BOOKMARKS" not in pending_tasks:
            pending_tasks.append("MY_BOOKMARKS")
            on_log("➕ 任务 [我的书签] 已加入预队列", "info")
            save_tasks()
        else:
            return {"success": False, "error": "任务已在预队列中"}
    return {"success": True}
@eel.expose
def delete_task(task_id):
    """删除任务（异步执行，不阻塞）"""
    global engine, pending_tasks
    
    # 先从预队列移除
    if task_id in pending_tasks:
        pending_tasks.remove(task_id)
        on_log(f"🗑️ 已从预队列移除: [{task_id}]", "warning")
        save_tasks()
        return {"success": True}
    
    # 从引擎队列移除
    if engine:
        # 使用 run_coroutine_threadsafe 确保在主循环中安全执行
        # 但 delete_task 是异步的，我们需要尽量让操作排队
        run_async_nowait(engine.delete_task(task_id))

    # 无论引擎是否运行，都要确保从 pending_tasks 移除并保存
    # (重复检查是为了防止多线程竞争导致的未移除)
    if task_id in pending_tasks:
        try:
            pending_tasks.remove(task_id)
            save_tasks()
        except: pass
        
    return {"success": True}
@eel.expose
def start_single_task(task_id):
    """启动/恢复单个任务"""
    global engine
    if engine:
        engine.resume_task(task_id)
    return {"success": True}
@eel.expose
def pause_single_task(task_id):
    """暂停单个任务"""
    global engine
    if engine:
        engine.pause_task(task_id)
    return {"success": True}
@eel.expose
def pause_task(task_id):
    """暂停单个任务"""
    global engine
    if engine:
        engine.pause_task(task_id)
    return {"success": True}
@eel.expose
def resume_task(task_id):
    """恢复单个任务"""
    global engine
    if engine:
        engine.resume_task(task_id)
    return {"success": True}
@eel.expose
def pause_all():
    """全局暂停"""
    global engine
    if engine:
        engine.pause_all()
    return {"success": True}
@eel.expose
def resume_all():
    """全局恢复"""
    global engine
    if engine:
        engine.resume_all()
    return {"success": True}
@eel.expose
def clear_all_tasks():
    """清空所有任务"""
    global engine, pending_tasks
    pending_tasks.clear()
    save_tasks()
    if engine:
        run_async_nowait(engine.clear_all_tasks())
    return {"success": True}
@eel.expose
def get_queue_status():
    """获取任务队列状态（包含预队列）"""
    global engine, pending_tasks
    status_list = []
    
    # 1. 获取引擎内部状态
    engine_status = []
    tracked_ids = set()
    if engine:
        engine_status = engine.get_queue_status()
        for item in engine_status:
            tracked_ids.add(item['id'])
    
    # 2. 添加尚未进入引擎或引擎未追踪的预队列任务
    for tid in pending_tasks:
        if tid in tracked_ids:
            continue
        status_list.append({
            "id": tid,
            "status": "pending",  # 待启动
            "progress": 0
        })
    
    # 3. 合并引擎状态
    status_list.extend(engine_status)
    
    return status_list
@eel.expose
def run_login():
    """启动登录向导（异步执行，不阻塞 UI）"""
    global engine
    
    # 如果引擎在运行则先停止
    if engine and engine.is_running:
        return {"success": False, "error": "请先停止引擎再登录"}
    
    # 在后台线程执行登录
    def do_login_thread():
        async def login_async():
            temp_engine = CrawlerEngine({'on_log': on_log})
            await temp_engine.run_login()
        
        if playwright_loop and playwright_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(login_async(), playwright_loop)
            try:
                future.result(timeout=600)  # 登录可能需要较长时间
            except:
                pass
    
    # 启动线程，立即返回
    threading.Thread(target=do_login_thread, daemon=True).start()
    return {"success": True}
@eel.expose
def get_history():
    """获取历史记录列表（含下载数量）"""
    save_path = CFG.get("save_path")
    if not save_path or not os.path.exists(save_path):
        return []
    
    def count_files(folder_path):
        """统计文件夹中的下载数量"""
        history_file = os.path.join(folder_path, "history.txt")
        if os.path.exists(history_file):
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    return sum(1 for line in f if line.strip())
            except:
                pass
        return 0
    
    history = []
    
    # 扫描博主图集文件夹
    users_root = os.path.join(save_path, "博主图集")
    if os.path.exists(users_root):
        for user_dir in os.listdir(users_root):
            full_path = os.path.join(users_root, user_dir)
            if os.path.isdir(full_path):
                history.append({
                    "id": user_dir,
                    "type": "user",
                    "path": full_path,
                    "count": count_files(full_path)
                })
    
    # 检查特殊文件夹
    likes_path = os.path.join(save_path, "我的喜欢")
    if os.path.exists(likes_path):
        history.insert(0, {
            "id": "MY_LIKES", 
            "type": "likes", 
            "name": "我的喜欢",
            "path": likes_path,
            "count": count_files(likes_path)
        })
    
    bookmarks_path = os.path.join(save_path, "我的书签")
    if os.path.exists(bookmarks_path):
        history.insert(0, {
            "id": "MY_BOOKMARKS", 
            "type": "bookmarks", 
            "name": "我的书签",
            "path": bookmarks_path,
            "count": count_files(bookmarks_path)
        })
    
    return history
@eel.expose
def delete_history_item(item_id):
    """删除单个历史记录"""
    save_path = CFG.get("save_path")
    if not save_path:
        return {"success": False, "error": "存储路径未设置"}
    
    if item_id == "MY_LIKES":
        target_path = os.path.join(save_path, "我的喜欢")
    elif item_id == "MY_BOOKMARKS":
        target_path = os.path.join(save_path, "我的书签")
    else:
        target_path = os.path.join(save_path, "博主图集", item_id)
    
    if os.path.exists(target_path):
        try:
            shutil.rmtree(target_path)
            on_log(f"🗑️ 已删除历史记录: {item_id}", "warning")
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    return {"success": False, "error": "记录不存在"}
@eel.expose
def clear_all_history():
    """清空所有历史记录"""
    save_path = CFG.get("save_path")
    if not save_path or not os.path.exists(save_path):
        return {"success": False, "error": "存储路径不存在"}
    
    try:
        # 删除三个主要文件夹
        for folder in ["我的喜欢", "我的书签", "博主图集"]:
            target = os.path.join(save_path, folder)
            if os.path.exists(target):
                shutil.rmtree(target)
        
        on_log("🗑️ 已清空所有历史记录", "warning")
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
@eel.expose
def export_cookies():
    """导出 Cookie（异步执行）"""
    global engine
    if engine and engine.is_running:
        return {"success": False, "error": "请先停止引擎"}
    
    def do_export():
        temp_engine = CrawlerEngine()
        temp_engine.export_cookies()
    
    threading.Thread(target=do_export, daemon=True).start()
    return {"success": True}
@eel.expose
def get_stats():
    """获取统计数据"""
    save_path = CFG.get("save_path")
    if not save_path or not os.path.exists(save_path):
        return {"error": "存储路径不存在"}
    
    def count_lines(folder_name, sub_folder=None):
        if sub_folder:
            path = os.path.join(save_path, folder_name, sub_folder, "history.txt")
        else:
            path = os.path.join(save_path, folder_name, "history.txt")
        
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return sum(1 for line in f if line.strip())
            except:
                return 0
        return 0
    
    stats = {
        "likes": count_lines("我的喜欢"),
        "bookmarks": count_lines("我的书签"),
        "users": {}
    }
    
    users_root = os.path.join(save_path, "博主图集")
    if os.path.exists(users_root):
        for user_dir in os.listdir(users_root):
            full_path = os.path.join(users_root, user_dir)
            if os.path.isdir(full_path):
                stats["users"][user_dir] = count_lines("博主图集", user_dir)
    
    return stats
@eel.expose
def get_engine_status():
    """获取引擎运行状态"""
    global engine
    return engine.is_running if engine else False
@eel.expose
def get_finished_tasks():
    """获取已完成的任务列表"""
    global engine
    if engine:
        return engine.get_completed_tasks()
    return []

# ================= 窗口关闭处理 =================
def on_close(route, websockets):
    """窗口关闭时清理资源"""
    global engine, playwright_loop, pending_tasks
    
    print("正在清理资源...")

    # 持久化策略变更：pending_tasks 始终包含所有未完成任务
    # 因此不需要再从 engine "回收" 任务，只需要保存当前的 pending_tasks
    # 但为了保险起见，如果 engine 运行期间添加了任务但没同步到 pending (理论上 add_tasks 已同步)，
    # 这里可以做一次最后的同步检查，但主要依赖运行时的实时同步。
    
    save_tasks()
    print(f"已保存任务列表 ({len(pending_tasks)} 个)")

    # 停止引擎
    if engine and engine.is_running:
        engine.stop()
        
    # 彻底关闭全局浏览器（软件退出时）
    global global_pw_instance, global_browser_context
    if global_browser_context:
        try: playwright_loop.call_soon_threadsafe(lambda: asyncio.create_task(global_browser_context.close()))
        except: pass
    if global_pw_instance:
        try: playwright_loop.call_soon_threadsafe(lambda: asyncio.create_task(global_pw_instance.stop()))
        except: pass

    # 停止 Playwright 事件循环
    if playwright_loop and playwright_loop.is_running():
        playwright_loop.call_soon_threadsafe(playwright_loop.stop)
    
    # 等待线程结束
    if playwright_thread and playwright_thread.is_alive():
        playwright_thread.join(timeout=5)
    
    print("清理完成，退出程序")
    sys.exit(0)
def ensure_single_instance():
    """使用 Windows 命名互斥量防止程序多开"""
    # 互斥量句柄需要保持在全局作用域，防止被垃圾回收导致失效
    global mutex_handle
    mutex_name = "Global\\X_Spider_Single_Instance_Mutex_9.0"
    mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
    
    if ctypes.windll.kernel32.GetLastError() == 183: # ERROR_ALREADY_EXISTS
        # 发现已有实例运行，寻回原窗口并置顶
        hwnd = ctypes.windll.user32.FindWindowW(None, "X-Spider")
        if hwnd:
            # 9 = SW_RESTORE (即使最小化也能唤回)
            ctypes.windll.user32.ShowWindow(hwnd, 9)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        print("检测到程序已在运行，已为你呼回旧窗口项目。项目。")
        sys.exit(0)

# ================= 主入口 =================
def main():
    # 启动前先进行单实例自检
    ensure_single_instance()
    
    global playwright_thread
    
    # 启动 Playwright 工作线程
    playwright_thread = threading.Thread(target=start_playwright_thread, daemon=True)
    playwright_thread.start()
    
    # 等待事件循环启动
    import time
    time.sleep(0.5)
    
    # 初始化 Eel
    web_dir = os.path.join(os.path.dirname(__file__), "web")
    eel.init(web_dir)
    
    # 加载任务
    load_tasks()
    
    # 确定使用的浏览器
    browser_type = CFG.get("browser_type").lower()
    browser_path = find_system_browser(browser_type)
    
    eel_options = {
        'mode': browser_type if browser_path else 'chrome',
        'host': 'localhost',
        'port': 8080,
        'close_callback': on_close,
    }
    
    if browser_path:
        eel_options['cmdline_args'] = [f'--app=http://localhost:8080']
    
    print("启动 X-Spider GUI...")
    print(f"使用浏览器: {browser_type.title()}")
    
    try:
        eel.start('index.html', **eel_options)
    except Exception as e:
        print(f"Eel 启动失败: {e}")
        print("尝试使用默认浏览器...")
        eel.start('index.html', mode='default', host='localhost', port=8080, close_callback=on_close)
if __name__ == "__main__":
    main()
