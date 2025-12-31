import streamlit as st
import pandas as pd
from datetime import datetime
import time
import gspread
from google.oauth2.service_account import Credentials
import json
import plotly.express as px
import yfinance as yf

# --- 頁面設定 ---
st.set_page_config(
    page_title="台股戰情室 V8.1", 
    page_icon="📱", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- Session State 初始化 ---
if "realtime_prices" not in st.session_state:
    st.session_state.realtime_prices = {}
if "price_update_time" not in st.session_state:
    st.session_state.price_update_time = None
if "debug_logs" not in st.session_state:
    st.session_state.debug_logs = []

# --- Google Sheets 設定 ---
SHEET_ID = "1-NbOD6TcHiRVDzWB5MXq6JVo7B73o31mPPPmltph_CA"

# --- 連線函式 ---
def get_google_sheet():
    if "gcp_service_account" not in st.secrets:
        st.error("找不到 Secrets 設定！")
        st.stop()

    secrets = st.secrets["gcp_service_account"]
    
    if "json_content" in secrets:
        creds_dict = json.loads(secrets["json_content"])
    else:
        creds_dict = secrets

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    try:
        sheet = client.open_by_key(SHEET_ID).sheet1
        return sheet
    except Exception as e:
        st.error(f"連線失敗！錯誤訊息: {e}")
        st.stop()

# --- 資料讀寫函式 ---
def load_data():
    sheet = get_google_sheet()
    try:
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        columns = ["ID", "日期", "買入日期", "策略", "代號", "買入價", "股數", "狀態", "賣出價", "損益", "手續費折數", "心得"]
        
        if df.empty:
            return pd.DataFrame(columns=columns)
            
        for col in columns:
            if col not in df.columns:
                df[col] = ""
        
        df = df[columns]

        if "ID" in df.columns:
            df["ID"] = df["ID"].astype(str)
        
        if "買入日期" in df.columns:
            df["買入日期"] = df["買入日期"].replace(r'^\s*$', pd.NA, regex=True)
            df["買入日期"] = df["買入日期"].fillna(df["日期"])
        
        df["買入價"] = pd.to_numeric(df["買入價"], errors='coerce').fillna(0.0)
        df["股數"] = pd.to_numeric(df["股數"], errors='coerce').fillna(0)
        df["手續費折數"] = pd.to_numeric(df["手續費折數"], errors='coerce').fillna(3.0) 
        df["心得"] = df["心得"].fillna("")
            
        return df
    except Exception as e:
        st.error(f"讀取資料發生錯誤: {e}")
        return pd.DataFrame(columns=["ID", "日期", "買入日期", "策略", "代號", "買入價", "股數", "狀態", "賣出價", "損益", "手續費折數", "心得"])

def save_data(df):
    sheet = get_google_sheet()
    sheet.clear()
    df_to_save = df.fillna("")
    if "日期" in df_to_save.columns:
        df_to_save["日期"] = df_to_save["日期"].astype(str)
    if "買入日期" in df_to_save.columns:
        df_to_save["買入日期"] = df_to_save["買入日期"].astype(str)
        
    data = [df_to_save.columns.values.tolist()] + df_to_save.values.tolist()
    sheet.update(data)

# --- 報價抓取函式 ---
def get_realtime_prices(stock_codes):
    if not stock_codes:
        return {}, []
    
    prices = {}
    logs = []
    
    for code in stock_codes:
        suffixes = ['.TW', '.TWO']
        price_found = False
        
        for suffix in suffixes:
            try:
                ticker_name = f"{code}{suffix}"
                stock = yf.Ticker(ticker_name)
                
                current_price = None
                if hasattr(stock, 'fast_info') and 'last_price' in stock.fast_info:
                    p = stock.fast_info['last_price']
                    if p is not None and p > 0:
                        current_price = p
                
                if current_price is None:
                    hist = stock.history(period="5d")
                    if not hist.empty:
                        current_price = hist['Close'].iloc[-1]
                
                if current_price is not None:
                    prices[code] = float(current_price)
                    logs.append(f"✅ {code}: {current_price:.2f}")
                    price_found = True
                    break 
                
            except Exception as e:
                continue
        
        if not price_found:
            logs.append(f"❌ {code}: 查無資料")
            
    return prices, logs

# --- 讀取資料 ---
df = load_data()

# --- 側邊欄 ---
st.sidebar.header("📝 新增交易")

trade_date = st.sidebar.date_input("交易日期", datetime.now())
strategy = st.sidebar.selectbox("策略", ["Alpha-Swing", "突破追價", "拉回低接", "長期存股", "隔日沖"])
stock_id_input = st.sidebar.text_input("代號 (如: 2330)", "2330") 
stock_name_input = st.sidebar.text_input("名稱 (選填)", "台積電")
stock_full_name = f"{stock_id_input} {stock_name_input}"
buy_price = st.sidebar.number_input("買入價格", min_value=0.0, step=0.1, format="%.2f")
volume = st.sidebar.number_input("股數", min_value=1, value=1000, step=1)
discount = st.sidebar.number_input("手續費折數", value=2.8, step=0.1)

if st.sidebar.button("➕ 建倉", use_container_width=True):
    with st.spinner("寫入中..."):
        df_fresh = load_data() 
        new_id = str(int(time.time() * 1000))
        date_str = trade_date.strftime("%Y-%m-%d")
        
        new_data = {
            "ID": new_id,
            "日期": date_str,
            "買入日期": date_str,
            "策略": strategy,
            "代號": stock_full_name,
            "買入價": buy_price,
            "股數": volume,
            "狀態": "持倉中",
            "賣出價": 0.0,
            "損益": 0,
            "手續費折數": discount,
            "心得": ""
        }
        
        df_fresh = pd.concat([pd.DataFrame([new_data]), df_fresh], ignore_index=True)
        save_data(df_fresh)
    
    st.sidebar.success(f"建倉成功！")
    time.sleep(1)
    st.rerun()

st.sidebar.markdown("---")

# --- 側邊欄出場試算機 ---
st.sidebar.header("🧮 出場試算機")
if not df.empty and "狀態" in df.columns:
    open_ops = df[df["狀態"] == "持倉中"]
    if not open_ops.empty:
        calc_options = {f"{row['代號']} (成本 {row['買入價']})": index for index, row in open_ops.iterrows()}
        selected_calc_idx = st.sidebar.selectbox("選擇庫存", list(calc_options.keys()))
        
        if selected_calc_idx is not None:
            target_pos = open_ops.loc[calc_options[selected_calc_idx]]
            cost_p = float(target_pos["買入價"])
            qty_h = int(target_pos["股數"])
            disc_h = float(target_pos["手續費折數"]) / 10.0
            
            target_sell_price = st.sidebar.number_input("目標賣出價", value=cost