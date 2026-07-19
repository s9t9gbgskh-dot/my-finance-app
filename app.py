import streamlit as st
import pandas as pd
import yfinance as yf
from supabase import create_client, Client
import re  # 確保 import re 在最前面或這裡

st.set_page_config(page_title="個人財務戰情室", layout="wide")

# === 🟢 初始化 Supabase 雲端連線 ===
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

supabase = init_supabase()

# ==================================================================
# 🌟 1. 密碼重置攔截器 (解決 UI/UX 跳轉與 Token 讀取問題)
# ==================================================================
# 攔截信件中帶有 ?token=xxx&type=recovery 的網址
if "token" in st.query_params and st.query_params.get("type") == "recovery":
    try:
        # 使用網址上的 token_hash 驗證身分並登入
        supabase.auth.verify_otp({
            "token_hash": st.query_params["token"],
            "type": "recovery"
        })
        st.query_params.clear()  # 清除網址參數避免重複觸發
        st.session_state.reset_password_mode = True  # 開啟「重設密碼」模式
    except Exception as e:
        st.error(f"⚠️ 連結已失效或發生錯誤：{e}")
        st.query_params.clear()

# 如果目前處於「重設密碼」模式，就只顯示這個專屬畫面
if st.session_state.get("reset_password_mode", False):
    st.title("🔐 設定新密碼")
    st.info("請為您的帳號設定新的密碼。")
    
    new_pwd = st.text_input("請輸入新密碼 (至少 6 碼)", type="password")
    if st.button("確認修改並登入"):
        if len(new_pwd) >= 6:
            try:
                # 呼叫 Supabase 更新使用者密碼
                supabase.auth.update_user({"password": new_pwd})
                st.success("✅ 密碼修改成功！系統即將為您重新載入...")
                st.session_state.reset_password_mode = False
                
                # 清除暫存讓使用者重新登入
                st.session_state.user = None 
                st.rerun()
            except Exception as e:
                st.error(f"修改失敗：{e}")
        else:
            st.warning("密碼長度必須大於 6 碼！")
            
    st.stop()  # 🌟 重要：擋住下方的程式碼，不要顯示一般的登入畫面或主系統


# === 🟢 建立 App 的登入記憶 ===
if "user" not in st.session_state:
    st.session_state.user = None

# === 🟢 登入與註冊介面 (守門員) ===
if st.session_state.user is None:
    st.title("🔐 歡迎來到專屬資產管理系統")
    st.write("請先登入或註冊帳號，系統將為您建立專屬且加密的資料庫。")

    tab_login, tab_signup = st.tabs(["登入", "註冊新帳號"])

    with tab_login:
        login_email = st.text_input("信箱 (Email)")
        login_password = st.text_input("密碼 (Password)", type="password")
        if st.button("登入"):
            try:
                response = supabase.auth.sign_in_with_password({"email": login_email, "password": login_password})
                st.session_state.user = response.user
                st.rerun()
            except Exception as e:
                st.error("登入失敗，請檢查帳號密碼。")

    with tab_signup:
        signup_email = st.text_input("註冊信箱 (Email)")
        signup_password = st.text_input("設定密碼（至少 6 碼）", type="password")
        
        if st.button("註冊帳號"):
            # 檢查信箱格式是否正確 (UI/UX 優化)
            email_pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
            if not re.match(email_pattern, signup_email):
                st.error("⚠️ 請輸入有效的 Email 格式！")
            elif len(signup_password) < 6:
                st.error("⚠️ 密碼長度必須至少 6 碼！")
            else:
                try:
                    response = supabase.auth.sign_up({"email": signup_email, "password": signup_password})
                    st.success("🎉 註冊成功！請至您的信箱點擊認證信件，完成後再切換到「登入」分頁進行登入。")
                except Exception as e:
                    st.error(f"註冊失敗：{e}")

    st.stop() 

# ==================================================================
# 👇 登入成功後：讀取雲端資料與初始化
# ==================================================================

# 🌟 2. 資料隔離 (Data Isolation)：確保只讀取當下登入使用者的資料
if "data_loaded" not in st.session_state:
    # 嚴格過濾 .eq("user_id", st.session_state.user.id)
    response = supabase.table("user_data").select("data").eq("user_id", st.session_state.user.id).execute()
    
    if response.data and response.data[0]["data"]:
        cloud_data = response.data[0]["data"]
        
        # 拆分變數：建立「基準線 (base)」防止畫面彈跳與 KeyError 空值崩潰
        dl = cloud_data.get("debt_list", [])
        st.session_state.base_debt_list = pd.DataFrame(dl) if dl else pd.DataFrame(columns=["已結清", "項目", "金額", "償還來源"])
        
        st.session_state.loan_data = cloud_data.get("loan_data", {"principal": 500000.0, "rate": 2.5, "periods": 60})
        
        cb = cloud_data.get("custom_banks_v3", [])
        st.session_state.base_custom_banks_v3 = pd.DataFrame(cb) if cb else pd.DataFrame(columns=["功能標籤", "銀行名稱", "帳戶總額"])
        
        pf = cloud_data.get("portfolio", [])
        st.session_state.base_portfolio = pd.DataFrame(pf) if pf else pd.DataFrame(columns=["市場", "股票代碼", "持有股數", "投入本金"])
        
        fe = cloud_data.get("future_events", [])
        st.session_state.base_future_events = pd.DataFrame(fe) if fe else pd.DataFrame(columns=["發生月份", "事件名稱", "金額"])
        
        manual_inputs = cloud_data.get("manual_inputs", {})
    else:
        # 預設資料 (新註冊的使用者會看到這個)
        st.session_state.base_debt_list = pd.DataFrame({"已結清": [False]*7, "項目": ["釜山行程超支", "Elantra 車輛花費", "露營裝備", "潛水裝備", "Garmin 手錶", "五月透支", "宮古島機酒"], "金額": [10661, 14955, 32339, 18570, 42780, 13000, 27460], "償還來源": ["七月分紅", "七月分紅", "七月分紅", "七月分紅", "七月分紅", "六月加班費", "八月分紅"]})
        st.session_state.loan_data = {"principal": 500000.0, "rate": 2.5, "periods": 60}
        st.session_state.base_custom_banks_v3 = pd.DataFrame({"功能標籤": ["一般活存"], "銀行名稱": ["渣打銀行"], "帳戶總額": [11111]})
        st.session_state.base_portfolio = pd.DataFrame({"市場": ["台股", "美股"], "股票代碼": ["2330.TW", "NVDA"], "持有股數": [321.0, 50.0], "投入本金": [445223.0, 5000.0]})   
        st.session_state.base_future_events = pd.DataFrame({"發生月份": ["第 1 個月", "第 1 個月", "第 2 個月", "第 10 個月"], "事件名稱": ["七月季分紅", "宮古島機酒扣款", "八月季分紅", "繳納牌照稅"], "金額": [140000, -27460, 140000, -7120]})
        manual_inputs = {}
    
    # 初始化所有手動輸入的獨立變數 (解決重整跑掉的問題)
    default_manual = {
        "ctbc_manual_cash": 250000,
        "union_total": 250000,
        "union_manual_reserve": 150000,
        "union_cc": 8000,
        "cathay_total": 180000,
        "cathay_manual_reserve": 50000,
        "cathay_cc": 25000
    }
    for k, v in default_manual.items():
        if k not in st.session_state:
            st.session_state[k] = manual_inputs.get(k, v)

    # 同步初始化 current 狀態
    st.session_state.current_debt_list = st.session_state.base_debt_list.copy()
    st.session_state.current_custom_banks_v3 = st.session_state.base_custom_banks_v3.copy()
    st.session_state.current_portfolio = st.session_state.base_portfolio.copy()
    st.session_state.current_future_events = st.session_state.base_future_events.copy()

    st.session_state.data_loaded = True

# 側邊欄控制與儲存機制
st.sidebar.success(f"👤 目前登入：\n{st.session_state.user.email}")
st.sidebar.markdown("---")

if st.sidebar.button("💾 儲存變更至雲端", type="primary"):
    with st.spinner("雲端同步中..."):
        manual_inputs_to_save = {
            "ctbc_manual_cash": st.session_state.get("ctbc_manual_cash", 250000),
            "union_total": st.session_state.get("union_total", 250000),
            "union_manual_reserve": st.session_state.get("union_manual_reserve", 150000),
            "union_cc": st.session_state.get("union_cc", 8000),
            "cathay_total": st.session_state.get("cathay_total", 180000),
            "cathay_manual_reserve": st.session_state.get("cathay_manual_reserve", 50000),
            "cathay_cc": st.session_state.get("cathay_cc", 25000)
        }
        
        current_data = {
            "debt_list": st.session_state.current_debt_list.to_dict('records'),
            "loan_data": st.session_state.loan_data,
            "custom_banks_v3": st.session_state.current_custom_banks_v3.to_dict('records'),
            "portfolio": st.session_state.current_portfolio.to_dict('records'),
            "future_events": st.session_state.current_future_events.to_dict('records'),
            "manual_inputs": manual_inputs_to_save
        }
        
        # 🌟 2. 資料隔離 (Data Isolation)：寫入時嚴格綁定該 user_id
        supabase.table("user_data").upsert({
            "user_id": st.session_state.user.id, 
            "data": current_data
        }).execute()
        
        st.session_state.base_debt_list = st.session_state.current_debt_list.copy()
        st.session_state.base_custom_banks_v3 = st.session_state.current_custom_banks_v3.copy()
        st.session_state.base_portfolio = st.session_state.current_portfolio.copy()
        st.session_state.base_future_events = st.session_state.current_future_events.copy()
        
    st.sidebar.success("✅ 已安全儲存！關閉網頁資料也不會遺失。")

st.sidebar.markdown("---")
if st.sidebar.button("登出"):
    supabase.auth.sign_out()
    st.session_state.user = None
    st.session_state.pop("data_loaded", None)
    st.rerun()

# ==================================================================
# 👇 系統核心介面
# ==================================================================
import datetime
st.title("💰 我的專屬資產管理系統")

tab1, tab2, tab3, tab4 = st.tabs(["📊 總覽儀表板", "🏦 12個月資金跑道", "📈 投資部位", "💳 帳戶與代墊"])

with tab2:
    st.subheader("🏦 12個月資金跑道 (動態預測)")
    st.markdown("### 🔮 模擬未來大筆收支 *(不包含每個月信用貸款)*")

    today = datetime.date.today()
    current_year = today.year
    current_month = today.month

    month_options = []
    for i in range(12):
        m = current_month + i
        y = current_year
        if m > 12:
            m -= 12
            y += 1
        month_options.append(f"{y}/{m:02d}")

    # 🌟 3. UI/UX 優化：強制鎖定欄位 column_order
    st.session_state.current_future_events = st.data_editor(
        st.session_state.base_future_events, num_rows="dynamic", use_container_width=True, hide_index=True,
        column_order=("發生月份", "事件名稱", "金額"), 
        column_config={
            "發生月份": st.column_config.SelectboxColumn("發生月份", options=month_options, required=True),
            "事件名稱": st.column_config.TextColumn("事件名稱", required=True),
            "金額": st.column_config.NumberColumn("金額 (收入正數，支出負數)", default=0, step=1, format="$ %d")
        }, key="future_events_editor"
    )

    st.markdown("---")
    st.markdown("### 📊 12個月滾動水位預測")
    
    current_cash = st.session_state.get("union_total", 250000)
    runway_data = []
    
    for month_label in month_options:
        month_events = st.session_state.current_future_events[st.session_state.current_future_events["發生月份"] == month_label]
        if not month_events.empty:
            event_names = " + ".join(month_events["事件名稱"].dropna().astype(str).tolist())
            event_total = month_events["金額"].sum()
        else:
            event_names = "-"
            event_total = 0
            
        end_of_month_cash = current_cash + event_total
        status = "✅ 通過" if end_of_month_cash >= 0 else "❌ 資金缺口"
        
        runway_data.append({
            "時間軸": month_label, 
            "🏦 聯邦現金流": current_cash, 
            "特殊事件": event_names, 
            "特殊金額": event_total, 
            "🏁 月底安全水位": status
        })
        
        current_cash = end_of_month_cash

    df_runway = pd.DataFrame(runway_data)
    st.dataframe(df_runway, column_config={
        "🏦 聯邦現金流": st.column_config.NumberColumn(format="$ %d"), 
        "特殊金額": st.column_config.NumberColumn(format="$ %d")
    }, hide_index=True, use_container_width=True)


with tab3:
    st.subheader("📈 投資部位與即時連線 ROI")
    st.info("💡 **輸入指南**：美股直接輸入代碼（例 `NVDA`）、台股加 `.TW`（例 `2330.TW`）、加密貨幣輸入國際代碼（例 `BTC-USD`）\n\n"
            "💵 **幣別指南**：台股請輸入「台幣」本金，美股與加密貨幣請填寫「美金」本金。系統將自動抓取即時匯率計算總資產。")
    
    # 🌟 3. UI/UX 優化：強制鎖定欄位 column_order
    st.session_state.current_portfolio = st.data_editor(
        st.session_state.base_portfolio, num_rows="dynamic", use_container_width=True, hide_index=True,
        column_order=("市場", "股票代碼", "持有股數", "投入本金"), 
        column_config={
            "市場": st.column_config.SelectboxColumn("市場", options=["台股", "美股", "加密貨幣"], required=True),
            "股票代碼": st.column_config.TextColumn("股票代碼 (Ticker)", required=True),
            "持有股數": st.column_config.NumberColumn("持有股數", step=1.0),
            "投入本金": st.column_config.NumberColumn("投入本金 (台股:TWD / 海外:USD)", step=100.0)
        }, key="portfolio_editor"
    )

    if st.button("🔄 更新最新即時報價與績效"):
        valid_stocks = st.session_state.current_portfolio.dropna(subset=["股票代碼"])
        valid_stocks = valid_stocks[valid_stocks["股票代碼"].str.strip() != ""]
        if valid_stocks.empty: 
            st.warning("請先輸入股票代碼！")
        else:
            with st.spinner('🌐 連線全球交易所與抓取即時匯率中...'):
                try:
                    usd_to_twd = yf.Ticker("TWD=X").history(period="1d")['Close'].iloc[-1]
                except Exception:
                    usd_to_twd = 32.5 
                    st.warning("⚠️ 匯率抓取失敗，暫時使用預設匯率 32.5")

                cols = st.columns(3)
                total_invest_twd = 0
                total_val_twd = 0

                for i, (index, row) in enumerate(valid_stocks.iterrows()):
                    market = str(row.get("市場", "台股"))
                    ticker_symbol = str(row["股票代碼"]).strip()
                    shares = float(row.get("持有股數", 0))
                    principal = float(row.get("投入本金", 0))

                    try:
                        ticker = yf.Ticker(ticker_symbol)
                        current_price = ticker.history(period="1d")['Close'].iloc[-1]
                        current_value = current_price * shares
                        
                        roi = ((current_value - principal) / principal) * 100 if principal > 0 else 0

                        if market == "台股":
                            currency_sym = "NT$"
                            principal_twd = principal
                            value_twd = current_value
                        else:
                            currency_sym = "US$"
                            principal_twd = principal * usd_to_twd
                            value_twd = current_value * usd_to_twd

                        total_invest_twd += principal_twd
                        total_val_twd += value_twd

                        with cols[i % 3]:
                            st.markdown(f"#### 🏷️ {ticker_symbol}")
                            st.metric(
                                label=f"現價: {currency_sym}{current_price:.2f} | 股數: {shares}", 
                                value=f"{currency_sym}{current_value:,.2f}", 
                                delta=f"{roi:.2f}%"
                            )
                    except Exception:
                        with cols[i % 3]: st.error(f"無法抓取 {ticker_symbol}")
                
                st.session_state.total_val_twd = total_val_twd
                
                st.markdown("---")
                st.subheader("📊 總體投資績效 (全數換算台幣)")
                overall_roi = ((total_val_twd - total_invest_twd) / total_invest_twd) * 100 if total_invest_twd > 0 else 0
                st.metric(f"總資產現值 (TWD) ｜ 💱 匯率: 1 USD = {usd_to_twd:.2f} TWD", f"NT$ {total_val_twd:,.0f}", f"整體報酬率: {overall_roi:.2f}%")

with tab4:
    st.subheader("💳 多帳戶資金樞紐與代墊管理")
    with st.expander("⚙️ 銀行名稱與新增帳戶設定", expanded=True):
        col_name1, col_name2, col_name3 = st.columns(3)
        with col_name1: 
            hub1_label = st.text_input("自訂功能標籤 (1)", value="貸款與允用樞紐")
            bank_1_name = st.text_input(f"設定核心銀行 (1)", value="中信銀行")
        with col_name2: 
            hub2_label = st.text_input("自訂功能標籤 (2)", value="代墊與活存樞紐")
            bank_2_name = st.text_input(f"設定核心銀行 (2)", value="聯邦銀行")
        with col_name3: 
            hub3_label = st.text_input("自訂功能標籤 (3)", value="投資與交割樞紐")
            bank_3_name = st.text_input(f"設定核心銀行 (3)", value="國泰銀行")
        
        st.write("新增其他一般活存帳戶：")
        st.session_state.current_custom_banks_v3 = st.data_editor(
            st.session_state.base_custom_banks_v3, num_rows="dynamic", use_container_width=True, hide_index=True, 
            column_order=("功能標籤", "銀行名稱", "帳戶總額"), 
            column_config={"帳戶總額": st.column_config.NumberColumn("帳戶總額", default=0, step=1, format="$ %d")}, key="custom_banks_editor_v3"
        )

    st.markdown("---")
    col_ctbc, col_union, col_cathay = st.columns(3)
    
    with col_ctbc:
        st.markdown(f"### 🏦 {bank_1_name}\n**{hub1_label}**") 
        st.markdown("**📝 本息攤還計算機**")
        p = st.number_input("總借貸金額", value=st.session_state.loan_data["principal"], step=10000.0)
        r = st.number_input("年利率 (%)", value=st.session_state.loan_data["rate"], step=0.1)
        n = st.number_input("剩餘期數 (月)", value=st.session_state.loan_data["periods"], step=1)
        st.session_state.loan_data.update({"principal": p, "rate": r, "periods": n})
        
        monthly_rate = (r / 100) / 12
        monthly_pmt = p * (monthly_rate * (1 + monthly_rate)**n) / ((1 + monthly_rate)**n - 1) if (monthly_rate > 0 and n > 0) else (p / n if n > 0 else 0)
        st.info(f"👉 每月應繳款: **${monthly_pmt:,.0f}**")
        
        if st.button("✅ 本期已還款 (自動扣除本金)") and n > 0:
            st.session_state.loan_data["principal"] -= (monthly_pmt - (p * monthly_rate))
            st.session_state.loan_data["periods"] -= 1
            st.rerun()

    with col_union:
        st.markdown(f"### 💳 {bank_2_name}\n**{hub2_label}**")
        union_cc = st.number_input("本期信用卡繳款", step=1, key="union_cc")
        st.markdown("**📋 動態待沖銷清單**")
        st.session_state.current_debt_list = st.data_editor(
            st.session_state.base_debt_list, num_rows="dynamic", use_container_width=True, 
            column_order=("已結清", "項目", "金額", "償還來源"), 
            column_config={"金額": st.column_config.NumberColumn("金額", format="$%d")}, key="debt_editor"
        )
        total_debt = st.session_state.current_debt_list[st.session_state.current_debt_list["已結清"] == False]["金額"].sum()
        st.error(f"🚨 待沖銷總計: ${total_debt:,.0f}")

    with col_cathay:
        st.markdown(f"### 🌳 {bank_3_name}\n**{hub3_label}**")
        cathay_cc = st.number_input("本期信用卡繳款", step=1, key="cathay_cc")

    valid_extra_banks = st.session_state.current_custom_banks_v3.dropna(subset=["銀行名稱"])
    valid_extra_banks = valid_extra_banks[valid_extra_banks["銀行名稱"].str.strip() != ""]
    if not valid_extra_banks.empty:
        st.markdown("---")
        st.markdown("### 🏦 其他自訂帳戶總覽")
        extra_cols = st.columns(3)
        for i, (index, row) in enumerate(valid_extra_banks.iterrows()):
            with extra_cols[i % 3]:
                st.markdown(f"#### 💰 {row['銀行名稱']}\n**{row['功能標籤'] if pd.notna(row['功能標籤']) else '一般活存'}**") 
                st.metric("目前總額", f"${row['帳戶總額'] if pd.notna(row['帳戶總額']) else 0:,.0f}")

# ==================================================================
# 🌟 4. UI/UX 優化：將 Tab 1 移到檔案最後面執行，實現「更新報價後完美瞬間連動」！
# ==================================================================
with tab1:
    st.subheader("🎯 財務快照與跨帳戶連動")
    
    total_val_twd = st.session_state.get("total_val_twd", 0) 
    
    # 計算目前總資產 (抓取 session_state 內的儲備金)
    total_assets = total_val_twd + st.session_state.get("cathay_manual_reserve", 50000) + st.session_state.get("union_manual_reserve", 150000)
    st.metric("💰 目前總資產", f"NT$ {total_assets:,.0f}", help="公式: 國泰總投資現值 + 國泰投資儲備金 + 聯邦現金流儲備")
    st.markdown("---")

    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("### 🏦 中信")
        ctbc_cash = st.number_input("(a) 可花費金額", step=1000, key="ctbc_manual_cash")
        st.metric("(b) 本月應繳貸款", f"${monthly_pmt:,.0f}", help="連動：帳戶與代墊 (中信)")
        st.caption("*(每月賣alpha股來還)*")
        
    with col2:
        st.markdown("### 💳 聯邦")
        union_total = st.number_input("(a) 帳戶總金額", step=1000, key="union_total")
        union_reserve = st.number_input("(b) 本月應有現金流儲備", step=1000, key="union_manual_reserve")
        st.metric("(c) 本月應繳卡費", f"${st.session_state.get('union_cc', 8000):,.0f}", help="連動：帳戶與代墊 (聯邦)")
        st.metric("(d) 代墊總計", f"${total_debt:,.0f}", help="連動：帳戶與代墊 (待沖銷清單)")
        
        union_shortfall = union_reserve - union_total + st.session_state.get('union_cc', 8000) - total_debt
        st.metric("(e) 聯邦缺損金額", f"${union_shortfall:,.0f}", help="公式：(b) - (a) + (c) - (d)")

    with col3:
        st.markdown("### 🌳 國泰")
        cathay_total = st.number_input("(a) 帳戶總金額", step=1000, key="cathay_total")
        cathay_reserve = st.number_input("(b) 本月應有投資儲備金", step=1000, key="cathay_manual_reserve")
        st.metric("(c) 本月應繳卡費", f"${st.session_state.get('cathay_cc', 25000):,.0f}", help="連動：帳戶與代墊 (國泰)")
        
        cathay_shortfall = cathay_reserve - cathay_total + st.session_state.get('cathay_cc', 25000)
        st.metric("(d) 國泰缺損金額", f"${cathay_shortfall:,.0f}", help="公式：(b) - (a) + (c)")
        st.metric("(e) 總投資現值", f"${total_val_twd:,.0f}", help="連動：投資部位 (即時匯率換算後)")