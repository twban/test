# -*- coding: utf-8 -*-
"""
대한민국 경제 지표 대시보드 (1980년~)
데이터 출처:
  - World Bank Open Data API (https://api.worldbank.org) : 별도 인증키 없이 사용 가능한 공신력 있는 국제기구 데이터
  - 한국은행 ECOS Open API (선택 사항, 사용자 본인 인증키 필요) : 기준금리 등 BOK 고유 통계

실행 방법:
  pip install -r requirements.txt
  streamlit run app.py
"""

import time
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

# --------------------------------------------------------------------------------------
# 기본 설정
# --------------------------------------------------------------------------------------
st.set_page_config(
    page_title="대한민국 경제 지표 대시보드",
    page_icon="📊",
    layout="wide",
)

CURRENT_YEAR = datetime.now().year
COUNTRY_CODE = "KOR"

# World Bank 지표 코드 매핑
# key: 화면에 표시할 한글 라벨 / value: (WB 지표코드, 단위, 카테고리, 값 스케일 나누기)
INDICATORS = {
    "실질 GDP 성장률": {"code": "NY.GDP.MKTP.KD.ZG", "unit": "%", "category": "성장", "scale": 1},
    "명목 GDP": {"code": "NY.GDP.MKTP.CD", "unit": "10억 달러", "category": "성장", "scale": 1e9},
    "1인당 GNI": {"code": "NY.GNP.PCAP.CD", "unit": "달러", "category": "성장", "scale": 1},
    "1인당 GDP": {"code": "NY.GDP.PCAP.CD", "unit": "달러", "category": "성장", "scale": 1},
    "소비자물가 상승률": {"code": "FP.CPI.TOTL.ZG", "unit": "%", "category": "물가", "scale": 1},
    "실업률": {"code": "SL.UEM.TOTL.ZS", "unit": "%", "category": "고용", "scale": 1},
    "경제활동참가율": {"code": "SL.TLF.CACT.ZS", "unit": "%", "category": "고용", "scale": 1},
    "수출 (GDP 대비)": {"code": "NE.EXP.GNFS.ZS", "unit": "% of GDP", "category": "대외거래", "scale": 1},
    "수입 (GDP 대비)": {"code": "NE.IMP.GNFS.ZS", "unit": "% of GDP", "category": "대외거래", "scale": 1},
    "경상수지 (GDP 대비)": {"code": "BN.CAB.XOKA.GD.ZS", "unit": "% of GDP", "category": "대외거래", "scale": 1},
    "외국인직접투자 순유입 (GDP 대비)": {"code": "BX.KLT.DINV.WD.GD.ZS", "unit": "% of GDP", "category": "대외거래", "scale": 1},
    "원/달러 환율 (연평균)": {"code": "PA.NUS.FCRF", "unit": "원/달러", "category": "대외거래", "scale": 1},
    "외환보유액": {"code": "FI.RES.TOTL.CD", "unit": "10억 달러", "category": "대외거래", "scale": 1e9},
    "중앙정부 부채 (GDP 대비)": {"code": "GC.DOD.TOTL.GD.ZS", "unit": "% of GDP", "category": "재정", "scale": 1},
    "제조업 부가가치 비중": {"code": "NV.IND.MANF.ZS", "unit": "% of GDP", "category": "산업구조", "scale": 1},
    "서비스업 부가가치 비중": {"code": "NV.SRV.TOTL.ZS", "unit": "% of GDP", "category": "산업구조", "scale": 1},
    "총인구": {"code": "SP.POP.TOTL", "unit": "명", "category": "인구", "scale": 1},
    "총저축률 (GDP 대비)": {"code": "NY.GNS.ICTR.ZS", "unit": "% of GDP", "category": "금융", "scale": 1},
    "실질금리": {"code": "FR.INR.RINR", "unit": "%", "category": "금융", "scale": 1},
    "R&D 지출 (GDP 대비)": {"code": "GB.XPD.RSDV.GD.ZS", "unit": "% of GDP", "category": "산업구조", "scale": 1},
}

DEFAULT_SELECTION = ["실질 GDP 성장률", "소비자물가 상승률", "실업률", "원/달러 환율 (연평균)"]


# --------------------------------------------------------------------------------------
# 데이터 수집 함수
# --------------------------------------------------------------------------------------
@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
def fetch_worldbank_indicator(indicator_code: str, start_year: int, end_year: int) -> pd.DataFrame:
    """World Bank Open Data API에서 대한민국(KOR)의 연도별 지표를 가져온다."""
    url = f"https://api.worldbank.org/v2/country/{COUNTRY_CODE}/indicator/{indicator_code}"
    params = {"date": f"{start_year}:{end_year}", "format": "json", "per_page": 1000}

    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        st.warning(f"데이터 요청 실패 ({indicator_code}): {exc}")
        return pd.DataFrame(columns=["year", "value"])

    if not isinstance(payload, list) or len(payload) < 2 or payload[1] is None:
        return pd.DataFrame(columns=["year", "value"])

    records = payload[1]
    df = pd.DataFrame(records)
    if df.empty:
        return pd.DataFrame(columns=["year", "value"])

    df = df[["date", "value"]].rename(columns={"date": "year"})
    df["year"] = df["year"].astype(int)
    df = df.dropna(subset=["value"]).sort_values("year").reset_index(drop=True)
    return df


@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
def fetch_ecos_base_rate(api_key: str, start_year: int, end_year: int) -> pd.DataFrame:
    """한국은행 ECOS API에서 기준금리(연말 기준, 월별 데이터 중 12월 값)를 가져온다."""
    start = f"{start_year}01"
    end = f"{end_year}12"
    url = (
        f"https://ecos.bok.or.kr/api/StatisticSearch/{api_key}/json/kr/1/1000/"
        f"722Y001/M/{start}/{end}/0101000"
    )
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        st.warning(f"ECOS 요청 실패: {exc}")
        return pd.DataFrame(columns=["year", "value"])

    if "StatisticSearch" not in payload or "row" not in payload["StatisticSearch"]:
        # 인증키 오류 등 메시지가 담긴 경우
        msg = payload.get("RESULT", {}).get("MESSAGE", "알 수 없는 오류")
        st.warning(f"ECOS 응답 오류: {msg}")
        return pd.DataFrame(columns=["year", "value"])

    rows = payload["StatisticSearch"]["row"]
    df = pd.DataFrame(rows)
    df["year"] = df["TIME"].str[:4].astype(int)
    df["value"] = pd.to_numeric(df["DATA_VALUE"], errors="coerce")
    # 연도별 12월(또는 해당 연도 마지막 관측치) 값을 대표값으로 사용
    df = df.dropna(subset=["value"]).sort_values("TIME")
    df_year_end = df.groupby("year", as_index=False).last()[["year", "value"]]
    return df_year_end.reset_index(drop=True)


# --------------------------------------------------------------------------------------
# 사이드바
# --------------------------------------------------------------------------------------
st.sidebar.title("⚙️ 대시보드 설정")

year_range = st.sidebar.slider(
    "조회 기간",
    min_value=1980,
    max_value=CURRENT_YEAR,
    value=(1980, CURRENT_YEAR),
)

category_list = sorted({v["category"] for v in INDICATORS.values()})
selected_categories = st.sidebar.multiselect(
    "카테고리 필터", category_list, default=category_list
)

available_indicators = [
    name for name, meta in INDICATORS.items() if meta["category"] in selected_categories
]

selected_indicators = st.sidebar.multiselect(
    "표시할 지표 선택",
    available_indicators,
    default=[i for i in DEFAULT_SELECTION if i in available_indicators],
)

chart_type = st.sidebar.radio("차트 유형", ["선 그래프", "막대 그래프"], horizontal=True)

st.sidebar.markdown("---")
with st.sidebar.expander("🏦 한국은행 ECOS 연동 (선택사항)"):
    st.caption(
        "기준금리 등 한국은행 고유 통계를 보려면 본인의 ECOS 인증키를 입력하세요.\n"
        "인증키는 https://ecos.bok.or.kr 에서 무료로 발급받을 수 있습니다."
    )
    ecos_key = st.text_input("ECOS API 인증키", type="password")
    show_base_rate = st.checkbox("한국은행 기준금리 표시", value=False)

st.sidebar.markdown("---")
st.sidebar.caption(
    "데이터 출처: World Bank Open Data API (api.worldbank.org), "
    "한국은행 ECOS Open API (ecos.bok.or.kr)"
)

# --------------------------------------------------------------------------------------
# 메인 화면
# --------------------------------------------------------------------------------------
st.title("📊 대한민국 경제 지표 대시보드")
st.caption(f"{year_range[0]}년 ~ {year_range[1]}년 · 데이터: World Bank Open Data / 한국은행 ECOS")

if not selected_indicators and not (show_base_rate and ecos_key):
    st.info("왼쪽 사이드바에서 하나 이상의 지표를 선택해주세요.")
    st.stop()

tab_charts, tab_compare, tab_table = st.tabs(["📈 개별 지표", "🔀 지표 비교(정규화)", "🗂️ 데이터 테이블"])

# 데이터 수집
data_frames = {}
with st.spinner("데이터를 불러오는 중입니다..."):
    for name in selected_indicators:
        meta = INDICATORS[name]
        df = fetch_worldbank_indicator(meta["code"], year_range[0], year_range[1])
        if not df.empty and meta["scale"] != 1:
            df["value"] = df["value"] / meta["scale"]
        data_frames[name] = df

    if show_base_rate:
        if not ecos_key:
            st.warning("ECOS 인증키를 입력해야 기준금리 데이터를 불러올 수 있습니다.")
        else:
            df_rate = fetch_ecos_base_rate(ecos_key, year_range[0], year_range[1])
            data_frames["한국은행 기준금리(연말)"] = df_rate
            INDICATORS_RUNTIME_UNIT = "%"

# --------------------------------------------------------------------------------------
# 탭 1: 개별 지표 그래프
# --------------------------------------------------------------------------------------
with tab_charts:
    for name, df in data_frames.items():
        unit = INDICATORS[name]["unit"] if name in INDICATORS else "%"
        st.subheader(f"{name} ({unit})")
        if df.empty:
            st.warning("해당 지표에 대한 데이터를 찾을 수 없습니다.")
            continue

        if chart_type == "선 그래프":
            fig = px.line(df, x="year", y="value", markers=True)
        else:
            fig = px.bar(df, x="year", y="value")

        fig.update_layout(
            xaxis_title="연도",
            yaxis_title=unit,
            height=380,
            margin=dict(l=10, r=10, t=10, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)

        col1, col2, col3 = st.columns(3)
        col1.metric("최신값", f"{df['value'].iloc[-1]:,.2f}", help=f"{int(df['year'].iloc[-1])}년 기준")
        col2.metric("최고값", f"{df['value'].max():,.2f}")
        col3.metric("최저값", f"{df['value'].min():,.2f}")

# --------------------------------------------------------------------------------------
# 탭 2: 지표 비교 (정규화, 시작연도=100)
# --------------------------------------------------------------------------------------
with tab_compare:
    st.markdown(
        "선택한 지표들을 **조회 기간 시작연도를 100으로 정규화**하여 같은 그래프에서 "
        "추세를 비교합니다. (단위가 서로 다른 지표를 함께 비교할 때 유용합니다.)"
    )
    fig = go.Figure()
    has_any = False
    for name, df in data_frames.items():
        if df.empty:
            continue
        base_value = df["value"].iloc[0]
        if base_value == 0:
            continue
        normalized = df["value"] / base_value * 100
        fig.add_trace(go.Scatter(x=df["year"], y=normalized, mode="lines+markers", name=name))
        has_any = True

    if has_any:
        fig.update_layout(
            xaxis_title="연도",
            yaxis_title="지수 (시작연도=100)",
            height=550,
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("비교할 데이터가 없습니다.")

# --------------------------------------------------------------------------------------
# 탭 3: 데이터 테이블 + 다운로드
# --------------------------------------------------------------------------------------
with tab_table:
    for name, df in data_frames.items():
        st.markdown(f"**{name}**")
        if df.empty:
            st.warning("데이터가 없습니다.")
            continue
        st.dataframe(df.rename(columns={"year": "연도", "value": "값"}), use_container_width=True, hide_index=True)
        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label=f"'{name}' CSV 다운로드",
            data=csv,
            file_name=f"{name}_{year_range[0]}_{year_range[1]}.csv",
            mime="text/csv",
            key=f"dl_{name}",
        )
        st.markdown("---")

st.caption(
    "⚠️ World Bank 데이터는 지표별로 대한민국 시계열이 1980년보다 늦게 시작하거나 "
    "일부 연도가 결측일 수 있습니다. 정확한 공식 통계는 한국은행 ECOS(ecos.bok.or.kr), "
    "통계청 KOSIS(kosis.kr) 원자료를 함께 확인하시기 바랍니다."
)
