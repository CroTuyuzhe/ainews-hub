# Delivery Report: 市场情绪看板

## Files Delivered

```
.
├── index.html                          # 前端页面（移动优先，响应式 320px+）
├── scripts/
│   ├── fetch_data.py                   # Python 爬虫（AKShare + yfinance）
│   └── build_site.py                   # 构建 & 验证脚本
├── data/
│   └── data.json                       # 样本数据（本地预览用）
├── .github/workflows/daily.yml         # GitHub Actions 定时任务
├── requirements.txt                    # Python 依赖
├── .gitignore
└── README.md
```

## Implementation Details

### 1. Fetch Script (`scripts/fetch_data.py`)
- **A股数据源**: AKShare — 三大指数、涨跌家数、涨停跌停、北向资金、成交量
- **美股数据源**: yfinance — VIX 指数、标普500
- **恐慌指数算法**: `涨跌比(40%) + 涨停跌停比(30%) + 成交量偏离(30%)`
- **容错处理**: 数据源异常时自动回退到上次有效数据（data.previous.json）
- **Mock模式**: `--mock` 参数生成模拟数据用于本地开发
- **自动恢复**: 采集失败时保留上次成功数据，非交易日显示"数据截止"

### 2. Build Script (`scripts/build_site.py`)
- 验证 data.json 完整性（检查所有必需字段）
- 复制 index.html + data.json 到 dist/ 目录
- 输出构建摘要

### 3. Frontend (`index.html`)
- **移动优先**: 320px+ 适配，`<400px` 单列布局
- **技术栈**: 纯 HTML/CSS/JS + Chart.js (CDN)
- **暗色主题**: 适合看板场景，渐变卡片设计
- **数据可视化**:
  - 恐慌指数: SVG 环形进度条 + 颜色分级（绿→黄→橙→红）
  - 趋势图: 6 个 Chart.js 折线图（恐慌、北向、成交量、VIX、标普500）
  - 三大指数: 响应式网格卡片
  - 涨跌家数: 两列网格布局
- **状态提示**: 交易中/已收盘/休市自动识别（按 CST 时间）
- **数据注记**: 模拟数据或异常情况自动显示警告条
- **错误处理**: 加载失败显示重试按钮

### 4. GitHub Actions (`.github/workflows/daily.yml`)
- **定时**: 工作日 10:30 UTC (18:30 CST)
- **流程**: 安装依赖 → 采集数据 → 构建站点 → 部署 gh-pages
- **容错**: `continue-on-error: true` 确保部分失败不阻塞部署
- **手动触发**: 支持 workflow_dispatch

## Self-Check Results

| Item | Status |
|------|--------|
| Python scripts parse clean | ✅ No syntax errors |
| data.json matches spec format | ✅ All fields present |
| HTML loads Chart.js via CDN | ✅ v4.4.7 |
| Mobile-first CSS | ✅ 320px+ with 3 breakpoints |
| GH Actions cron correct | ✅ `30 10 * * 1-5` |
| Error handling in fetch | ✅ Fallback to previous data + mock mode |
| Panic index algorithm | ✅ 40/30/30 weights per spec |
| data_note for non-trading day | ✅ Displayed in warning bar |

## How to Use

```bash
# Local preview (mock data)
pip install -r requirements.txt
python scripts/fetch_data.py --mock
python scripts/build_site.py
cd dist && python -m http.server 8000
# Open http://localhost:8000

# Production (GitHub)
# Push to main branch → Actions runs daily at 18:30 CST
# Or manually trigger via GitHub UI
```
