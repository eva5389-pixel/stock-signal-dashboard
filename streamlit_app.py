"""台股多因子交易訊號 Dashboard 範本。"""

from pathlib import Path

import pandas as pd
import streamlit as st


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
    keyword = st.text_input("搜尋股票", placeholder="輸入代號或名稱")
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
