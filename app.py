import streamlit as st
import pandas as pd
from datetime import datetime
import time
import gspread
from google.oauth2.service_account import Credentials
import json

# --- 頁面設定 ---
st.set_page_config(page_title="台股雲端日誌 V3.0", page_icon="☁️", layout="wide")

# --- Google Sheets 設定 ---
# 請確保你的 Google 試算表名稱跟下面這個一樣
SHEET_NAME = "stock_db"

# --- 連線函式 (Connect to Google) ---
def get_google_sheet():
    # 讀取 Secrets
    if "gcp_service_account" not in st.secrets:
        st.error("找不到 Secrets 設定！請檢查 Streamlit 後台。")
        st.stop()

    # 判斷使用者是用哪種方式貼上 Secrets 的
    secrets = st.secrets["gcp_service_account"]
    
    # 如果是用 "json_content" 的偷吃步方法
    if "json_content" in secrets:
        creds_dict = json.loads(secrets["json_content"])
    else:
        # 如果是標準 TOML 格式
        creds_dict = secrets

    # 設定權限範圍
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    try:
        sheet = client.open(SHEET_NAME).sheet1
        return sheet
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"找不到名稱為 '{SHEET_NAME}' 的試算表！請確認 Google Drive 裡的檔名，並確認有共用給機器人。")
        st.stop()

# --- 資料讀寫函式 ---
def load_data():
    sheet = get_google_sheet()
    try:
        # 抓取所有資料
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        # 處理空資料的情況
        if df.empty:
            return pd.DataFrame(columns=["ID", "日期", "策略", "代號", "買入價", "股數", "狀態", "賣出價", "損益", "手續費折數"])
            
        # 強制轉型 ID 為字串 (避免科學記號)
        if "ID" in df.columns:
            df["ID"] = df["ID"].astype(str)
        else:
             # 如果是全新的表，可能沒有 ID，補上空欄位
             pass
             
        return df
    except Exception as e:
        st.error(f"讀取資料失敗: {e}")
        return pd.DataFrame()

def save_data(df):
    sheet = get_google_sheet()
    # 因為 gspread 更新整張表比較快且安全，我們先清空再寫入
    # 為了避免格式跑掉，我們把所有資料轉成字串或標準格式
    sheet.clear()
    
    # 準備寫入的資料 (包含標題)
    # 處理 NaN 空值，轉成空字串
    df_to_save = df.fillna("")
    data = [df_to_save.columns.values.tolist()] + df_to_save.values.tolist()
    
    sheet.update(data)

# --- 側邊欄：新增交易 ---
st.sidebar.header("📝 新增交易 (雲端版)")

trade_date = st.sidebar.date_input("交易日期", datetime.now())
strategy = st.sidebar.selectbox("策略", ["突破追價", "拉回低接", "長期存股", "隔日沖", "抄底失敗"])
stock_id = st.sidebar.text_input("股票代號/名稱", "2330 台積電")
buy_price = st.sidebar.number_input("買入價格", min_value=0.0, step=0.1, format="%.2f")
volume = st.sidebar.number_input("買入股數", min_value=1, value=1000, step=1)
discount = st.sidebar.number_input("手續費折數 (折)", value=2.8, step=0.1)

if st.sidebar.button("➕ 建倉 (寫入雲端)"):
    with st.spinner("正在寫入 Google Sheet..."): # 轉圈圈特效
        df = load_data()
        new_id = str(int(time.time() * 1000))
        
        new_data = {
            "ID": new_id,
            "日期": trade_date.strftime("%Y-%m-%d"),
            "策略": strategy,
            "代號": stock_id,
            "買入價": buy_price,
            "股數": volume,
            "狀態": "持倉中",
            "賣出價": 0.0,
            "損益": 0,
            "手續費折數": discount
        }
        
        df = pd.concat([pd.DataFrame([new_data]), df], ignore_index=True)
        save_data(df)
    
    st.sidebar.success(f"已成功寫入！")
    time.sleep(1)
    st.rerun()

# --- 主畫面 ---
st.title("☁️ 台股雲端日誌 V3.0 (Google Sheet)")

# 讀取資料
# 這裡加個快取，避免每次按按鈕都重讀，但為了即時性，我們暫時不加 @st.cache_data
df = load_data()

tab1, tab2, tab3 = st.tabs(["💼 持倉管理", "📜 歷史戰績", "🗑️ 資料管理"])

# === Tab 1: 持倉管理 ===
with tab1:
    st.subheader("目前庫存部位")
    if not df.empty and "狀態" in df.columns:
        open_positions = df[df["狀態"] == "持倉中"]
        
        if not open_positions.empty:
            st.dataframe(open_positions[["日期", "策略", "代號", "買入價", "股數", "手續費折數"]], use_container_width=True)
            st.markdown("---")
            
            options = {f"{row['代號']} ({row['日期']} 買 {row['股數']}股)": row['ID'] for index, row in open_positions.iterrows()}
            selected_label = st.selectbox("選擇要平倉的部位", list(options.keys()))
            
            if selected_label:
                selected_id = options[selected_label]
                target_row = df[df["ID"] == selected_id].iloc[0]
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    sell_price = st.number_input("賣出價格", min_value=0.0, step=0.1, format="%.2f")
                with col2:
                    current_qty = int(target_row["股數"])
                    sell_qty = st.number_input("賣出股數", min_value=1, max_value=current_qty, value=current_qty)
                with col3:
                    st.markdown("<br>", unsafe_allow_html=True)
                    confirm_sell = st.button("⚡ 執行賣出")

                if confirm_sell:
                    with st.spinner("更新雲端資料庫..."):
                        d_rate = float(target_row["手續費折數"]) / 10
                        buy_cost = int(float(target_row["買入價"]) * sell_qty)
                        buy_fee = max(int(buy_cost * 0.001425 * d_rate), 1)
                        
                        sell_revenue = int(sell_price * sell_qty)
                        sell_fee = max(int(sell_revenue * 0.001425 * d_rate), 1)
                        tax = int(sell_revenue * 0.003)
                        profit = sell_revenue - sell_fee - tax - (buy_cost + buy_fee)
                        
                        # 重新讀取最新的 df 以確保不覆蓋別人改的
                        df = load_data()
                        # 找到對應的 index
                        # 注意：ID 必須轉成字串比對
                        idx_list = df.index[df['ID'].astype(str) == str(selected_id)].tolist()
                        
                        if not idx_list:
                            st.error("找不到該筆資料，可能已被刪除")
                        else:
                            original_idx = idx_list[0]
                            
                            if sell_qty == current_qty:
                                df.at[original_idx, "狀態"] = "已平倉"
                                df.at[original_idx, "賣出價"] = sell_price
                                df.at[original_idx, "損益"] = profit
                                msg = "全數平倉成功！"
                            else:
                                remain_qty = current_qty - sell_qty
                                df.at[original_idx, "股數"] = remain_qty
                                
                                new_closed_record = target_row.copy()
                                new_closed_record["ID"] = str(int(time.time() * 1000))
                                new_closed_record["股數"] = sell_qty
                                new_closed_record["賣出價"] = sell_price
                                new_closed_record["狀態"] = "已平倉"
                                new_closed_record["損益"] = profit
                                
                                df = pd.concat([pd.DataFrame([new_closed_record]), df], ignore_index=True)
                                msg = f"分批賣出 {sell_qty} 股成功！"

                            save_data(df)
                            st.success(msg)
                            time.sleep(1)
                            st.rerun()
        else:
            st.info("目前沒有庫存。")
    else:
        st.info("讀取資料中或是新資料庫...")

# === Tab 2: 歷史戰績 ===
with tab2:
    st.subheader("已實現損益")
    if not df.empty and "狀態" in df.columns:
        closed_positions = df[df["狀態"] == "已平倉"].copy()
        
        if not closed_positions.empty:
            def highlight_profit(val):
                try:
                    color = '#ff4b4b' if float(val) > 0 else '#00c853'
                    return f'color: {color}; font-weight: bold;'
                except:
                    return ''

            display_cols = ["日期", "策略", "代號", "買入價", "賣出價", "股數", "損益"]
            st.dataframe(closed_positions[display_cols].style.applymap(highlight_profit, subset=['損益']), use_container_width=True)
        else:
            st.info("尚未有平倉紀錄")

# === Tab 3: 資料管理 ===
with tab3:
    st.subheader("🗑️ 刪除或修正資料")
    if not df.empty:
        st.dataframe(df)
        delete_options = {f"[{row['狀態']}] {row['日期']} - {row['代號']}": row['ID'] for index, row in df.iterrows()}
        
        if delete_options:
            delete_id = st.selectbox("選擇要刪除的紀錄", list(delete_options.keys()))
            if st.button("❌ 確認刪除"):
                with st.spinner("正在刪除..."):
                    real_delete_id = delete_options[delete_id]
                    df = df[df["ID"].astype(str) != str(real_delete_id)]
                    save_data(df)
                st.error("已刪除！")
                time.sleep(1)
                st.rerun()