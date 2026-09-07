import os
import base64
import streamlit as st
import pandas as pd
import datetime
import io
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from data_loader import fetch_skhy_data, get_summary_stats, DEFAULT_START_DATE

LOGO_PATH = os.path.join(os.path.dirname(__file__), "sk_hynix_logo.png")

def get_logo_html(height: int = 46) -> str:
    if os.path.exists(LOGO_PATH):
        with open(LOGO_PATH, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        return f"<img src='data:image/png;base64,{b64}' style='height: {height}px; object-fit: contain; vertical-align: middle;' alt='SK hynix'>"
    return ""

# ==========================================
# 1. 페이지 환경설정
# ==========================================
st.set_page_config(
    page_title="SKHY(ADR) 프리미엄 추이",
    page_icon=LOGO_PATH if os.path.exists(LOGO_PATH) else "📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# 2. 커스텀 CSS 스타일링 (00 Bookmarks 다크 테마 계승)
# ==========================================
st.markdown("""
<style>
    /* 메인 배경 및 기본 폰트 */
    .stApp {
        background-color: #0f172a !important;
        color: #f8fafc !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans KR", sans-serif;
    }
    
    /* 상단 여백 최적화 */
    .main .block-container,
    [data-testid="stMainBlockContainer"] {
        padding-top: 2.2rem !important;
        padding-bottom: 3.5rem !important;
        max-width: 1440px;
    }
    
    /* 사이드바 스타일링 */
    section[data-testid="stSidebar"] {
        background-color: #1e293b !important;
        border-right: 1px solid #334155 !important;
    }
    
    /* 제목 폰트 색상 (00 Bookmarks 공식 타이틀 색상: #8AB4F8) */
    .dashboard-title {
        color: #8AB4F8 !important;
        font-size: 2.2rem !important;
        font-weight: 800 !important;
        letter-spacing: -0.5px;
        margin: 0 0 6px 0;
        display: flex;
        align-items: center;
        gap: 12px;
    }
    
    .section-title {
        color: #8AB4F8 !important;
        font-size: 1.45rem !important;
        font-weight: 700 !important;
        letter-spacing: -0.3px;
        margin-top: 36px;
        margin-bottom: 14px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    
    .dashboard-subtitle {
        color: #94a3b8;
        font-size: 0.95rem;
        line-height: 1.5;
        margin-bottom: 24px;
    }

    /* KPI 요약 카드 디자인 */
    .kpi-container {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
        gap: 14px;
        margin-bottom: 24px;
    }
    
    .kpi-card {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 16px 18px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
        transition: transform 0.2s, border-color 0.2s;
    }
    
    .kpi-card:hover {
        transform: translateY(-2px);
        border-color: #64748b;
    }
    
    .kpi-label {
        font-size: 0.82rem;
        color: #94a3b8;
        font-weight: 600;
        margin-bottom: 6px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    .kpi-value {
        font-size: 1.45rem;
        font-weight: 800;
        color: #f8fafc;
        margin-bottom: 4px;
    }
    
    .kpi-subtext {
        font-size: 0.8rem;
        color: #cbd5e1;
    }
    
    .kpi-highlight-green {
        color: #34d399 !important;
    }
    
    .kpi-highlight-blue {
        color: #38bdf8 !important;
    }
    
    .kpi-highlight-orange {
        color: #fb923c !important;
    }
    
    /* 사이드바 인풋 및 버튼 커스텀 */
    div[data-testid="stDateInput"] label {
        color: #cbd5e1 !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
    }
    
    div[data-testid="stDateInput"] input {
        background-color: #0f172a !important;
        color: #f8fafc !important;
        border: 1px solid #475569 !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
    }
    
    .stButton button {
        border-radius: 8px !important;
        font-weight: 700 !important;
        transition: all 0.2s ease-in-out !important;
    }
    
    /* 테이블 스타일 튜닝 */
    [data-testid="stDataFrame"] {
        border: 1px solid #334155 !important;
        border-radius: 10px !important;
        overflow: hidden !important;
    }
    
    /* Plotly 툴팁 글래스모피즘 반투명 및 블러 효과 */
    .hoverlayer .hovertext path.bg {
        backdrop-filter: blur(6px) !important;
        -webkit-backdrop-filter: blur(6px) !important;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. 데이터 캐싱 로더
# ==========================================
@st.cache_data(ttl=600, show_spinner=False)
def load_data(start_d: datetime.date, end_d: datetime.date) -> pd.DataFrame:
    """데이터 수집 및 캐싱 (10분 TTL)"""
    return fetch_skhy_data(start_d, end_d)

# ==========================================
# 4. 세션 상태(Session State) 초기화
# ==========================================
if 'start_date' not in st.session_state:
    st.session_state.start_date = DEFAULT_START_DATE
if 'end_date' not in st.session_state:
    st.session_state.end_date = datetime.date.today()

# ==========================================
# 5. 대시보드 왼쪽 (사이드바 제어 패널)
# ==========================================
with st.sidebar:
    st.markdown("<h2 style='color: #8AB4F8; font-size: 1.3rem; margin-top: 0;'>⚙️ 조회 설정</h2>", unsafe_allow_html=True)
    st.markdown("<p style='color: #94a3b8; font-size: 0.85rem; margin-bottom: 20px;'>분석할 기간과 차트 형태를 설정합니다.</p>", unsafe_allow_html=True)
    
    # 캘린더 입력 (시작일, 종료일)
    
    input_start_date = st.date_input(
        "📅 시작일",
        value=st.session_state.start_date,
        min_value=datetime.date(2026, 1, 1),
        max_value=datetime.date.today(),
        help="SKHY 상장 이후 첫 거래일(2026-07-13)이 기본값입니다."
    )
    
    input_end_date = st.date_input(
        "📅 종료일",
        value=st.session_state.end_date,
        min_value=input_start_date,
        max_value=datetime.date.today(),
        help="조회 당일 날짜가 기본값입니다."
    )
    
    # 빠른 날짜 선택 프리셋 버튼
    st.markdown("<div style='font-size: 0.82rem; color: #94a3b8; margin: 12px 0 6px 0; font-weight: 600;'>⚡ 빠른 기간 선택</div>", unsafe_allow_html=True)
    preset_c1, preset_c2, preset_c3 = st.columns(3)
    with preset_c1:
        if st.button("전체", use_container_width=True, help="상장일(7/13)부터 현재까지"):
            st.session_state.start_date = DEFAULT_START_DATE
            st.session_state.end_date = datetime.date.today()
            st.rerun()
    with preset_c2:
        if st.button("1개월", use_container_width=True, help="최근 30일"):
            st.session_state.start_date = max(DEFAULT_START_DATE, datetime.date.today() - datetime.timedelta(days=30))
            st.session_state.end_date = datetime.date.today()
            st.rerun()
    with preset_c3:
        if st.button("2주", use_container_width=True, help="최근 14일"):
            st.session_state.start_date = max(DEFAULT_START_DATE, datetime.date.today() - datetime.timedelta(days=14))
            st.session_state.end_date = datetime.date.today()
            st.rerun()

    st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)

    # 조회 버튼
    submit_btn = st.button("🔍 조회", type="primary", use_container_width=True)
    if submit_btn:
        st.session_state.start_date = input_start_date
        st.session_state.end_date = input_end_date
        st.rerun()
        
    st.markdown("---")
    
    # [시각화 옵션: 사용자 질문에 따른 차트 표현 방식 선택]
    st.markdown("<div style='font-size: 0.88rem; color: #8AB4F8; font-weight: 700; margin-bottom: 6px;'>📊 차트 표현 방식</div>", unsafe_allow_html=True)
    chart_style = st.radio(
        "차트 유형 선택",
        options=[
            "주가 꺾은선 + 프리미엄 막대 (강력 추천)",
            "주가 꺾은선 + 프리미엄 꺾은선",
            "주가 그룹 막대 + 프리미엄 꺾은선"
        ],
        index=0,
        label_visibility="collapsed"
    )
    
    st.caption("💡 **금융 시각화 가이드**: 두 주가는 시계열 연속성을 가진 **꺾은선**으로 비교하고, 괴리율(%)은 0% 기준선의 **막대**로 표기하는 방식이 추세와 괴리 크기를 가장 직관적으로 보여줍니다.")

    st.markdown("<div style='margin-top: 14px; font-size: 0.88rem; color: #8AB4F8; font-weight: 700; margin-bottom: 4px;'>🔍 데이터 창(툴팁) 투명도</div>", unsafe_allow_html=True)
    tooltip_opacity = st.slider(
        "데이터 창 불투명도",
        min_value=20,
        max_value=100,
        value=75,
        step=5,
        format="%d%%",
        help="차트 영역에 마우스를 올렸을 때 나타나는 데이터 창의 불투명도를 조절합니다. (낮을수록 투명해져 가려진 차트 곡선이 잘 보입니다.)",
        label_visibility="collapsed"
    )
    st.caption("💡 차트를 가리지 않도록 **75% 반투명**이 기본 적용되어 있습니다. 슬라이더로 투명도를 자유롭게 조절할 수 있습니다.")

    st.markdown("---")
    st.markdown("""
    <div style='font-size: 0.78rem; color: #64748b; line-height: 1.5;'>
        • <b>SKHY</b>: 미국 나스닥 상장 종목<br/>
        • <b>SK하이닉스</b>: 000660 (KOSPI)<br/>
        • <b>환산 공식</b>: USD 주가 × 10 × 당일 환율<br/>
        • 양국 휴장일 차이는 직전 거래일 기준 자동 보정(ffill)됩니다.
    </div>
    """, unsafe_allow_html=True)

# ==========================================
# 6. 메인 대시보드 상단 (헤더 및 안내)
# ==========================================
# 오른쪽 상단 타이틀 (00 Bookmarks 컬러 #8AB4F8 적용, SK hynix 로고 이미지 적용)
logo_markup = get_logo_html(46)
st.markdown(
    f"<h1 class='dashboard-title'>{logo_markup}SKHY(ADR) 프리미엄 추이</h1>",
    unsafe_allow_html=True
)
st.markdown(
    "<div class='dashboard-subtitle'>"
    "미국 나스닥 <b>SKHY</b>와 국내 증시 <b>SK하이닉스</b>의 주가를 비교하고, "
    "실시간 환율을 반영한 원화 환산 주가(<code>달러 주가 × 10 × 당일 환율</code>) 및 "
    "<b>ADR 프리미엄(괴리율)</b>의 변동 추이를 추적하는 대시보드입니다."
    "</div>",
    unsafe_allow_html=True
)

# ==========================================
# 7. 데이터 로드 및 검증
# ==========================================
start_query = st.session_state.start_date
end_query = st.session_state.end_date

if start_query > end_query:
    st.error("⚠️ 시작일이 종료일보다 이후 날짜일 수 없습니다. 사이드바에서 날짜를 다시 설정해 주세요.")
    st.stop()

with st.spinner("최신 주가 및 환율 데이터를 집계하는 중입니다..."):
    try:
        df = load_data(start_query, end_query)
    except Exception as e:
        st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {e}")
        st.stop()

if df.empty:
    st.warning("⚠️ 선택하신 기간의 데이터가 존재하지 않습니다. 시작일을 SKHY 상장일(2026-07-13) 이후로 설정해 주세요.")
    st.stop()

stats = get_summary_stats(df)

# ==========================================
# 8. 핵심 지표 KPI 카드 (대시보드 상단 요약)
# ==========================================
latest_date_str = stats['latest_date'].strftime('%Y-%m-%d')
sk_krw_str = f"₩{int(stats['sk_krw']):,}"
skhy_usd_str = f"${stats['skhy_usd']:.2f}"
usdkrw_str = f"₩{stats['usdkrw']:,.2f}"
skhy_krw_str = f"₩{int(stats['skhy_krw']):,}"
prem_krw_str = f"{'+' if stats['premium_krw'] >= 0 else ''}₩{int(stats['premium_krw']):,}"
prem_pct_str = f"{'+' if stats['premium_pct'] >= 0 else ''}{stats['premium_pct']:.2f}%"

delta_pct = stats['delta_premium_pct']
delta_sign = "▲" if delta_pct > 0 else ("▼" if delta_pct < 0 else "─")
delta_color_cls = "kpi-highlight-green" if delta_pct >= 0 else "kpi-highlight-orange"
delta_str = f"{delta_sign} {abs(delta_pct):.2f}%p (전일비)"

st.markdown(f"""
<div class='kpi-container'>
    <div class='kpi-card'>
        <div class='kpi-label'>🇰🇷 SK하이닉스 종가</div>
        <div class='kpi-value kpi-highlight-blue'>{sk_krw_str}</div>
        <div class='kpi-subtext'>기준일: {latest_date_str}</div>
    </div>
    <div class='kpi-card'>
        <div class='kpi-label'>🇺🇸 SKHY (나스닥)</div>
        <div class='kpi-value'>{skhy_usd_str}</div>
        <div class='kpi-subtext'>환율: {usdkrw_str}</div>
    </div>
    <div class='kpi-card'>
        <div class='kpi-label'>💵 SKHY 원화 환산가</div>
        <div class='kpi-value kpi-highlight-orange'>{skhy_krw_str}</div>
        <div class='kpi-subtext'>$ × 10 × 당일 환율</div>
    </div>
    <div class='kpi-card'>
        <div class='kpi-label'>🎯 최신 ADR 프리미엄</div>
        <div class='kpi-value kpi-highlight-green'>{prem_pct_str}</div>
        <div class='kpi-subtext {delta_color_cls}'>{delta_str} | {prem_krw_str}</div>
    </div>
    <div class='kpi-card'>
        <div class='kpi-label'>📈 기간 평균 / 최고 / 최저</div>
        <div class='kpi-value'>{stats['avg_premium']:.1f}%</div>
        <div class='kpi-subtext'>최고: <b style='color:#34d399;'>+{stats['max_premium']:.1f}%</b> | 최저: <b style='color:#f87171;'>+{stats['min_premium']:.1f}%</b></div>
    </div>
</div>
""", unsafe_allow_html=True)

# ==========================================
# 9. 차트 영역 (Plotly 인터랙티브 듀얼 축 차트)
# ==========================================
date_index_str = [d.strftime('%Y-%m-%d') for d in df.index]

# 커스텀 툴팁을 위한 지표별 전용 텍스트 구성 (중복 노출 방지 및 가독성 최적화)
hover_sk = [f"₩{int(r['SK_KRW']):,}" for _, r in df.iterrows()]
hover_skhy = [f"₩{int(r['SKHY_KRW']):,} (${r['SKHY_USD']:.2f} | 환율 ₩{r['USDKRW']:,.2f})" for _, r in df.iterrows()]
hover_prem = [
    f"<b>{'+' if r['Premium_Pct']>=0 else ''}{r['Premium_Pct']:.2f}%</b> ({'+' if r['Premium_KRW']>=0 else ''}₩{int(r['Premium_KRW']):,})"
    for _, r in df.iterrows()
]

# 막대 그래프 색상 (양수: 반투명 에메랄드 그린, 음수: 반투명 코랄 레드)
bar_colors = [
    'rgba(52, 211, 153, 0.55)' if val >= 0 else 'rgba(248, 113, 113, 0.55)'
    for val in df['Premium_Pct']
]
bar_border_colors = [
    '#10b981' if val >= 0 else '#ef4444'
    for val in df['Premium_Pct']
]

# 보조 축을 포함하는 Figure 생성
fig = make_subplots(specs=[[{"secondary_y": True}]])

# 1) 주가 꺾은선 + 프리미엄 막대 (강력 추천 / 기본 요청)
if chart_style == "주가 꺾은선 + 프리미엄 막대 (강력 추천)":
    # 3번 데이터: 프리미엄 백분율(%) 막대 그래프 (보조 Y축)
    fig.add_trace(
        go.Bar(
            x=date_index_str,
            y=df['Premium_Pct'],
            name="ADR 프리미엄(%)",
            marker=dict(
                color=bar_colors,
                line=dict(color=bar_border_colors, width=1.2)
            ),
            hoverinfo="text",
            hovertext=hover_prem,
            opacity=0.85
        ),
        secondary_y=True
    )
    
    # 1번 데이터: SK하이닉스 주가 원화 (주 Y축, 꺾은선)
    fig.add_trace(
        go.Scatter(
            x=date_index_str,
            y=df['SK_KRW'],
            name="SK하이닉스 (원)",
            mode='lines+markers',
            line=dict(color='#38bdf8', width=2.8),
            marker=dict(size=5, color='#38bdf8'),
            hoverinfo="text",
            hovertext=hover_sk
        ),
        secondary_y=False
    )
    
    # 2번 데이터: SKHY 원화 환산 주가 (주 Y축, 꺾은선)
    fig.add_trace(
        go.Scatter(
            x=date_index_str,
            y=df['SKHY_KRW'],
            name="SKHY 환산주가 ($×10×환율)",
            mode='lines+markers',
            line=dict(color='#fb923c', width=2.8),
            marker=dict(size=5, color='#fb923c'),
            hoverinfo="text",
            hovertext=hover_skhy
        ),
        secondary_y=False
    )

# 2) 주가 꺾은선 + 프리미엄 꺾은선 (전체 라인형)
elif chart_style == "주가 꺾은선 + 프리미엄 꺾은선":
    fig.add_trace(
        go.Scatter(
            x=date_index_str,
            y=df['SK_KRW'],
            name="SK하이닉스 (원)",
            mode='lines+markers',
            line=dict(color='#38bdf8', width=2.8),
            marker=dict(size=5),
            hoverinfo="text",
            hovertext=hover_sk
        ),
        secondary_y=False
    )
    fig.add_trace(
        go.Scatter(
            x=date_index_str,
            y=df['SKHY_KRW'],
            name="SKHY 환산주가 ($×10×환율)",
            mode='lines+markers',
            line=dict(color='#fb923c', width=2.8),
            marker=dict(size=5),
            hoverinfo="text",
            hovertext=hover_skhy
        ),
        secondary_y=False
    )
    fig.add_trace(
        go.Scatter(
            x=date_index_str,
            y=df['Premium_Pct'],
            name="ADR 프리미엄(%)",
            mode='lines+markers',
            line=dict(color='#34d399', width=2.5, dash='dot'),
            marker=dict(size=6, symbol='diamond', color='#34d399'),
            hoverinfo="text",
            hovertext=hover_prem
        ),
        secondary_y=True
    )

# 3) 주가 그룹 막대 + 프리미엄 꺾은선
else:
    fig.add_trace(
        go.Bar(
            x=date_index_str,
            y=df['SK_KRW'],
            name="SK하이닉스 (원)",
            marker=dict(color='rgba(56, 189, 248, 0.7)', line=dict(color='#38bdf8', width=1)),
            hoverinfo="text",
            hovertext=hover_sk
        ),
        secondary_y=False
    )
    fig.add_trace(
        go.Bar(
            x=date_index_str,
            y=df['SKHY_KRW'],
            name="SKHY 환산주가 ($×10×환율)",
            marker=dict(color='rgba(251, 146, 60, 0.7)', line=dict(color='#fb923c', width=1)),
            hoverinfo="text",
            hovertext=hover_skhy
        ),
        secondary_y=False
    )
    fig.add_trace(
        go.Scatter(
            x=date_index_str,
            y=df['Premium_Pct'],
            name="ADR 프리미엄(%)",
            mode='lines+markers',
            line=dict(color='#34d399', width=3),
            marker=dict(size=7, color='#34d399'),
            hoverinfo="text",
            hovertext=hover_prem
        ),
        secondary_y=True
    )

# 0% 기준선 추가 (보조 Y축)
fig.add_hline(
    y=0,
    line_dash="dash",
    line_color="#64748b",
    line_width=1.5,
    secondary_y=True,
    annotation_text="기준선 (0%)",
    annotation_position="bottom right",
    annotation_font_color="#94a3b8"
)

# 데이터 창 투명도 색상 계산 (사이드바 슬라이더 연동)
alpha = tooltip_opacity / 100.0
hover_bg = f'rgba(15, 23, 42, {alpha:.2f})'
hover_border = f'rgba(148, 163, 184, {min(1.0, alpha + 0.15):.2f})'

# 차트 레이아웃 튜닝 (다크 테마 디자인)
fig.update_layout(
    paper_bgcolor='#0f172a',
    plot_bgcolor='#1e293b',
    font=dict(family='Noto Sans KR, sans-serif', color='#cbd5e1', size=12),
    height=540,
    margin=dict(l=20, r=20, t=30, b=20),
    hovermode='x unified',
    hoverlabel=dict(
        bgcolor=hover_bg,
        font_size=12,
        font_family="Noto Sans KR, monospace",
        bordercolor=hover_border
    ),
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="center",
        x=0.5,
        bgcolor='rgba(15, 23, 42, 0.85)',
        bordercolor='#334155',
        borderwidth=1,
        font=dict(color='#f8fafc', size=12)
    ),
    barmode='group' if "그룹 막대" in chart_style else 'relative',
    bargap=0.3
)

# 좌측 주 Y축 (원화 주가)
fig.update_yaxes(
    title=dict(text="<b>주가 (원, KRW)</b>", font=dict(color='#38bdf8', size=13)),
    tickprefix="₩",
    tickformat=",.0f",
    color='#cbd5e1',
    gridcolor='#334155',
    zeroline=False,
    secondary_y=False
)

# 우측 보조 Y축 (프리미엄 %)
fig.update_yaxes(
    title=dict(text="<b>ADR 프리미엄 괴리율 (%)</b>", font=dict(color='#34d399', size=13)),
    ticksuffix="%",
    tickformat="+.1f",
    color='#cbd5e1',
    gridcolor='rgba(51, 65, 85, 0.3)',
    zeroline=False,
    secondary_y=True
)

# X축
fig.update_xaxes(
    color='#cbd5e1',
    gridcolor='#334155',
    tickangle=-35,
    type='category'
)

# 차트 렌더링
st.plotly_chart(fig, use_container_width=True)

# ==========================================
# 10. 하단 원본 데이터 테이블 영역
# ==========================================
st.markdown(
    "<h2 class='section-title'>📋 SKHY(ADR) 프리미엄 원본 데이터 확인</h2>",
    unsafe_allow_html=True
)

# 테이블 표시용 DataFrame 가공 (최신 일자 내림차순 정렬)
df_display = df.sort_index(ascending=False).copy()

# 다운로드용 원본 데이터 복사본
export_df = df_display.copy()
export_df.index.name = "Date"

# 화면 출력용 포맷팅
formatted_table = pd.DataFrame(index=df_display.index)
formatted_table['일자'] = [d.strftime('%Y-%m-%d') for d in df_display.index]
formatted_table['SK하이닉스 (원)'] = df_display['SK_KRW'].apply(lambda x: f"₩{int(x):,}")
formatted_table['SKHY ($)'] = df_display['SKHY_USD'].apply(lambda x: f"${x:.2f}")
formatted_table['원/달러 환율'] = df_display['USDKRW'].apply(lambda x: f"₩{x:,.2f}")
formatted_table['SKHY 환산가 (원)'] = df_display['SKHY_KRW'].apply(lambda x: f"₩{int(x):,}")
formatted_table['프리미엄 금액 (원)'] = df_display['Premium_KRW'].apply(lambda x: f"{'+' if x>=0 else ''}₩{int(x):,}")
formatted_table['프리미엄 율 (%)'] = df_display['Premium_Pct'].apply(lambda x: f"{'+' if x>=0 else ''}{x:.2f}%")

# 다운로드 버튼 및 안내 컨트롤
tb_col1, tb_col2, tb_col3 = st.columns([6, 2, 2])
with tb_col1:
    st.caption(f"총 {len(formatted_table)}개 거래일 데이터가 조회되었습니다. (최근 일자 순 정렬)")

with tb_col2:
    # CSV 다운로드
    csv_data = export_df.to_csv(encoding='utf-8-sig').encode('utf-8-sig')
    st.download_button(
        label="📥 CSV 다운로드",
        data=csv_data,
        file_name=f"SKHY_Premium_{start_query}_{end_query}.csv",
        mime="text/csv",
        use_container_width=True
    )

with tb_col3:
    # Excel 다운로드
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        export_df.to_excel(writer, sheet_name='SKHY_Premium')
    st.download_button(
        label="📊 Excel 다운로드",
        data=excel_buffer.getvalue(),
        file_name=f"SKHY_Premium_{start_query}_{end_query}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

# 데이터프레임 렌더링
st.dataframe(
    formatted_table.reset_index(drop=True),
    use_container_width=True,
    height=420
)
