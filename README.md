# X-Spider (Ultimate GUI Edition)

<p align="center">
  <img src="https://img.shields.io/badge/version-1.0-blue.svg?style=for-the-badge" alt="Version">
  <img src="https://img.shields.io/badge/python-3.8+-green.svg?style=for-the-badge" alt="Python">
  <img src="https://img.shields.io/badge/Playwright-Backend-orange.svg?style=for-the-badge" alt="Playwright">
  <img src="https://img.shields.io/badge/Eel-GUI-yellow.svg?style=for-the-badge" alt="Eel">
</p>

---

**X-Spider** 是一款专为媒体采集设计的下一代现代化推特下载工具。它将强大的 Playwright 爬虫内核与精致的 Web GUI 相结合，旨在为用户提供最丝滑、最稳定的离线归档体验。

[查看功能详情](#-核心特性) • [快速开始](#-运行指南) • [常见问题](#-设置生效机制详解)

---

## 📸 界面预览 (Screenshots)

<p align="center">
  <!-- 建议：在此处替换为您实际封装后的软件截图 -->
  <img src="web/assets/preview_main.png" alt="Main Interface" width="800" style="border-radius: 10px; border: 1px solid #333">
</p>
<p align="center">
  <em>现代化深色模式设计，状态一目了然</em>
</p>

---

## ✨ 核心特性

- **🎨 极致视觉体验**：精致的 Web 驱动界面，支持跟随系统的原生主题切换，磁贴式布局整齐对齐。
- **👻 幽灵采集模式**：内置无头 (Headless) 与 穿透 (Deep Scan) 双重逻辑，平衡效率与深度。
- **🛡️ 工业级稳健性**：
  - **单实例运行锁**：杜绝多开冲突，自动唤回已有窗口。
  - **防御性下载**：具备文件锁定自动重试及下载中断残留清理机制。
  - **僵尸进程查杀**：确保引擎停止时，所有子进程及浏览器实例彻底退出。
- **🧠 智能身份识别**：自动嗅探登录账号 ID，无需手动查找，支持“我的喜欢/书签”一件批量下载。
- **⚡ 高并发架构**：支持数个页面并发采集与数十个线程同步下载，榨干网络带宽。

---

## 🛠️ 技术栈

- **Core**: Python 3.8+ / Playwright (Asynchronous)
- **GUI**: Eel (Python-JS Bridge) / HTML5 / CSS3 (Vanilla)
- **Networking**: Requests / Playwright Response Sniffing
- **Concurrency**: Asyncio / ThreadPoolExecutor

---

## 🚀 运行指南

### 1. 软件打包版 (Windows .exe)
1. 下载最新 [Releases](https://github.com/your-username/X-Spider/releases)。
2. 双击启动 `X-Spider.exe`，无需额外安装 Python 环境。

### 2. 源码开发者环境 (Source Code)
```bash
# 克隆仓库
git clone https://github.com/your-username/X-Spider.git
cd X-Spider

# 安装依赖
pip install -r requirements.txt
playwright install

# 运行主程序
python main.py
```

---

## ⚙️ 设置生效机制详解

| 参数类型 | 内容 | 应用时机 |
| :--- | :--- | :--- |
| **即时应用** | 阈值、穿透模式、超时、过滤开关、路径 | **确认保存后 3-5 秒内自动更新** |
| **架构重启** | 内核选择、无头模式、页面/线程并发 | **需停止并重启引擎生效** |

---

## 🤝 参与贡献

欢迎通过 [Issues](https://github.com/your-username/X-Spider/issues) 反馈 Bug 或提交 Pull Request。

1. Fork 本仓库
2. 新建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

---

## ⚖️ 免责声明

本工具仅用于学术交流及个人备份数据使用。请遵循 X (Twitter) 的用户协议，尊重内容作者版权。因违规使用而产生的任何法律纠纷与开发者无关。

---

<p align="center">
  如果这个项目对你有帮助，欢迎给一个 ⭐️ <b>Star</b> ！
</p>
