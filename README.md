<div align="center">

# PCBuilder 硬件价格采集系统

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Playwright](https://img.shields.io/badge/Playwright-1.40+-green.svg)](https://playwright.dev/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

天猫五大件（CPU/GPU/内存/硬盘/主板）二手价格并行采集 + 智能清洗 + 合理估值参考价

</div>

## 📋 目录

- [功能特性](#-功能特性)
- [系统架构](#-系统架构)
- [快速开始](#-快速开始)
- [项目结构](#-项目结构)
- [技术栈](#-技术栈)
- [反爬策略](#-反爬策略)
- [数据清洗算法](#-数据清洗算法)
- [效果展示](#-效果展示)
- [许可证](#-许可证)

## ✨ 功能特性

- **五大件全覆盖**：CPU（151款）、GPU（150+款）、内存（100+规格）、硬盘（39种）、主板（60+芯片组）
- **并行采集**：多进程并行爬取，错峰启动，单品类独立浏览器实例
- **智能清洗**：MAD（中位数绝对偏差）稳健异常值检测，自动选择最优σ（1.5/2.0/2.5/3.0）
- **套条识别**：内存套条自动计算单根价格（16G*2 → 单根价）
- **混卖过滤**：标题多容量/多型号混卖自动过滤，严格规格匹配
- **品牌识别**：40+ CPU/GPU品牌、24+内存品牌、40+硬盘品牌、50+主板品牌
- **反爬增强**：浏览器指纹伪装、人类行为模拟、泊松请求间隔、指数退避
- **断点续爬**：已爬型号自动跳过，中断后可恢复
- **自动清洗**：爬完自动触发清洗，输出价格统计（最低/25%/中位/均值/75%/最高/推荐价）

## 🏗 系统架构

```
┌─────────────────────────────────────────────────────┐
│                   run.py (总调度器)                    │
│  多进程并行 | 错峰启动 | 日志汇总 | 失败重试           │
└──────────┬──────────┬──────────┬──────────┬─────────┘
           │          │          │          │
     ┌─────▼──┐ ┌────▼───┐ ┌──▼────┐ ┌──▼────┐ ┌▼─────┐
     │ CPU    │ │ GPU    │ │ 内存  │ │ 硬盘  │ │ 主板  │
     │Scraper│ │Scraper│ │Scraper│ │Scraper│ │Scraper│
     └────┬───┘ └────┬───┘ └───┬───┘ └───┬───┘ └──┬───┘
          │           │          │          │         │
     ┌────▼───┐  ┌────▼───┐ ┌──▼────┐ ┌──▼────┐ ┌▼─────┐
     │ CPU    │  │ GPU    │ │ 内存  │ │ 硬盘  │ │ 主板  │
     │Cleaner │  │Cleaner │ │Cleaner│ │Cleaner│ │Cleaner│
     └────┬───┘  └────┬───┘ └───┬───┘ └───┬───┘ └──┬───┘
          │            │          │          │         │
          └────────────┴──────────┴──────────┴─────────┘
                               │
                    ┌──────────▼──────────┐
                    │   价格统计 JSON      │
                    │  (按型号+品牌分组)   │
                    └─────────────────────┘
```

## 🚀 快速开始

### 环境要求

- Python 3.10+
- Windows 10/11（Playwright 浏览器自动化）
- 国内网络（或代理访问天猫）

### 安装

```bash
# 克隆项目
git clone https://github.com/hmyld/scraper_for_computer_five_major_parts_tianmao.git
cd PCBuilder

# 安装依赖
pip install -r requirements.txt
playwright install chromium
```

### 配置

1. 首次运行需扫码登录天猫，登录态自动保存到 `state.json`
2. 如需代理，在 `anti_crawl.py` 中配置代理地址

### 运行

```bash
# 全部五大件并行采集+清洗
python run.py

# 只跑指定品类（逗号分隔）
python run.py CPU,GPU
python run.py 内存,硬盘
python run.py 主板
```

### 输出

```
data/
├── cpu_result.json              # CPU原始数据
├── cpu_result_cleaned.json      # CPU清洗后数据
├── cpu_price_summary.json       # CPU价格统计
├── gpu_result.json              # GPU原始数据
├── ...                          # 其他品类
logs/
├── run_all_20260917_XXXXXX.log # 总调度日志
├── CPU_scraper.log              # CPU爬虫日志
└── CPU_cleaner.log              # CPU清洗日志
```

## 📁 项目结构

```
PCBuilder/
├── run.py                  # 总调度器（并行采集+自动清洗）
├── anti_crawl.py           # 反爬增强模块（指纹伪装+行为模拟）
├── cpu_scraper.py          # CPU爬虫
├── cpu_cleaner.py          # CPU清洗
├── gpu_scraper.py          # GPU爬虫
├── gpu_cleaner.py          # GPU清洗
├── ram_scraper.py          # 内存爬虫
├── ram_cleaner.py          # 内存清洗
├── sto_scraper.py          # 硬盘爬虫
├── sto_cleaner.py          # 硬盘清洗
├── mb_scraper.py           # 主板爬虫
├── mb_cleaner.py           # 主板清洗
├── dictionary/             # 硬件型号库
│   ├── hardware_base_cpu.json
│   ├── hardware_base_gpu.json
│   ├── hardware_base_ram.json
│   ├── hardware_base_sto.json
│   └── hardware_base_mb.json
├── data/                   # 采集数据（gitignore）
├── logs/                   # 运行日志（gitignore）
├── state.json              # 天猫登录态（gitignore，绝不提交）
├── requirements.txt        # 依赖清单
├── .gitignore              # Git忽略规则
├── LICENSE                 # 开源协议
└── README.md               # 项目文档
```

## 🛠 技术栈

| 类别 | 技术 |
|------|------|
| 语言 | Python 3.10+ |
| 浏览器自动化 | Playwright |
| 反检测 | playwright-stealth + 自定义指纹注入 |
| 数据处理 | NumPy（MAD稳健统计） |
| 并行 | concurrent.futures.ProcessPoolExecutor |
| 数据格式 | JSON |
| 日志 | logging + subprocess 捕获 |

## 🛡 反爬策略

### 浏览器层
- WebGL / Canvas / AudioContext 指纹随机化
- navigator.webdriver / plugins / languages 伪装
- 随机 User-Agent + 随机视口 + 时区伪装

### 行为层
- 贝塞尔曲线鼠标移动（非直线）
- 人类式滚动（变速+偶尔回滚）
- 逐字打字输入（5%概率打错重打）
- 搜索流程模拟（首页→搜索框→点按钮）
- 页面停留8-15秒（滚动+悬停+浏览）

### 调度层
- 泊松分布请求间隔（非均匀）
- 错峰启动（45秒间隔）
- 指数退避（限流后30s→60s→120s）
- 多进程隔离（独立浏览器实例）

## 📊 数据清洗算法

### MAD 稳健异常值检测

```
对于每个型号+品牌分组的价格列表：
1. 计算中位数 median
2. 计算中位数绝对偏差 MAD = median(|x - median|)
3. 稳健标准差 = MAD × 1.4826
4. 分别尝试 σ = 1.5 / 2.0 / 2.5 / 3.0
5. 选择变异系数（CV = std/mean）最小的方案
6. 输出：最低/25%/中位/均值/75%/最高/推荐价
```

### 推荐价 = min(中位数, 均值)

中位数对极端值不敏感，均值反映整体水平，取较小值作为保守估值参考。

## 📈 效果展示

| 品类 | 型号数 | 平均样本量 | 清洗后保留率 | 价格准确度 |
|------|--------|-----------|-------------|-----------|
| CPU | 151 | ~25 | ~85% | 高 |
| GPU | 150+ | ~20 | ~80% | 中高（专业卡样本少） |
| 内存 | 100+ | ~15 | ~75% | 中（老型号混卖多） |
| 硬盘 | 39 | ~20 | ~85% | 高 |
| 主板 | 60+ | ~18 | ~80% | 中高 |

## ⚠️ 免责声明

- 本项目仅供学习研究使用，请勿用于商业用途
- 采集数据时请遵守目标网站的 `robots.txt` 和使用条款
- 请控制采集频率，避免对目标网站造成压力
- 登录态 `state.json` 包含个人账号信息，请勿泄露或提交到公开仓库

## 📄 许可证

[MIT License](LICENSE)
