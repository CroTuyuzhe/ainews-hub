# 📊 市场情绪看板

A股 + 美股市场情绪实时看板 — 每日自动更新。

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

## 自动更新

GitHub Actions 工作日 18:30 CST 自动采集并部署。

## License

MIT
