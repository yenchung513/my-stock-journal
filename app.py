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
st.set_page_config(page_title="台股雲端戰情室 V6.7", page_icon="📈", layout="wide")

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
        
        columns = ["ID", "日期", "買入日期", "策略", "代號", "買入價", "止損價", "股數", "狀態", "賣出價", "損益", "手續費折數", "心得"]
        
        if df.empty:
            return pd.DataFrame(columns=columns)
            
        for col in columns:
            if col not in df.columns:
                df[col] = ""

        if "ID" in df.columns:
            df["ID"] = df["ID"].astype(str)
        
        if "買入日期" in df.columns:
            df["買入日期"] = df["買入日期"].replace(r'^\s*$', pd.NA, regex=True)
            df["買入日期"] = df["買入日期"].fillna(df["日期"])
        
        df["買入價"] = pd.to_numeric(df["買入價"], errors='coerce').fillna(0.0)
        df["止損價"] = pd.to_numeric(df["止損價"], errors='coerce').fillna(0.0)
        df["股數"] = pd.to_numeric(df["股數"], errors='coerce').fillna(0)
        df["心得"] = df["心得"].fillna("")
            
        return df
    except Exception as e:
        st.error(f"讀取資料發生錯誤: {e}")
        return pd.DataFrame(columns=["ID", "日期", "買入日期", "策略", "代號", "買入價", "止損價", "股數", "狀態", "賣出價", "損益", "手續費折數", "心得"])

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

# --- V6.7 核心修正：智慧判斷上市(.TW)與上櫃(.TWO) ---
def get_realtime_prices(stock_codes):
    """
    逐一嘗試 .TW 與 .TWO，確保抓到正確股價
    回傳: (prices_dict, debug_logs)
    """
    if not stock_codes:
        return {}, []
    
    prices = {}
    logs = []
    
    for code in stock_codes:
        # 定義嘗試順序：先假設是上市 (.TW)，若失敗再試上櫃 (.TWO)
        suffixes = ['.TW', '.TWO']
        price_found = False
        
        for suffix in suffixes:
            try:
                ticker_name = f"{code}{suffix}"
                stock = yf.Ticker(ticker_name)
                
                # 方法 1: 嘗試 fast_info (最即時)
                current_price = None
                if hasattr(stock, 'fast_info') and 'last_price' in stock.fast_info:
                    p = stock.fast_info['last_price']
                    # 必須確認價格有效且非 None
                    if p is not None and p > 0:
                        current_price = p
                
                # 方法 2: 若 fast_info 無效，嘗試 history (抓最近 5 天以防假日)
                if current_price is None:
                    hist = stock.history(period="5d")
                    if not hist.empty:
                        current_price = hist['Close'].iloc[-1]
                
                # 判定是否成功抓到
                if current_price is not None:
                    prices[code] = float(current_price)
                    logs.append(f"✅ {code} -> 成功 ({ticker_name}): {current_price:.2f}")
                    price_found = True
                    break # 成功就跳出 suffix 迴圈，不用試下一個了
                
            except Exception as e:
                # 單一後綴失敗，繼續嘗試下一個
                continue
        
        if not price_found:
            logs.append(f"❌ {code} -> 失敗 (上市櫃皆無數據)")
            
    return prices, logs

# --- 側邊欄：新增交易 ---
st.sidebar.header("📝 新增交易")

trade_date = st.sidebar.date_input("交易日期 (買進日)", datetime.now())
strategy = st.sidebar.selectbox("策略 (紀錄用)", ["Alpha-Swing", "突破追價", "拉回低接", "長期存股", "隔日沖", "抄底失敗"])
stock_id_input = st.sidebar.text_input("股票代號 (例如: 2330)", "2330") 
stock_name_input = st.sidebar.text_input("股票名稱 (選填)", "台積電")
stock_full_name = f"{stock_id_input} {stock_name_input}"
buy_price = st.sidebar.number_input("買入價格", min_value=0.0, step=0.1, format="%.2f")
stop_loss_price = st.sidebar.number_input("初始止損價 (風控)", min_value=0.0, step=0.1, format="%.2f", help="跌破此價格應考慮出場")
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
            "代號": stock_full_name,
            "買入價": buy_price,
            "止損價": stop_loss_price,
            "股數": volume,
            "狀態": "持倉中",
            "賣出價": 0.0,
            "損益": 0,
            "手續費折數": discount,
            "心得": ""
        }
        
        df = pd.concat([pd.DataFrame([new_data]), df], ignore_index=True)
        save_data(df)
    
    st.sidebar.success(f"建倉成功！")
    time.sleep(1)
    st.rerun()

# --- 主畫面 ---
st.title("📊 台股雲端戰情室 V6.7 (智慧報價版)")

df = load_data()

tab1, tab2, tab3, tab4 = st.tabs(["💼 持倉監控", "📜 歷史戰績", "📊 圖表分析", "🗑️ 資料管理"])

# === Tab 1: 持倉監控 ===
with tab1:
    st.subheader("目前庫存部位 & 風控監測")
    if not df.empty and "狀態" in df.columns:
        open_positions = df[df["狀態"] == "持倉中"].copy()
        
        if not open_positions.empty:
            # 1. 解析股票代號
            open_positions['code'] = open_positions['代號'].astype(str).str.extract(r'^(\d+)')
            unique_codes = open_positions['code'].dropna().unique().tolist()
            
            realtime_prices = {}
            debug_logs = []
            
            if unique_codes:
                with st.spinner("正在智慧搜尋股價 (上市/上櫃)..."):
                    realtime_prices, debug_logs = get_realtime_prices(unique_codes)
            
            # --- V6.7 新增：除錯資訊展開 ---
            with st.expander("查看報價抓取狀態 (Debug Info)"):
                for log in debug_logs:
                    st.text(log)
            # ---------------------------

            # 2. 計算未實現損益
            total_market_value = 0
            total_unrealized_profit = 0
            display_rows = []
            
            for index, row in open_positions.iterrows():
                code = row['code']
                # 若抓不到現價，回退使用買入價
                current_price = realtime_prices.get(code, row['買入價']) 
                
                qty = float(row['股數'])
                buy_p = float(row['買入價'])
                stop_loss = float(row['止損價'])
                
                market_val = current_price * qty
                unrealized = (current_price - buy_p) * qty
                
                total_market_value += market_val
                total_unrealized_profit += unrealized
                
                status_signal = "🟢 正常"
                if stop_loss > 0 and current_price < stop_loss:
                    status_signal = "🔴 破止損!"
                
                display_rows.append({
                    "ID": row["ID"],
                    "代號": row["代號"],
                    "買入日期": row["買入日期"],
                    "買入價": buy_p,
                    "現價": current_price,
                    "止損價": stop_loss,
                    "股數": qty,
                    "未實現損益": int(unrealized),
                    "狀態訊號": status_signal
                })

            # 3. 顯示看板
            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("庫存總市值", f"${total_market_value:,.0f}")
            col_m2.metric("預估未實現損益", f"${total_unrealized_profit:,.0f}", delta_color="normal")
            col_m3.metric("持倉檔數", f"{len(open_positions)} 檔")

            # 4. 表格顯示
            results_df = pd.DataFrame(display_rows)
            def highlight_stop_loss(s):
                is_danger = s["狀態訊號"] == "🔴 破止損!"
                return ['background-color: #ffcccc' if is_danger else '' for _ in s]

            st.dataframe(
                results_df[["代號", "買入日期", "買入價", "現價", "止損價", "股數", "未實現損益", "狀態訊號"]].style.apply(highlight_stop_loss, axis=1),
                use_container_width=True
            )
            
            st.caption("* 註：價格來源 Yahoo Finance (延遲 15 分鐘)。若未顯示損益，請檢查 Debug 資訊。")
            st.markdown("---")
            
            # --- 平倉區 ---
            options = {f"{row['代號']} (買入 ${row['買入價']} | 現價 ${row['現價']})": row['ID'] for row in display_rows}
            selected_label = st.selectbox("選擇要平倉的部位", list(options.keys()))
            
            if selected_label:
                selected_id = options[selected_label]
                target_row = df[df["ID"].astype(str) == str(selected_id)].iloc[0]
                
                current_market_price = next((item['現價'] for item in display_rows if str(item['ID']) == str(selected_id)), 0.0)
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    sell_date_input = st.date_input("賣出日期", datetime.now())
                with col2:
                    sell_price = st.number_input("賣出價格", min_value=0.0, step=0.1, value=float(current_market_price), format="%.2f")
                with col3:
                    current_qty = int(float(target_row["股數"]))
                    sell_qty = st.number_input("賣出股數", min_value=1, max_value=current_qty, value=current_qty)
                with col4:
                    st.markdown("<br>", unsafe_allow_html=True)
                    confirm_sell = st.button("⚡ 執行賣出")

                if confirm_sell:
                    with st.spinner("計算損益..."):
                        d_rate = float(target_row["手續費折數"]) / 10
                        buy_p_val = float(target_row["買入價"])
                        buy_cost = int(buy_p_val * sell_qty)
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
                                new_closed_record["心得"] = "" 
                                
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
    st.subheader("📜 已實現損益明細")
    if not df.empty and "狀態" in df.columns:
        closed_positions = df[df["狀態"] == "已平倉"].copy()
        if not closed_positions.empty:
            closed_positions["損益"] = pd.to_numeric(closed_positions["損益"])
            
            def highlight_profit(val):
                color = '#ff4b4b' if val > 0 else '#00c853'
                return f'color: {color}; font-weight: bold;'

            display_cols = ["買入日期", "日期", "代號", "買入價", "賣出價", "損益", "心得"]
            show_df = closed_positions[display_cols].rename(columns={"日期": "賣出日期"})
            
            st.dataframe(show_df.style.applymap(highlight_profit, subset=['損益']), use_container_width=True)
            
            st.markdown("---")
            st.subheader("✍️ 撰寫/修改交易心得")
            note_options = {
                f"{row['日期']} | {row['代號']} | ${row['損益']}": row['ID'] 
                for index, row in closed_positions.iterrows()
            }
            selected_note_key = st.selectbox("選擇一筆交易來寫筆記", list(note_options.keys()))
            if selected_note_key:
                note_id = note_options[selected_note_key]
                current_row = df[df["ID"].astype(str) == str(note_id)].iloc[0]
                current_note = current_row["心得"] if "心得" in current_row else ""
                new_note = st.text_area("輸入你的檢討或筆記", value=str(current_note), height=100)
                if st.button("💾 儲存心得"):
                    with st.spinner("儲存中..."):
                        idx_list = df.index[df['ID'].astype(str) == str(note_id)].tolist()
                        if idx_list:
                            df.at[idx_list[0], "心得"] = new_note
                            save_data(df)
                            st.success("心得已更新！")
                            time.sleep(1)
                            st.rerun()
        else:
            st.info("尚未有平倉紀錄")

# === Tab 3: 圖表分析 ===
with tab3:
    st.subheader("📈 交易數據分析")
    
    if not df.empty and "狀態" in df.columns:
        closed_df = df[df["狀態"] == "已平倉"].copy()
        
        if not closed_df.empty:
            closed_df["損益"] = pd.to_numeric(closed_df["損益"])
            closed_df["日期"] = pd.to_datetime(closed_df["日期"])
            closed_df["買入日期"] = pd.to_datetime(closed_df["買入日期"])
            closed_df = closed_df.sort_values("日期")
            
            closed_df["累積損益"] = closed_df["損益"].cumsum()
            st.markdown("##### 💰 帳戶淨值走勢")
            fig_line = px.line(closed_df, x="日期", y="累積損益", markers=True)
            fig_line.update_traces(line_color='#2980b9', line_width=3)
            st.plotly_chart(fig_line, use_container_width=True)
            
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("##### 📅 每週損益")
                closed_df["週次"] = closed_df["日期"].dt.strftime('%Y-W%U')
                weekly_perf = closed_df.groupby("週次")["損益"].sum().reset_index()
                fig_bar = px.bar(weekly_perf, x="週次", y="損益",
                                 color="損益",
                                 color_continuous_scale=["#00c853", "#ff4b4b"],
                                 text_auto=True)
                st.plotly_chart(fig_bar, use_container_width=True)
                
            with col2:
                st.markdown("##### ⏳ 持倉天數 vs 損益")
                closed_df["持倉天數"] = (closed_df["日期"] - closed_df["買入日期"]).dt.days
                fig_scatter = px.scatter(closed_df, x="持倉天數", y="損益",
                                         color="損益",
                                         size=closed_df["損益"].abs(),
                                         hover_data=["代號", "買入日期", "心得"],
                                         color_continuous_scale=["#00c853", "#ff4b4b"])
                fig_scatter.add_hline(y=0, line_dash="dash", line_color="gray")
                fig_scatter.update_layout(xaxis=dict(tickmode='linear', tick0=0, dtick=1))
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