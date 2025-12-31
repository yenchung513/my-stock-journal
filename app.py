import streamlit as st
import pandas as pd
from datetime import datetime
import time
import gspread
from google.oauth2.service_account import Credentials
import json
import plotly.express as px
import yfinance as yf

# --- 頁面設定 (維持行動版優化) ---
st.set_page_config(
    page_title="台股戰情室 V8.0", 
    page_icon="📱", 
    layout="wide",import streamlit as st
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
            
            target_sell_price = st.sidebar.number_input("目標賣出價", value=cost_p, min_value=0.0, step=0.1, format="%.2f")
            
            buy_cost_val = cost_p * qty_h
            buy_fee_val = max(int(buy_cost_val * 0.001425 * disc_h), 1)
            
            sell_val = target_sell_price * qty_h
            sell_fee_val = max(int(sell_val * 0.001425 * disc_h), 1)
            tax_val = int(sell_val * 0.003)
            
            net_p = sell_val - sell_fee_val - tax_val - (buy_cost_val + buy_fee_val)
            roi = (net_p / (buy_cost_val + buy_fee_val)) * 100 if buy_cost_val > 0 else 0
            
            if net_p > 0:
                st.sidebar.success(f"預估淨利: ${int(net_p)}")
            elif net_p < 0:
                st.sidebar.error(f"預估虧損: ${int(net_p)}")
            else:
                st.sidebar.info("預估損益: $0")
                
            st.sidebar.caption(f"報酬率: {roi:.2f}% | 稅金: ${tax_val}")
    else:
        st.sidebar.caption("無庫存可試算")
else:
    st.sidebar.caption("無資料")


# --- 主畫面 ---
st.title("📱 台股戰情室 V8.1")

tab1, tab2, tab3, tab4 = st.tabs(["💼 持倉", "📜 歷史", "📊 分析", "🗑️ 管理"])

# === Tab 1: 持倉 (新增顯示買入日) ===
with tab1:
    if not df.empty and "狀態" in df.columns:
        open_positions = df[df["狀態"] == "持倉中"].copy()
        
        if not open_positions.empty:
            open_positions['code'] = open_positions['代號'].astype(str).str.extract(r'^(\d+)')
            unique_codes = open_positions['code'].dropna().unique().tolist()
            
            if st.button("🔄 更新即時股價", type="primary", use_container_width=True):
                if unique_codes:
                    with st.spinner("連線中..."):
                        prices, logs = get_realtime_prices(unique_codes)
                        st.session_state.realtime_prices = prices
                        st.session_state.debug_logs = logs
                        st.session_state.price_update_time = datetime.now().strftime("%H:%M:%S")

            if st.session_state.price_update_time:
                st.caption(f"最後更新: {st.session_state.price_update_time}")

            realtime_prices = st.session_state.realtime_prices
            
            total_market_value = 0
            total_unrealized_net_profit = 0
            display_data = []
            
            for index, row in open_positions.iterrows():
                code = row['code']
                current_price = realtime_prices.get(code, row['買入價']) 
                
                qty = float(row['股數'])
                buy_p = float(row['買入價'])
                disc = float(row['手續費折數']) / 10.0
                
                market_val = current_price * qty
                cost_val = buy_p * qty
                
                buy_fee = max(int(cost_val * 0.001425 * disc), 1)
                sell_fee = max(int(market_val * 0.001425 * disc), 1)
                tax = int(market_val * 0.003)
                
                net_profit = (market_val - sell_fee - tax) - (cost_val + buy_fee)
                
                total_market_value += market_val
                total_unrealized_net_profit += net_profit
                
                display_data.append({
                    "ID": row["ID"],
                    "代號": row["代號"],
                    "買價": buy_p,
                    "股數": int(qty),
                    "現價": current_price,
                    "損益": int(net_profit),
                    "折數": row["手續費折數"],
                    "買入日期": row["買入日期"] # 這裡已經有了，下面顯示出來
                })

            col_m1, col_m2 = st.columns(2)
            col_m1.metric("市值", f"${total_market_value:,.0f}")
            col_m2.metric("淨損益", f"${total_unrealized_net_profit:,.0f}", delta_color="inverse")

            st.markdown("---")
            st.caption("📋 持倉明細")
            display_df = pd.DataFrame(display_data)
            
            # V8.1 修改：加入 '買入日期'
            mobile_cols = ["代號", "買入日期", "股數", "現價", "損益"]
            
            st.dataframe(
                display_df[mobile_cols].style.format({
                    "現價": "{:.2f}",
                    "損益": "{:+d}",
                }),
                use_container_width=True,
                hide_index=True
            )
            
            st.markdown("---")
            
            with st.expander("⚡ 執行平倉 (點擊展開)", expanded=True):
                options = {f"{row['代號']} (${row['損益']})": row['ID'] for row in display_data}
                selected_label = st.selectbox("選擇部位", list(options.keys()))
                
                if selected_label:
                    selected_id = options[selected_label]
                    target_data = next((item for item in display_data if str(item['ID']) == str(selected_id)), None)
                    
                    if target_data:
                        current_market_price = target_data['現價']
                        current_qty = target_data['股數']
                        
                        c1, c2 = st.columns(2)
                        with c1:
                            sell_date_input = st.date_input("賣出日", datetime.now())
                            sell_qty = st.number_input("股數", min_value=1, max_value=current_qty, value=current_qty)
                        with c2:
                            sell_price = st.number_input("價格", min_value=0.0, step=0.1, value=float(current_market_price), format="%.2f")
                            st.markdown("<br>", unsafe_allow_html=True) 
                            confirm_sell = st.button("🔴 賣出", use_container_width=True)

                        if confirm_sell:
                            df_curr = load_data()
                            raw_row = df_curr[df_curr["ID"].astype(str) == str(selected_id)].iloc[0]
                            
                            with st.spinner("處理中..."):
                                d_rate = float(raw_row["手續費折數"]) / 10
                                buy_p_val = float(raw_row["買入價"])
                                
                                buy_cost_raw = buy_p_val * sell_qty
                                buy_fee = max(int(buy_cost_raw * 0.001425 * d_rate), 1)
                                
                                sell_revenue = int(sell_price * sell_qty)
                                sell_fee = max(int(sell_revenue * 0.001425 * d_rate), 1)
                                tax = int(sell_revenue * 0.003)
                                
                                net_profit = sell_revenue - sell_fee - tax - (buy_cost_raw + buy_fee)
                                
                                idx_list = df_curr.index[df_curr['ID'].astype(str) == str(selected_id)].tolist()
                                
                                if idx_list:
                                    original_idx = idx_list[0]
                                    sell_date_str = sell_date_input.strftime("%Y-%m-%d")
                                    original_buy_date = raw_row.get("買入日期")
                                    if pd.isna(original_buy_date) or str(original_buy_date).strip() == "":
                                        original_buy_date = raw_row["日期"]

                                    if sell_qty == current_qty:
                                        df_curr.at[original_idx, "狀態"] = "已平倉"
                                        df_curr.at[original_idx, "賣出價"] = sell_price
                                        df_curr.at[original_idx, "損益"] = net_profit
                                        df_curr.at[original_idx, "日期"] = sell_date_str 
                                        df_curr.at[original_idx, "買入日期"] = original_buy_date
                                    else:
                                        remain_qty = current_qty - sell_qty
                                        df_curr.at[original_idx, "股數"] = remain_qty
                                        
                                        new_closed_record = raw_row.copy()
                                        new_closed_record["ID"] = str(int(time.time() * 1000))
                                        new_closed_record["股數"] = sell_qty
                                        new_closed_record["賣出價"] = sell_price
                                        new_closed_record["狀態"] = "已平倉"
                                        new_closed_record["損益"] = net_profit
                                        new_closed_record["日期"] = sell_date_str
                                        new_closed_record["買入日期"] = original_buy_date
                                        new_closed_record["心得"] = "" 
                                        if "止損價" in new_closed_record:
                                            del new_closed_record["止損價"]
                                        
                                        df_curr = pd.concat([pd.DataFrame([new_closed_record]), df_curr], ignore_index=True)

                                    save_data(df_curr)
                                    st.success(f"平倉完成！損益: {net_profit}")
                                    time.sleep(1)
                                    st.rerun()
        else:
            st.info("目前沒有庫存。")
    else:
        st.info("載入中...")

# === Tab 2: 歷史 (新增顯示買入日) ===
with tab2:
    if not df.empty and "狀態" in df.columns:
        closed_positions = df[df["狀態"] == "已平倉"].copy()
        if not closed_positions.empty:
            closed_positions["損益"] = pd.to_numeric(closed_positions["損益"])
            
            st.caption("📊 戰績健檢")
            wins = closed_positions[closed_positions["損益"] > 0]
            losses = closed_positions[closed_positions["損益"] <= 0]
            
            total_trades = len(closed_positions)
            win_count = len(wins)
            win_rate = (win_count / total_trades) * 100 if total_trades > 0 else 0
            
            total_profit = wins["損益"].sum()
            total_loss = abs(losses["損益"].sum())
            profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
            avg_pl = closed_positions["損益"].mean()
            
            c1, c2 = st.columns(2)
            c1.metric("勝率", f"{win_rate:.1f}%")
            c1.metric("總獲利", f"${closed_positions['損益'].sum():,.0f}")
            c2.metric("賺賠比", f"{profit_factor:.2f}")
            c2.metric("平均損益", f"${avg_pl:,.0f}")
            st.markdown("---")

            def highlight_profit(val):
                color = '#ff4b4b' if val > 0 else '#00c853'
                return f'color: {color}; font-weight: bold;'

            # V8.1 修改：加入 '買入日期' 並顯示在最前
            display_cols = ["買入日期", "日期", "代號", "損益", "心得"]
            show_df = closed_positions[display_cols].rename(columns={"日期": "賣出日"})
            
            st.dataframe(show_df.style.applymap(highlight_profit, subset=['損益']), use_container_width=True, hide_index=True)
            
            st.markdown("---")
            st.subheader("✍️ 心得筆記")
            note_options = {
                f"{row['日期']} {row['代號']} (${row['損益']})": row['ID'] 
                for index, row in closed_positions.iterrows()
            }
            selected_note_key = st.selectbox("選擇交易", list(note_options.keys()))
            if selected_note_key:
                note_id = note_options[selected_note_key]
                current_row = df[df["ID"].astype(str) == str(note_id)].iloc[0]
                current_note = current_row["心得"] if "心得" in current_row else ""
                new_note = st.text_area("筆記內容", value=str(current_note), height=100)
                if st.button("💾 儲存", use_container_width=True):
                    idx_list = df.index[df['ID'].astype(str) == str(note_id)].tolist()
                    if idx_list:
                        df.at[idx_list[0], "心得"] = new_note
                        save_data(df)
                        st.success("已更新！")
                        time.sleep(1)
                        st.rerun()
        else:
            st.info("尚無紀錄")

# === Tab 3: 分析 ===
with tab3:
    if not df.empty and "狀態" in df.columns:
        closed_df = df[df["狀態"] == "已平倉"].copy()
        if not closed_df.empty:
            closed_df["損益"] = pd.to_numeric(closed_df["損益"])
            closed_df["日期"] = pd.to_datetime(closed_df["日期"])
            closed_df["買入日期"] = pd.to_datetime(closed_df["買入日期"])
            closed_df = closed_df.sort_values("日期")
            
            closed_df["累積損益"] = closed_df["損益"].cumsum()
            st.markdown("##### 💰 淨值走勢")
            fig_line = px.line(closed_df, x="日期", y="累積損益", markers=True)
            fig_line.update_traces(line_color='#2980b9', line_width=3)
            fig_line.update_layout(margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig_line, use_container_width=True)
            
            st.markdown("---")

            st.markdown("##### 📅 每週損益")
            closed_df["週次"] = closed_df["日期"].dt.strftime('%W')
            weekly_perf = closed_df.groupby("週次")["損益"].sum().reset_index()
            fig_bar = px.bar(weekly_perf, x="週次", y="損益",
                                color="損益",
                                color_continuous_scale=["#00c853", "#ff4b4b"])
            fig_bar.update_layout(margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig_bar, use_container_width=True)
            
            st.markdown("---")

            st.markdown("##### ⏳ 持倉天數 vs 損益")
            closed_df["持倉天數"] = (closed_df["日期"] - closed_df["買入日期"]).dt.days
            
            fig_scatter = px.scatter(closed_df, x="持倉天數", y="損益",
                                     color="損益",
                                     size=closed_df["損益"].abs(),
                                     hover_data=["代號", "買入日期", "心得"],
                                     color_continuous_scale=["#00c853", "#ff4b4b"])
            fig_scatter.add_hline(y=0, line_dash="dash", line_color="gray")
            fig_scatter.update_layout(
                xaxis=dict(tickmode='linear', tick0=0, dtick=1),
                margin=dict(l=0, r=0, t=30, b=0)
            )
            st.plotly_chart(fig_scatter, use_container_width=True)

        else:
            st.info("累積紀錄後顯示圖表")
    else:
        st.info("尚無數據")

# === Tab 4: 管理 ===
with tab4:
    if not df.empty and "ID" in df.columns:
        st.caption("完整資料庫預覽")
        st.dataframe(df, use_container_width=True)
        
        st.subheader("🗑️ 刪除紀錄")
        delete_options = {f"{row['日期']} {row['代號']}": row['ID'] for index, row in df.iterrows()}
        if delete_options:
            delete_id = st.selectbox("選擇紀錄", list(delete_options.keys()))
            if st.button("❌ 刪除", type="primary", use_container_width=True):
                with st.spinner("刪除中..."):
                    real_delete_id = delete_options[delete_id]
                    df = df[df["ID"].astype(str) != str(real_delete_id)]
                    save_data(df)
                st.success("已刪除")
                time.sleep(1)
                st.rerun()
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

# --- 讀取資料 (全域) ---
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
        # 重新讀取以防覆蓋
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

# --- V8.0 新功能：側邊欄出場試算機 ---
st.sidebar.header("🧮 出場試算機")
if not df.empty and "狀態" in df.columns:
    open_ops = df[df["狀態"] == "持倉中"]
    if not open_ops.empty:
        # 製作選單
        calc_options = {f"{row['代號']} (成本 {row['買入價']})": index for index, row in open_ops.iterrows()}
        selected_calc_idx = st.sidebar.selectbox("選擇庫存", list(calc_options.keys()))
        
        if selected_calc_idx is not None:
            # 取得該筆資料
            target_pos = open_ops.loc[calc_options[selected_calc_idx]]
            cost_p = float(target_pos["買入價"])
            qty_h = int(target_pos["股數"])
            disc_h = float(target_pos["手續費折數"]) / 10.0
            
            # 目標價輸入
            target_sell_price = st.sidebar.number_input("目標賣出價", value=cost_p, min_value=0.0, step=0.1, format="%.2f")
            
            # 即時計算
            buy_cost_val = cost_p * qty_h
            buy_fee_val = max(int(buy_cost_val * 0.001425 * disc_h), 1)
            
            sell_val = target_sell_price * qty_h
            sell_fee_val = max(int(sell_val * 0.001425 * disc_h), 1)
            tax_val = int(sell_val * 0.003)
            
            net_p = sell_val - sell_fee_val - tax_val - (buy_cost_val + buy_fee_val)
            roi = (net_p / (buy_cost_val + buy_fee_val)) * 100 if buy_cost_val > 0 else 0
            
            # 顯示結果
            if net_p > 0:
                st.sidebar.success(f"預估淨利: ${int(net_p)}")
            elif net_p < 0:
                st.sidebar.error(f"預估虧損: ${int(net_p)}")
            else:
                st.sidebar.info("預估損益: $0")
                
            st.sidebar.caption(f"報酬率: {roi:.2f}% | 稅金: ${tax_val}")

    else:
        st.sidebar.caption("無庫存可試算")
else:
    st.sidebar.caption("無資料")


# --- 主畫面 ---
st.title("📱 台股戰情室 V8.0")

tab1, tab2, tab3, tab4 = st.tabs(["💼 持倉", "📜 歷史", "📊 分析", "🗑️ 管理"])

# === Tab 1: 持倉 ===
with tab1:
    if not df.empty and "狀態" in df.columns:
        open_positions = df[df["狀態"] == "持倉中"].copy()
        
        if not open_positions.empty:
            open_positions['code'] = open_positions['代號'].astype(str).str.extract(r'^(\d+)')
            unique_codes = open_positions['code'].dropna().unique().tolist()
            
            if st.button("🔄 更新即時股價", type="primary", use_container_width=True):
                if unique_codes:
                    with st.spinner("連線中..."):
                        prices, logs = get_realtime_prices(unique_codes)
                        st.session_state.realtime_prices = prices
                        st.session_state.debug_logs = logs
                        st.session_state.price_update_time = datetime.now().strftime("%H:%M:%S")

            if st.session_state.price_update_time:
                st.caption(f"最後更新: {st.session_state.price_update_time}")

            realtime_prices = st.session_state.realtime_prices
            
            total_market_value = 0
            total_unrealized_net_profit = 0
            display_data = []
            
            for index, row in open_positions.iterrows():
                code = row['code']
                current_price = realtime_prices.get(code, row['買入價']) 
                
                qty = float(row['股數'])
                buy_p = float(row['買入價'])
                disc = float(row['手續費折數']) / 10.0
                
                market_val = current_price * qty
                cost_val = buy_p * qty
                
                buy_fee = max(int(cost_val * 0.001425 * disc), 1)
                sell_fee = max(int(market_val * 0.001425 * disc), 1)
                tax = int(market_val * 0.003)
                
                net_profit = (market_val - sell_fee - tax) - (cost_val + buy_fee)
                
                total_market_value += market_val
                total_unrealized_net_profit += net_profit
                
                display_data.append({
                    "ID": row["ID"],
                    "代號": row["代號"],
                    "買價": buy_p,
                    "股數": int(qty),
                    "現價": current_price,
                    "損益": int(net_profit),
                    "折數": row["手續費折數"],
                    "買入日期": row["買入日期"]
                })

            col_m1, col_m2 = st.columns(2)
            col_m1.metric("市值", f"${total_market_value:,.0f}")
            col_m2.metric("淨損益", f"${total_unrealized_net_profit:,.0f}", delta_color="inverse")

            st.markdown("---")
            st.caption("📋 持倉明細")
            display_df = pd.DataFrame(display_data)
            mobile_cols = ["代號", "股數", "現價", "損益"]
            
            st.dataframe(
                display_df[mobile_cols].style.format({
                    "現價": "{:.2f}",
                    "損益": "{:+d}",
                }),
                use_container_width=True,
                hide_index=True
            )
            
            st.markdown("---")
            
            with st.expander("⚡ 執行平倉 (點擊展開)", expanded=True):
                options = {f"{row['代號']} (${row['損益']})": row['ID'] for row in display_data}
                selected_label = st.selectbox("選擇部位", list(options.keys()))
                
                if selected_label:
                    selected_id = options[selected_label]
                    target_data = next((item for item in display_data if str(item['ID']) == str(selected_id)), None)
                    
                    if target_data:
                        current_market_price = target_data['現價']
                        current_qty = target_data['股數']
                        
                        c1, c2 = st.columns(2)
                        with c1:
                            sell_date_input = st.date_input("賣出日", datetime.now())
                            sell_qty = st.number_input("股數", min_value=1, max_value=current_qty, value=current_qty)
                        with c2:
                            sell_price = st.number_input("價格", min_value=0.0, step=0.1, value=float(current_market_price), format="%.2f")
                            st.markdown("<br>", unsafe_allow_html=True) 
                            confirm_sell = st.button("🔴 賣出", use_container_width=True)

                        if confirm_sell:
                            # 讀取最新 DB
                            df_curr = load_data()
                            raw_row = df_curr[df_curr["ID"].astype(str) == str(selected_id)].iloc[0]
                            
                            with st.spinner("處理中..."):
                                d_rate = float(raw_row["手續費折數"]) / 10
                                buy_p_val = float(raw_row["買入價"])
                                
                                buy_cost_raw = buy_p_val * sell_qty
                                buy_fee = max(int(buy_cost_raw * 0.001425 * d_rate), 1)
                                
                                sell_revenue = int(sell_price * sell_qty)
                                sell_fee = max(int(sell_revenue * 0.001425 * d_rate), 1)
                                tax = int(sell_revenue * 0.003)
                                
                                net_profit = sell_revenue - sell_fee - tax - (buy_cost_raw + buy_fee)
                                
                                idx_list = df_curr.index[df_curr['ID'].astype(str) == str(selected_id)].tolist()
                                
                                if idx_list:
                                    original_idx = idx_list[0]
                                    sell_date_str = sell_date_input.strftime("%Y-%m-%d")
                                    original_buy_date = raw_row.get("買入日期")
                                    if pd.isna(original_buy_date) or str(original_buy_date).strip() == "":
                                        original_buy_date = raw_row["日期"]

                                    if sell_qty == current_qty:
                                        df_curr.at[original_idx, "狀態"] = "已平倉"
                                        df_curr.at[original_idx, "賣出價"] = sell_price
                                        df_curr.at[original_idx, "損益"] = net_profit
                                        df_curr.at[original_idx, "日期"] = sell_date_str 
                                        df_curr.at[original_idx, "買入日期"] = original_buy_date
                                    else:
                                        remain_qty = current_qty - sell_qty
                                        df_curr.at[original_idx, "股數"] = remain_qty
                                        
                                        new_closed_record = raw_row.copy()
                                        new_closed_record["ID"] = str(int(time.time() * 1000))
                                        new_closed_record["股數"] = sell_qty
                                        new_closed_record["賣出價"] = sell_price
                                        new_closed_record["狀態"] = "已平倉"
                                        new_closed_record["損益"] = net_profit
                                        new_closed_record["日期"] = sell_date_str
                                        new_closed_record["買入日期"] = original_buy_date
                                        new_closed_record["心得"] = "" 
                                        if "止損價" in new_closed_record:
                                            del new_closed_record["止損價"]
                                        
                                        df_curr = pd.concat([pd.DataFrame([new_closed_record]), df_curr], ignore_index=True)

                                    save_data(df_curr)
                                    st.success(f"平倉完成！損益: {net_profit}")
                                    time.sleep(1)
                                    st.rerun()
        else:
            st.info("目前沒有庫存。")
    else:
        st.info("載入中...")

# === Tab 2: 歷史 (V8.0 新增進階分析) ===
with tab2:
    if not df.empty and "狀態" in df.columns:
        closed_positions = df[df["狀態"] == "已平倉"].copy()
        if not closed_positions.empty:
            closed_positions["損益"] = pd.to_numeric(closed_positions["損益"])
            
            # --- V8.0 新增：戰績儀表板 ---
            st.caption("📊 戰績健檢")
            wins = closed_positions[closed_positions["損益"] > 0]
            losses = closed_positions[closed_positions["損益"] <= 0]
            
            total_trades = len(closed_positions)
            win_count = len(wins)
            win_rate = (win_count / total_trades) * 100 if total_trades > 0 else 0
            
            total_profit = wins["損益"].sum()
            total_loss = abs(losses["損益"].sum())
            profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
            avg_pl = closed_positions["損益"].mean()
            
            # 顯示指標 (2x2)
            c1, c2 = st.columns(2)
            c1.metric("勝率 (Win Rate)", f"{win_rate:.1f}%")
            c1.metric("總獲利", f"${closed_positions['損益'].sum():,.0f}")
            
            c2.metric("賺賠比 (PF)", f"{profit_factor:.2f}", help="總獲利 / 總虧損，建議 > 2.0")
            c2.metric("平均損益", f"${avg_pl:,.0f}")
            st.markdown("---")
            # ---------------------------

            def highlight_profit(val):
                color = '#ff4b4b' if val > 0 else '#00c853'
                return f'color: {color}; font-weight: bold;'

            display_cols = ["日期", "代號", "損益", "心得"]
            show_df = closed_positions[display_cols].rename(columns={"日期": "賣出日"})
            
            st.dataframe(show_df.style.applymap(highlight_profit, subset=['損益']), use_container_width=True, hide_index=True)
            
            st.markdown("---")
            st.subheader("✍️ 心得筆記")
            note_options = {
                f"{row['日期']} {row['代號']} (${row['損益']})": row['ID'] 
                for index, row in closed_positions.iterrows()
            }
            selected_note_key = st.selectbox("選擇交易", list(note_options.keys()))
            if selected_note_key:
                note_id = note_options[selected_note_key]
                current_row = df[df["ID"].astype(str) == str(note_id)].iloc[0]
                current_note = current_row["心得"] if "心得" in current_row else ""
                new_note = st.text_area("筆記內容", value=str(current_note), height=100)
                if st.button("💾 儲存", use_container_width=True):
                    idx_list = df.index[df['ID'].astype(str) == str(note_id)].tolist()
                    if idx_list:
                        df.at[idx_list[0], "心得"] = new_note
                        save_data(df)
                        st.success("已更新！")
                        time.sleep(1)
                        st.rerun()
        else:
            st.info("尚無紀錄")

# === Tab 3: 分析 ===
with tab3:
    if not df.empty and "狀態" in df.columns:
        closed_df = df[df["狀態"] == "已平倉"].copy()
        if not closed_df.empty:
            closed_df["損益"] = pd.to_numeric(closed_df["損益"])
            closed_df["日期"] = pd.to_datetime(closed_df["日期"])
            closed_df["買入日期"] = pd.to_datetime(closed_df["買入日期"])
            closed_df = closed_df.sort_values("日期")
            
            closed_df["累積損益"] = closed_df["損益"].cumsum()
            st.markdown("##### 💰 淨值走勢")
            fig_line = px.line(closed_df, x="日期", y="累積損益", markers=True)
            fig_line.update_traces(line_color='#2980b9', line_width=3)
            fig_line.update_layout(margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig_line, use_container_width=True)
            
            st.markdown("---")

            st.markdown("##### 📅 每週損益")
            closed_df["週次"] = closed_df["日期"].dt.strftime('%W')
            weekly_perf = closed_df.groupby("週次")["損益"].sum().reset_index()
            fig_bar = px.bar(weekly_perf, x="週次", y="損益",
                                color="損益",
                                color_continuous_scale=["#00c853", "#ff4b4b"])
            fig_bar.update_layout(margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig_bar, use_container_width=True)
            
            st.markdown("---")

            st.markdown("##### ⏳ 持倉天數 vs 損益")
            closed_df["持倉天數"] = (closed_df["日期"] - closed_df["買入日期"]).dt.days
            
            fig_scatter = px.scatter(closed_df, x="持倉天數", y="損益",
                                     color="損益",
                                     size=closed_df["損益"].abs(),
                                     hover_data=["代號", "買入日期", "心得"],
                                     color_continuous_scale=["#00c853", "#ff4b4b"])
            fig_scatter.add_hline(y=0, line_dash="dash", line_color="gray")
            fig_scatter.update_layout(
                xaxis=dict(tickmode='linear', tick0=0, dtick=1),
                margin=dict(l=0, r=0, t=30, b=0)
            )
            st.plotly_chart(fig_scatter, use_container_width=True)

        else:
            st.info("累積紀錄後顯示圖表")
    else:
        st.info("尚無數據")

# === Tab 4: 管理 ===
with tab4:
    if not df.empty and "ID" in df.columns:
        st.caption("完整資料庫預覽")
        st.dataframe(df, use_container_width=True)
        
        st.subheader("🗑️ 刪除紀錄")
        delete_options = {f"{row['日期']} {row['代號']}": row['ID'] for index, row in df.iterrows()}
        if delete_options:
            delete_id = st.selectbox("選擇紀錄", list(delete_options.keys()))
            if st.button("❌ 刪除", type="primary", use_container_width=True):
                with st.spinner("刪除中..."):
                    real_delete_id = delete_options[delete_id]
                    df = df[df["ID"].astype(str) != str(real_delete_id)]
                    save_data(df)
                st.success("已刪除")
                time.sleep(1)
                st.rerun()