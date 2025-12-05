import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials # <--- 換成新套件

# --- 設定頁面 ---
st.set_page_config(page_title="資產負債與現金流戰情室", layout="wide", page_icon="🛡️")

# ==========================================
# 1. 資料處理核心
# ==========================================
def parse_my_data(raw_data):
    assets = []
    liabilities = []
    section = "asset" 
    
    for row in raw_data:
        # 補齊欄位長度
        row = row + [''] * (5 - len(row))
        item_name = str(row[0]).strip()
        
        # 排除無效行與合計行
        if not item_name or item_name in ["項目", ""]: continue
        if "合計" in item_name: continue
        if "淨值" in item_name: continue
        if "匯率" in item_name: continue

        def clean_num(x):
            if isinstance(x, (int, float)): return x
            x_str = str(x).replace(',', '').replace('NT$', '').replace('%', '').strip()
            return float(x_str) if x_str else 0
        
        val_1 = clean_num(row[1])
        val_3 = clean_num(row[3])

        # 特殊處理：抵利型現金 (備援)
        if "抵利型" in item_name and "房貸" not in item_name and "現金" in item_name:
            amount = max(val_1, val_3)
            assets.append({"類別": "備援現金", "項目": item_name, "金額": amount, "股數": 0, "備援": True})
            continue

        # 區塊切換判斷
        if ("房貸" in item_name or "信貸" in item_name or "借款" in item_name) and "抵利型" not in item_name:
            section = "liability"
        
        # 資產區塊處理
        if section == "asset":
            amount = val_3 if val_3 > 0 else val_1
            shares = val_1 if val_3 > 0 else 0
            
            category = "其他"
            if "現金" in item_name or "口袋" in item_name or "活存" in item_name or "e財庫" in item_name: category = "現金"
            elif "美股" in item_name or "VT" in item_name or "VOO" in item_name: category = "美股"
            elif "鴻海" in item_name or "0050" in item_name or "台股" in item_name: category = "台股"
            
            assets.append({
                "類別": category, "項目": item_name, "金額": amount, "股數": shares, "備援": False
            })

        # 負債區塊處理
        elif section == "liability":
            amount = val_1
            if amount > 0:
                liabilities.append({"類別": "負債", "項目": item_name, "金額": -amount, "股數": 0, "備援": False})

    return pd.DataFrame(assets + liabilities)

# ==========================================
# 2. 新版穩定連線 (使用 google-auth)
# ==========================================
# 增加快取機制，避免頻繁連線錯誤
@st.cache_data(ttl=600)
def load_google_sheet_data():
    try:
        # 定義權限範圍
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        
        # 判斷是在雲端還是在本地
        if "gcp_service_account" in st.secrets:
            # 雲端模式：直接從 Secrets 讀取字典
            creds_dict = dict(st.secrets["gcp_service_account"])
            
            # 修正 private_key 的換行問題 (這是最常見的錯誤點)
            if "private_key" in creds_dict:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        else:
            # 本地模式
            creds = Credentials.from_service_account_file('secrets.json', scopes=scopes)
        
        client = gspread.authorize(creds)
        
        # ⚠️ 請確認檔名
        sheet_name = "@最新_家用收支入管理表_google程式用"
        sheet = client.open(sheet_name).sheet1
        return sheet.get_all_values()
        
    except Exception as e:
        return str(e) # 回傳錯誤訊息

# ==========================================
# 3. 儀表板顯示邏輯
# ==========================================
st.title("🛡️ 資產配置與現金流戰情室")

# 更新按鈕
if st.sidebar.button("🔄 更新最新數據 (Clear Cache)"):
    st.cache_data.clear()
    st.rerun()

# 載入資料
raw_data_or_error = load_google_sheet_data()

# 檢查是否連線失敗
if isinstance(raw_data_or_error, str):
    st.error(f"連線失敗！請檢查 Secrets 設定。錯誤詳情：{raw_data_or_error}")
    # 為了不讓畫面全白，建立一個空表格
    df = pd.DataFrame()
else:
    df = parse_my_data(raw_data_or_error)

if not df.empty:
    assets_df = df[df['金額'] > 0]
    liabilities_df = df[df['金額'] < 0]
    
    # --- 1. 數據分類計算 ---
    
    # Buffer Cash (Layer 4)
    buffer_cash_df = assets_df[assets_df['備援'] == True]
    buffer_cash = buffer_cash_df['金額'].sum() 
    
    # General Assets (包含既有現金 Layer 3 + 股票)
    general_assets_df = assets_df[assets_df['備援'] == False]
    general_assets = general_assets_df['金額'].sum()
    
    # Normal Cash only (Layer 3)
    normal_cash_df = assets_df[(assets_df['類別'] == '現金') & (assets_df['備援'] == False)]
    normal_cash = normal_cash_df['金額'].sum()
    
    # Total Assets
    total_assets = general_assets + buffer_cash 
    
    total_liabilities = liabilities_df['金額'].sum()
    net_worth = total_assets + total_liabilities
    
    honhai_df = assets_df[assets_df['項目'].str.contains("鴻海")]
    total_honhai_shares = honhai_df['股數'].sum()

    # --- 2. 頂部指標區 ---
    col1, col2, col3, col4 = st.columns(4)
    
    col1.metric("真實總資產", f"${total_assets/10000:,.0f} 萬", 
                help=f"一般資產 {general_assets/10000:.0f}萬 + 備援現金 {buffer_cash/10000:.0f}萬")
    
    col2.metric("總負債", f"${total_liabilities/10000:,.0f} 萬", delta_color="inverse")
    
    col3.metric("淨資產", f"${net_worth/10000:,.0f} 萬")
    
    col4.metric("🛡️ 抵利型備援現金", f"${buffer_cash/10000:,.0f} 萬", 
                delta="Layer 4 最後防線", delta_color="off")
    
    st.info(f"💰 **現金水位分析**：既有活存 **${normal_cash/10000:,.0f} 萬** (Layer 3) / 抵利型備援 **${buffer_cash/10000:,.0f} 萬** (Layer 4)")

    st.markdown("---")

    # --- 3. 核心功能 ---
    st.header("🌊 現金流與提領策略")

    st.sidebar.header("📊 參數設定")
    
    honhai_eps = st.sidebar.number_input("鴻海預估配息 (元)", value=7.0, step=0.5)
    iwr = st.sidebar.number_input("GK 初始提領率 (%)", value=4.0, step=0.1) / 100
    inflation_rate = st.sidebar.number_input("預估通膨率 (%)", value=2.0, step=0.1) / 100
    monthly_living = st.sidebar.number_input("純生活費 (月)", value=60000, step=5000)
    monthly_debt = st.sidebar.number_input("負債月付金 (房貸/信貸)", value=125000, step=5000)
    
    # --- 運算邏輯 ---
    annual_living_cost = monthly_living * 12 * (1 + inflation_rate)
    annual_debt_cost = monthly_debt * 12
    total_expense = annual_living_cost + annual_debt_cost

    dividend_income = total_honhai_shares * honhai_eps
    
    gk_base = general_assets 
    gk_total_limit = gk_base * iwr 
    sell_stock_amount = max(0, gk_total_limit - dividend_income) 
    
    funds_stage_1 = dividend_income + sell_stock_amount
    gap_1 = total_expense - funds_stage_1
    
    use_normal_cash = 0
    use_buffer_cash = 0
    
    if gap_1 > 0:
        use_normal_cash = min(gap_1, normal_cash)
        gap_2 = gap_1 - use_normal_cash
        if gap_2 > 0:
            use_buffer_cash = gap_2

    # --- 版面顯示 ---
    c1, c2 = st.columns([1, 2])

    with c1:
        st.subheader("📊 資金調度順序")
        st.metric("1. 股息收入", f"${dividend_income:,.0f}", delta="Layer 1")
        st.metric("2. GK 賣股", f"${sell_stock_amount:,.0f}", delta="Layer 2")
        
        if use_normal_cash > 0:
            st.metric("3. 動用既有現金", f"${use_normal_cash:,.0f}", delta="Layer 3 (優先)", delta_color="inverse")
        else:
            st.write("3. 動用既有現金: $0 (充足)")
            
        if use_buffer_cash > 0:
            st.metric("4. 動用抵利型備援", f"${use_buffer_cash:,.0f}", delta="Layer 4 (最後)", delta_color="inverse")
            st.error("⚠️ 需動用最後防線")
        else:
            st.write("4. 動用抵利型備援: $0 (安全)")
            
        st.markdown("---")
        total_income = funds_stage_1 + use_normal_cash + use_buffer_cash
        final_balance = total_income - total_expense
        st.metric("總支出需求", f"${total_expense:,.0f}", delta_color="inverse")

    with c2:
        st.subheader("🌊 資金瀑布圖 (Waterfall)")
        
        measure_list = ["relative", "relative"]
        x_list = ["1.股息", "2.賣股(GK)"]
        y_list = [dividend_income, sell_stock_amount]
        text_list = [f"+{dividend_income/10000:.0f}萬", f"+{sell_stock_amount/10000:.0f}萬"]
        
        if use_normal_cash > 0:
            measure_list.append("relative")
            x_list.append("3.既有現金")
            y_list.append(use_normal_cash)
            text_list.append(f"+{use_normal_cash/10000:.0f}萬")
            
        if use_buffer_cash > 0:
            measure_list.append("relative")
            x_list.append("4.備援現金")
            y_list.append(use_buffer_cash)
            text_list.append(f"+{use_buffer_cash/10000:.0f}萬")
            
        measure_list.extend(["total", "relative", "relative", "total"])
        x_list.extend(["可用資金小計", "生活費(含通膨)", "還債", "最終結餘"])
        
        subtotal = dividend_income + sell_stock_amount + use_normal_cash + use_buffer_cash
        
        y_list.extend([0, -annual_living_cost, -annual_debt_cost, 0])
        text_list.extend([
            f"={subtotal/10000:.0f}萬",
            f"-{annual_living_cost/10000:.0f}萬",
            f"-{annual_debt_cost/10000:.0f}萬",
            f"{final_balance/10000:.0f}萬"
        ])
        
        fig = go.Figure(go.Waterfall(
            name = "Cashflow", orientation = "v",
            measure = measure_list,
            x = x_list,
            textposition = "outside",
            text = text_list,
            y = y_list,
            connector = {"line":{"color":"rgb(63, 63, 63)"}},
            decreasing = {"marker":{"color":"#EF553B"}}, 
            increasing = {"marker":{"color":"#00CC96"}}, 
            totals = {"marker":{"color":"#1f77b4"}}
        ))
        st.plotly_chart(fig, use_container_width=True)

    # --- 資產圖表 ---
    st.markdown("---")
    col_chart1, col_chart2 = st.columns(2)
    with col_chart1:
        st.subheader("資產配置 (含備援)")
        fig_pie = px.pie(assets_df, values='金額', names='類別', hole=0.4)
        st.plotly_chart(fig_pie, use_container_width=True)
    with col_chart2:
        st.subheader("資產負債明細表")
        st.dataframe(df, height=300)

else:
    st.info("請確認 Secrets 設定是否正確...")