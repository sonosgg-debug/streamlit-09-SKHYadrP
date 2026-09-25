import socket
socket.setdefaulttimeout(5.0)

import datetime
import re
import logging
import pandas as pd
import yfinance as yf
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DEFAULT_START_DATE = datetime.date(2026, 7, 13)

def get_now_kst_date() -> datetime.date:
    """한국 표준시(KST, UTC+9) 기준 현재 날짜(datetime.date)를 반환합니다."""
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    return (now_utc + datetime.timedelta(hours=9)).date()

import requests

# 한국거래소(KRX) 정규 휴장일 및 법정 공휴일 (2024~2027)
KRX_HOLIDAYS = {
    # 2024
    '20240101', '20240209', '20240212', '20240301', '20240410', '20240501', '20240506',
    '20240515', '20240606', '20240815', '20240916', '20240917', '20240918', '20241001',
    '20241003', '20241009', '20241225', '20241231',
    # 2025
    '20250101', '20250128', '20250129', '20250130', '20250303', '20250501', '20250505',
    '20250506', '20250606', '20250815', '20251003', '20251006', '20251007', '20251008',
    '20251009', '20251225', '20251231',
    # 2026
    '20260101', '20260216', '20260217', '20260218', '20260302', '20260501', '20260505',
    '20260525', '20260603', '20260606', '20260817', '20260924', '20260925', '20261005',
    '20261009', '20261225', '20261231',
    # 2027
    '20270101', '20270208', '20270209', '20270210', '20270301', '20270503', '20270505',
    '20270513', '20270607', '20270816', '20270914', '20270915', '20270916', '20271004',
    '20271011', '20271225', '20271231'
}

_CACHED_TRADING_DAYS = None

def get_krx_trading_days(count=120):
    """
    한국거래소(KRX)의 실제 거래일(개장일) 목록을 반환합니다.
    1. 네이버 증시 API를 통해 실시간 실제 거래일 리스트를 우선 확보
    2. 실패 시 사전 정의된 휴장일 캘린더 및 주말 제외 알고리즘으로 폴백
    """
    global _CACHED_TRADING_DAYS
    if _CACHED_TRADING_DAYS is not None and len(_CACHED_TRADING_DAYS) >= count:
        return _CACHED_TRADING_DAYS
        
    days = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    pages_needed = (count + 59) // 60
    for page in range(1, pages_needed + 1):
        try:
            url = f'https://m.stock.naver.com/api/stock/005930/price?pageSize=60&page={page}'
            r = requests.get(url, headers=headers, timeout=3)
            if r.status_code == 200:
                items = r.json()
                if items:
                    days.extend([item['localTradedAt'].replace('-', '') for item in items])
                else:
                    break
        except Exception:
            pass
            
    if days:
        _CACHED_TRADING_DAYS = sorted(list(set(days)))
        return _CACHED_TRADING_DAYS
        
    fallback_days = []
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_kst = now_utc + datetime.timedelta(hours=9)
    d = now_kst
    for _ in range(count * 3):
        d_str = d.strftime('%Y%m%d')
        if d.weekday() < 5 and d_str not in KRX_HOLIDAYS:
            fallback_days.append(d_str)
            if len(fallback_days) >= count:
                break
        d -= datetime.timedelta(days=1)
        
    _CACHED_TRADING_DAYS = sorted(fallback_days)
    return _CACHED_TRADING_DAYS

def is_krx_trading_day(date_val):
    """주어진 날짜(date, YYYYMMDD 또는 YYYY-MM-DD)가 실제 거래일인지 판별합니다."""
    clean_date = str(date_val).replace('-', '')
    trading_days = get_krx_trading_days(120)
    if clean_date in trading_days:
        return True
    try:
        dt = datetime.datetime.strptime(clean_date, "%Y%m%d")
        return (dt.weekday() < 5) and (clean_date not in KRX_HOLIDAYS)
    except:
        return False

def get_latest_business_date(target_date=None) -> datetime.date:
    """
    서버 OS 타임존(UTC 등)과 무관하게 한국 표준시(KST, UTC+9)를 기준으로
    가장 최근 정규 거래가 완료된 영업일(YYYY-MM-DD)을 datetime.date 객체로 반환합니다.
    - target_date가 전달된 경우: 해당 날짜가 거래일이면 그대로, 휴장일이면 직전 실제 거래일로 자동 보정
    - target_date가 없는 경우: KST 기준 16:00 이전이거나 오늘이 휴장일이면 최신 마감 거래일 반환
    """
    trading_days = get_krx_trading_days(120)
    
    if target_date:
        clean_date = str(target_date).replace('-', '')
        if clean_date in trading_days:
            return datetime.datetime.strptime(clean_date, "%Y%m%d").date()
        earlier = [d for d in trading_days if d <= clean_date]
        if earlier:
            return datetime.datetime.strptime(earlier[-1], "%Y%m%d").date()
        try:
            dt = datetime.datetime.strptime(clean_date, "%Y%m%d")
            while True:
                d_str = dt.strftime("%Y%m%d")
                if dt.weekday() < 5 and d_str not in KRX_HOLIDAYS:
                    return dt.date()
                dt -= datetime.timedelta(days=1)
        except Exception:
            if isinstance(target_date, datetime.date):
                return target_date
            return datetime.datetime.strptime(clean_date, "%Y%m%d").date()

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_kst = now_utc + datetime.timedelta(hours=9)
    today_str = now_kst.strftime('%Y%m%d')

    if now_kst.hour >= 16 and today_str in trading_days:
        return datetime.datetime.strptime(today_str, "%Y%m%d").date()

    prior_days = [d for d in trading_days if d < today_str]
    if prior_days:
        return datetime.datetime.strptime(prior_days[-1], "%Y%m%d").date()

    fallback_str = trading_days[-1] if trading_days else (now_kst - datetime.timedelta(days=1)).strftime('%Y%m%d')
    return datetime.datetime.strptime(fallback_str, "%Y%m%d").date()

def download_ticker_yf(ticker: str, start_date: datetime.date, end_date: datetime.date) -> pd.Series:
    """
    yfinance를 통해 티커의 종가(Close) 데이터를 다운로드합니다.
    Yahoo Finance에서 최근 거래일의 일봉 Close가 None/NaN으로 반환되는 현상을 감지하여
    Ticker의 1일 시세(history 1d) 및 fast_info(last_price)로 정합성을 자동 보정합니다.
    """
    # yfinance end_date는 exclusive이므로 +1일
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = (end_date + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    
    logging.info(f"yfinance 다운로드: {ticker} ({start_str} ~ {end_str})")
    try:
        df = yf.download(ticker, start=start_str, end=end_str, progress=False)
        if df.empty:
            logging.warning(f"{ticker} yf.download 데이터가 비어있습니다.")
            s = pd.Series(dtype=float, name=ticker)
        else:
            if isinstance(df.columns, pd.MultiIndex):
                if 'Close' in df.columns.levels[0]:
                    ticker_cols = [c for c in df['Close'].columns if ticker in c or c in ticker]
                    s = df['Close'][ticker_cols[0]] if ticker_cols else df['Close'].iloc[:, 0]
                else:
                    s = df.iloc[:, 0]
            else:
                s = df['Close'] if 'Close' in df.columns else df.iloc[:, 0]
            s = s.copy()
            s.index = pd.to_datetime(s.index).date

        # 최신 거래일 종가 누락/NaN 보정 로직
        try:
            t = yf.Ticker(ticker)
            # 1. Ticker.history(period='1d') 확인 (장 마감 직후 일봉 미확정 시 정규장 종가 반영)
            h1 = t.history(period='1d')
            if not h1.empty:
                h1_date = h1.index[-1].date()
                h1_close = float(h1['Close'].iloc[-1])
                if pd.notna(h1_close) and h1_close > 0:
                    if h1_date in s.index:
                        if pd.isna(s.loc[h1_date]):
                            logging.info(f"[{ticker}] {h1_date} 누락 종가를 history(1d) 종가({h1_close})로 보정합니다.")
                            s.loc[h1_date] = h1_close
                    elif start_date <= h1_date <= end_date:
                        logging.info(f"[{ticker}] {h1_date} 누락 거래일을 history(1d) 종가({h1_close})로 추가합니다.")
                        s.loc[h1_date] = h1_close

            # 2. fast_info last_price 확인 (여전히 마지막 값이 NaN인 경우)
            if hasattr(t, 'fast_info'):
                last_p = getattr(t.fast_info, 'last_price', None)
                if last_p and pd.notna(last_p) and float(last_p) > 0:
                    if not s.empty and pd.isna(s.iloc[-1]):
                        logging.info(f"[{ticker}] 마지막 행 NaN을 fast_info.last_price({last_p})로 보정합니다.")
                        s.iloc[-1] = float(last_p)
        except Exception as repair_err:
            logging.warning(f"[{ticker}] 최신 종가 보정 중 예외 발생 (무시하고 계속 진행): {repair_err}")

        s = s.dropna().sort_index()
        s = s[~s.index.duplicated(keep='last')]
        s.name = ticker
        return s
    except Exception as e:
        logging.error(f"yfinance 다운로드 실패 ({ticker}): {e}")
        return pd.Series(dtype=float, name=ticker)

def download_naver_fchart(code: str, start_date: datetime.date, end_date: datetime.date) -> pd.Series:
    """
    네이버 금융 공식 fchart API에서 국내 종목의 일별 공식 종가를 가져옵니다.
    KRX 동시호가 체결가 및 실시간 종가가 정확히 반영됩니다.
    """
    logging.info(f"네이버 fchart 시세 조회: {code} ({start_date} ~ {end_date})")
    url = f"https://fchart.stock.naver.com/sise.nhn?timeframe=day&count=1200&requestType=0&symbol={code}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        res = requests.get(url, headers=headers, timeout=6)
        if res.status_code != 200:
            logging.warning(f"네이버 fchart HTTP 응답 오류: {res.status_code}")
            return pd.Series(dtype=float, name=code)
            
        root = ET.fromstring(res.text)
        items = root.findall('.//item')
        data = []
        for it in items:
            val = it.get('data')
            if not val:
                continue
            parts = val.split('|')
            # 형태: YYYYMMDD|Open|High|Low|Close|Volume
            if len(parts) >= 5:
                try:
                    dt = datetime.datetime.strptime(parts[0], '%Y%m%d').date()
                    if start_date <= dt <= end_date:
                        close = float(parts[4])
                        data.append((dt, close))
                except ValueError:
                    continue
                    
        if not data:
            logging.warning(f"네이버 fchart 파싱 결과 데이터 없음: {code}")
            return pd.Series(dtype=float, name=code)
            
        df = pd.DataFrame(data, columns=['Date', code]).set_index('Date').sort_index()
        s = df[code].astype(float)
        s = s[~s.index.duplicated(keep='last')]
        return s
    except Exception as e:
        logging.error(f"네이버 fchart 조회 에러 ({code}): {e}")
        return pd.Series(dtype=float, name=code)

def download_sk_domestic(start_date: datetime.date, end_date: datetime.date) -> pd.Series:
    """
    국내 SK하이닉스(000660) 종가를 공식 국내 금융 소스로부터 수집합니다.
    1순위: FinanceDataReader (네이버/KRX 연동)
    2순위: 네이버 fchart API 직접 호출
    3순위: pykrx 라이브러리
    4순위: yfinance (000660.KS - 동시호가 반영 지연 가능성 존재)
    """
    # 1순위: FinanceDataReader
    try:
        import FinanceDataReader as fdr
        df = fdr.DataReader('000660', start_date, end_date)
        if not df.empty and 'Close' in df.columns:
            s = df['Close'].astype(float).copy()
            s.index = pd.to_datetime(s.index).date
            s.name = '000660'
            s = s[~s.index.duplicated(keep='last')]
            if len(s) >= 1:
                logging.info(f"SK하이닉스 FinanceDataReader 수집 성공 ({len(s)}건)")
                return s
    except Exception as e:
        logging.warning(f"FinanceDataReader 수집 실패: {e}")

    # 2순위: 네이버 fchart API
    s = download_naver_fchart('000660', start_date, end_date)
    if not s.empty and len(s) >= 1:
        logging.info(f"SK하이닉스 네이버 fchart 수집 성공 ({len(s)}건)")
        return s

    # 3순위: pykrx
    try:
        from pykrx import stock
        s_date_str = start_date.strftime('%Y%m%d')
        e_date_str = end_date.strftime('%Y%m%d')
        df_krx = stock.get_market_ohlcv_by_date(s_date_str, e_date_str, '000660')
        if not df_krx.empty:
            col_close = '종가' if '종가' in df_krx.columns else df_krx.columns[3]
            s = df_krx[col_close].astype(float).copy()
            s.index = pd.to_datetime(s.index).date
            s.name = '000660'
            s = s[~s.index.duplicated(keep='last')]
            if len(s) >= 1:
                logging.info(f"SK하이닉스 pykrx 수집 성공 ({len(s)}건)")
                return s
    except Exception as e:
        logging.warning(f"pykrx 수집 실패: {e}")

    # 4순위: yfinance 폴백
    logging.warning("국내 소스 실패로 yfinance 000660.KS 폴백 시도")
    return download_ticker_yf('000660.KS', start_date, end_date)

def fetch_skhy_data(start_date: datetime.date, end_date: datetime.date, include_live: bool = False) -> pd.DataFrame:
    """
    SKHY, KRW=X(환율), SK하이닉스(000660) 데이터를 수집하고
    정합성 정제 및 원화 환산, 프리미엄을 계산한 통합 DataFrame을 반환합니다.
    
    :param include_live: False(기본값)이면 양 시장 정규장이 모두 마감 확정된 공식 종가만 포함(데이터 정합성 보장),
                         True이면 오늘 국내 장중 실시간 데이터도 포함합니다.
    """
    # 1. 미국 SKHY 주가 (최신 종가 NaN 누락 자동 보정)
    s_skhy = download_ticker_yf('SKHY', start_date, end_date)
    
    # 2. USD/KRW 원달러 환율
    s_krw = download_ticker_yf('KRW=X', start_date, end_date)
    
    # 3. 국내 SK하이닉스 주가 (KRX/네이버 공식 종가 우선)
    s_sk = download_sk_domestic(start_date, end_date)

    # 4. 결합 및 전처리
    df = pd.concat([s_skhy, s_krw, s_sk], axis=1)
    df.columns = ['SKHY_USD', 'USDKRW', 'SK_KRW']
    
    # 두 주식 시장 중 최소 한 곳이라도 개장한 날 보존
    df = df.dropna(subset=['SKHY_USD', 'SK_KRW'], how='all')
    
    # [데이터 정합성 보장 로직]
    # 공식 마감 종가 기준(include_live=False)인 경우:
    # 아직 정규장 마감이 되지 않은 미완성 실시간 거래일은 제외하고,
    # 한국 및 미국 정규장 공식 마감 종가가 확정된 최신 영업일(latest_bdate)까지만 안전하게 반영합니다.
    if not include_live:
        latest_bdate = get_latest_business_date()
        df = df[df.index <= latest_bdate]
    
    # 시계열 오름차순 정렬 후 양국 공휴일/영업일 차이 Forward Fill
    df = df.sort_index(ascending=True)
    df = df.ffill()
    # 시작 시점 이전 NaN 제거
    df = df.dropna(subset=['SKHY_USD', 'USDKRW', 'SK_KRW'])
    
    # 날짜 범위 엄격 필터링
    df = df[(df.index >= start_date) & (df.index <= end_date)]
    
    # 5. 지표 계산
    # 공식 2: SKHY(원화) = 달러 기준 주가 * 10 * 당일 환율
    df['SKHY_KRW'] = df['SKHY_USD'] * 10.0 * df['USDKRW']
    
    # 공식 3: 프리미엄 금액 및 백분율(%)
    # 프리미엄 금액 = SKHY(원화) - SK하이닉스(원)
    df['Premium_KRW'] = df['SKHY_KRW'] - df['SK_KRW']
    # 프리미엄 % = ((SKHY(원화) - SK하이닉스) / SK하이닉스) * 100
    df['Premium_Pct'] = (df['Premium_KRW'] / df['SK_KRW']) * 100.0

    return df

def get_summary_stats(df: pd.DataFrame) -> dict:
    """
    대시보드 KPI 카드 및 통계 요약을 생성합니다.
    """
    if df.empty:
        return {}
        
    latest_row = df.iloc[-1]
    prev_row = df.iloc[-2] if len(df) >= 2 else latest_row
    
    latest_date = df.index[-1]
    sk_krw = latest_row['SK_KRW']
    skhy_usd = latest_row['SKHY_USD']
    usdkrw = latest_row['USDKRW']
    skhy_krw = latest_row['SKHY_KRW']
    premium_krw = latest_row['Premium_KRW']
    premium_pct = latest_row['Premium_Pct']
    
    prev_premium_pct = prev_row['Premium_Pct']
    delta_premium_pct = premium_pct - prev_premium_pct
    
    avg_premium = df['Premium_Pct'].mean()
    max_premium = df['Premium_Pct'].max()
    min_premium = df['Premium_Pct'].min()
    
    max_date = df['Premium_Pct'].idxmax()
    min_date = df['Premium_Pct'].idxmin()

    return {
        'latest_date': latest_date,
        'sk_krw': sk_krw,
        'skhy_usd': skhy_usd,
        'usdkrw': usdkrw,
        'skhy_krw': skhy_krw,
        'premium_krw': premium_krw,
        'premium_pct': premium_pct,
        'delta_premium_pct': delta_premium_pct,
        'avg_premium': avg_premium,
        'max_premium': max_premium,
        'min_premium': min_premium,
        'max_date': max_date,
        'min_date': min_date,
        'data_count': len(df)
    }

if __name__ == '__main__':
    today = get_now_kst_date()
    print(f"테스트 데이터 수집: {DEFAULT_START_DATE} ~ {today}")
    result_df = fetch_skhy_data(DEFAULT_START_DATE, today)
    print("결과 샘플:")
    print(result_df.tail())
    stats = get_summary_stats(result_df)
    print("통계 요약:", stats)

def get_latest_expected_trading_day(target_date: str = None) -> str:
    """
    가장 최근 거래 완료된 실제 영업일 YYYY-MM-DD 반환.
    - target_date가 전달된 경우: 해당 날짜 기준 (또는 직전 영업일)
    - target_date가 없는 경우: KST 기준 15:45 이전이거나 오늘이 주말/새벽이면 직전 마감 거래일 반환
    """
    from datetime import datetime, timezone, timedelta
    now_kst = datetime.now(timezone(timedelta(hours=9)))
    if target_date:
        try:
            clean_date = str(target_date).replace('-', '')
            dt = datetime.strptime(clean_date, "%Y%m%d").replace(tzinfo=timezone(timedelta(hours=9)))
        except Exception:
            dt = now_kst
    else:
        dt = now_kst

    # 평일 15:45 이후에만 당일 종가 확정
    if dt.weekday() < 5 and (dt.hour > 15 or (dt.hour == 15 and dt.minute >= 45)):
        return dt.strftime("%Y-%m-%d")

    # 장전, 새벽, 주말: 직전 마감 거래일 산출
    if dt.weekday() == 0:    # 월요일 장전 -> 지난주 금요일 (3일 전)
        days_back = 3
    elif dt.weekday() == 6:  # 일요일 -> 지난주 금요일 (2일 전)
        days_back = 2
    elif dt.weekday() == 5:  # 토요일 -> 지난주 금요일 (1일 전)
        days_back = 1
    else:                    # 화~금 장전/새벽 -> 전일 (1일 전)
        days_back = 1

    return (dt - timedelta(days=days_back)).strftime("%Y-%m-%d")
