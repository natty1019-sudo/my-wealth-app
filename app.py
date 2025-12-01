import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 設定頁面 ---
st.set_page_config(page_title="資產負債與現金流戰情室", layout="wide", page_icon="🛡️")

# ==========================================
# 1. 資料處理核心 (升級版：讀取股數 + 備援標記)
# ==========================================
def parse_my_data(raw_data):
    assets = []
    liabilities = []
    section = "asset"
    
    for row in raw_data:
        row = row + [''] * (5 - len(row))
        item_name = str(row[0]).strip()
        
        # 判斷區塊
        if "資產合計" in item_name or "美金匯率" in item_name:
            section = "switch_to_liability_soon"
            continue
        if section == "switch_to_liability_soon" and ("房貸" in item_name or "信貸" in item_name or "借款" in item_name):
            section = "liability"
        if not item_name or item_name in ["項目", ""]: continue
        if "合計" in item_name or "淨值" in item_name: continue

        # 數值清理
        def clean_num(x):
            if isinstance(x, (int, float)): return x
            x_str = str(x).replace(',', '').replace('NT$', '').replace('%', '').strip()
            return float(x_str) if x_str else 0

        try:
            if section == "asset":
                amount = clean_num(row[3]) # 金額在第4欄
                shares = clean_num(row[1]) if row[1] else 0 # 股數在第2欄
                
                # 修正：若金額為0但有股數/金額填在第2欄的現金
                if amount == 0 and shares > 10000 and "現金" in item_name: 
                    amount = shares
                    shares = 0
                
                category = "其他"
                if "現金" in item_name or "口袋" in item_name or "活存" in item_name: category = "現金"
                elif "美股" in item_name or "VT" in item_name or "VOO" in item_name or "TSLA" in item_name: category = "美股"
                elif "鴻海" in item_name or "0050" in item_name or "台股" in item_name: category = "台股"
                
                # 標記：是否為抵利型備援現金
                is_buffer = "抵利型" in item_name

                assets.append({"類別": category, "項目": item_name, "金額": amount, "股數": shares, "備援": is_buffer})

            elif section == "liability":
                amount = clean_num(row[1])
                if amount > 0:
                    liabilities.append({"類別": "負債", "項目": item_name, "金額": -amount, "股數": 0, "備援": False})
        except ValueError:
            continue
    return pd.DataFrame(assets + liabilities)

# ==========================================
# 2. 資料來源設定
# ==========================================

# --- 模式 A: 測試數據 (包含您的 652萬 備援現金) ---
# ⚠️ 正式連線時，請註解掉這一段
raw_data_paste = [
    ["鴻海股票（質押中）", "142000", "229.5", "32,589,000"],
    ["鴻海股票（可動用）", "80000", "229.5", "18,360,000"],
    ["0050 ETF單筆投資", "20,000", "61.95", "1,239,000"],
    ["美股_VT", "70", "140.22", "307,232"],
    ["現金_一般活存", "", "", "3,000,000"],
    ["現金_富邦_抵利型房貸專戶", "", "", "6,520,000"], # 您的關鍵備援 652萬
    ["✅ 資產合計", "", "", "62,015,232"],
    ["美金匯率", "1", "31.3", ""],
    ["富邦理財型房貸(抵利型)", "6,520,000", "2.60%", "14,500"], # 對應的負債
    ["股票質押借款", "16,020,000", "2.41%", "32,174"]
]

# --- 模式 B: 正式連線 Google Sheets ---
# ⚠️ 要啟用時，請把上面 raw_data_paste刪掉，並解開下面註解
# -------------------------------------------------------
# try:
#     scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
#     if "gcp_service_account" in st.secrets:
#         creds_dict = st.secrets["gcp_service_account"]
#         creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
#     else:
#         creds = ServiceAccountCredentials.from_json_keyfile_name('secrets.json', scope)
#     client = gspread.authorize(creds)
#     
#     # *** 請確認這裡是您的試算表名稱 ***
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
    
    total_assets = assets_df['金額'].sum()
    total_liabilities = liabilities_df['金額'].sum()
    net_worth = total_assets + total_liabilities
    
    # 提取「備援現金」(抵利型)
    buffer_cash_df = assets_df[assets_df['備援'] == True]
    buffer_cash = buffer_cash_df['金額'].sum()
    
    # 計算鴻海總股數
    honhai_df = assets_df[assets_df['項目'].str.contains("鴻海")]
    total_honhai_shares = honhai_df['股數'].sum()

    # --- 1. 關鍵指標 ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("淨資產", f"${net_worth/10000:,.0f} 萬")
    col2.metric("總負債", f"${total_liabilities/10000:,.0f} 萬", delta_color="inverse")
    
    # 備援現金展示
    col3.metric("🛡️ 抵利型備援池", f"${buffer_cash/10000:,.0f} 萬", 
                help="此現金目前抵銷了同額房貸利息。若動用，房貸利息將會增加。")
    
    lv_ratio = abs(total_liabilities) / total_assets if total_assets > 0 else 0
    col4.metric("總槓桿比率", f"{lv_ratio:.1%}", delta_color="inverse")

    st.markdown("---")

    # --- 2. 核心分析區：現金流 + GK + 備援 ---
    st.header("🌊 年度現金流與提領策略")

    # 參數設定
    st.sidebar.header("參數設定")
    honhai_eps = st.sidebar.number_input("鴻海預估配息 (元)", value=7.0, step=0.5)
    iwr = st.sidebar.number_input("GK 初始提領率 (%)", value=4.0, step=0.1) / 100
    monthly_expense = st.sidebar.number_input("預估月生活費", value=100000, step=10000)
    
    # 計算邏輯
    annual_expense = monthly_expense * 12
    estimated_dividend = total_honhai_shares * honhai_eps
    
    # 淨投資本金 = 總資產 - 負債(槓桿) - 備援現金(保命錢)
    # 這裡的邏輯：GK提領率應該只針對「風險資產」計算，而不該包含「已經拿去抵房貸的現金」
    investment_debt = abs(total_liabilities) # 簡化計算，視所有負債為槓桿成本
    net_investable = total_assets - investment_debt 
    # 若 net_investable 低於 0 (負債比資產多)，則設為 0
    base_for_gk = max(0, net_investable)

    target_withdraw = base_for_gk * iwr
    gap = target_withdraw - estimated_dividend # 缺口 (需要賣股票的錢)

    # 版面配置
    c1, c2 = st.columns([1, 2])

    with c1:
        st.subheader("📊 收入來源預估")
        st.write(f"鴻海股數合計: **{total_honhai_shares:,.0f}** 股")
        st.metric("1. 預估股息收入", f"${estimated_dividend:,.0f}", delta=f"EPS: {honhai_eps}元")
        st.metric("2. GK 建議提領總額", f"${target_withdraw:,.0f}", help="基於淨投資部位 x 提領率")
        
        # 備援警語
        if buffer_cash > 0:
            st.info(f"""
            **🛡️ 備援機制分析**
            目前備援水位：**${buffer_cash/10000:,.0f} 萬**
            
            若完全不賣股、不領股息：
            可支撐生活 **{buffer_cash/monthly_expense:.1f} 個月**。
            
            ⚠️ **注意：** 動用備援金 = 變相增加房貸負債。
            """)

    with c2:
        st.subheader("🌊 資金瀑布圖 (Waterfall)")
        
        # 準備瀑布圖數據
        # 邏輯：股息 -> 賣股(Gap) -> 總現金 -> 扣除生活費 -> 餘額
        
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
            decreasing = {"marker":{"color":"#EF553B"}}, # 紅色 (支出)
            increasing = {"marker":{"color":"#00CC96"}}, # 綠色 (收入)
            totals = {"marker":{"color":"#1f77b4"}}      # 藍色 (總計)
        ))
        
        fig.update_layout(title="資金來源 vs 支出結構", height=400, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

        # 結論文字
        balance = target_withdraw - annual_expense
        if balance >= 0:
            st.success(f"🎉 **資金充裕**：股息加上 GK 提領規則，扣除生活費後仍有盈餘 **${balance:,.0f}**。")
        else:
            st.warning(f"⚠️ **資金缺口**：GK 規則上限不足以支付生活費，缺口 **${abs(balance):,.0f}**。\n\n建議：1. 降低支出 2. 動用部分備援金(需注意利息成本)。")

    st.markdown("---")
    
    # --- 3. 資產細節與分佈 ---
    col_chart1, col_chart2 = st.columns(2)
    with col_chart1:
        st.subheader("資產配置 (含備援)")
        fig_pie = px.pie(assets_df, values='金額', names='類別', hole=0.4)
        st.plotly_chart(fig_pie, use_container_width=True)
    with col_chart2:
        st.subheader("資產明細表")
        st.dataframe(df, height=300)

else:
    st.write("資料讀取中...")