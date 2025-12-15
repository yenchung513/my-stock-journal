import streamlit as st
import pandas as pd
from datetime import datetime
import time
import gspread
from google.oauth2.service_account import Credentials
import json
import plotly.express as px

# --- 頁面設定 ---
st.set_page_config(page_title="台股雲端戰情室 V6.0", page_icon="📈", layout="wide")

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
        
        if df.empty:
            return pd.DataFrame(columns=["ID", "日期", "買入日期", "策略", "代號", "買入價", "股數", "狀態", "賣出價", "損益", "手續費折數"])
            
        if "ID" in df.columns:
            df["ID"] = df["ID"].astype(str)
        
        # 自動修復舊資料：若無買入日期，用日期填補
        if "買入日期" not in df.columns:
            df["買入日期"] = df["日期"]
        else:
            df["買入日期"] = df["買入日期"].replace(r'^\s*$', pd.NA, regex=True)
            df["買入日期"] = df["買入日期"].fillna(df["日期"])
            
        return df
    except Exception as e:
        return pd.DataFrame(columns=["ID", "日期", "買入日期", "策略", "代號", "買入價", "股數", "狀態", "賣出價", "損益", "手續費折數"])

def save_data(df):
    sheet = get_google_sheet()
    sheet.clear()
    df_to_save = df.fillna("")
    data = [df_to_save.columns.values.tolist()] + df_to_save.values.tolist()
    sheet.update(data)

# --- 側邊欄：新增交易 ---
st.sidebar.header("📝 新增交易")

trade_date = st.sidebar.date_input("交易日期 (買進日)", datetime.now())
# 雖然圖表不顯示策略，但紀錄還是保留策略欄位供未來參考，這裡保留輸入框
strategy = st.sidebar.selectbox("策略 (紀錄用)", ["突破追價", "拉回低接", "長期存股", "隔日沖", "抄底失敗"])
stock_id = st.sidebar.text_input("股票代號/名稱", "2330 台積電")
buy_price = st.sidebar.number_input("買入價格", min_value=0.0, step=0.1, format="%.2f")
volume = st.sidebar.number_input("買入股數", min_value=1, value=1000, step=1)
discount = st.sidebar.number_input("手續費折數 (折)", value=2.8, step=0.1)

if st.sidebar.button("➕ 建倉"):
    with st.spinner("寫入中..."):
        df = load_data()
        new_id = str(int(time.time() * 1000))
        date_str = trade_date.strftime("%Y-%m-%d")
        
        new_data = {
            "ID": new_id,
            "日期": date_str,
            "買入日期": date_str,
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
    
    st.sidebar.success(f"建倉成功！")
    time.sleep(1)
    st.rerun()

# --- 主畫面 ---
st.title("📊 台股雲端戰情室 V6.0")

df = load_data()

tab1, tab2, tab3, tab4 = st.tabs(["💼 持倉管理", "📜 歷史戰績", "📊 圖表分析", "🗑️ 資料管理"])

# === Tab 1: 持倉管理 ===
with tab1:
    st.subheader("目前庫存部位")
    if not df.empty and "狀態" in df.columns:
        open_positions = df[df["狀態"] == "持倉中"]
        
        if not open_positions.empty:
            market_value = (open_positions["買入價"].astype(float) * open_positions["股數"].astype(int)).sum()
            st.metric("庫存總成本 (約)", f"${market_value:,.0f}")

            display_df = open_positions[["買入日期", "策略", "代號", "買入價", "股數", "手續費折數"]].copy()
            st.dataframe(display_df, use_container_width=True)
            st.markdown("---")
            
            options = {f"{row['代號']} ({row['買入日期']} 買 {row['股數']}股)": row['ID'] for index, row in open_positions.iterrows()}
            selected_label = st.selectbox("選擇要平倉的部位", list(options.keys()))
            
            if selected_label:
                selected_id = options[selected_label]
                target_row = df[df["ID"].astype(str) == str(selected_id)].iloc[0]
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    sell_date_input = st.date_input("賣出日期", datetime.now())
                with col2:
                    sell_price = st.number_input("賣出價格", min_value=0.0, step=0.1, format="%.2f")
                with col3:
                    current_qty = int(target_row["股數"])
                    sell_qty = st.number_input("賣出股數", min_value=1, max_value=current_qty, value=current_qty)
                with col4:
                    st.markdown("<br>", unsafe_allow_html=True)
                    confirm_sell = st.button("⚡ 執行賣出")

                if confirm_sell:
                    with st.spinner("計算損益..."):
                        d_rate = float(target_row["手續費折數"]) / 10
                        buy_cost = int(float(target_row["買入價"]) * sell_qty)
                        buy_fee = max(int(buy_cost * 0.001425 * d_rate), 1)
                        sell_revenue = int(sell_price * sell_qty)
                        sell_fee = max(int(sell_revenue * 0.001425 * d_rate), 1)
                        tax = int(sell_revenue * 0.003)
                        profit = sell_revenue - sell_fee - tax - (buy_cost + buy_fee)
                        
                        df = load_data()
                        idx_list = df.index[df['ID'].astype(str) == str(selected_id)].tolist()
                        
                        if idx_list:
                            original_idx = idx_list[0]
                            sell_date_str = sell_date_input.strftime("%Y-%m-%d")
                            original_buy_date = target_row.get("買入日期")
                            if pd.isna(original_buy_date) or str(original_buy_date).strip() == "":
                                original_buy_date = target_row["日期"]

                            if sell_qty == current_qty:
                                df.at[original_idx, "狀態"] = "已平倉"
                                df.at[original_idx, "賣出價"] = sell_price
                                df.at[original_idx, "損益"] = profit
                                df.at[original_idx, "日期"] = sell_date_str
                                df.at[original_idx, "買入日期"] = original_buy_date
                            else:
                                remain_qty = current_qty - sell_qty
                                df.at[original_idx, "股數"] = remain_qty
                                
                                new_closed_record = target_row.copy()
                                new_closed_record["ID"] = str(int(time.time() * 1000))
                                new_closed_record["股數"] = sell_qty
                                new_closed_record["賣出價"] = sell_price
                                new_closed_record["狀態"] = "已平倉"
                                new_closed_record["損益"] = profit
                                new_closed_record["日期"] = sell_date_str
                                new_closed_record["買入日期"] = original_buy_date
                                
                                df = pd.concat([pd.DataFrame([new_closed_record]), df], ignore_index=True)

                            save_data(df)
                            st.success(f"平倉完成！損益: {profit}")
                            time.sleep(1)
                            st.rerun()
        else:
            st.info("目前沒有庫存。")
    else:
        st.info("資料載入中...")

# === Tab 2: 歷史戰績 ===
with tab2:
    st.subheader("已實現損益明細")
    if not df.empty and "狀態" in df.columns:
        closed_positions = df[df["狀態"] == "已平倉"].copy()
        if not closed_positions.empty:
            closed_positions["損益"] = pd.to_numeric(closed_positions["損益"])
            
            def highlight_profit(val):
                color = '#ff4b4b' if val > 0 else '#00c853'
                return f'color: {color}; font-weight: bold;'

            display_cols = ["買入日期", "日期", "策略", "代號", "買入價", "賣出價", "股數", "損益"]
            show_df = closed_positions[display_cols].rename(columns={"日期": "賣出日期"})
            
            st.dataframe(show_df.style.applymap(highlight_profit, subset=['損益']), use_container_width=True)
        else:
            st.info("尚未有平倉紀錄")

# === Tab 3: 圖表分析 (V6.0 重點更新) ===
with tab3:
    st.subheader("📈 交易數據分析")
    
    if not df.empty and "狀態" in df.columns:
        closed_df = df[df["狀態"] == "已平倉"].copy()
        
        if not closed_df.empty:
            # 資料處理
            closed_df["損益"] = pd.to_numeric(closed_df["損益"])
            closed_df["日期"] = pd.to_datetime(closed_df["日期"])     # 賣出日
            closed_df["買入日期"] = pd.to_datetime(closed_df["買入日期"]) # 買入日
            closed_df = closed_df.sort_values("日期")
            
            # 計算持倉天數
            closed_df["持倉天數"] = (closed_df["日期"] - closed_df["買入日期"]).dt.days
            # 至少算 1 天 (當沖)
            closed_df["持倉天數"] = closed_df["持倉天數"].apply(lambda x: 1 if x < 1 else x)

            # 計算月份 (YYYY-MM)
            closed_df["月份"] = closed_df["日期"].dt.strftime('%Y-%m')

            # 1. 資金曲線 (不變，因為這最重要)
            closed_df["累積損益"] = closed_df["損益"].cumsum()
            st.markdown("##### 💰 帳戶淨值走勢")
            fig_line = px.line(closed_df, x="日期", y="累積損益", markers=True)
            fig_line.update_traces(line_color='#2980b9', line_width=3)
            st.plotly_chart(fig_line, use_container_width=True)
            
            # 版面：左右兩欄
            col1, col2 = st.columns(2)
            
            with col1:
                # 2. 每月損益 (取代策略分析)
                st.markdown("##### 📅 每月損益 (Monthly P/L)")
                monthly_perf = closed_df.groupby("月份")["損益"].sum().reset_index()
                
                # 設定顏色：賺錢紅，賠錢綠
                fig_bar = px.bar(monthly_perf, x="月份", y="損益",
                                 color="損益",
                                 color_continuous_scale=["#00c853", "#ff4b4b"],
                                 text_auto=True)
                st.plotly_chart(fig_bar, use_container_width=True)
                
            with col2:
                # 3. 持倉天數 vs 損益 (新功能)
                st.markdown("##### ⏳ 持倉天數 vs 損益")
                # 這張圖可以看出：你是不是抱越久賠越多？
                fig_scatter = px.scatter(closed_df, x="持倉天數", y="損益",
                                         color="損益",
                                         size=closed_df["損益"].abs(), # 泡泡大小 = 賺賠金額絕對值
                                         hover_data=["代號", "買入日期"], # 滑鼠移上去顯示股票
                                         color_continuous_scale=["#00c853", "#ff4b4b"])
                # 加一條 0 軸線方便看
                fig_scatter.add_hline(y=0, line_dash="dash", line_color="gray")
                st.plotly_chart(fig_scatter, use_container_width=True)

        else:
            st.info("累積平倉紀錄後，圖表將自動顯示。")
    else:
        st.info("尚無數據。")

# === Tab 4: 資料管理 ===
with tab4:
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