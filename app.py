import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re

# --- 設定頁面 ---
st.set_page_config(page_title="資產負債與提領儀表板", layout="wide", page_icon="📈")

# ==========================================
# 1. 資料處理核心 (專門解析您的表格格式)
# ==========================================
def parse_my_data(raw_data):
    """
    將混合格式的清單轉換為乾淨的 DataFrame
    raw_data: list of lists (模擬 Google Sheets get_all_values 的輸出)
    """
    assets = []
    liabilities = []
    
    section = "asset" # 預設從資產開始讀
    
    for row in raw_data:
        # 防呆：確保 row 長度足夠，不足補空字串
        row = row + [''] * (4 - len(row))
        
        item_name = str(row[0]).strip()
        
        # --- 判斷區塊切換 ---
        if "負債" in item_name and "合計" not in item_name:
             # 遇到負債標題行 (不含合計行)，切換模式
             # 但您的資料是直接接著項目，所以我們用關鍵字判斷項目內容更準
             pass

        if "資產合計" in item_name or "美金匯率" in item_name:
            section = "switch_to_liability_soon"
            continue
        
        if section == "switch_to_liability_soon" and ("房貸" in item_name or "信貸" in item_name or "借款" in item_name):
            section = "liability"

        # --- 略過無效行 ---
        if not item_name or item_name in ["項目", ""]:
            continue
        if "合計" in item_name or "淨值" in item_name:
            continue

        # --- 資料清洗與分類 ---
        try:
            # 移除千分位逗號
            def clean_num(x):
                if isinstance(x, (int, float)): return x
                return float(str(x).replace(',', '').replace('NT$', '').replace('%', '').strip()) if x else 0

            # 邏輯 A: 資產區塊
            if section == "asset":
                # 資產金額通常在第 4 欄 (index 3)，但有些現金只有總額可能在其他位置
                # 您的資料：股票在 col 3 (總金額), 現金在 col 3
                amount = clean_num(row[3]) 
                
                # 若第4欄沒數字，嘗試找第2或3欄 (針對某些現金行)
                if amount == 0 and clean_num(row[1]) > 10000: amount = clean_num(row[1])
                
                # 自動分類
                category = "其他"
                if "現金" in item_name or "口袋" in item_name or "活存" in item_name: category = "現金"
                elif "美股" in item_name or "VT" in item_name or "VOO" in item_name or "TSLA" in item_name: category = "美股"
                elif "鴻海" in item_name or "0050" in item_name or "台股" in item_name: category = "台股"
                
                assets.append({"類別": category, "項目": item_name, "金額": amount, "性質": "資產"})

            # 邏輯 B: 負債區塊
            elif section == "liability":
                # 負債金額在第 2 欄 (index 1)
                amount = clean_num(row[1])
                if amount > 0: # 確保讀到數字
                    liabilities.append({"類別": "負債", "項目": item_name, "金額": -amount, "性質": "負債"})

        except ValueError:
            continue

    return pd.DataFrame(assets + liabilities)

# ==========================================
# 2. 模擬數據 (或切換為 Google Sheets)
# ==========================================
# 這裡我把您提供的資料直接寫成 List，方便直接展示
raw_data_paste = [
    ["鴻海股票（質押中）", "142000", "229.5", "32,589,000"],
    ["鴻海股票（可動用）", "80000", "229.5", "18,360,000"],
    ["0050 ETF單筆投資", "20,000", "61.95", "1,239,000"],
    ["0050 ETF定期定額", "907", "61.95", "56,189"],
    ["美股_VT", "70", "140.22", "307,232"],
    ["美股_TSLA", "17", "426.58", "226,990"],
    ["美股_VOO", "70", "624.95", "1,369,309"],
    ["美股_GOOGL", "2", "319.95", "20,030"],
    ["美股定期定額_SPY", "3.28", "679.68", "69,967"],
    ["現金_e財庫", "", "", "274,086"],
    ["現金_凱基銀行", "", "", "3,083,694"],
    ["現金_國泰", "", "", "217,433"],
    ["現金_LINK Bank口袋帳戶", "", "", "500,000"],
    ["現金_富邦_活期", "", "", "119,684"],
    ["希_美股_VT", "50", "140.22", "219,451"],
    ["✅ 資產合計", "", "", "59,678,424"], # 分隔線
    ["美金匯率", "1", "31.3", ""],
    ["富邦房貸（轉貸後）寬限期", "11,540,000", "2.60%", "25,003"],
    ["富邦分期房貸", "1,960,000", "2.67%", "4,500"],
    ["富邦信貸整合", "5,000,000", "2.38%", "64,000"],
    ["股票質押借款", "16,020,000", "2.41%", "32,174"]
]

# --- 這裡切換：如果要連 Google Sheets，請把下面註解打開 ---
# 請在 secrets.json 設定好後使用
# import gspread
# from oauth2client.service_account import ServiceAccountCredentials
# ... (連線代碼同前一次回答) ...
# sheet = client.open("您的表名").sheet1
# raw_data_paste = sheet.get_all_values() 

df = parse_my_data(raw_data_paste)

# ==========================================
# 3. 儀表板顯示邏輯
# ==========================================
st.title("💰 資產負債與提領策略 (槓桿管理版)")
st.markdown("---")

if not df.empty:
    # 數值計算
    assets_df = df[df['金額'] > 0]
    liabilities_df = df[df['金額'] < 0]
    
    total_assets = assets_df['金額'].sum()
    total_liabilities = liabilities_df['金額'].sum() # 負數
    net_worth = total_assets + total_liabilities
    
    # 槓桿率計算 (Debt Ratio)
    leverage_ratio = abs(total_liabilities) / total_assets if total_assets > 0 else 0

    # 1. 資產負債總覽
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("總資產", f"${total_assets/10000:,.0f} 萬", delta="Asset")
    col2.metric("總負債", f"${total_liabilities/10000:,.0f} 萬", delta_color="inverse", delta="Liability")
    col3.metric("淨資產", f"${net_worth/10000:,.0f} 萬")
    col4.metric("槓桿比率 (LTV)", f"{leverage_ratio:.1%}", 
                delta="注意風險" if leverage_ratio > 0.5 else "安全", delta_color="inverse")

    # 2. 圖表分析
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.subheader("資產配置 (類別)")
        fig_pie = px.pie(assets_df, values='金額', names='類別', hole=0.4, 
                         color_discrete_map={'台股':'#1f77b4', '美股':'#ff7f0e', '現金':'#2ca02c'})
        st.plotly_chart(fig_pie, use_container_width=True)
        
    with col_chart2:
        st.subheader("負債結構")
        # 將負債轉為正數顯示以便畫圖
        liabilities_df_plot = liabilities_df.copy()
        liabilities_df_plot['金額'] = liabilities_df_plot['金額'].abs()
        fig_bar = px.bar(liabilities_df_plot, x='金額', y='項目', orientation='h', text_auto='.2s', color_discrete_sequence=['#d62728'])
        st.plotly_chart(fig_bar, use_container_width=True)

    st.markdown("---")

    # 3. GK 提領與現金流試算
    st.header("🧮 提領策略 (考慮質押與槓桿)")
    
    # 計算「淨投資部位」 (Net Investable Assets)
    # 定義：退休提領的基礎應該是 (股票+現金) - (與投資相關的負債: 質押+信貸)
    # 房貸通常視為生活開銷的一環，不直接從投資本金扣除，而是算在支出面，但保守起見這裡提供兩種視角
    
    stock_pledge_loan = liabilities_df[liabilities_df['項目'].str.contains('質押')]['金額'].sum()
    credit_loan = liabilities_df[liabilities_df['項目'].str.contains('信貸')]['金額'].sum()
    investment_debt = abs(stock_pledge_loan + credit_loan)
    
    gross_investable = total_assets # 總資產 (含質押股票)
    net_investable = total_assets - investment_debt # 扣除質押與信貸後的淨值
    
    st.info(
        f"""
        **💡 提領基數分析：**
        *   **總資產 (含質押股)**: ${gross_investable:,.0f} (您目前的總市值)
        *   **投資型負債 (質押+信貸)**: ${investment_debt:,.0f} (需償還的槓桿成本)
        *   **👉 建議提領基數 (淨投資部位)**: **${net_investable:,.0f}** (扣除槓桿後的真實本金)
        """
    )
    
    # GK 參數
    st.sidebar.header("提領參數")
    calc_base = st.sidebar.radio("選擇提領計算基數", ["淨投資部位 (保守/推薦)", "總資產 (積極)"])
    base_amount = net_investable if "淨投資部位" in calc_base else gross_investable
    
    iwr = st.sidebar.number_input("初始提領率 (%)", 3.0, 8.0, 4.0, 0.1) / 100
    inflation = st.sidebar.number_input("通膨率 (%)", 0.0, 10.0, 2.0, 0.1) / 100
    last_withdraw = st.sidebar.number_input("去年提領金額 (第一年填0)", value=0)

    col_gk1, col_gk2 = st.columns(2)
    
    with col_gk1:
        st.subheader("固定比例提領")
        fixed_val = base_amount * iwr
        st.metric("本年度可提領", f"${fixed_val:,.0f}")
        st.caption(f"每月約: ${fixed_val/12:,.0f}")

    with col_gk2:
        st.subheader("GK 動態提領建議")
        
        if last_withdraw == 0:
            gk_val = base_amount * iwr
            st.success("🎉 第一年：依照初始比例提領")
        else:
            # GK 邏輯
            base_w_inflation = last_withdraw * (1 + inflation)
            current_wr = base_w_inflation / base_amount
            
            ceiling = iwr * 1.2
            floor = iwr * 0.8
            
            if current_wr > ceiling:
                gk_val = last_withdraw * 0.9
                st.error(f"⚠️ 觸發減支規則 (提領率 {current_wr:.1%} > {ceiling:.1%})\n\n建議金額減少 10%。")
            elif current_wr < floor:
                gk_val = last_withdraw * 1.1
                st.success(f"🚀 觸發加薪規則 (提領率 {current_wr:.1%} < {floor:.1%})\n\n建議金額增加 10%！")
            else:
                gk_val = base_w_inflation
                st.info(f"✅ 依照通膨調整\n\n提領金額增加 {inflation*100}%。")

        st.metric("GK 建議金額", f"${gk_val:,.0f}")
        st.caption(f"每月約: ${gk_val/12:,.0f}")

else:
    st.write("無法解析資料")
