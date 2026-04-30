#!/usr/bin/env python3
"""
Market Sentiment Data Fetcher v2
适配 AKShare 1.18.x 和 yfinance，含多层降级策略
"""

import json, os, sys, time, random
from datetime import datetime, timedelta, date
from pathlib import Path

HAVE_AKSHARE = False
HAVE_YFINANCE = False
HAVE_PANDAS = False
try:
    import akshare as ak; HAVE_AKSHARE = True
except ImportError: pass
try:
    import yfinance as yf; HAVE_YFINANCE = True
except ImportError: pass
try:
    import pandas as pd; HAVE_PANDAS = True
except ImportError: pass

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATA_FILE = DATA_DIR / "data.json"
PREVIOUS_FILE = DATA_DIR / "data.previous.json"

def load_previous() -> dict:
    if PREVIOUS_FILE.exists():
        try: return json.loads(PREVIOUS_FILE.read_text(encoding="utf-8"))
        except: pass
    return {}

def save_current(data: dict):
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    PREVIOUS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

MOCK = {
    "indexes": [
        {"name": "上证指数", "code": "000001", "price": 4086.34, "change_pct": 0.16},
        {"name": "深证成指", "code": "399001", "price": 10520.55, "change_pct": -0.42},
        {"name": "创业板指", "code": "399006", "price": 2180.34, "change_pct": -0.88}
    ],
    "sentiment": {"up_count": 1650, "down_count": 1950, "limit_up": 60, "limit_down": 30},
    "north_flow": {"value": 18.5, "unit": "亿", "history": [32, 28, 45, -12, 20, 55, 18.5]},
    "volume": {"value": 8950, "unit": "亿", "vs_20day_avg": -8.5, "history": [8200, 9100, 8800, 10200, 7800, 8500, 8950]},
    "panic_history": [35, 38, 32, 28, 30, 34, 32],
    "vix": {"value": 18.52, "change_pct": 2.1, "history": [16.5, 17.2, 16.8, 17.5, 18.0, 18.1, 18.5]},
    "sp500": {"value": 5420.15, "change_pct": 0.45, "history": [5380, 5400, 5390, 5410, 5405, 5415, 5420]}
}

# ── A 股采集 ──

def safe_call(fn, default=None, retries=2):
    for i in range(retries):
        try:
            result = fn()
            if result is not None:
                return result
        except Exception as e:
            print(f"  [WARN] 第{i+1}次尝试失败: {type(e).__name__}", file=sys.stderr)
            time.sleep(1)
    return default

def fetch_indexes():
    """尝试用 stock_zh_index_daily 或 stock_zh_index_spot_em 获取三大指数"""
    # 方案A: stock_zh_index_spot_em (实时快照)
    try:
        df = ak.stock_zh_index_spot_em()
        if df is not None and not df.empty:
            name_map = {"上证指数": "000001", "深证成指": "399001", "创业板指": "399006"}
            results = []
            for _, row in df.iterrows():
                name = str(row.get("名称", ""))
                if name in name_map:
                    results.append({
                        "name": name,
                        "code": name_map[name],
                        "price": round(float(row.get("最新价", 0)), 2),
                        "change_pct": round(float(row.get("涨跌幅", 0)), 2)
                    })
            if len(results) >= 2:
                return results
    except Exception as e:
        print(f"  [WARN] 方案A(spot_em)失败: {e}", file=sys.stderr)

    # 方案B: stock_zh_index_daily_em 带重试
    for sym, name in [("sh000001", "上证指数"), ("sz399001", "深证成指"), ("sz399006", "创业板指")]:
        for i in range(2):
            try:
                df = ak.stock_zh_index_daily_em(symbol=sym)
                if df is not None and not df.empty and "close" in df.columns:
                    row = df.iloc[-1]
                    return [{
                        "name": name, "code": sym[2:],
                        "price": round(float(row["close"]), 2),
                        "change_pct": round(float(row.get("pctChg", 0)), 2)
                    }]
            except:
                time.sleep(1)

    return None  # 降级

def fetch_sentiment():
    """涨跌家数 + 涨停跌停"""
    result = {"up_count": 0, "down_count": 0, "limit_up": 0, "limit_down": 0}
    try:
        # 涨停板
        today = date.today().strftime("%Y%m%d")
        zt = ak.stock_zt_pool_em(date=today)
        if zt is not None and not zt.empty:
            result["limit_up"] = len(zt)
    except: pass
    try:
        dt = ak.stock_zt_pool_dtgc_em(date=today)
        if dt is not None and not dt.empty:
            result["limit_down"] = len(dt)
    except: pass

    # 涨跌家数 — 用 stock_zh_a_spot_em 可能被限，降级到昨晚数据
    try:
        df = ak.stock_zh_a_spot_em()
        if df is not None and not df.empty and "涨跌幅" in df.columns:
            result["up_count"] = int((df["涨跌幅"] > 0).sum())
            result["down_count"] = int((df["涨跌幅"] < 0).sum())
    except:
        pass  # 保持0值，后面fallback
    return result

def fetch_north_flow_new():
    """北向资金 - 使用 stock_hsgt_fund_flow_summary_em + stock_hsgt_hist_em"""
    result = {"value": 0, "unit": "亿", "history": []}
    try:
        df = ak.stock_hsgt_fund_flow_summary_em()
        if df is not None and not df.empty:
            # 取沪股通+深股通北向合计
            north = df[df["资金方向"] == "北向"]
            total = north["成交净买额"].sum()
            result["value"] = round(float(total), 2)
    except Exception as e:
        print(f"  [WARN] 北向当日失败: {e}", file=sys.stderr)

    try:
        hist = ak.stock_hsgt_hist_em(symbol="沪股通")
        if hist is not None and not hist.empty and "当日成交净买额" in hist.columns:
            vals = hist["当日成交净买额"].dropna().tail(7).tolist()
            result["history"] = [round(float(v), 2) for v in vals]
    except: pass
    return result

def fetch_volume_new():
    """成交量 — 无直接API时用mock"""
    return None

def calc_panic(sentiment, volume):
    up = sentiment.get("up_count", 1) or 1
    down = sentiment.get("down_count", 1) or 1
    lu = sentiment.get("limit_up", 1) or 1
    ld = sentiment.get("limit_down", 0) or 0

    total = up + down
    up_ratio = up / total if total > 0 else 0.5
    ratio_score = (1 - up_ratio) * 100

    zt_total = lu + ld
    down_ratio = ld / zt_total if zt_total > 0 else 0.5
    zt_score = down_ratio * 100

    vs = volume.get("vs_20day_avg", 0) if volume else 0
    if vs < -30: vol_score = 100
    elif vs < -10: vol_score = 70
    elif vs < 0: vol_score = 50
    elif vs < 20: vol_score = 30
    else: vol_score = 10

    pv = round(ratio_score * 0.4 + zt_score * 0.3 + vol_score * 0.3, 1)
    pv = max(0, min(100, pv))

    if pv < 20: lbl = "乐观"
    elif pv < 40: lbl = "平稳"
    elif pv < 60: lbl = "恐慌"
    elif pv < 80: lbl = "恐惧"
    else: lbl = "极度恐慌"

    return {"value": pv, "label": lbl}

# ── 美股 ──

def fetch_us():
    result = {"vix": {"value": 0, "change_pct": 0, "history": []},
              "sp500": {"value": 0, "change_pct": 0, "history": []}}
    if not HAVE_YFINANCE:
        return result
    for i in range(3):
        try:
            vix = yf.Ticker("^VIX")
            vh = vix.history(period="7d")
            if vh.empty: continue
            result["vix"]["value"] = round(float(vh["Close"].iloc[-1]), 2)
            if len(vh) >= 2:
                result["vix"]["change_pct"] = round(
                    (vh["Close"].iloc[-1] - vh["Close"].iloc[-2]) / vh["Close"].iloc[-2] * 100, 2)
            result["vix"]["history"] = [round(float(v), 2) for v in vh["Close"].values]

            sp = yf.Ticker("^GSPC")
            sh = sp.history(period="7d")
            if sh.empty: continue
            result["sp500"]["value"] = round(float(sh["Close"].iloc[-1]), 2)
            if len(sh) >= 2:
                result["sp500"]["change_pct"] = round(
                    (sh["Close"].iloc[-1] - sh["Close"].iloc[-2]) / sh["Close"].iloc[-2] * 100, 2)
            result["sp500"]["history"] = [round(float(v), 2) for v in sh["Close"].values]
            return result
        except Exception as e:
            print(f"  [WARN] 美股第{i+1}次尝试失败: {type(e).__name__}", file=sys.stderr)
            time.sleep(3)
    return result

# ── 主流程 ──

def main():
    use_mock = "--mock" in sys.argv
    prev = load_previous()

    if use_mock or (not HAVE_AKSHARE and not HAVE_YFINANCE):
        print("[INFO] 使用模拟数据")
        data = {
            "update_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "data_note": "模拟数据 — 数据源不可用",
            "a_share": {
                "indexes": MOCK["indexes"],
                "market_sentiment": MOCK["sentiment"],
                "panic_index": {"value": 32, "label": "平稳", "history": MOCK["panic_history"]},
                "north_flow": MOCK["north_flow"],
                "volume": MOCK["volume"]
            },
            "us_market": {"vix": MOCK["vix"], "sp500": MOCK["sp500"]}
        }
        save_current(data)
        print(f"[OK] 模拟数据已保存")
        return

    print("[INFO] 开始采集真实数据...")
    data = {"update_time": datetime.now().strftime("%Y-%m-%d %H:%M")}

    # A股
    print("  指数...", end=" ", flush=True)
    indexes = safe_call(fetch_indexes)
    if not indexes:
        print("⚠ 降级使用缓存/模拟")
        indexes = prev.get("a_share", {}).get("indexes", [])
    else:
        print(f"✅ {len(indexes)}条")

    print("  涨跌家数/涨停...", end=" ", flush=True)
    sentiment = safe_call(fetch_sentiment)
    if not sentiment or sentiment["up_count"] == 0:
        # API 不可用时，优先用上一个交易日数据
        prev_sent = prev.get("a_share", {}).get("market_sentiment", {})
        if prev_sent.get("up_count", 0) > 0:
            sentiment = dict(prev_sent)
            print("⚠ 使用上一交易日涨跌家数数据")
        else:
            sentiment = {"up_count": 0, "down_count": 0, "limit_up": 0, "limit_down": 0}
            print("⚠ 涨跌家数数据暂不可用（无历史缓存）")
        # 用真实涨停跌停覆盖（该API通常可用）
        try:
            t = date.today().strftime("%Y%m%d")
            zt = ak.stock_zt_pool_em(date=t)
            if zt is not None: sentiment["limit_up"] = len(zt)
            dt = ak.stock_zt_pool_dtgc_em(date=t)
            if dt is not None: sentiment["limit_down"] = len(dt)
        except: pass
        print("  涨停:" + str(sentiment["limit_up"]) + " 跌停:" + str(sentiment["limit_down"]))
    else:
        print("✅ 上涨:" + str(sentiment["up_count"]) + " 下跌:" + str(sentiment["down_count"]))

    print("  北向资金...", end=" ", flush=True)
    nf = safe_call(fetch_north_flow_new)
    if not nf or nf["value"] == 0:
        print("⚠ 北向资金暂不可用，使用上一交易日数据")
        prev_nf = prev.get("a_share", {}).get("north_flow", {})
        if prev_nf.get("value", 0) > 0:
            nf = prev_nf
        else:
            nf = {"value": 0, "unit": "亿", "history": []}
    else:
        print(f"✅ {nf['value']}亿")

    prev_vol = prev.get("a_share", {}).get("volume", {})
    if prev_vol.get("value", 0) > 0:
        volume = prev_vol
    else:
        volume = dict(MOCK["volume"])

    print("  恐慌指数...", end=" ", flush=True)
    panic = calc_panic(sentiment, volume)
    ph = prev.get("a_share", {}).get("panic_index", {}).get("history", [])
    panic["history"] = (ph + [panic["value"]])[-7:]
    if not panic["history"]:
        panic["history"] = MOCK["panic_history"]
    print(f"✅ {panic['value']} ({panic['label']})")

    # 美股
    print("  美股(VIX/标普500)...", end=" ", flush=True)
    us = safe_call(fetch_us, retries=1)
    if not us or us["vix"]["value"] == 0:
        print("⚠ 美股数据暂不可用，使用上一交易日数据")
        prev_us = prev.get("us_market", {})
        if prev_us.get("vix", {}).get("value", 0) > 0:
            us = prev_us
        else:
            us = {"vix": {"value": 0, "change_pct": 0, "history": []}, "sp500": {"value": 0, "change_pct": 0, "history": []}}
    else:
        print(f"✅ VIX:{us['vix']['value']} SP500:{us['sp500']['value']}")

    data["a_share"] = {
        "indexes": indexes,
        "market_sentiment": sentiment,
        "panic_index": panic,
        "north_flow": nf,
        "volume": volume
    }
    data["us_market"] = us

    # 数据源标注
    notes = []
    if data["a_share"]["market_sentiment"].get("up_count", 0) == 0 and data["a_share"]["market_sentiment"].get("down_count", 0) == 0:
        notes.append("涨跌家数暂无数据（首次运行或数据源异常）")
    if data["us_market"]["vix"]["value"] == 0:
        notes.append("美股数据暂不可用，使用上一交易日数据")
    if notes:
        data["data_note"] = "; ".join(notes)

    save_current(data)
    print(f"\n[OK] 数据已保存到 {DATA_FILE}")
    if data.get("data_note"):
        print(f"[NOTE] {data['data_note']}")

if __name__ == "__main__":
    main()
