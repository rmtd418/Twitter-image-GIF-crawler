# X-Spider (Ultimate GUI Edition)

<p align="center">
  <img src="https://img.shields.io/badge/version-1.0-blue.svg?style=for-the-badge" alt="Version">
  <img src="https://img.shields.io/badge/python-3.8+-green.svg?style=for-the-badge" alt="Python">
  <img src="https://img.shields.io/badge/Playwright-Backend-orange.svg?style=for-the-badge" alt="Playwright">
  <img src="https://img.shields.io/badge/Eel-GUI-yellow.svg?style=for-the-badge" alt="Eel">
</p>

---

**X-Spider** 是一款专为媒体采集设计的推特下载工具。其只能下载图片与 GIF(推特的 GIF 本质上是超短视频重播),其视频下载功能正在开发中.

[查看功能详情](#-核心特性) • [快速开始](#-运行指南) 

---

## 📸 界面预览 (Screenshots)

<p align="center">
  
<img width="1200" height="" alt="PixPin_2026-01-11_18-07-37" src="https://github.com/user-attachments/assets/64807030-a348-4282-8e8a-24a16311e1d4"/>
<img width="1200" height="" alt="PixPin_2026-01-11_18-07-44" src="https://github.com/user-attachments/assets/c1f088c8-2f7c-4aed-bfe5-38f4de63bf29" />

</p>
<p align="center">
  <em></em>
</p>

---

## 心得

<span style="font-size: 12px; line-height: 1.6;">
这是一个完全靠 AI 开发的项目，我个人基本不会任何代码（顶多知道 HTML 里怎么改图片长宽高，一个函数都不懂）。我本来想着先用 AI 做一个自己感兴趣的项目，之后再围绕这个项目学习编程，没想到一上手就折腾了两周。

最开始是在Google AI Studio里让Gemini 3 Pro帮我制作全栈Python版本。但因为AI的输出长度有限，代码量顶天也就1000行，所以无论怎么调整，程序都存在bug。我甚至连IDE都没用过（电脑上装了IDE，但压根没想过要打开），全程就按照AI的指示在命令提示符里输入指令。

后来刷视频了解到有AI IDE这种工具，我就让Gemini 3 Pro删掉原来的Python前端，改成了CLI版本，再让功能更强的AI IDE给它做一个前端。为了让界面效果更好，我用Google AI Studio里的Build功能制作前端，可这个工具制作的前端只能用React框架,这为后来我折腾前后端对接埋下的伏笔。

接下来就是前后端对接，我完全没料到这是最耗时间的环节，断断续续花了整整一周，最后还是放弃了这个前端。

没办法只能换方案，尝试用纯HTML、CSS来做前端，于是找了一款国产AI工具trea，可它根本达不到我的需求，我又不想花钱买付费工具。刚好刷视频刷到谷歌刚推出不久的Antigravity IDE，里面有免费的Opus模型可用。我最后用两个账号的Opus额度打好了项目基础，再用Gemini 3 Pro和3F做了一些局部bug修复，最终才算完成了这个软件。
</span>

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

## ⚖️ 免责声明

本工具仅用于学术交流及个人备份数据使用。请遵循 X (Twitter) 的用户协议，尊重内容作者版权。因违规使用而产生的任何法律纠纷与开发者无关。

---

<p align="center">
  如果这个项目对你有帮助，欢迎给一个 ⭐️ <b>Star</b> ！
</p>
