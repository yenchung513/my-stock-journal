import streamlit as st
import pandas as pd
from datetime import datetime
import time # 用來產生唯一 ID

# --- 頁面設定 ---
st.set_page_config(page_title="台股交易日誌 V2", page_icon="📈", layout="wide")

# --- 檔案設定 ---
FILE_NAME = "trades_v2.csv"

# --- 核心函式 ---
def load_data():
    if "data_changed" not in st.session_state:
        st.session_state.data_changed = False

    try:
        # 讀取 CSV，確保 ID 是字串以免被當成數字運算
        df = pd.read_csv(FILE_NAME, dtype={"ID": str})
    except FileNotFoundError:
        # 初始化 DataFrame
        df = pd.DataFrame(columns=["ID", "日期", "策略", "代號", "買入價", "股數", "狀態", "賣出價", "損益", "手續費折數"])
    return df

def save_data(df):
    df.to_csv(FILE_NAME, index=False)

# --- 側邊欄：新增交易 (建倉) ---
st.sidebar.header("📝 新增交易 (建倉)")

# 1. 自訂日期
trade_date = st.sidebar.date_input("交易日期", datetime.now())

strategy = st.sidebar.selectbox("策略", ["突破追價", "拉回低接", "長期存股", "隔日沖", "抄底失敗"])
stock_id = st.sidebar.text_input("股票代號/名稱", "2330 台積電")
buy_price = st.sidebar.number_input("買入價格", min_value=0.0, step=0.1, format="%.2f")
volume = st.sidebar.number_input("買入股數", min_value=1, value=1000, step=1)
discount = st.sidebar.number_input("手續費折數 (折)", value=2.8, step=0.1, help="例如 2.8 折")

if st.sidebar.button("➕ 建倉 (買進)"):
    df = load_data()
    # 產生唯一 ID (用時間戳記)
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
    
    # 存檔
    df = pd.concat([pd.DataFrame([new_data]), df], ignore_index=True)
    save_data(df)
    st.sidebar.success(f"已買入 {stock_id} ({volume}股)")
    time.sleep(1) # 稍微停頓讓使用者看到成功訊息
    st.rerun() # 重新整理畫面

# --- 主畫面 ---
st.title("📈 專業台股交易日誌 V2.0")

# 讀取資料
df = load_data()

# 分頁設計
tab1, tab2, tab3 = st.tabs(["💼 持倉管理 (分批賣出)", "📜 歷史戰績", "🗑️ 資料管理 (刪除)"])

# === Tab 1: 持倉管理 ===
with tab1:
    st.subheader("目前庫存部位")
    # 篩選持倉
    open_positions = df[df["狀態"] == "持倉中"]

    if not open_positions.empty:
        # 顯示簡易表格
        st.dataframe(open_positions[["日期", "策略", "代號", "買入價", "股數", "手續費折數"]])
        st.markdown("---")
        
        # 選擇要處理的股票
        # 製作選單標籤： 代號 (日期 - 股數)
        options = {f"{row['代號']} ({row['日期']} 買 {row['股數']}股)": row['ID'] for index, row in open_positions.iterrows()}
        selected_label = st.selectbox("選擇要平倉的部位", list(options.keys()))
        selected_id = options[selected_label]

        # 抓出該筆資料
        target_row = df[df["ID"] == selected_id].iloc[0]
        
        col1, col2, col3 = st.columns(3)
        with col1:
            sell_price = st.number_input("賣出價格", min_value=0.0, step=0.1, format="%.2f")
        with col2:
            # 預設為全部賣出，但可以改
            sell_qty = st.number_input("賣出股數 (支援分批)", min_value=1, max_value=int(target_row["股數"]), value=int(target_row["股數"]))
        with col3:
            st.markdown("<br>", unsafe_allow_html=True) # 排版用空白
            confirm_sell = st.button("⚡ 執行賣出")

        if confirm_sell:
            # --- 核心邏輯：分批賣出 ---
            
            # 1. 計算損益 (針對賣出的數量)
            d_rate = target_row["手續費折數"] / 10
            buy_cost = int(target_row["買入價"] * sell_qty)
            buy_fee = max(int(buy_cost * 0.001425 * d_rate), 1) # 最低手續費1元
            
            sell_revenue = int(sell_price * sell_qty)
            sell_fee = max(int(sell_revenue * 0.001425 * d_rate), 1)
            tax = int(sell_revenue * 0.003)
            
            profit = sell_revenue - sell_fee - tax - (buy_cost + buy_fee)
            
            # 2. 判斷是「全賣」還是「分批」
            original_idx = df[df["ID"] == selected_id].index[0]
            
            if sell_qty == target_row["股數"]:
                # 全賣：直接更新原資料狀態
                df.at[original_idx, "狀態"] = "已平倉"
                df.at[original_idx, "賣出價"] = sell_price
                df.at[original_idx, "損益"] = profit
                msg = f"全數平倉成功！獲利 {profit} 元"
            else:
                # 分批：分裂成兩筆
                
                # A. 修改原來的庫存 (減少股數)
                remain_qty = target_row["股數"] - sell_qty
                df.at[original_idx, "股數"] = remain_qty
                
                # B. 新增一筆「已平倉」的紀錄
                new_closed_record = target_row.copy()
                new_closed_record["ID"] = str(int(time.time() * 1000)) # 給新ID
                new_closed_record["股數"] = sell_qty
                new_closed_record["賣出價"] = sell_price
                new_closed_record["狀態"] = "已平倉"
                new_closed_record["損益"] = profit
                
                # 加回 DataFrame
                df = pd.concat([pd.DataFrame([new_closed_record]), df], ignore_index=True)
                msg = f"分批賣出 {sell_qty} 股成功！獲利 {profit} 元 (剩餘 {remain_qty} 股)"

            save_data(df)
            st.success(msg)
            time.sleep(1)
            st.rerun()

    else:
        st.info("目前兩袖清風，沒有庫存。")

# === Tab 2: 歷史戰績 ===
with tab2:
    st.subheader("已實現損益")
    closed_positions = df[df["狀態"] == "已平倉"].copy()
    
    if not closed_positions.empty:
        # 損益上色
        def highlight_profit(val):
            color = '#ff4b4b' if val > 0 else '#00c853' # 台股紅漲綠跌
            return f'color: {color}; font-weight: bold;'

        # 顯示表格 (隱藏 ID)
        display_cols = ["日期", "策略", "代號", "買入價", "賣出價", "股數", "損益"]
        st.dataframe(closed_positions[display_cols].style.applymap(highlight_profit, subset=['損益']), use_container_width=True)
        
        # 統計
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
        # 讓用戶看清楚所有資料
        st.dataframe(df)
        
        # 選擇要刪除的 ID
        delete_options = {f"[{row['狀態']}] {row['日期']} - {row['代號']} ({row['股數']}股)": row['ID'] for index, row in df.iterrows()}
        delete_id = st.selectbox("選擇要刪除的紀錄", list(delete_options.keys()))
        real_delete_id = delete_options[delete_id]
        
        if st.button("❌ 確認刪除"):
            df = df[df["ID"] != real_delete_id] # 過濾掉該ID
            save_data(df)
            st.error("已刪除該筆資料！")
            time.sleep(1)
            st.rerun()
    else:
        st.write("目前沒有任何資料。")