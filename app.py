import streamlit as st
import pandas as pd
from datetime import datetime
import os

# --- 設定網頁標題 ---
st.set_page_config(page_title="我的台股日誌", page_icon="📈")

# --- 核心邏輯：讀寫資料 ---
# 為了簡單，我們先把資料存在 CSV 檔案裡 (Streamlit Cloud 重啟會重置，若要永久保存需串接資料庫，我們先求跑起來)
FILE_NAME = "trades.csv"

def load_data():
    if os.path.exists(FILE_NAME):
        return pd.read_csv(FILE_NAME)
    else:
        return pd.DataFrame(columns=["日期", "策略", "代號", "買入價", "股數", "狀態", "賣出價", "損益"])

def save_data(df):
    df.to_csv(FILE_NAME, index=False)

# --- 介面開始 ---
st.title("📈 專屬台股交易日誌 (Python版)")

# 側邊欄：新增交易
st.sidebar.header("📝 新增交易")
strategy = st.sidebar.selectbox("策略", ["突破追價", "拉回低接", "長期存股", "隔日沖"])
stock_id = st.sidebar.text_input("股票代號/名稱", "2330 台積電")
buy_price = st.sidebar.number_input("買入價格", min_value=0.0, step=0.1)
volume = st.sidebar.number_input("股數", min_value=1, value=1000, step=1)
discount = st.sidebar.number_input("手續費折數 (折)", value=2.8, step=0.1)

if st.sidebar.button("➕ 建倉 (買進)"):
    df = load_data()
    new_data = {
        "日期": datetime.now().strftime("%Y-%m-%d"),
        "策略": strategy,
        "代號": stock_id,
        "買入價": buy_price,
        "股數": volume,
        "狀態": "持倉中",
        "賣出價": 0.0,
        "損益": 0
    }
    # 使用 pd.concat 新增資料
    df = pd.concat([pd.DataFrame([new_data]), df], ignore_index=True)
    save_data(df)
    st.sidebar.success(f"已買入 {stock_id}")

# --- 主畫面：顯示資料 ---
df = load_data()

# 分頁顯示
tab1, tab2 = st.tabs(["💼 持倉部位", "📜 歷史戰績"])

with tab1:
    st.subheader("目前庫存")
    # 篩選出持倉中的股票
    open_positions = df[df["狀態"] == "持倉中"]
    
    if not open_positions.empty:
        # 顯示表格
        st.dataframe(open_positions[["日期", "策略", "代號", "買入價", "股數"]])
        
        # 平倉操作區
        st.write("---")
        st.write("🖐 **平倉操作**")
        
        # 讓用戶選擇要賣哪一檔
        trade_to_close = st.selectbox("選擇要平倉的股票", open_positions["代號"].unique())
        sell_price = st.number_input("賣出價格", min_value=0.0, step=0.1)
        
        if st.button("⚡ 平倉 (賣出)"):
            # 找到這筆資料並更新
            idx = df[(df["代號"] == trade_to_close) & (df["狀態"] == "持倉中")].index[0]
            
            # 計算損益 (Python 算數很強大)
            row = df.loc[idx]
            d_rate = discount / 10
            buy_cost = int(row["買入價"] * row["股數"])
            buy_fee = max(int(buy_cost * 0.001425 * d_rate), 1)
            
            sell_revenue = int(sell_price * row["股數"])
            sell_fee = max(int(sell_revenue * 0.001425 * d_rate), 1)
            tax = int(sell_revenue * 0.003)
            
            profit = sell_revenue - sell_fee - tax - (buy_cost + buy_fee)
            
            # 更新 DataFrame
            df.at[idx, "狀態"] = "已平倉"
            df.at[idx, "賣出價"] = sell_price
            df.at[idx, "損益"] = profit
            
            save_data(df)
            st.success(f"平倉成功！損益：{profit} 元")
            st.rerun() # 重新整理畫面
    else:
        st.info("目前沒有庫存")

with tab2:
    st.subheader("已結算紀錄")
    closed_positions = df[df["狀態"] == "已平倉"]
    if not closed_positions.empty:
        # 依照損益上色
        def highlight_profit(val):
            color = 'red' if val > 0 else 'green'
            return f'color: {color}'

        st.dataframe(closed_positions.style.applymap(highlight_profit, subset=['損益']))
        
        total_profit = closed_positions["損益"].sum()
        st.metric("總損益", f"{total_profit} 元")
    else:
        st.info("尚無歷史紀錄")