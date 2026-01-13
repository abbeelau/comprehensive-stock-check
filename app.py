import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import os
import requests

# ==================== VERSION INFO ====================
APP_VERSION = "v4.0"
VERSION_DATE = "2025-01-13"
CHANGELOG = """
**v4.0** (2025-01-13) - Comprehensive Stock Check Edition
- ✅ Technical Indicators: Added ATR Percentile, A/D, Insider indicators
- ✅ Fundamental Scoring Changes:
  - Sales Growth: 0.5 for acceleration + 0.5 for >15% YoY (or 1.0 for >30%)
  - Gross Margin: Changed from Operating Margin to Gross Margin with >40% threshold
  - Earnings Growth: 0.5 for acceleration + 0.5 for >20% YoY
  - ROE: Threshold changed from 17% to 15%
- ✅ Max Technical Score: 6 points (was 3)
- ✅ Max Total Score: 13 points (was 10)
"""

# Set page configuration
st.set_page_config(page_title=f"Comprehensive Stock Check {APP_VERSION}", layout="wide")

# Custom CSS for better UI
st.markdown("""
<style>
    .stMetric label { font-size: 0.9rem !important; }
    .stMetric .metric-value { font-size: 1.3rem !important; }
    h1 { font-size: 1.8rem !important; margin-bottom: 1rem !important; }
    h2 { font-size: 1.3rem !important; margin-top: 0.5rem !important; }
    h3 { font-size: 1.1rem !important; }
    .element-container { margin-bottom: 0.3rem !important; }
</style>
""", unsafe_allow_html=True)

# ==================== PERSISTENT STORAGE ====================
USER_INPUTS_FILE = "user_inputs.json"

def load_user_inputs():
    """Load previously saved user inputs from JSON file"""
    if os.path.exists(USER_INPUTS_FILE):
        try:
            with open(USER_INPUTS_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_user_inputs(inputs):
    """Save user inputs to JSON file"""
    try:
        with open(USER_INPUTS_FILE, 'w') as f:
            json.dump(inputs, f, indent=2)
    except:
        pass

# Initialize session state
saved_inputs = load_user_inputs()

if 'market_pulse' not in st.session_state:
    st.session_state.market_pulse = saved_inputs.get('market_pulse', 'Green - Acceleration')
if 'alpha_vantage_key' not in st.session_state:
    st.session_state.alpha_vantage_key = saved_inputs.get('alpha_vantage_key', '')
if 'av_calls_today' not in st.session_state:
    st.session_state.av_calls_today = 0
if 'top_rated_group' not in st.session_state:
    st.session_state.top_rated_group = saved_inputs.get('top_rated_group', False)
if 'new_development' not in st.session_state:
    st.session_state.new_development = saved_inputs.get('new_development', False)
if 'atr_percentile' not in st.session_state:
    st.session_state.atr_percentile = saved_inputs.get('atr_percentile', 50)
if 'accumulation_distribution' not in st.session_state:
    st.session_state.accumulation_distribution = saved_inputs.get('accumulation_distribution', 0)
if 'insider_activity' not in st.session_state:
    st.session_state.insider_activity = saved_inputs.get('insider_activity', 0)

# ==================== ALPHA VANTAGE API FUNCTIONS ====================

def fetch_alpha_vantage_data(ticker, api_key):
    """Fetch fundamental data from Alpha Vantage API"""
    if not api_key or api_key.strip() == '':
        return None, "Please provide a valid Alpha Vantage API key"
    
    try:
        base_url = "https://www.alphavantage.co/query"
        
        income_params = {
            "function": "INCOME_STATEMENT",
            "symbol": ticker,
            "apikey": api_key
        }
        
        income_response = requests.get(base_url, params=income_params, timeout=15)
        
        if income_response.status_code != 200:
            return None, f"Alpha Vantage API error: {income_response.status_code}"
        
        income_json = income_response.json()
        
        if "Error Message" in income_json:
            return None, f"Alpha Vantage error: {income_json['Error Message']}"
        elif "Note" in income_json:
            return None, f"Alpha Vantage rate limit: {income_json['Note']}"
        elif "Information" in income_json:
            return None, f"Alpha Vantage info: {income_json['Information']}"
        elif "quarterlyReports" not in income_json:
            error_msg = f"No quarterly data. API returned: {list(income_json.keys())[:5]}"
            return None, error_msg
        
        income_data = income_json["quarterlyReports"]
        
        return income_data, None
        
    except Exception as e:
        return None, f"Error fetching Alpha Vantage data: {str(e)}"


def calculate_alpha_vantage_fundamentals(income_data, ticker):
    """Calculate fundamental indicators from Alpha Vantage data"""
    scores = {
        'sales_growth': 0,
        'gross_margin': 0,
        'earnings': 0,
        'rule_of_40': 0,
        'roe': 0
    }
    
    details = {}
    
    if not income_data or len(income_data) < 4:
        return scores, details
    
    # Get quarter dates
    quarter_dates = []
    for q in income_data[:8]:
        date_str = q.get('fiscalDateEnding', '')
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            quarter_dates.append(date_obj.strftime('%b-%Y'))
        except:
            quarter_dates.append(date_str)
    
    details['quarter_dates'] = quarter_dates
    details['revenue_quarters_available'] = len(income_data)
    details['earnings_quarters_available'] = len(income_data)
    details['sales_source'] = 'Alpha Vantage'
    details['earnings_source'] = 'Alpha Vantage'
    details['margin_source'] = 'Alpha Vantage'
    
    # Extract basic data
    revenues = []
    net_incomes = []
    gross_profits = []
    
    for q in income_data[:8]:
        rev = q.get('totalRevenue')
        revenues.append(int(rev) if rev and rev != 'None' else 0)
        
        ni = q.get('netIncome')
        net_incomes.append(int(ni) if ni and ni != 'None' else 0)
        
        gp = q.get('grossProfit')
        gross_profits.append(int(gp) if gp and gp != 'None' else 0)
    
    details['sales'] = revenues
    details['earnings'] = net_incomes
    details['gross_profit'] = gross_profits
    
    # 1. Sales Growth Acceleration (YoY)
    if len(income_data) >= 12:
        sales_growth = []
        for i in range(8):
            current_rev = revenues[i] if i < len(revenues) else 0
            year_ago_rev_data = income_data[i + 4].get('totalRevenue')
            year_ago_rev = int(year_ago_rev_data) if year_ago_rev_data and year_ago_rev_data != 'None' else 0
            
            if year_ago_rev != 0 and current_rev != 0:
                yoy = ((current_rev - year_ago_rev) / abs(year_ago_rev)) * 100
                sales_growth.append(yoy)
            else:
                sales_growth.append(None)
        
        details['sales_growth'] = sales_growth
        
        latest_yoy = sales_growth[0]
        prev_yoy = sales_growth[1]
        
        if latest_yoy is not None:
            if latest_yoy > 30:
                scores['sales_growth'] = 1.0
            else:
                if prev_yoy is not None and latest_yoy > prev_yoy:
                    scores['sales_growth'] += 0.5
                if latest_yoy > 15:
                    scores['sales_growth'] += 0.5
                    
    elif len(income_data) >= 8:
        sales_growth = []
        for i in range(4):
            current_rev = revenues[i]
            year_ago_rev_data = income_data[i + 4].get('totalRevenue')
            year_ago_rev = int(year_ago_rev_data) if year_ago_rev_data and year_ago_rev_data != 'None' else 0
            
            if year_ago_rev != 0 and current_rev != 0:
                yoy = ((current_rev - year_ago_rev) / abs(year_ago_rev)) * 100
                sales_growth.append(yoy)
            else:
                sales_growth.append(None)
        
        details['sales_growth'] = sales_growth
        
        latest_yoy = sales_growth[0]
        prev_yoy = sales_growth[1]
        
        if latest_yoy is not None:
            if latest_yoy > 30:
                scores['sales_growth'] = 1.0
            else:
                if prev_yoy is not None and latest_yoy > prev_yoy:
                    scores['sales_growth'] += 0.5
                if latest_yoy > 15:
                    scores['sales_growth'] += 0.5
    else:
        details['sales_growth'] = [None, None, None, None]
    
    # 2. GROSS Profit Margin Acceleration
    gross_margin_values = []
    for i in range(min(8, len(gross_profits))):
        if i < len(revenues) and revenues[i] != 0 and gross_profits[i] != 0:
            margin = (gross_profits[i] / revenues[i]) * 100
            gross_margin_values.append(margin)
        else:
            gross_margin_values.append(None)
    
    details['gross_margin'] = gross_margin_values
    
    if len(gross_margin_values) >= 2:
        latest_margin = gross_margin_values[0]
        prev_margin = gross_margin_values[1]
        
        if latest_margin is not None:
            if prev_margin is not None and latest_margin > prev_margin:
                scores['gross_margin'] += 0.5
            if latest_margin > 40:
                scores['gross_margin'] += 0.5
    
    # 3. Earnings Growth Acceleration (YoY)
    if len(income_data) >= 12:
        earnings_growth = []
        for i in range(8):
            current_ni = net_incomes[i] if i < len(net_incomes) else 0
            year_ago_ni_data = income_data[i + 4].get('netIncome')
            year_ago_ni = int(year_ago_ni_data) if year_ago_ni_data and year_ago_ni_data != 'None' else 0
            
            if year_ago_ni != 0 and current_ni != 0:
                yoy = ((current_ni - year_ago_ni) / abs(year_ago_ni)) * 100
                earnings_growth.append(yoy)
            else:
                earnings_growth.append(None)
        
        details['earnings_growth'] = earnings_growth
        
        latest_yoy = earnings_growth[0]
        prev_yoy = earnings_growth[1]
        
        if latest_yoy is not None:
            if prev_yoy is not None and latest_yoy > prev_yoy:
                scores['earnings'] += 0.5
            if latest_yoy > 20:
                scores['earnings'] += 0.5
                
    elif len(income_data) >= 8:
        earnings_growth = []
        for i in range(4):
            current_ni = net_incomes[i]
            year_ago_ni_data = income_data[i + 4].get('netIncome')
            year_ago_ni = int(year_ago_ni_data) if year_ago_ni_data and year_ago_ni_data != 'None' else 0
            
            if year_ago_ni != 0 and current_ni != 0:
                yoy = ((current_ni - year_ago_ni) / abs(year_ago_ni)) * 100
                earnings_growth.append(yoy)
            else:
                earnings_growth.append(None)
        
        details['earnings_growth'] = earnings_growth
        
        latest_yoy = earnings_growth[0]
        prev_yoy = earnings_growth[1]
        
        if latest_yoy is not None:
            if prev_yoy is not None and latest_yoy > prev_yoy:
                scores['earnings'] += 0.5
            if latest_yoy > 20:
                scores['earnings'] += 0.5
    else:
        details['earnings_growth'] = [None, None, None, None]
    
    # 4. Rule of 40
    if len(income_data) >= 5:
        latest_rev = revenues[0]
        year_ago_rev_data = income_data[4].get('totalRevenue')
        year_ago_rev = int(year_ago_rev_data) if year_ago_rev_data and year_ago_rev_data != 'None' else 0
        
        if year_ago_rev != 0:
            revenue_growth = ((latest_rev - year_ago_rev) / abs(year_ago_rev)) * 100
            details['latest_revenue_growth'] = revenue_growth
            
            if revenues[0] != 0 and gross_profits[0] != 0:
                profit_margin = (gross_profits[0] / revenues[0]) * 100
                details['latest_profit_margin'] = profit_margin
                
                rule_of_40 = revenue_growth + profit_margin
                details['rule_of_40'] = rule_of_40
                
                if rule_of_40 >= 40:
                    scores['rule_of_40'] = 1
    
    # 5. ROE - Get from Yahoo Finance
    details['roe_source'] = 'Yahoo Finance (calculated separately)'
    details['roe_quarters'] = [None, None, None, None]
    
    return scores, details

# ==================== HELPER FUNCTIONS ====================

def calc_ma(data, period):
    """Calculate moving average"""
    if len(data) < period:
        return None
    return data.tail(period).mean()

def calculate_stage(price, ma50, ma150, ma200):
    """Calculate market stage based on moving averages"""
    try:
        current_price = float(price)
        ma_50 = float(ma50)
        ma_150 = float(ma150)
        ma_200 = float(ma200)
        
        if current_price > ma_50 and ma_50 > ma_150 and ma_150 > ma_200:
            return "S2", 1.0
        elif current_price > ma_50 and ma_50 > ma_150 and ma_150 < ma_200:
            return "S1", 0.5
        elif current_price > ma_50 and ma_50 < ma_150 and ma_150 > ma_200:
            return "S3 Strong", 0.5
        else:
            return "Other", 0.0
    except:
        return "Error", 0.0

def detect_key_bars(df):
    """Detect Key Bars in the stock data"""
    if df is None or len(df) < 30:
        return None, None
    
    df = df.copy()
    
    df['Volume_SMA30'] = df['Volume'].rolling(window=30).mean()
    df['Open_Close_Change_Pct'] = ((df['Close'] - df['Open']) / df['Open']) * 100
    df['High_5D_Previous'] = df['High'].shift(1).rolling(window=5).max()
    
    df['Is_Key_Bar'] = (
        (df['Volume'] > df['Volume_SMA30']) &
        (abs(df['Open_Close_Change_Pct']) > 1.5) &
        (df['High'] > df['High_5D_Previous'])
    )
    
    recent_data = df.tail(10)
    recent_key_bars = recent_data[recent_data['Is_Key_Bar']]
    
    if len(recent_key_bars) > 0:
        most_recent_kb = recent_key_bars.iloc[-1]
        return df, most_recent_kb
    
    return df, None

def calculate_key_bar_score(df, recent_key_bar):
    """Calculate Key Bar score"""
    if df is None or recent_key_bar is None:
        return 0.0, "No recent key bar"
    
    score = 0.5
    current_price = df['Close'].iloc[-1]
    kb_close = recent_key_bar['Close']
    
    details = f"Recent Key Bar found (Score: 0.5)"
    
    if current_price <= kb_close * 1.05:
        score += 0.5
        details += f"\nPrice near Key Bar (Score: +0.5)"
        details += f"\nCurrent: ${current_price:.2f} | Key Bar: ${kb_close:.2f}"
    else:
        details += f"\nPrice too far from Key Bar (Score: 0)"
        details += f"\nCurrent: ${current_price:.2f} | Key Bar: ${kb_close:.2f}"
    
    return score, details

@st.cache_data(ttl=3600)
def fetch_stock_data(ticker):
    """Fetch stock price and volume data"""
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)
        
        stock = yf.Ticker(ticker)
        df = stock.history(start=start_date, end=end_date)
        
        if df is None or len(df) == 0:
            return None, "No price data available"
        
        return df, None
    except Exception as e:
        return None, f"Error fetching data: {str(e)}"

@st.cache_data(ttl=3600)
def fetch_fundamental_data(ticker):
    """Fetch fundamental data from Yahoo Finance"""
    try:
        stock = yf.Ticker(ticker)
        
        quarterly_income = stock.quarterly_income_stmt
        quarterly_balance = stock.quarterly_balance_sheet
        
        info = stock.info
        
        return {
            'income': quarterly_income,
            'balance': quarterly_balance,
            'info': info
        }, None
    except Exception as e:
        return None, f"Error fetching fundamentals: {str(e)}"

def check_growth_acceleration(values):
    """Check if latest YoY growth rate > previous YoY growth rate"""
    if values is None or len(values) < 5:
        return False, []
    
    growth_rates = []
    
    if len(values) > 4 and values[4] != 0 and not pd.isna(values[0]) and not pd.isna(values[4]):
        yoy_growth = ((values[0] - values[4]) / abs(values[4])) * 100
        growth_rates.append(yoy_growth)
    else:
        growth_rates.append(None)
    
    if len(values) > 5 and values[5] != 0 and not pd.isna(values[1]) and not pd.isna(values[5]):
        yoy_growth = ((values[1] - values[5]) / abs(values[5])) * 100
        growth_rates.append(yoy_growth)
    else:
        growth_rates.append(None)
    
    if len(values) > 6 and values[6] != 0 and not pd.isna(values[2]) and not pd.isna(values[6]):
        yoy_growth = ((values[2] - values[6]) / abs(values[6])) * 100
        growth_rates.append(yoy_growth)
    else:
        growth_rates.append(None)
    
    if len(values) > 7 and values[7] != 0 and not pd.isna(values[3]) and not pd.isna(values[7]):
        yoy_growth = ((values[3] - values[7]) / abs(values[7])) * 100
        growth_rates.append(yoy_growth)
    else:
        growth_rates.append(None)
    
    if len(growth_rates) >= 2 and growth_rates[0] is not None and growth_rates[1] is not None:
        return growth_rates[0] > growth_rates[1], growth_rates
    
    return False, growth_rates

def calculate_fundamental_scores(fund_data):
    """Calculate all 5 fundamental indicator scores"""
    scores = {
        'sales_growth': 0,
        'gross_margin': 0,
        'earnings': 0,
        'rule_of_40': 0,
        'roe': 0
    }
    
    details = {}
    
    if fund_data is None:
        return scores, details
    
    income = fund_data['income']
    balance = fund_data['balance']
    info = fund_data['info']
    
    quarter_dates = []
    if hasattr(income, 'columns'):
        for col in income.columns[:4]:
            try:
                quarter_dates.append(col.strftime('%b-%Y'))
            except:
                quarter_dates.append(str(col))
    
    details['quarter_dates'] = quarter_dates
    
    # 1. Sales Growth Acceleration (YoY)
    try:
        if 'Total Revenue' in income.index:
            revenue = income.loc['Total Revenue'].values[:8]
            is_accelerating, growth_rates = check_growth_acceleration(revenue)
            
            details['revenue_quarters_available'] = len(revenue)
            
            latest_yoy = growth_rates[0] if growth_rates else None
            
            if latest_yoy is not None:
                if latest_yoy > 30:
                    scores['sales_growth'] = 1.0
                else:
                    if is_accelerating:
                        scores['sales_growth'] += 0.5
                    if latest_yoy > 15:
                        scores['sales_growth'] += 0.5
            
            details['sales'] = revenue[:4]
            details['sales_growth'] = growth_rates[:4] if growth_rates else []
    except Exception as e:
        details['sales_error'] = str(e)
        pass
    
    # 2. GROSS Profit Margin Acceleration
    try:
        gross_margin_values = []
        if 'Gross Profit' in income.index and 'Total Revenue' in income.index:
            gross_profit = income.loc['Gross Profit'].values[:4]
            revenue = income.loc['Total Revenue'].values[:4]
            if len(revenue) == len(gross_profit):
                gross_margin_values = [(gross_profit[i] / revenue[i] * 100) if revenue[i] != 0 else None for i in range(len(revenue))]
        
        if len(gross_margin_values) >= 2:
            latest_margin = gross_margin_values[0]
            prev_margin = gross_margin_values[1]
            
            if latest_margin is not None:
                if prev_margin is not None and latest_margin > prev_margin:
                    scores['gross_margin'] += 0.5
                if latest_margin > 40:
                    scores['gross_margin'] += 0.5
                    
            details['gross_margin'] = gross_margin_values
    except:
        pass
    
    # 3. Earnings Growth Acceleration (YoY)
    try:
        if 'Net Income' in income.index:
            earnings = income.loc['Net Income'].values[:8]
            is_accelerating, growth_rates = check_growth_acceleration(earnings)
            
            details['earnings_quarters_available'] = len(earnings)
            
            latest_yoy = growth_rates[0] if growth_rates else None
            
            if latest_yoy is not None:
                if is_accelerating:
                    scores['earnings'] += 0.5
                if latest_yoy > 20:
                    scores['earnings'] += 0.5
            
            details['earnings'] = earnings[:4]
            details['earnings_growth'] = growth_rates[:4] if growth_rates else []
    except Exception as e:
        details['earnings_error'] = str(e)
        pass
    
    # 4. Rule of 40
    try:
        revenue_growth = None
        profit_margin_pct = None
        
        if 'Total Revenue' in income.index:
            revenue = income.loc['Total Revenue'].values[:2]
            if len(revenue) >= 2 and revenue[1] != 0:
                revenue_growth = ((revenue[0] - revenue[1]) / abs(revenue[1])) * 100
                details['latest_revenue_growth'] = revenue_growth
        
        if 'Gross Profit' in income.index and 'Total Revenue' in income.index:
            gross_profit = income.loc['Gross Profit'].values[0]
            revenue = income.loc['Total Revenue'].values[0]
            if revenue != 0:
                profit_margin_pct = (gross_profit / revenue) * 100
                details['latest_profit_margin'] = profit_margin_pct
        elif 'EBITDA' in income.index and 'Total Revenue' in income.index:
            ebitda = income.loc['EBITDA'].values[0]
            revenue = income.loc['Total Revenue'].values[0]
            if revenue != 0:
                profit_margin_pct = (ebitda / revenue) * 100
                details['latest_profit_margin'] = profit_margin_pct
        
        if revenue_growth is not None and profit_margin_pct is not None:
            rule_of_40_value = revenue_growth + profit_margin_pct
            details['rule_of_40'] = rule_of_40_value
            if rule_of_40_value >= 40:
                scores['rule_of_40'] = 1
    except:
        pass
    
    # 5. ROE - Threshold changed to 15%
    try:
        roe = info.get('returnOnEquity', None)
        if roe is not None:
            roe_pct = roe * 100
            details['roe'] = roe_pct
            details['roe_quarters'] = [roe_pct]
            if roe_pct >= 15:
                scores['roe'] = 1
        else:
            if 'Net Income' in income.index and 'Stockholders Equity' in balance.index:
                net_income = income.loc['Net Income'].values[:4]
                equity = balance.loc['Stockholders Equity'].values[:4]
                
                roe_quarters = []
                for i in range(min(len(net_income), len(equity))):
                    if equity[i] != 0 and not pd.isna(net_income[i]) and not pd.isna(equity[i]):
                        quarterly_roe = (net_income[i] * 4 / equity[i]) * 100
                        roe_quarters.append(quarterly_roe)
                    else:
                        roe_quarters.append(None)
                
                if roe_quarters:
                    details['roe_quarters'] = roe_quarters
                    if roe_quarters[0] is not None and roe_quarters[0] >= 15:
                        scores['roe'] = 1
    except:
        pass
    
    return scores, details

# ==================== MAIN APP ====================

st.title(f"📊 Comprehensive Stock Check App {APP_VERSION}")
st.markdown("Enhanced technical and fundamental analysis with expanded scoring criteria")

# Version info in sidebar
with st.sidebar:
    st.markdown(f"### 🔖 Version {APP_VERSION}")
    st.caption(f"Released: {VERSION_DATE}")
    
    with st.expander("📝 Changelog"):
        st.markdown(CHANGELOG)
    
    st.markdown("---")
    
    st.markdown("### 🔑 Alpha Vantage API Key")
    st.caption("[Get free key](https://www.alphavantage.co/support/#api-key) (25 calls/day)")
    
    av_key = st.text_input(
        "Alpha Vantage API Key",
        value=st.session_state.alpha_vantage_key,
        type="password",
        help="Free tier: 25 calls/day"
    )
    
    if av_key != st.session_state.alpha_vantage_key:
        st.session_state.alpha_vantage_key = av_key
        saved_inputs = load_user_inputs()
        saved_inputs['alpha_vantage_key'] = av_key
        save_user_inputs(saved_inputs)
    
    if av_key and av_key.strip() != '':
        st.success("✅ Using Alpha Vantage API")
    else:
        st.warning("⚠️ Using Yahoo Finance (limited data)")

# Ticker input
col1, col2 = st.columns([3, 1])
with col1:
    ticker = st.text_input("Enter Stock Ticker (e.g., AAPL, TSLA, MSFT)", value="AAPL").upper()
with col2:
    analyze_button = st.button("🔍 Analyze", type="primary")

if analyze_button or ticker:
    
    with st.spinner(f"Fetching data for {ticker}..."):
        stock_df, error = fetch_stock_data(ticker)
        
        use_av = False
        if av_key and av_key.strip() != '':
            with st.spinner('📡 Fetching from Alpha Vantage API...'):
                av_income, av_error = fetch_alpha_vantage_data(ticker, av_key)
            
            if not av_error and av_income:
                use_av = True
                st.session_state.av_calls_today += 1
                st.success(f"✅ Alpha Vantage: {len(av_income)} quarters")
            else:
                st.warning(f"⚠️ Alpha Vantage failed: {av_error}. Using Yahoo Finance fallback...")
                use_av = False
        
        if not use_av:
            fund_data, fund_error = fetch_fundamental_data(ticker)
    
    if error:
        st.error(error)
        st.stop()
    
    # Display basic info
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Current Price", f"${stock_df['Close'].iloc[-1]:.2f}")
        with col2:
            change = stock_df['Close'].iloc[-1] - stock_df['Close'].iloc[-2]
            change_pct = (change / stock_df['Close'].iloc[-2]) * 100
            st.metric("Change", f"{change_pct:.2f}%", delta=f"${change:.2f}")
        with col3:
            st.metric("Volume", f"{stock_df['Volume'].iloc[-1]:,.0f}")
        with col4:
            st.metric("Company", info.get('shortName', ticker))
    except:
        pass
    
    st.markdown("---")
    total_score_placeholder = st.empty()
    st.markdown("---")
    
    tab1, tab2, tab3 = st.tabs(["🔧 Technical Analysis", "💼 Fundamental Analysis", "📝 Remarks"])
    
    # ==================== TECHNICAL TAB ====================
    with tab1:
        st.header("Technical Indicators (Max: 6 points)")
        
        tech_scores = {}
        
        # 1. Stage 2
        st.subheader("1️⃣ Stage 2")
        
        if len(stock_df) >= 200:
            current_price = float(stock_df['Close'].iloc[-1])
            ma_50 = calc_ma(stock_df['Close'], 50)
            ma_150 = calc_ma(stock_df['Close'], 150)
            ma_200 = calc_ma(stock_df['Close'], 200)
            
            if ma_50 and ma_150 and ma_200:
                stage, score = calculate_stage(current_price, ma_50, ma_150, ma_200)
                tech_scores['stage2'] = score
                
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.info(f"**Stage: {stage}**\n\nPrice: ${current_price:.2f} | 50MA: ${ma_50:.2f} | 150MA: ${ma_150:.2f} | 200MA: ${ma_200:.2f}")
                with col2:
                    emoji = "🟢" if score == 1.0 else ("🟡" if score == 0.5 else "🔴")
                    st.metric("Score", f"{score}/1.0", delta=emoji)
            else:
                tech_scores['stage2'] = 0
                st.warning("Unable to calculate moving averages")
        else:
            tech_scores['stage2'] = 0
            st.warning("Not enough data for Stage 2 calculation")
        
        st.markdown("---")
        
        # 2. Market Pulse
        st.subheader("2️⃣ Market Pulse")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            market_pulse = st.selectbox(
                "Overall Market Condition",
                ["Green - Acceleration", "Grey Strong - Accumulation", "Grey Weak - Distribution", "Red - Deceleration"],
                index=["Green - Acceleration", "Grey Strong - Accumulation", "Grey Weak - Distribution", "Red - Deceleration"].index(st.session_state.market_pulse)
            )
            
            if market_pulse != st.session_state.market_pulse:
                st.session_state.market_pulse = market_pulse
                saved_inputs = load_user_inputs()
                saved_inputs['market_pulse'] = market_pulse
                save_user_inputs(saved_inputs)
        
        with col2:
            if market_pulse == "Green - Acceleration":
                pulse_score = 1.0
                st.metric("Score", f"{pulse_score}/1.0", delta="🟢")
            elif market_pulse == "Grey Strong - Accumulation":
                pulse_score = 0.5
                st.metric("Score", f"{pulse_score}/1.0", delta="🟡")
            else:
                pulse_score = 0.0
                st.metric("Score", f"{pulse_score}/1.0", delta="🔴")
        
        tech_scores['market_pulse'] = pulse_score
        
        st.markdown("---")
        
        # 3. ATR Percentile
        st.subheader("3️⃣ ATR Percentile")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            atr_percentile = st.number_input(
                "ATR Percentile (%)",
                min_value=0,
                max_value=100,
                value=st.session_state.atr_percentile,
                step=1
            )
            
            if atr_percentile != st.session_state.atr_percentile:
                st.session_state.atr_percentile = atr_percentile
                saved_inputs = load_user_inputs()
                saved_inputs['atr_percentile'] = atr_percentile
                save_user_inputs(saved_inputs)
            
            if atr_percentile > 50:
                st.success(f"✅ ATR Percentile: {atr_percentile}% > 50%")
                atr_score = 1
            else:
                st.warning(f"❌ ATR Percentile: {atr_percentile}% ≤ 50%")
                atr_score = 0
        
        with col2:
            emoji = "🟢" if atr_score == 1 else "🔴"
            st.metric("Score", f"{atr_score}/1", delta=emoji)
        
        tech_scores['atr_percentile'] = atr_score
        
        st.markdown("---")
        
        # 4. Accumulation/Distribution
        st.subheader("4️⃣ Accumulation/Distribution")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            ad_score = st.radio(
                "Accumulation/Distribution Status",
                options=[0, 1],
                format_func=lambda x: "Distribution (0)" if x == 0 else "Accumulation (1)",
                index=st.session_state.accumulation_distribution,
                horizontal=True
            )
            
            if ad_score != st.session_state.accumulation_distribution:
                st.session_state.accumulation_distribution = ad_score
                saved_inputs = load_user_inputs()
                saved_inputs['accumulation_distribution'] = ad_score
                save_user_inputs(saved_inputs)
            
            if ad_score == 1:
                st.success("✅ Accumulation detected")
            else:
                st.warning("❌ Distribution or neutral")
        
        with col2:
            emoji = "🟢" if ad_score == 1 else "🔴"
            st.metric("Score", f"{ad_score}/1", delta=emoji)
        
        tech_scores['accumulation_distribution'] = ad_score
        
        st.markdown("---")
        
        # 5. Insider Activity
        st.subheader("5️⃣ Insider Activity or Other Indicator")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            insider_score = st.radio(
                "Insider Activity Status",
                options=[0, 1],
                format_func=lambda x: "Negative/Neutral (0)" if x == 0 else "Positive (1)",
                index=st.session_state.insider_activity,
                horizontal=True
            )
            
            if insider_score != st.session_state.insider_activity:
                st.session_state.insider_activity = insider_score
                saved_inputs = load_user_inputs()
                saved_inputs['insider_activity'] = insider_score
                save_user_inputs(saved_inputs)
            
            if insider_score == 1:
                st.success("✅ Positive insider activity")
            else:
                st.warning("❌ Negative or neutral insider activity")
        
        with col2:
            emoji = "🟢" if insider_score == 1 else "🔴"
            st.metric("Score", f"{insider_score}/1", delta=emoji)
        
        tech_scores['insider_activity'] = insider_score
        
        st.markdown("---")
        
        # 6. Key Bar
        st.subheader("6️⃣ Key Bar")
        
        df_with_kb, recent_kb = detect_key_bars(stock_df)
        kb_score, kb_details = calculate_key_bar_score(df_with_kb, recent_kb)
        tech_scores['key_bar'] = kb_score
        
        col1, col2 = st.columns([3, 1])
        with col1:
            if recent_kb is not None:
                st.success(kb_details)
            else:
                st.warning("No Key Bar detected in last 10 trading days")
        with col2:
            emoji = "🟢" if kb_score == 1.0 else ("🟡" if kb_score == 0.5 else "🔴")
            st.metric("Score", f"{kb_score}/1.0", delta=emoji)
        
        total_tech_score = sum(tech_scores.values())
        st.markdown("---")
        st.markdown(f"### 📊 Technical Score: **{total_tech_score:.1f}/6.0**")
        
        # Price Chart
        st.markdown("---")
        st.subheader("📈 Price Chart with Moving Averages")
        
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                            vertical_spacing=0.03, 
                            row_heights=[0.7, 0.3])
        
        fig.add_trace(go.Candlestick(
            x=stock_df.index,
            open=stock_df['Open'],
            high=stock_df['High'],
            low=stock_df['Low'],
            close=stock_df['Close'],
            name='Price'
        ), row=1, col=1)
        
        if len(stock_df) >= 50:
            ma50_series = stock_df['Close'].rolling(window=50).mean()
            fig.add_trace(go.Scatter(x=stock_df.index, y=ma50_series, 
                                     name='50 MA', line=dict(color='blue', width=1)), row=1, col=1)
        
        if len(stock_df) >= 150:
            ma150_series = stock_df['Close'].rolling(window=150).mean()
            fig.add_trace(go.Scatter(x=stock_df.index, y=ma150_series, 
                                     name='150 MA', line=dict(color='orange', width=1)), row=1, col=1)
        
        if len(stock_df) >= 200:
            ma200_series = stock_df['Close'].rolling(window=200).mean()
            fig.add_trace(go.Scatter(x=stock_df.index, y=ma200_series, 
                                     name='200 MA', line=dict(color='red', width=1)), row=1, col=1)
        
        if df_with_kb is not None:
            key_bar_dates = df_with_kb[df_with_kb['Is_Key_Bar']].index
            key_bar_prices = df_with_kb[df_with_kb['Is_Key_Bar']]['High']
            
            fig.add_trace(go.Scatter(
                x=key_bar_dates,
                y=key_bar_prices,
                mode='markers',
                name='Key Bar',
                marker=dict(color='green', size=10, symbol='star')
            ), row=1, col=1)
        
        colors = ['red' if stock_df['Close'].iloc[i] < stock_df['Open'].iloc[i] 
                  else 'green' for i in range(len(stock_df))]
        
        fig.add_trace(go.Bar(x=stock_df.index, y=stock_df['Volume'], 
                             name='Volume', marker_color=colors), row=2, col=1)
        
        if len(stock_df) >= 30:
            vol_sma = stock_df['Volume'].rolling(window=30).mean()
            fig.add_trace(go.Scatter(x=stock_df.index, y=vol_sma, 
                                     name='30D Avg Vol', line=dict(color='orange', width=2)), row=2, col=1)
        
        fig.update_layout(height=800, xaxis_rangeslider_visible=False)
        fig.update_yaxes(title_text="Price", row=1, col=1)
        fig.update_yaxes(title_text="Volume", row=2, col=1)
        
        st.plotly_chart(fig, use_container_width=True)
    
    # ==================== FUNDAMENTAL TAB ====================
    with tab2:
        st.header("Fundamental Indicators (Max: 5 points)")
        
        if use_av:
            st.info("📊 Using Alpha Vantage for 4 indicators")
            fund_scores, fund_details = calculate_alpha_vantage_fundamentals(av_income, ticker)
            fund_error = None
            
            try:
                yahoo_stock = yf.Ticker(ticker)
                yahoo_info = yahoo_stock.info
                
                roe_ttm = yahoo_info.get('returnOnEquity')
                
                if roe_ttm is not None:
                    roe_pct = roe_ttm * 100 if roe_ttm < 1 else roe_ttm
                    fund_details['roe'] = roe_pct
                    fund_details['roe_source'] = 'Yahoo Finance (TTM)'
                    
                    if roe_pct >= 15:
                        fund_scores['roe'] = 1
                else:
                    fund_details['roe'] = None
                    fund_details['roe_source'] = 'Not available'
                    
            except Exception as e:
                fund_details['roe'] = None
                fund_details['roe_source'] = f'Error: {str(e)}'
                
        else:
            if fund_error:
                st.error(fund_error)
                fund_scores = {k: 0 for k in ['sales_growth', 'gross_margin', 'earnings', 'rule_of_40', 'roe']}
                fund_details = {}
            else:
                fund_scores, fund_details = calculate_fundamental_scores(fund_data)
        
        # Display fundamental indicators (simplified for space)
        st.subheader("1️⃣ Sales Growth Acceleration")
        col1, col2 = st.columns([3, 1])
        with col1:
            if 'sales_growth' in fund_details:
                growth_data = fund_details['sales_growth']
                if growth_data and len(growth_data) > 0 and growth_data[0] is not None:
                    st.write(f"Latest YoY: {growth_data[0]:+.2f}%")
        with col2:
            score_val = fund_scores['sales_growth']
            emoji = "🟢" if score_val == 1 else ("🟡" if score_val == 0.5 else "🔴")
            st.metric("Score", f"{score_val}/1", delta=emoji)
        
        st.markdown("---")
        
        st.subheader("2️⃣ Gross Profit Margin")
        col1, col2 = st.columns([3, 1])
        with col1:
            if 'gross_margin' in fund_details:
                margin_data = fund_details['gross_margin']
                if margin_data and len(margin_data) > 0 and margin_data[0] is not None:
                    st.write(f"Latest: {margin_data[0]:.2f}%")
        with col2:
            score_val = fund_scores['gross_margin']
            emoji = "🟢" if score_val == 1 else ("🟡" if score_val == 0.5 else "🔴")
            st.metric("Score", f"{score_val}/1", delta=emoji)
        
        st.markdown("---")
        
        st.subheader("3️⃣ Earnings Growth")
        col1, col2 = st.columns([3, 1])
        with col1:
            if 'earnings_growth' in fund_details:
                growth_data = fund_details['earnings_growth']
                if growth_data and len(growth_data) > 0 and growth_data[0] is not None:
                    st.write(f"Latest YoY: {growth_data[0]:+.2f}%")
        with col2:
            score_val = fund_scores['earnings']
            emoji = "🟢" if score_val == 1 else ("🟡" if score_val == 0.5 else "🔴")
            st.metric("Score", f"{score_val}/1", delta=emoji)
        
        st.markdown("---")
        
        st.subheader("4️⃣ Rule of 40")
        col1, col2 = st.columns([3, 1])
        with col1:
            if 'rule_of_40' in fund_details:
                ro40 = fund_details['rule_of_40']
                st.write(f"Rule of 40: {ro40:.2f}%")
        with col2:
            emoji = "🟢" if fund_scores['rule_of_40'] == 1 else "🔴"
            st.metric("Score", f"{fund_scores['rule_of_40']}/1", delta=emoji)
        
        st.markdown("---")
        
        st.subheader("5️⃣ ROE (≥15%)")
        col1, col2 = st.columns([3, 1])
        with col1:
            if 'roe' in fund_details and fund_details['roe'] is not None:
                roe_val = fund_details['roe']
                st.write(f"ROE: {roe_val:.2f}%")
        with col2:
            emoji = "🟢" if fund_scores['roe'] == 1 else "🔴"
            st.metric("Score", f"{fund_scores['roe']}/1", delta=emoji)
        
        total_fund_score = sum(fund_scores.values())
        st.markdown("---")
        st.markdown(f"### 📊 Fundamental Score: **{total_fund_score}/5.0**")
    
    # ==================== REMARKS TAB ====================
    with tab3:
        st.header("Remarks (Max: 2 points)")
        
        remarks_scores = {}
        
        st.subheader("1️⃣ Top-Rated in Group")
        col1, col2 = st.columns([3, 1])
        with col1:
            top_rated = st.radio(
                "Is this stock among top-rated in its group?",
                options=["No", "Yes"],
                index=1 if st.session_state.top_rated_group else 0,
                horizontal=True
            )
            
            if top_rated == "Yes":
                remarks_scores['top_rated_group'] = 1
                if not st.session_state.top_rated_group:
                    st.session_state.top_rated_group = True
                    saved_inputs = load_user_inputs()
                    saved_inputs['top_rated_group'] = True
                    save_user_inputs(saved_inputs)
            else:
                remarks_scores['top_rated_group'] = 0
                if st.session_state.top_rated_group:
                    st.session_state.top_rated_group = False
                    saved_inputs = load_user_inputs()
                    saved_inputs['top_rated_group'] = False
                    save_user_inputs(saved_inputs)
        
        with col2:
            emoji = "🟢" if remarks_scores['top_rated_group'] == 1 else "🔴"
            st.metric("Score", f"{remarks_scores['top_rated_group']}/1", delta=emoji)
        
        st.markdown("---")
        
        st.subheader("2️⃣ New Development")
        col1, col2 = st.columns([3, 1])
        with col1:
            new_dev = st.radio(
                "Any significant new development?",
                options=["No", "Yes"],
                index=1 if st.session_state.new_development else 0,
                horizontal=True
            )
            
            if new_dev == "Yes":
                remarks_scores['new_development'] = 1
                if not st.session_state.new_development:
                    st.session_state.new_development = True
                    saved_inputs = load_user_inputs()
                    saved_inputs['new_development'] = True
                    save_user_inputs(saved_inputs)
            else:
                remarks_scores['new_development'] = 0
                if st.session_state.new_development:
                    st.session_state.new_development = False
                    saved_inputs = load_user_inputs()
                    saved_inputs['new_development'] = False
                    save_user_inputs(saved_inputs)
        
        with col2:
            emoji = "🟢" if remarks_scores['new_development'] == 1 else "🔴"
            st.metric("Score", f"{remarks_scores['new_development']}/1", delta=emoji)
        
        total_remarks_score = sum(remarks_scores.values())
        st.markdown("---")
        st.markdown(f"### 📊 Remarks Score: **{total_remarks_score}/2.0**")
    
    # Total Score
    st.markdown("---")
    st.header("🎯 Total Score Summary")
    
    total_score = total_tech_score + total_fund_score + total_remarks_score
    max_score = 13.0
    
    with total_score_placeholder.container():
        st.header("🎯 Overall Score Dashboard")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Technical", f"{total_tech_score:.1f}/6.0")
        with col2:
            st.metric("Fundamental", f"{total_fund_score}/5.0")
        with col3:
            st.metric("Remarks", f"{total_remarks_score}/2.0")
        with col4:
            percentage = (total_score / max_score) * 100
            color = "🟢" if percentage >= 70 else ("🟡" if percentage >= 50 else "🔴")
            st.metric("**TOTAL**", f"**{total_score:.1f}/{max_score}**", delta=f"{percentage:.0f}% {color}")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Technical", f"{total_tech_score:.1f}/6.0")
    with col2:
        st.metric("Fundamental", f"{total_fund_score}/5.0")
    with col3:
        st.metric("Remarks", f"{total_remarks_score}/2.0")
    with col4:
        percentage = (total_score / max_score) * 100
        color = "🟢" if percentage >= 70 else ("🟡" if percentage >= 50 else "🔴")
        st.metric("TOTAL", f"{total_score:.1f}/{max_score}", delta=f"{percentage:.0f}% {color}")
    
    if percentage >= 75:
        rating = "⭐⭐⭐⭐⭐ Excellent"
    elif percentage >= 60:
        rating = "⭐⭐⭐⭐ Good"
    elif percentage >= 45:
        rating = "⭐⭐⭐ Average"
    elif percentage >= 30:
        rating = "⭐⭐ Below Average"
    else:
        rating = "⭐ Poor"
    
    st.markdown(f"### Rating: {rating}")

st.markdown("---")
st.caption("⚠️ This is for educational purposes only. Not financial advice.")
st.caption(f"📅 Data as of {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
