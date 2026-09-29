# 台股多因子交易訊號 Dashboard

這是一個可在瀏覽器開啟的 Streamlit 網頁模板。內建示範資料，也可上傳同欄位格式的 CSV。

## 啟動方式（Mac）

在終端機執行：

```bash
cd /Users/evalin5310/.codex/.chatgpt-projects/g-p-6a6af6fcc7648191991528c986ed5892/stock-signal-dashboard
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m streamlit run streamlit_app.py
```

啟動後通常會自動開啟：<http://localhost:8501>

## 資料更新

1. 複製 `sample_stocks.csv` 的欄位格式。
2. 填入證交所／櫃買中心法人資料、技術指標與基本面數字。
3. 在左側上傳 CSV，Dashboard 會自動計分。

訊號只作篩選及風險管理用途，不構成投資建議。
