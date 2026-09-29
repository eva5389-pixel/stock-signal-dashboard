"""台股多因子交易訊號 Dashboard 範本。"""

from pathlib import Path

import pandas as pd
import streamlit as st
import yfinance as yf


APP_DIR = Path(__file__).parent
DATA_FILE = APP_DIR / "sample_stocks.csv"

st.set_page_config(
    page_title="台股多因子交易訊號",
    page_icon=":material/candlestick_chart:",
    layout="wide",
)


@st.cache_data
def load_sample_data() -> pd.DataFrame:
    return pd.read_csv(DATA_FILE)


@st.cache_data(ttl="15m", show_spinner="正在取得股價資料…")
def load_market_snapshot(symbol: str) -> dict[str, object]:
    """從 Yahoo Finance 取得技術面快照；法人資料另由官方來源補充。"""
    ticker = yf.Ticker(symbol)
    history = ticker.history(period="6mo", auto_adjust=True)
    if history.empty or len(history) < 61:
        raise ValueError("找不到足夠的歷史行情，請確認代號，例如 2330.TW 或 6488.TWO。")

    close = history["Close"].dropna()
    volume = history["Volume"].dropna()
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()
    delta = close.diff()
    gains = delta.clip(lower=0).rolling(14).mean()
    losses = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gains / losses.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))

    latest = float(close.iloc[-1])
    previous_20_high = float(close.iloc[-21:-1].max())
    recent_20_low = float(close.iloc[-20:].min())
    volume_ratio = float(volume.iloc[-1] / volume.iloc[-20:].mean())
    info = ticker.fast_info
    return {
        "symbol": symbol,
        "name": ticker.info.get("longName") or ticker.info.get("shortName") or symbol,
        "price": latest,
        "change_pct": (latest / float(close.iloc[-2]) - 1) * 100,
        "ma20": float(ma20.iloc[-1]),
        "ma60": float(ma60.iloc[-1]),
        "above_ma": bool(latest > ma20.iloc[-1] and latest > ma60.iloc[-1]),
        "ma20_up": bool(ma20.iloc[-1] > ma20.iloc[-6]),
        "breakout": bool(latest > previous_20_high),
        "previous_20_high": previous_20_high,
        "recent_20_low": recent_20_low,
        "stop_reference": max(recent_20_low, latest * 0.92),
        "rsi": float(rsi.iloc[-1]),
        "volume_ratio": volume_ratio,
        "currency": info.get("currency", "TWD"),
        "date": history.index[-1].strftime("%Y-%m-%d"),
    }


def technical_recommendation(snapshot: dict[str, object]) -> dict[str, object]:
    """只依可驗證的價格與成交量產生暫定操作建議。"""
    points = 0
    points += 20 if snapshot["above_ma"] else 0
    points += 10 if snapshot["ma20_up"] else 0
    points += 10 if snapshot["breakout"] else 0
    points += 10 if 50 <= snapshot["rsi"] <= 70 else 0
    points += 5 if snapshot["volume_ratio"] >= 1.3 else 0

    cautions: list[str] = []
    if snapshot["rsi"] > 75:
        cautions.append("RSI 過熱，不宜追價")
    if snapshot["volume_ratio"] >= 2 and not snapshot["breakout"]:
        cautions.append("爆量但未突破，留意上方賣壓")

    if points >= 45 and not cautions:
        label = "技術偏多／分批觀察"
        action = "突破確認後先配置預定部位40%；回測支撐不破再加30%，再創高且量價續強才補足剩餘30%。"
    elif points >= 30:
        label = "偏多但等待確認"
        action = "暫不追價；等待回測20日均線止穩，或帶量突破前20日高點後再分批觀察。"
    elif snapshot["above_ma"]:
        label = "中性觀望"
        action = "價格仍在均線之上，但動能不足；等待RSI與成交量改善，不先建立新部位。"
    else:
        label = "技術轉弱／暫時避開"
        action = "尚未站回20與60日均線，不建立新部位；既有部位可依前低或停損參考價管理風險。"

    if cautions:
        action = f"{action} 注意：{'；'.join(cautions)}。"
    return {"points": points, "label": label, "action": action}


def score_row(row: pd.Series) -> int:
    """依法人、趨勢、基本面、量能與市場環境計算 0–100 分。"""
    score = 0

    # 法人動向：30 分
    score += 20 if row["法人5日買超占成交量%"] >= 3 else 10 if row["法人5日買超占成交量%"] > 0 else 0
    score += 5 if row["法人連買日數"] >= 3 else 0
    score += 5 if bool(row["外資投信同買"]) else 0

    # 價格趨勢：25 分
    score += 10 if bool(row["站上20日與60日均線"]) else 0
    score += 5 if bool(row["20日均線向上"]) else 0
    score += 5 if bool(row["突破20日高點"]) else 0
    score += 5 if 50 <= row["RSI"] <= 70 else 0

    # 基本面：20 分
    score += 7 if row["營收年增%"] > 0 else 0
    score += 7 if row["獲利年增%"] > 0 else 0
    score += 6 if bool(row["ROE與自由現金流健康"]) else 0

    # 成交量與動能：15 分
    score += 10 if row["成交量/20日均量"] >= 1.3 else 5 if row["成交量/20日均量"] >= 1 else 0
    score += 5 if not bool(row["爆量長上影"]) else 0

    # 大盤與產業：10 分
    score += 5 if bool(row["大盤多頭"]) else 0
    score += 5 if bool(row["產業多頭"]) else 0
    return min(int(score), 100)


def signal_from_score(score: int) -> str:
    if score >= 80:
        return "買進候選"
    if score >= 65:
        return "偏多／等回檔"
    if score >= 45:
        return "觀望"
    if score >= 30:
        return "減碼"
    return "賣出／避開"


def action_from_signal(signal: str) -> str:
    return {
        "買進候選": "突破40% → 回測30% → 再創高30%",
        "偏多／等回檔": "等回測20日線且量縮",
        "觀望": "等待量價與法人同步",
        "減碼": "先減碼50%，觀察60日線",
        "賣出／避開": "退出或暫不進場",
    }[signal]


def calculate_dashboard(df: pd.DataFrame, account_risk_pct: float) -> pd.DataFrame:
    result = df.copy()
    result["總分"] = result.apply(score_row, axis=1)
    result["訊號"] = result["總分"].map(signal_from_score)
    result["建議操作"] = result["訊號"].map(action_from_signal)
    result["最大部位%"] = (account_risk_pct / result["停損距離%"].clip(lower=0.1) * 100).clip(upper=25)
    return result.sort_values(["總分", "法人5日買超占成交量%"], ascending=False)


st.title(":material/candlestick_chart: 台股多因子交易訊號")
st.caption("法人籌碼 × 價格趨勢 × 基本面 × 成交量 × 市場環境")

with st.sidebar:
    st.header("資料與風險設定")
    with st.form("live_lookup_form"):
        live_symbol = st.text_input(
            "即時股票代號",
            placeholder="例如 2330.TW、6488.TWO",
        ).strip().upper()
        lookup_submitted = st.form_submit_button(
            ":material/search: 查詢技術資料",
            type="primary",
            width="stretch",
        )
    uploaded = st.file_uploader("上傳股票資料 CSV", type="csv")
    account_risk_pct = st.slider(
        "單筆最大風險（占總資金）",
        min_value=0.25,
        max_value=2.0,
        value=1.0,
        step=0.25,
        format="%.2f%%",
    )
    st.info("未上傳檔案時使用示範資料。CSV 欄位格式可參考專案內的 sample_stocks.csv。")

if lookup_submitted:
    st.session_state["lookup_symbol"] = live_symbol

lookup_symbol = st.session_state.get("lookup_symbol", "")
if lookup_symbol:
    try:
        snapshot = load_market_snapshot(lookup_symbol)
        recommendation = technical_recommendation(snapshot)
        with st.container(border=True):
            st.subheader(f"{snapshot['name']}（{snapshot['symbol']}）")
            st.caption(f"Yahoo Finance 行情日期：{snapshot['date']}｜法人資料尚未串接，因此不產生完整買賣評分。")
            with st.container(horizontal=True):
                st.metric(
                    "收盤價",
                    f"{snapshot['price']:.2f} {snapshot['currency']}",
                    f"{snapshot['change_pct']:+.2f}%",
                    border=True,
                )
                st.metric("RSI（14日）", f"{snapshot['rsi']:.1f}", border=True)
                st.metric("成交量／20日均量", f"{snapshot['volume_ratio']:.2f}×", border=True)
                st.metric(
                    "20／60日均線",
                    "站上" if snapshot["above_ma"] else "尚未站上",
                    border=True,
                )
            checks = pd.DataFrame(
                {
                    "技術條件": ["站上20與60日均線", "20日均線向上", "突破前20日高點", "RSI介於50–70"],
                    "結果": [
                        snapshot["above_ma"],
                        snapshot["ma20_up"],
                        snapshot["breakout"],
                        50 <= snapshot["rsi"] <= 70,
                    ],
                }
            )
            st.dataframe(checks, hide_index=True)
            st.subheader(":material/strategy: 暫定建議操作")
            st.markdown(f"**{recommendation['label']}**（技術條件 {recommendation['points']}／55 分）")
            st.write(recommendation["action"])
            with st.container(horizontal=True):
                st.metric(
                    "前20日高點",
                    f"{snapshot['previous_20_high']:.2f} {snapshot['currency']}",
                    border=True,
                )
                st.metric(
                    "停損參考價",
                    f"{snapshot['stop_reference']:.2f} {snapshot['currency']}",
                    f"{(snapshot['stop_reference'] / snapshot['price'] - 1) * 100:.1f}%",
                    delta_color="inverse",
                    border=True,
                )
            st.caption("此建議只使用價格、均線、RSI與成交量。法人、財報及產業資料未補齊前，不會標示為完整買進或賣出訊號。")
    except Exception as exc:
        st.warning(f"無法查詢 {lookup_symbol}：{exc}")

try:
    raw = pd.read_csv(uploaded) if uploaded is not None else load_sample_data()
    scored = calculate_dashboard(raw, account_risk_pct)
except (KeyError, ValueError, pd.errors.ParserError) as exc:
    st.error(f"資料格式不正確：{exc}")
    st.stop()

markets = ["全部", *sorted(scored["市場"].dropna().unique().tolist())]
signals = ["全部", "買進候選", "偏多／等回檔", "觀望", "減碼", "賣出／避開"]

filter_row = st.container(horizontal=True)
with filter_row:
    keyword = st.text_input("篩選目前清單", placeholder="輸入清單內的代號或名稱")
    market = st.selectbox("市場", markets)
    signal = st.selectbox("訊號", signals)

filtered = scored.copy()
if keyword:
    mask = (
        filtered["股票代號"].astype(str).str.contains(keyword, case=False, na=False)
        | filtered["股票名稱"].astype(str).str.contains(keyword, case=False, na=False)
    )
    filtered = filtered[mask]
if market != "全部":
    filtered = filtered[filtered["市場"] == market]
if signal != "全部":
    filtered = filtered[filtered["訊號"] == signal]

if filtered.empty:
    st.info("目前載入的清單沒有符合項目。若要查詢其他股票，請使用左側的「即時股票代號」。")

with st.container(horizontal=True):
    st.metric("買進候選", int((scored["訊號"] == "買進候選").sum()), border=True)
    st.metric("偏多／等回檔", int((scored["訊號"] == "偏多／等回檔").sum()), border=True)
    st.metric("觀望", int((scored["訊號"] == "觀望").sum()), border=True)
    st.metric("減碼／賣出", int(scored["訊號"].isin(["減碼", "賣出／避開"]).sum()), border=True)

left, right = st.columns([3, 2])
with left:
    with st.container(border=True):
        st.subheader("股票評分排名")
        display_columns = [
            "股票代號", "股票名稱", "市場", "總分", "訊號",
            "法人5日買超占成交量%", "法人連買日數", "RSI",
            "成交量/20日均量", "停損距離%", "最大部位%", "建議操作",
        ]
        st.dataframe(
            filtered[display_columns],
            hide_index=True,
            column_config={
                "總分": st.column_config.ProgressColumn("總分", min_value=0, max_value=100),
                "法人5日買超占成交量%": st.column_config.NumberColumn("法人5日%", format="%.2f%%"),
                "成交量/20日均量": st.column_config.NumberColumn("量比", format="%.2fx"),
                "停損距離%": st.column_config.NumberColumn("停損距離", format="%.1f%%"),
                "最大部位%": st.column_config.NumberColumn("最大部位", format="%.1f%%"),
            },
        )

with right:
    with st.container(border=True):
        st.subheader("訊號分布")
        signal_order = ["買進候選", "偏多／等回檔", "觀望", "減碼", "賣出／避開"]
        counts = scored["訊號"].value_counts().reindex(signal_order, fill_value=0).rename_axis("訊號").reset_index(name="股票數")
        st.bar_chart(counts, x="訊號", y="股票數", horizontal=True)

with st.expander("查看評分規則"):
    st.markdown(
        """
        - **法人動向 30%**：5日買超占成交量、連買日數、外資與投信同買。
        - **價格趨勢 25%**：站上20／60日均線、20日線向上、突破20日高點、RSI 50–70。
        - **基本面 20%**：營收與獲利年增、ROE與自由現金流。
        - **成交量 15%**：量比及是否出現爆量長上影。
        - **市場環境 10%**：大盤與所屬產業趨勢。
        """
    )

st.warning("本工具只作為篩選與交易紀律模板，不保證報酬，也不構成個別投資建議。")
