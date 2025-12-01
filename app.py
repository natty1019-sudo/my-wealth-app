import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 設定頁面 ---
st.set_page_config(page_title="資產負債與現金流戰情室", layout="wide", page_icon="🛡️")

# ==========================================
# 1. 資料處理核心 (改良版：讀取股數 + 抓取底部備援金)
# ==========================================
def parse_my_data(raw_data):
    """
    解析混合格式，重點：
    1. 抓取股數 (Column 2)
    2. 抓取底部的抵利型現金
    3. 排除原本表格的合計列 (避免重複計算)
    """
    assets = []
    liabilities = []
    
    # 用於判斷目前讀取位置的狀態
    section = "asset" 
    
    for row in raw_data:
        # 1. 補齊欄位長度
        row = row + [''] * (5 - len(row))
        item_name = str(row[0]).strip()
        
        # 2. 【防呆機制】排除無效行與合計行 (確保資產不會算兩次)
        if not item_name or item_name in ["項目", ""]: continue
        if "合計" in item_name: continue  # 關鍵：略過原本表格的加總行
        if "淨值" in item_name: continue
        if "匯率" in item_name: continue

        # 3. 數值清理 (讀取金額與股數)
        def clean_num(x):
            if isinstance(x, (int, float)): return x
            x_str = str(x).replace(',', '').replace('NT$', '').replace('%', '').strip()
            return float(x_str) if x_str else 0
        
        # 嘗試讀取各個位置的數值
        val_1 = clean_num(row[1]) # 第2欄 (通常是股數 或 負債金額)
        val_3 = clean_num(row[3]) # 第4欄 (通常是資產金額)

        # 4. 判斷邏輯
        
        # --- 特殊處理：抵利型現金 (備援) ---
        # 即使它在表格下方，只要名字對了，就強制歸類為資產
        if "抵利型" in item_name and "房貸" not in item_name and "現金" in item_name:
            # 這是資產 (現金)
            amount = max(val_1, val_3) # 抓最大的數字
            assets.append({"類別": "備援現金", "項目": item_name, "金額": amount, "股數": 0, "備援": True})
            continue

        # --- 區塊切換邏輯 ---
        if ("房貸" in item_name or "信貸" in item_name or "借款" in item_name) and "抵利型" not in item_name:
            section = "liability"
        
        # --- A. 資產區塊 ---
        if section == "asset":
            # 金額通常在第4欄，若無則找第2欄
            amount = val_3 if val_3 > 0 else val_1
            
            # 股數通常在第2欄 (若金額在第4欄)
            shares = val_1 if val_3 > 0 else 0
            
            # 自動分類
            category = "其他"
            if "現金" in item_name or "口袋" in item_name or "活存" in item_name: category = "現金"
            elif "美股" in item_name or "VT" in item_name or "VOO" in item_name: category = "美股"
            elif "鴻海" in item_name or "0050" in item_name or "台股" in item_name: category = "台股"
            
            assets.append({
                "類別": category, 
                "項目": item_name, 
                "金額": amount, 
                "股數": shares, 
                "備援": False
            })

        # --- B. 負債區塊 ---
        elif section == "liability":
            amount = val_1
            if amount > 0:
                liabilities.append({"類別": "負債", "項目": item_name, "金額": -amount, "股數": 0, "備援": False})

    return pd.DataFrame(assets + liabilities)

# ==========================================
# 2. 資料來源設定
# ==========================================

# --- 模式 A: 測試數據 (加入您的 652萬 備援現金) ---
# ⚠️ 這裡加入了您指定的「抵利型」在最下方，驗證是否能被抓到
raw_data_paste = [
    ["鴻海股票（質押中）", "142000", "229.5", "32,589,000"],
    ["鴻海股票（可動用）", "80000", "229.5", "18,360,000"],
    ["0050 ETF", "20,000", "61.95", "1,239,000"],
    ["美股資產", "", "", "4,000,000"],
    ["一般現金", "", "", "2,292,969"],
    ["✅ 資產合計", "", "", "58,480,969"], # 程式會略過這行，防止重複
    ["", "", "", ""],
    ["富邦房貸", "11,540,000", "2.60%", ""],
    ["股票質押借款", "16,020,000", "2.41%", ""],
    ["其他信貸", "6,960,000", "", ""], 
    ["❌ 負債合計", "34,520,000", "", ""], # 程式會略過這行
    ["", "", "", ""],
    ["現金_富邦_抵利型現金帳戶", "", "", "6,520,000"] # 這是您要補上的 652萬
]

# --- 模式 B: 正式連線 Google Sheets ---
# ⚠️ 確認數字無誤後，請刪除上面的 raw_data_paste，並解開下面註解
# -------------------------------------------------------
# try:
#     scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
#     
#     # 讀取 Secrets
#     if "gcp_service_account" in st.secrets:
#         creds_dict = st.secrets["gcp_service_account"]
#         creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
#     else:
#         creds = ServiceAccountCredentials.from_json_keyfile_name('secrets.json', scope)
#     
#     client = gspread.authorize(creds)
#     
#     # *** 請務必確認這裡的名稱與您的 Google Sheet 檔名一致 ***
#     sheet = client.open("2024資產負債表").sheet1 
#     raw_data_paste = sheet.get_all_values()
# except Exception as e:
#     st.error(f"連線失敗: {e}")
#     raw_data_paste = []
# -------------------------------------------------------

df = parse_my_data(raw_data_paste)

# ==========================================
# 3. 儀表板顯示邏輯
# ==========================================
st.title("🛡️ 資產配置與現金流戰情室")

if not df.empty:
    assets_df = df[df['金額'] > 0]
    liabilities_df = df[df['金額'] < 0]
    
    # --- 關鍵數據計算 ---
    
    # 1. 備援現金 (獨立拉出來)
    buffer_cash_df = assets_df[assets_df['備援'] == True]
    buffer_cash = buffer_cash_df['金額'].sum()
    
    # 2. 一般資產 (扣除備援)
    general_assets_df = assets_df[assets_df['備援'] == False]
    general_assets = general_assets_df['金額'].sum()
    
    # 3. 真實總資產 = 一般 + 備援
    total_assets = general_assets + buffer_cash
    
    # 4. 總負債
    total_liabilities = liabilities_df['金額'].sum()
    
    # 5. 淨值
    net_worth = total_assets + total_liabilities
    
    # 6. 鴻海總股數
    honhai_df = assets_df[assets_df['項目'].str.contains("鴻海")]
    total_honhai_shares = honhai_df['股數'].sum()

    # --- 頂部指標區 ---
    col1, col2, col3, col4 = st.columns(4)
    
    col1.metric("真實總資產", f"${total_assets/10000:,.0f} 萬", 
                help=f"一般資產 {general_assets/10000:.0f}萬 + 備援現金 {buffer_cash/10000:.0f}萬")
    
    col2.metric("總負債", f"${total_liabilities/10000:,.0f} 萬", delta_color="inverse")
    
    col3.metric("淨資產", f"${net_worth/10000:,.0f} 萬")
    
    # 備援現金展示
    col4.metric("🛡️ 抵利型備援現金", f"${buffer_cash/10000:,.0f} 萬", 
                delta="未計入GK提領基數", delta_color="off")

    st.markdown("---")

    # --- 核心功能：股息現金流 + GK 提領 ---
    st.header("🌊 現金流與提領策略")

    st.sidebar.header("參數設定")
    
    # 1. 股息設定
    honhai_eps = st.sidebar.number_input("鴻海預估配息 (元)", value=7.0, step=0.5)
    
    # 2. GK 提領設定
    iwr = st.sidebar.number_input("GK 初始提領率 (%)", value=4.0, step=0.1) / 100
    
    # 3. 生活費設定
    monthly_expense = st.sidebar.number_input("預估月生活費", value=100000, step=10000)
    annual_expense = monthly_expense * 12

    # --- 計算邏輯 ---
    estimated_dividend = total_honhai_shares * honhai_eps
    
    # GK 提領基數選擇：
    # 這裡預設將「抵利型現金」視為安全氣囊，不納入提領計算
    # 基數 = (總資產 - 備援現金 - 投資型負債)
    # 若要更保守，可扣除全部負債
    
    investment_debt = abs(total_liabilities) # 簡化：視所有負債為需償還成本
    base_for_gk = max(0, total_assets - buffer_cash - investment_debt)
    
    target_withdraw = base_for_gk * iwr
    
    # 資金缺口 = GK建議提領 - 股息收入
    gap = target_withdraw - estimated_dividend

    # --- 版面顯示 ---
    c1, c2 = st.columns([1, 2])

    with c1:
        st.subheader("📊 收入來源")
        st.write(f"鴻海股數: **{total_honhai_shares:,.0f}** 股")
        st.metric("1. 預估股息 (現金流)", f"${estimated_dividend:,.0f}", delta=f"EPS: {honhai_eps}元")
        st.metric("2. GK 建議提領上限", f"${target_withdraw:,.0f}", help="基數 = (總資產 - 備援 - 負債)")
        
        st.info(f"""
        **🛡️ 備援能力分析**
        抵利型現金：`${buffer_cash:,.0f}`
        可支撐生活： **{buffer_cash/monthly_expense:.1f} 個月**
        *(假設完全不賣股、不領息)*
        """)

    with c2:
        st.subheader("🌊 資金瀑布圖 (Waterfall)")
        
        fig = go.Figure(go.Waterfall(
            name = "Cashflow", orientation = "v",
            measure = ["relative", "relative", "total", "total", "relative"],
            x = ["股息收入", "需賣資產補足", "可提領現金總額", "年度生活費", "結餘/透支"],
            textposition = "outside",
            text = [
                f"+{estimated_dividend/10000:.0f}萬", 
                f"+{gap/10000:.0f}萬", 
                f"={target_withdraw/10000:.0f}萬", 
                f"-{annual_expense/10000:.0f}萬",
                f"{(target_withdraw - annual_expense)/10000:.0f}萬"
            ],
            y = [
                estimated_dividend, 
                gap, 
                target_withdraw, 
                -annual_expense, 
                (target_withdraw - annual_expense)
            ],
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
    st.write("資料讀取中... 若無顯示請檢查連線。")