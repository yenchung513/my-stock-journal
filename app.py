import streamlit as st
import pandas as pd
from datetime import datetime
import time 

# --- 頁面設定 ---
st.set_page_config(page_title="台股交易日誌 V2.1", page_icon="📈", layout="wide")

# --- 檔案設定 ---
FILE_NAME = "trades.csv"

# --- 核心函式 (含自動修復功能) ---
def load_data():
    if "data_changed" not in st.session_state:
        st.session_state.data_changed = False

    try:
        # 1. 嘗試讀取資料
        df = pd.read_csv(FILE_NAME, dtype={"ID": str})
        
        # 2. 自動修復機制 (Migration)
        # 檢查是否缺少 "手續費折數" 欄位 (這是舊資料常見的問題)
        if "手續費折數" not in df.columns:
            df["手續費折數"] = 2.8 # 給舊資料一個預設值
        
        # 檢查是否缺少 "ID" 欄位
        if "ID" not in df.columns:
            # 幫每一筆舊資料補上一個唯一的 ID
            df["ID"] = [str(int(time.time() * 1000) + i) for i in range(len(df))]
            
        # 3. 確保 ID 是字串格式 (避免後續錯誤)
        df["ID"] = df["ID"].astype(str)
            
        return df
        
    except FileNotFoundError:
        # 如果檔案不存在，建立全新的
        df = pd.DataFrame(columns=["ID", "日期", "策略", "代號", "買入價", "股數", "狀態", "賣出價", "損益", "手續費折數"])
        return df

def save_data(df):
    df.to_csv(FILE_NAME, index=False)

# --- 側邊欄：新增交易 (建倉) ---
st.sidebar.header("📝 新增交易 (建倉)")

trade_date = st.sidebar.date_input("交易日期", datetime.now())
strategy = st.sidebar.selectbox("策略", ["突破追價", "拉回低接", "長期存股", "隔日沖", "抄底失敗"])
stock_id = st.sidebar.text_input("股票代號/名稱", "2330 台積電")
buy_price = st.sidebar.number_input("買入價格", min_value=0.0, step=0.1, format="%.2f")
volume = st.sidebar.number_input("買入股數", min_value=1, value=1000, step=1)
discount = st.sidebar.number_input("手續費折數 (折)", value=2.8, step=0.1)

if st.sidebar.button("➕ 建倉 (買進)"):
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
    st.sidebar.success(f"已買入 {stock_id}")
    time.sleep(1)
    st.rerun()

# --- 主畫面 ---
st.title("📈 專業台股交易日誌 V2.1")
df = load_data()

tab1, tab2, tab3 = st.tabs(["💼 持倉管理", "📜 歷史戰績", "🗑️ 資料管理"])

# === Tab 1: 持倉管理 ===
with tab1:
    st.subheader("目前庫存部位")
    open_positions = df[df["狀態"] == "持倉中"]

    if not open_positions.empty:
        st.dataframe(open_positions[["日期", "策略", "代號", "買入價", "股數", "手續費折數"]], use_container_width=True)
        st.markdown("---")
        
        options = {f"{row['代號']} ({row['日期']} 買 {row['股數']}股)": row['ID'] for index, row in open_positions.iterrows()}
        selected_label = st.selectbox("選擇要平倉的部位", list(options.keys()))
        
        if selected_label: # 確保有選到東西
            selected_id = options[selected_label]
            target_row = df[df["ID"] == selected_id].iloc[0]
            
            col1, col2, col3 = st.columns(3)
            with col1:
                sell_price = st.number_input("賣出價格", min_value=0.0, step=0.1, format="%.2f")
            with col2:
                current_qty = int(target_row["股數"])
                sell_qty = st.number_input("賣出股數 (支援分批)", min_value=1, max_value=current_qty, value=current_qty)
            with col3:
                st.markdown("<br>", unsafe_allow_html=True)
                confirm_sell = st.button("⚡ 執行賣出")

            if confirm_sell:
                d_rate = target_row["手續費折數"] / 10
                buy_cost = int(target_row["買入價"] * sell_qty)
                buy_fee = max(int(buy_cost * 0.001425 * d_rate), 1)
                
                sell_revenue = int(sell_price * sell_qty)
                sell_fee = max(int(sell_revenue * 0.001425 * d_rate), 1)
                tax = int(sell_revenue * 0.003)
                
                profit = sell_revenue - sell_fee - tax - (buy_cost + buy_fee)
                
                original_idx = df[df["ID"] == selected_id].index[0]
                
                if sell_qty == target_row["股數"]:
                    df.at[original_idx, "狀態"] = "已平倉"
                    df.at[original_idx, "賣出價"] = sell_price
                    df.at[original_idx, "損益"] = profit
                    msg = f"全數平倉成功！獲利 {profit} 元"
                else:
                    remain_qty = target_row["股數"] - sell_qty
                    df.at[original_idx, "股數"] = remain_qty
                    
                    new_closed_record = target_row.copy()
                    new_closed_record["ID"] = str(int(time.time() * 1000))
                    new_closed_record["股數"] = sell_qty
                    new_closed_record["賣出價"] = sell_price
                    new_closed_record["狀態"] = "已平倉"
                    new_closed_record["損益"] = profit
                    
                    df = pd.concat([pd.DataFrame([new_closed_record]), df], ignore_index=True)
                    msg = f"分批賣出 {sell_qty} 股成功！獲利 {profit} 元"

                save_data(df)
                st.success(msg)
                time.sleep(1)
                st.rerun()
    else:
        st.info("目前沒有庫存。")

# === Tab 2: 歷史戰績 ===
with tab2:
    st.subheader("已實現損益")
    closed_positions = df[df["狀態"] == "已平倉"].copy()
    
    if not closed_positions.empty:
        def highlight_profit(val):
            color = '#ff4b4b' if val > 0 else '#00c853'
            return f'color: {color}; font-weight: bold;'

        display_cols = ["日期", "策略", "代號", "買入價", "賣出價", "股數", "損益"]
        st.dataframe(closed_positions[display_cols].style.applymap(highlight_profit, subset=['損益']), use_container_width=True)
        
        total_profit = closed_positions["損益"].sum()
        win_rate = len(closed_positions[closed_positions["損益"] > 0]) / len(closed_positions) * 100
        
        col_a, col_b = st.columns(2)
        col_a.metric("總損益", f"${total_profit:,}")
        col_b.metric("勝率", f"{win_rate:.1f}%")
    else:
        st.info("尚未有平倉紀錄")

# === Tab 3: 資料管理 ===
with tab3:
    st.subheader("🗑️ 刪除或修正資料")
    st.warning("注意：刪除後無法復原！")
    
    if not df.empty:
        st.dataframe(df)
        delete_options = {f"[{row['狀態']}] {row['日期']} - {row['代號']} ({row['股數']}股)": row['ID'] for index, row in df.iterrows()}
        
        # 這裡加個防呆，如果 delete_options 是空的就不顯示選單
        if delete_options:
            delete_id = st.selectbox("選擇要刪除的紀錄", list(delete_options.keys()))
            if st.button("❌ 確認刪除"):
                real_delete_id = delete_options[delete_id]
                df = df[df["ID"] != real_delete_id]
                save_data(df)
                st.error("已刪除該筆資料！")
                time.sleep(1)
                st.rerun()
    else:
        st.write("目前沒有任何資料。")