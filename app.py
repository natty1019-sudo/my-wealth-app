import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials

# --- 設定網頁 ---
st.set_page_config(page_title="資產負債與現金流戰情室", layout="wide", page_icon="🛡️")

# ==========================================
# A. 連線模組 (針對 Secrets 格式進行防呆處理)
# ==========================================
@st.cache_data(ttl=600)
def load_data():
    """連線 Google Sheets 並讀取所有資料"""
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    
    try:
        # 1. 取得憑證資料 (強制轉為字典格式)
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
        else:
            # 本地開發用
            return "錯誤：找不到 Secrets 設定。"

        # 2. 修正 private_key 的換行符號問題 (最常見的連線錯誤原因)
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

        # 3. 建立憑證與連線
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        
        # 4. 開啟試算表 (請確認檔名完全一致)
        sheet_name = "@最新_家用收支入管理表_google程式用"
        sheet = client.open(sheet_name).sheet1
        return sheet.get_all_values()

    except Exception as e:
        return f"連線失敗: {str(e)}"

# ==========================================
# B. 資料解析模組 (邏輯核心)
# ==========================================
def parse_data(raw_data):
    assets = []
    liabilities = []
    
    # 預設狀態
    section = "asset"
    
    for row in raw_data:
        # 補齊欄位長度
        row = row + [''] * (5 - len(row))
        item_name = str(row[0]).strip()
        
        # --- 排除無效行 ---
        if not item_name or item_name in ["項目", ""]: continue
        if "合計" in item_name: continue # 關鍵：排除表格原本的加總，由程式重算
        if "淨值" in item_name: continue
        if "匯率" in item_name: continue

        # --- 數值清理函式 ---
        def clean_num(x):
            if isinstance(x, (int, float)): return x
            x_str = str(x).replace(',', '').replace('NT$', '').replace('%', '').strip()
            return float(x_str) if x_str else 0
        
        val_1 = clean_num(row[1]) # 第2欄
        val_3 = clean_num(row[3]) # 第4欄

        # --- 1. 特殊判定：抵利型備援現金 ---
        # 無論它在表格哪裡，只要名字對，就強制歸類為 "備援"
        if "抵利型" in item_name and "房貸" not in item_name and "現金" in item_name:
            amount = max(val_1, val_3)
            assets.append({"類別": "備援現金", "項目": item_name, "金額": amount, "股數": 0, "備援": True})
            continue

        # --- 2. 區塊切換判定 (資產 -> 負債) ---
        if ("房貸" in item_name or "信貸" in item_name or "借款" in item_name) and "抵利型" not in item_name:
            section = "liability"
        
        # --- 3. 資產區塊處理 ---
        if section == "asset":
            # 抓取金額 (優先看第4欄)
            amount = val_3 if val_3 > 0 else val_1
            # 抓取股數 (若金額在第4欄，股數通常在第2欄)
            shares = val_1 if val_3 > 0 else 0
            
            # 自動分類
            category = "其他"
            if any(x in item_name for x in ["現金", "口袋", "活存", "e財庫"]): category = "現金"
            elif any(x in item_name for x in ["美股", "VT", "VOO"]): category = "美股"
            elif any(x in item_name for x in ["鴻海", "0050", "台股"]): category = "台股"
            
            assets.append({
                "類別": category, "項目": item_name, "金額": amount, "股數": shares, "備援": False
            })

        # --- 4. 負債區塊處理 ---
        elif section == "liability":
            amount = val_1
            if amount > 0:
                liabilities.append({"類別": "負債", "項目": item_name, "金額": -amount, "股數": 0, "備援": False})

    return pd.DataFrame(assets + liabilities)

# ==========================================
# C. 主程式介面
# ==========================================

# 1. 側邊欄更新按鈕
st.sidebar.title("⚙️ 設定")
if st.sidebar.button("🔄 更新最新數據"):
    st.cache_data.clear()
    st.rerun()

# 2. 載入資料
raw_data_or_error = load_data()

# 3. 錯誤檢查
if isinstance(raw_data_or_error, str):
    st.error("⚠️ 無法讀取資料")
    st.code(raw_data_or_error)
    st.warning("請檢查：1. Secrets 格式是否正確 2. Google Sheet 檔名是否完全一致 3. 是否已共用給機器人")
    st.stop() # 停止執行後續程式

# 4. 解析資料
df = parse_data(raw_data_or_error)

if not df.empty:
    # --- 數據運算 ---
    assets_df = df[df['金額'] > 0]
    liabilities_df = df[df['金額'] < 0]
    
    # 分類加總
    buffer_cash_df = assets_df[assets_df['備援'] == True]
    buffer_cash = buffer_cash_df['金額'].sum() 
    
    general_assets_df = assets_df[assets_df['備援'] == False]
    general_assets = general_assets_df['金額'].sum()
    
    normal_cash_df = assets_df[(assets_df['類別'] == '現金') & (assets_df['備援'] == False)]
    normal_cash = normal_cash_df['金額'].sum()
    
    total_assets = general_assets + buffer_cash 
    total_liabilities = liabilities_df['金額'].sum()
    net_worth = total_assets + total_liabilities
    
    # 鴻海股數
    honhai_df = assets_df[assets_df['項目'].str.contains("鴻海")]
    total_honhai_shares = honhai_df['股數'].sum()

    # --- 頂部指標區 ---
    st.title("🛡️ 資產負債與現金流戰情室")
    col1, col2, col3, col4 = st.columns(4)
    
    col1.metric("真實總資產", f"${total_assets/10000:,.0f} 萬", help="一般資產 + 抵利型備援")
    col2.metric("總負債", f"${total_liabilities/10000:,.0f} 萬", delta_color="inverse")
    col3.metric("淨資產", f"${net_worth/10000:,.0f} 萬")
    col4.metric("🛡️ 抵利型備援", f"${buffer_cash/10000:,.0f} 萬", delta="Layer 4", delta_color="off")
    
    st.info(f"💰 **現金水位**：一般活存 **${normal_cash/10000:,.0f} 萬** (Layer 3) / 抵利型備援 **${buffer_cash/10000:,.0f} 萬** (Layer 4)")

    st.markdown("---")

    # --- 核心策略區 ---
    st.header("🌊 現金流與提領策略")

    # 參數設定
    st.sidebar.header("📊 參數設定")
    honhai_eps = st.sidebar.number_input("鴻海預估配息 (元)", value=7.0, step=0.5)
    iwr = st.sidebar.number_input("GK 初始提領率 (%)", value=4.0, step=0.1) / 100
    inflation_rate = st.sidebar.number_input("預估通膨率 (%)", value=2.0, step=0.1) / 100
    monthly_living = st.sidebar.number_input("純生活費 (月)", value=60000, step=5000)
    monthly_debt = st.sidebar.number_input("負債月付金 (房貸/信貸)", value=125000, step=5000)
    
    # --- 資金邏輯運算 ---
    
    # 1. 支出
    annual_living_cost = monthly_living * 12 * (1 + inflation_rate)
    annual_debt_cost = monthly_debt * 12
    total_expense = annual_living_cost + annual_debt_cost

    # 2. Layer 1: 股息
    dividend_income = total_honhai_shares * honhai_eps
    
    # 3. Layer 2: GK 賣股 (基數為一般資產，不含備援)
    gk_base = general_assets 
    gk_total_limit = gk_base * iwr 
    sell_stock_amount = max(0, gk_total_limit - dividend_income) 
    
    # 第一階段資金
    funds_stage_1 = dividend_income + sell_stock_amount
    gap_1 = total_expense - funds_stage_1
    
    # 4. Layer 3 & 4 調度
    use_normal_cash = 0
    use_buffer_cash = 0
    
    if gap_1 > 0:
        # 先扣既有現金
        use_normal_cash = min(gap_1, normal_cash)
        gap_2 = gap_1 - use_normal_cash
        
        # 再扣備援現金
        if gap_2 > 0:
            use_buffer_cash = gap_2

    # --- 顯示結果 ---
    c1, c2 = st.columns([1, 2])

    with c1:
        st.subheader("📊 收支概況")
        st.write(f"鴻海總股數: **{total_honhai_shares:,.0f}** 股")
        st.metric("1. 股息收入", f"${dividend_income:,.0f}", delta="Layer 1")
        st.metric("2. GK 賣股", f"${sell_stock_amount:,.0f}", delta="Layer 2")
        st.metric("3. 總支出需求", f"${total_expense:,.0f}", delta_color="inverse")
        
        st.markdown("---")
        if use_buffer_cash > 0:
            st.error(f"⚠️ **需動用備援金**")
            st.metric("提領金額", f"${use_buffer_cash:,.0f}", delta="Layer 4")
            survival_years = buffer_cash / use_buffer_cash if use_buffer_cash > 0 else 99
            st.write(f"備援金可支撐： **{survival_years:.1f} 年**")
        else:
            surplus = (funds_stage_1 + use_normal_cash) - total_expense
            st.success(f"🎉 **現金流充裕**")
            st.metric("年度結餘", f"${surplus:,.0f}")

    with c2:
        st.subheader("🌊 資金瀑布圖")
        
        # 繪圖數據
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
        
        final_balance = subtotal - annual_living_cost - annual_debt_cost
        
        text_list.extend([
            f"={subtotal/10000:.0f}萬",
            f"-{annual_living_cost/10000:.0f}萬",
            f"-{annual_debt_cost/10000:.0f}萬",
            f"{final_balance/10000:.0f}萬"
        ])
        
        fig = go.Figure(go.Waterfall(
            name = "Cashflow", orientation = "v",
            measure = measure_list, x = x_list, textposition = "outside", text = text_list, y = y_list,
            connector = {"line":{"color":"rgb(63, 63, 63)"}},
            decreasing = {"marker":{"color":"#EF553B"}}, 
            increasing = {"marker":{"color":"#00CC96"}}, 
            totals = {"marker":{"color":"#1f77b4"}}
        ))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    with st.expander("查看詳細資產清單"):
        st.dataframe(df)