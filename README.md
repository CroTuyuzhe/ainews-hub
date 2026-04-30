# 📊 市场情绪看板

A股 + 美股市场情绪实时看板 — 每日自动更新。

![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/CroTuyuzhe/ainews-hub/daily.yml?label=%E6%9B%B4%E6%96%B0&logo=github)
![Last Commit](https://img.shields.io/github/last-commit/CroTuyuzhe/ainews-hub/gh-pages?label=%E6%9C%80%E5%90%8E%E9%83%A8%E7%BD%B2&logo=github)

> 🌐 **在线看板**: `https://crotuyuzhe.github.io/ainews-hub/`

## 技术栈

- **前端**: 纯 HTML/CSS/JS + Chart.js
- **数据源**: AKShare (A股) + yfinance (美股)
- **部署**: GitHub Pages + GitHub Actions

## 目录结构

```
.
├── index.html                    # 前端页面（移动优先）
├── scripts/
│   ├── fetch_data.py             # 数据采集爬虫
│   └── build_site.py             # 构建脚本
├── data/
│   └── data.json                 # 采集的数据
├── .github/workflows/
│   └── daily.yml                 # GitHub Actions 定时任务
└── dist/                         # 构建产物（部署到 gh-pages）
```

## 数据源

### A 股 (AKShare)
- 三大指数: 上证 / 深证 / 创业板
- 涨跌家数、涨停跌停
- 北向资金净流入
- 成交量

### 美股 (yfinance)
- VIX 恐慌指数
- 标普500

## 恐慌指数算法

```
恐慌指数(0-100) = 涨跌比权重40% + 涨停跌停比权重30% + 成交量偏离权重30%
```

## 自动更新

- **定时**: 工作日 18:30 CST (GitHub Actions)
- **手动触发**: 在 GitHub Actions 页面点击 `workflow_dispatch`
- **失败保护**: 数据采集失败时自动跳过部署，保留上次正常数据

## 本地开发

```bash
# 1. 安装依赖
pip install akshare yfinance pandas requests

# 2. 采集数据（--mock 使用模拟数据）
python scripts/fetch_data.py --mock

# 3. 构建
python scripts/build_site.py

# 4. 启动本地服务
cd dist && python -m http.server 8000
# 访问 http://localhost:8000
```

## License

MIT
