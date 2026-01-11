/**
 * X-Spider GUI 前端逻辑
 * 修复版本：任务独立控制、历史记录增强、阈值输入框
 */

// ================= 状态管理 =================
const state = {
    engineRunning: false,
    tasks: [],
    settings: {},      // 原始配置（已保存到硬盘的）
    draftSettings: {}   // 预览配置（尚未保存的）
};

// ================= 初始化 =================
document.addEventListener('DOMContentLoaded', async () => {
    // 初始化 Bootstrap Tooltips
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    tooltipTriggerList.forEach(el => new bootstrap.Tooltip(el));

    // 绑定事件
    bindEvents();

    // 初始化主题
    initTheme();

    // 加载设置
    await loadSettings();

    // 检查登录状态
    await checkLoginStatus();

    // 获取引擎状态
    await refreshEngineStatus();
    
    // 刷新任务列表
    await refreshTaskList();

    console.log('X-Spider GUI 初始化完成');
});

// ================= 事件绑定 =================
function bindEvents() {
    // 导航切换
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', () => {
            const page = item.dataset.page;
            switchPage(page);
        });
    });

    // 添加任务
    document.getElementById('btn-add-task').addEventListener('click', addTasks);
    document.getElementById('task-input').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') addTasks();
    });

    // 快捷按钮
    document.getElementById('btn-add-bookmarks').addEventListener('click', addBookmarks);
    document.getElementById('btn-add-likes').addEventListener('click', addLikes);

    // 引擎控制
    document.getElementById('btn-start-engine').addEventListener('click', toggleEngine);
    document.getElementById('btn-clear-tasks').addEventListener('click', clearAllTasks);
    document.getElementById('btn-history').addEventListener('click', showHistory);
    document.getElementById('btn-finished').addEventListener('click', showFinishedTasks);
    document.getElementById('btn-clear-log').addEventListener('click', clearLog);

    // 设置页相关
    document.getElementById('btn-login').addEventListener('click', runLogin);
    document.getElementById('btn-export').addEventListener('click', exportCookies);
    document.getElementById('btn-select-path').addEventListener('click', selectFolder);
    document.getElementById('btn-reset-settings').addEventListener('click', resetSettings);
    
    // 操作栏按钮
    document.getElementById('btn-confirm-settings').addEventListener('click', confirmSettings);
    document.getElementById('btn-undo-settings').addEventListener('click', undoSettings);

    bindSettingsEvents();

    // 主题切换
    document.querySelectorAll('#theme-switcher button').forEach(btn => {
        btn.addEventListener('click', () => {
            const theme = btn.dataset.theme;
            setTheme(theme);
        });
    });
}

function bindSettingsEvents() {
    // 浏览器选择
    document.getElementById('setting-browser').addEventListener('change', (e) => {
        updateSetting('browser_type', e.target.value);
    });

    // 开关类设置
    document.getElementById('setting-dl-images').addEventListener('change', (e) => {
        updateSetting('dl_images', e.target.checked);
    });
    document.getElementById('setting-dl-gifs').addEventListener('change', (e) => {
        updateSetting('dl_gifs', e.target.checked);
    });
    document.getElementById('setting-create-link').addEventListener('change', (e) => {
        updateSetting('create_link_file', e.target.checked);
    });
    document.getElementById('setting-headless').addEventListener('change', (e) => {
        updateSetting('headless', e.target.checked);
    });
    document.getElementById('setting-deep-scan').addEventListener('change', (e) => {
        updateSetting('deep_scan', e.target.checked);
        updateThreshUIState(e.target.checked);
    });
    document.getElementById('setting-use-tmp-files').addEventListener('change', (e) => {
        updateSetting('use_tmp_files', e.target.checked);
    });

    // 数字输入（包括阈值）
    document.getElementById('setting-max-video-size').addEventListener('change', (e) => {
        updateSetting('max_video_size', parseInt(e.target.value) || 0);
    });
    document.getElementById('setting-timeout').addEventListener('change', (e) => {
        updateSetting('timeout', parseInt(e.target.value) || 60);
    });
    document.getElementById('setting-thresh').addEventListener('change', (e) => {
        updateSetting('stop_thresh', parseInt(e.target.value) || 70);
    });

    // 滑块设置
    const concurrencySlider = document.getElementById('setting-concurrency');
    const concurrencyValue = document.getElementById('concurrency-value');
    concurrencySlider.addEventListener('input', (e) => {
        concurrencyValue.textContent = e.target.value;
    });
    concurrencySlider.addEventListener('change', (e) => {
        updateSetting('concurrency', parseInt(e.target.value));
    });

    const threadsSlider = document.getElementById('setting-threads');
    const threadsValue = document.getElementById('threads-value');
    threadsSlider.addEventListener('input', (e) => {
        threadsValue.textContent = e.target.value;
    });
    threadsSlider.addEventListener('change', (e) => {
        updateSetting('download_threads', parseInt(e.target.value));
    });
}

// ================= 页面切换 =================
function switchPage(page) {
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.page === page);
    });
    document.querySelectorAll('.page').forEach(p => {
        p.classList.toggle('active', p.id === `page-${page}`);
    });
}

// ================= 设置相关 =================
async function loadSettings() {
    try {
        const settings = await eel.get_settings()();
        state.settings = settings;
        state.draftSettings = JSON.parse(JSON.stringify(settings)); // 克隆到草稿箱
        applySettingsToUI(settings);
    } catch (e) {
        console.error('加载设置失败:', e);
    }
}

function applySettingsToUI(settings) {
    document.getElementById('setting-path').value = settings.save_path || '';
    document.getElementById('setting-browser').value = settings.browser_type || 'Edge';
    document.getElementById('setting-dl-images').checked = settings.dl_images !== false;
    document.getElementById('setting-dl-gifs').checked = settings.dl_gifs === true;
    document.getElementById('setting-max-video-size').value = settings.max_video_size || 5;
    document.getElementById('setting-create-link').checked = settings.create_link_file !== false;
    document.getElementById('setting-use-tmp-files').checked = settings.use_tmp_files !== false;
    
    // 阈值（改为数字输入框）
    document.getElementById('setting-thresh').value = settings.stop_thresh || 70;
    
    document.getElementById('setting-timeout').value = settings.timeout || 60;
    document.getElementById('setting-headless').checked = settings.headless === true;
    document.getElementById('setting-deep-scan').checked = settings.deep_scan === true;
    
    const concurrency = settings.concurrency || 3;
    document.getElementById('setting-concurrency').value = concurrency;
    document.getElementById('concurrency-value').textContent = concurrency;
    
    const threads = settings.download_threads || 16;
    document.getElementById('setting-threads').value = threads;
    document.getElementById('threads-value').textContent = threads;

    // 主题状态同步
    if (settings.theme) {
        applyTheme(settings.theme);
    }

    // 联动状态同步
    updateThreshUIState(settings.deep_scan === true);
}

function updateThreshUIState(isDeepScan) {
    const threshInput = document.getElementById('setting-thresh');
    const threshItem = threshInput.closest('.setting-item');
    
    if (isDeepScan) {
        threshInput.disabled = true;
        threshItem.style.opacity = '0.5';
        threshItem.style.pointerEvents = 'none';
        threshItem.title = "穿透模式下无需阈值";
    } else {
        threshInput.disabled = false;
        threshItem.style.opacity = '1';
        threshItem.style.pointerEvents = 'auto';
        threshItem.title = "";
    }
}

function updateSetting(key, value) {
    // 仅更新草稿箱，不直接写入硬盘
    state.draftSettings[key] = value;
    showActionBar();
}

function showActionBar() {
    document.getElementById('settings-action-bar').classList.add('show');
}

function hideActionBar() {
    document.getElementById('settings-action-bar').classList.remove('show');
}

async function confirmSettings() {
    try {
        // 将草稿箱内容全量同步到后端
        const keys = Object.keys(state.draftSettings);
        for (const key of keys) {
            // 只有当值确实发生变化时才更新（可选优化）
            if (state.draftSettings[key] !== state.settings[key]) {
                await eel.update_setting(key, state.draftSettings[key])();
            }
        }
        
        // 更新本地原始状态并隐藏工具栏
        state.settings = JSON.parse(JSON.stringify(state.draftSettings));
        hideActionBar();
        showToast('设置保存成功');
    } catch (e) {
        console.error('保存设置失败:', e);
        showToast('保存设置失败，请重试', 'danger');
    }
}

function undoSettings() {
    // 强制恢复到原始设置
    state.draftSettings = JSON.parse(JSON.stringify(state.settings));
    applySettingsToUI(state.settings);
    hideActionBar();
    showToast('已撤销所有未保存的更改', 'info');
}

async function resetSettings() {
    // 提取当前存储路径，以便重置时保留
    const currentPath = state.draftSettings.save_path || state.settings.save_path || "Download";
    
    // 恢复为默认值（基于后端提供的默认配置）
    const defaultSettings = {
        "save_path": currentPath, 
        "concurrency": 3,
        "download_threads": 16,
        "max_scrolls": 1000,
        "stop_thresh": 300,
        "max_video_size": 5,
        "dl_images": true,
        "dl_gifs": true,
        "browser_type": "Edge",
        "create_link_file": true,
        "use_tmp_files": true,
        "deep_scan": false,
        "headless": false,
        "theme": "system",
        "timeout": 60
    };
    
    state.draftSettings = defaultSettings;
    applySettingsToUI(defaultSettings);
    showActionBar();
    showToast('已恢复默认参数（已保留当前路径），请确认后保存', 'warning');
}

function showToast(msg, type = 'success') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-stack-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `custom-toast toast-${type}`;
    toast.innerHTML = `
        <i class="bi bi-${type === 'success' ? 'check-circle' : type === 'warning' ? 'exclamation-triangle' : 'info-circle'}-fill"></i>
        <span>${msg}</span>
    `;
    container.appendChild(toast);
    
    // 强制触发回流以启动动画
    toast.offsetHeight;
    toast.classList.add('show');
    
    // 自动移除
    setTimeout(() => {
        toast.classList.remove('show');
        toast.style.opacity = '0';
        setTimeout(() => {
            toast.remove();
        }, 500);
    }, 3000);
}

// ================= 主题系统 =================
function initTheme() {
    // 优先尝试从本地存储或默认值初始化，不依赖还未加载的 state.settings
    const html = document.documentElement;
    const currentTheme = html.getAttribute('data-theme') || 'dark';
    applyTheme(currentTheme);
    
    // 监听系统主题变化
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
        // 只有当用户设置为 system 时才自动同步
        if (state.settings && state.settings.theme === 'system') {
            applyTheme('system');
        }
    });
}

function setTheme(theme) {
    applyTheme(theme);
    updateSetting('theme', theme);
}

function applyTheme(theme) {
    const html = document.documentElement;
    let effectiveTheme = theme;
    
    if (theme === 'system') {
        effectiveTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    
    html.setAttribute('data-theme', effectiveTheme);
    
    // 更新按钮状态
    document.querySelectorAll('#theme-switcher button').forEach(btn => {
        const isActive = btn.dataset.theme === theme;
        btn.classList.toggle('btn-primary', isActive);
        btn.classList.toggle('active', isActive);
        btn.classList.toggle('btn-outline-secondary', !isActive);
    });
}

async function selectFolder() {
    try {
        const folder = await eel.select_folder()();
        if (folder) {
            document.getElementById('setting-path').value = folder;
            updateSetting('save_path', folder);
        }
    } catch (e) {
        console.error('选择文件夹失败:', e);
    }
}

// ================= 登录相关 =================
async function checkLoginStatus() {
    try {
        const loggedIn = await eel.check_login_status()();
        const btn = document.getElementById('btn-login');
        if (loggedIn) {
            btn.innerHTML = '<i class="bi bi-arrow-repeat"></i>';
            btn.title = '更新 Cookie';
        } else {
            btn.innerHTML = '<i class="bi bi-key"></i>';
            btn.title = '启动登录向导';
        }
    } catch (e) {
        console.error('检查登录状态失败:', e);
    }
}

async function runLogin() {
    try {
        addLog('🔑 正在启动登录向导...', 'info');
        const result = await eel.run_login()();
        if (!result.success) {
            showAlert('错误', result.error);
        } else {
            showAlert('提示', '请在弹出的浏览器中登录 Twitter，完成后关闭浏览器窗口。');
        }
    } catch (e) {
        console.error('启动登录失败:', e);
    }
}

async function exportCookies() {
    try {
        addLog('📤 正在导出 Cookie...', 'info');
        const result = await eel.export_cookies()();
        if (result.success) {
            showAlert('成功', 'Cookie 已导出到 cookies_backup.json');
        } else {
            showAlert('错误', result.error);
        }
    } catch (e) {
        console.error('导出 Cookie 失败:', e);
    }
}

// ================= 引擎控制 =================
async function refreshEngineStatus() {
    try {
        const running = await eel.get_engine_status()();
        updateEngineUI(running);
    } catch (e) {
        console.error('获取引擎状态失败:', e);
    }
}

function updateEngineUI(running) {
    state.engineRunning = running;
    const btn = document.getElementById('btn-start-engine');
    const statusDot = document.querySelector('.status-dot');

    if (running) {
        btn.innerHTML = '<i class="bi bi-stop-fill"></i> 停止引擎';
        btn.classList.remove('btn-success');
        btn.classList.add('running');
        statusDot.classList.add('running');
    } else {
        btn.innerHTML = '<i class="bi bi-play-fill"></i> 启动引擎';
        btn.classList.add('btn-success');
        btn.classList.remove('running');
        statusDot.classList.remove('running');
    }
}

async function toggleEngine() {
    if (state.engineRunning) {
        await stopEngine();
    } else {
        await startEngine();
    }
}

async function startEngine() {
    try {
        const result = await eel.start_engine()();
        if (result.success) {
            updateEngineUI(true);
        } else {
            showAlert('启动失败', result.error);
        }
    } catch (e) {
        console.error('启动引擎失败:', e);
        showAlert('错误', '启动引擎时发生错误');
    }
}

async function stopEngine() {
    try {
        await eel.stop_engine()();
        updateEngineUI(false);
    } catch (e) {
        console.error('停止引擎失败:', e);
    }
}

// ================= 任务管理 =================
async function addTasks() {
    const input = document.getElementById('task-input');
    const value = input.value.trim();
    if (!value) return;

    try {
        const result = await eel.add_tasks(value)();
        if (result.success) {
            input.value = '';
            await refreshTaskList();
        } else {
            showAlert('添加失败', result.error);
        }
    } catch (e) {
        console.error('添加任务失败:', e);
    }
}

async function addBookmarks() {
    try {
        const result = await eel.add_my_bookmarks()();
        if (result.success) {
            await refreshTaskList();
        } else {
            showAlert('添加失败', result.error);
        }
    } catch (e) {
        console.error('添加书签任务失败:', e);
    }
}

async function addLikes() {
    try {
        const result = await eel.add_my_likes()();
        if (result.success) {
            await refreshTaskList();
        } else {
            showAlert('添加失败', result.error);
        }
    } catch (e) {
        console.error('添加喜欢任务失败:', e);
    }
}

async function deleteTask(taskId) {
    try {
        await eel.delete_task(taskId)();
        await refreshTaskList();
    } catch (e) {
        console.error('删除任务失败:', e);
    }
}

async function pauseTask(taskId) {
    try {
        await eel.pause_single_task(taskId)();
        await refreshTaskList();
    } catch (e) {
        console.error('暂停任务失败:', e);
    }
}

async function resumeTask(taskId) {
    try {
        await eel.start_single_task(taskId)();
        await refreshTaskList();
    } catch (e) {
        console.error('恢复任务失败:', e);
    }
}

async function clearAllTasks() {
    try {
        await eel.clear_all_tasks()();
        await refreshTaskList();
    } catch (e) {
        console.error('清空任务失败:', e);
    }
}

async function refreshTaskList() {
    try {
        const tasks = await eel.get_queue_status()();
        state.tasks = tasks;
        renderTaskList(tasks);
    } catch (e) {
        console.error('刷新任务列表失败:', e);
    }
}

function renderTaskList(tasks) {
    const container = document.getElementById('task-list');
    const countBadge = document.getElementById('task-count');
    
    countBadge.textContent = tasks.length;

    if (tasks.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <i class="bi bi-plus-circle"></i>
                <p>暂未添加采集任务</p>
            </div>
        `;
        return;
    }

    container.innerHTML = tasks.map(task => {
        const statusClass = task.status;
        const statusEmoji = task.status === 'running' ? '▶️' : 
                           task.status === 'queued' ? '⏳' : 
                           task.status === 'paused' ? '⏸️' : 
                           task.status === 'pending' ? '📋' : 
                           task.status === 'error' ? '❌' : '❓';
        const statusText = task.status === 'running' ? '运行中' : 
                          task.status === 'queued' ? '排队中' : 
                          task.status === 'paused' ? '已暂停' : 
                          task.status === 'pending' ? '待启动' : 
                          task.status === 'error' ? '任务异常' : task.status;
        const displayName = task.id === 'MY_LIKES' ? '❤️ 我的喜欢' : 
                           task.id === 'MY_BOOKMARKS' ? '🔖 我的书签' : 
                           `@${task.id}`;
        
        // 根据状态显示不同的控制按钮
        const isRunningOrQueued = task.status === 'running' || task.status === 'queued';
        const isError = task.status === 'error';
        
        let controlBtn = '';
        if (isRunningOrQueued) {
            controlBtn = `<button class="btn btn-outline-warning btn-sm" onclick="pauseTask('${task.id}')" title="暂停">
                               <i class="bi bi-pause-fill"></i>
                           </button>`;
        } else if (isError) {
            controlBtn = `<button class="btn btn-outline-warning restart-btn btn-sm" onclick="resumeTask('${task.id}')" title="重启任务">
                               <i class="bi bi-arrow-clockwise"></i>
                           </button>`;
        } else {
            controlBtn = `<button class="btn btn-outline-success btn-sm" onclick="resumeTask('${task.id}')" title="开始">
                               <i class="bi bi-play-fill"></i>
                           </button>`;
        }

        return `
            <div class="task-item" data-id="${task.id}">
                <div class="task-info">
                    <div class="task-status ${statusClass}"></div>
                    <div class="task-details">
                        <span class="task-name">${displayName}</span>
                        <div class="task-meta">
                            <span class="task-state">${statusEmoji} ${statusText}</span>
                            ${task.progress > 0 ? `<span class="task-count">已下载 ${task.progress} 个</span>` : ''}
                        </div>
                    </div>
                </div>
                <div class="task-actions">
                    ${controlBtn}
                    <button class="btn btn-outline-danger btn-sm" onclick="deleteTask('${task.id}')" title="删除">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

// ================= 历史记录 =================
async function showHistory() {
    try {
        const history = await eel.get_history()();
        renderHistoryList(history);
        const modal = new bootstrap.Modal(document.getElementById('historyModal'));
        modal.show();
    } catch (e) {
        console.error('获取历史记录失败:', e);
    }
}

function renderHistoryList(history) {
    const container = document.getElementById('history-list');

    if (history.length === 0) {
        container.innerHTML = '<p class="text-center text-muted py-4">暂无历史记录</p>';
        return;
    }

    container.innerHTML = history.map(item => {
        const icon = item.type === 'likes' ? 'bi-heart-fill text-danger' : 
                    item.type === 'bookmarks' ? 'bi-bookmark-fill text-primary' : 
                    'bi-person-fill';
        const name = item.name || `@${item.id}`;
        const typeText = item.type === 'likes' ? '喜欢' : 
                        item.type === 'bookmarks' ? '书签' : '博主';
        const count = item.count || 0;

        return `
            <div class="history-item">
                <div class="history-item-info">
                    <i class="bi ${icon} history-item-icon"></i>
                    <div>
                        <div class="history-item-name">${name}</div>
                        <div class="history-item-type">${typeText} · ${count} 个文件</div>
                    </div>
                </div>
                <div class="history-item-actions">
                    <button class="btn btn-outline-primary btn-sm" onclick="addHistoryToQueue('${item.id}')" title="加入队列">
                        <i class="bi bi-plus-lg"></i>
                    </button>
                    <button class="btn btn-outline-danger btn-sm" onclick="deleteHistoryItem('${item.id}')" title="删除记录">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

async function addHistoryToQueue(id) {
    if (id === 'MY_LIKES') {
        await addLikes();
    } else if (id === 'MY_BOOKMARKS') {
        await addBookmarks();
    } else {
        try {
            const result = await eel.add_tasks(`@${id}`)();
            if (result.success) {
            }
        } catch (e) {
            console.error('添加历史任务失败:', e);
        }
    }
    // 关闭模态框
    bootstrap.Modal.getInstance(document.getElementById('historyModal')).hide();
}

async function showFinishedTasks() {
    try {
        const finished = await eel.get_finished_tasks()();
        const container = document.getElementById('finished-list');
        
        if (finished.length === 0) {
            container.innerHTML = '<p class="text-center text-muted py-4">本次启动暂无完成任务</p>';
        } else {
            container.innerHTML = finished.map(item => {
                const displayName = item.id === 'MY_LIKES' ? '❤️ 我的喜欢' : 
                                   item.id === 'MY_BOOKMARKS' ? '🔖 我的书签' : 
                                   `@${item.id}`;
                return `
                    <div class="history-item">
                        <div class="history-item-info">
                            <i class="bi bi-check-circle-fill text-success history-item-icon"></i>
                            <div>
                                <div class="history-item-name">${displayName}</div>
                                <div class="history-item-type">完成时间: ${item.time}</div>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');
        }
        
        const modal = new bootstrap.Modal(document.getElementById('finishedModal'));
        modal.show();
    } catch (e) {
        console.error('获取已完成任务失败:', e);
    }
}

async function deleteHistoryItem(id) {
    if (!confirm(`确定要删除 ${id} 的历史记录吗？\n这将删除本地所有已下载的文件！`)) {
        return;
    }
    
    try {
        const result = await eel.delete_history_item(id)();
        if (result.success) {
            // 刷新历史列表
            const history = await eel.get_history()();
            renderHistoryList(history);
        } else {
            showAlert('删除失败', result.error);
        }
    } catch (e) {
        console.error('删除历史记录失败:', e);
    }
}

async function clearAllHistory() {
    if (!confirm('确定要清空所有历史记录吗？\n这将删除所有本地已下载的文件！此操作不可恢复！')) {
        return;
    }
    
    try {
        const result = await eel.clear_all_history()();
        if (result.success) {
            renderHistoryList([]);
            showAlert('成功', '已清空所有历史记录');
        } else {
            showAlert('清空失败', result.error);
        }
    } catch (e) {
        console.error('清空历史记录失败:', e);
    }
}

// ================= 日志相关 =================
function addLog(message, level = 'info') {
    const container = document.getElementById('log-container');
    const time = new Date().toLocaleTimeString('zh-CN', { hour12: false });
    
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    entry.innerHTML = `
        <span class="log-time">[${time}]</span>
        <span class="log-message ${level}">${message}</span>
    `;
    
    container.appendChild(entry);
    container.scrollTop = container.scrollHeight;
    
    // 限制日志数量 (最新 400 条)
    while (container.children.length > 400) {
        container.removeChild(container.firstChild);
    }
}

function clearLog() {
    document.getElementById('log-container').innerHTML = '';
}

// ================= 弹窗 =================
function showAlert(title, message) {
    document.getElementById('alert-title').textContent = title;
    document.getElementById('alert-message').textContent = message;
    const modal = new bootstrap.Modal(document.getElementById('alertModal'));
    modal.show();
}

// ================= Eel 回调函数（后端推送） =================
eel.expose(onLog);
function onLog(message, level) {
    addLog(message, level);
}

eel.expose(onTaskUpdate);
function onTaskUpdate(tasks) {
    state.tasks = tasks;
    renderTaskList(tasks);
}

eel.expose(onProgress);
function onProgress(taskId, count) {
    const taskItem = document.querySelector(`.task-item[data-id="${taskId}"]`);
    if (taskItem) {
        const progressEl = taskItem.querySelector('.task-progress');
        if (progressEl) {
            progressEl.textContent = `已下载 ${count} 个`;
        }
    }
}

eel.expose(onEngineStatus);
function onEngineStatus(running) {
    updateEngineUI(running);
}

// 定期刷新任务列表
setInterval(() => {
    if (state.engineRunning) {
        refreshTaskList();
    }
}, 3000);
