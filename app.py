import streamlit as st
import pandas as pd
from datetime import datetime
import time
import gspread
from google.oauth2.service_account import Credentials
import json

# --- 頁面設定 ---
st.set_page_config(page_title="台股雲端日誌 V3.1", page_icon="☁️", layout="wide")

# --- Google Sheets 設定 (改用 ID) ---
# ⚠️ 請把下面這串換成你剛剛複製的 ID
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
        # ⚠️ 關鍵修改：改用 open_by_key (直接抓ID，不搜尋檔名)
        sheet = client.open_by_key(SHEET_ID).sheet1
        return sheet
    except Exception as e:
        st.error(f"連線失敗！請檢查 ID 是否正確，或是否忘記共用給機器人。\n錯誤訊息: {e}")
        st.stop()

# --- 資料讀寫函式 ---
def load_data():
    sheet = get_google_sheet()
    try:
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        if df.empty:
            return pd.DataFrame(columns=["ID", "日期", "策略", "代號", "買入價", "股數", "狀態", "賣出價", "損益", "手續費折數"])
            
        if "ID" in df.columns:
            df["ID"] = df["ID"].astype(str)
             
        return df
    except Exception as e:
        # 如果是全新的表，get_all_records 可能會因為標題列也沒有而報錯，這裡做個防護
        return pd.DataFrame(columns=["ID", "日期", "策略", "代號", "買入價", "股數", "狀態", "賣出價", "損益", "手續費折數"])

def save_data(df):
    sheet = get_google_sheet()
    sheet.clear()
    df_to_save = df.fillna("")
    # 將 DataFrame 轉換為 list of lists，並包含標題
    data = [df_to_save.columns.values.tolist()] + df_to_save.values.tolist()
    sheet.update(data)

# --- 側邊欄：新增交易 ---
st.sidebar.header("📝 新增交易 (雲端 ID 版)")

trade_date = st.sidebar.date_input("交易日期", datetime.now())
strategy = st.sidebar.selectbox("策略", ["突破追價", "拉回低接", "長期存股", "隔日沖", "抄底失敗"])
stock_id = st.sidebar.text_input("股票代號/名稱", "2330 台積電")
buy_price = st.sidebar.number_input("買入價格", min_value=0.0, step=0.1, format="%.2f")
volume = st.sidebar.number_input("買入股數", min_value=1, value=1000, step=1)
discount = st.sidebar.number_input("手續費折數 (折)", value=2.8, step=0.1)

if st.sidebar.button("➕ 建倉 (寫入雲端)"):
    with st.spinner("正在寫入 Google Sheet..."):
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
st.title("☁️ 台股雲端日誌 V3.1 (ID直連版)")

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
                # ID 比對修正
                target_row = df[df["ID"].astype(str) == str(selected_id)].iloc[0]
                
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
                        
                        df = load_data()
                        idx_list = df.index[df['ID'].astype(str) == str(selected_id)].tolist()
                        
                        if not idx_list:
                            st.error("找不到該筆資料")
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
        st.info("連結成功！請新增第一筆交易。")

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
    if not df.empty and "ID" in df.columns:
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