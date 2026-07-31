"""Streamlit：六爻、问事奇门、终身奇门与历史复盘。"""
from __future__ import annotations

import datetime as dt
import html
import os
import uuid

import streamlit as st

from engine.astronomy import AstronomyCalculationError
from engine.caster import CastingError
from engine.guardrails import GuardrailValidationError
from engine.llm_interpreter import LLMInterpretationError, LLMInterpreter
from engine.paipan import PaipanError
from engine.qimen import QimenCalculationError, QimenService
from engine.tracker import AuditTracker
from main import run_divination_pipeline


st.set_page_config(page_title="数智易学", page_icon="☯️", layout="wide")
st.markdown(
    """
    <style>
    :root {
        --ink: #f5f0df;
        --muted: #a9afc0;
        --night: #070914;
        --line: rgba(196, 168, 103, .26);
        --gold: #e8c977;
        --gold-strong: #f2d47f;
        --blue: #5b8cff;
    }
    .stApp {
        background:
            radial-gradient(circle at 82% 8%, rgba(61, 82, 157, .20), transparent 28rem),
            radial-gradient(circle at 18% 72%, rgba(62, 45, 107, .13), transparent 32rem),
            var(--night);
        color: var(--ink);
    }
    [data-testid="stHeader"] { background: rgba(7, 9, 20, .72); }
    [data-testid="stAppViewContainer"] > .main .block-container {
        max-width: 1220px;
        padding-top: 2.25rem;
        padding-bottom: 5rem;
    }
    [data-testid="stMainBlockContainer"] {
        box-sizing: border-box;
        width: 100%;
    }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0b1022 0%, #080b16 100%);
        border-right: 1px solid var(--line);
    }
    [data-testid="stSidebar"] [data-testid="stSidebarContent"] { padding-top: 1.5rem; }
    h1, h2, h3, h4 {
        color: var(--ink) !important;
        font-family: "Noto Serif SC", "Songti SC", "STSong", serif !important;
        letter-spacing: .02em;
    }
    p, label, [data-testid="stCaptionContainer"] { color: #c6cad5; }
    [data-testid="stCaptionContainer"] { color: var(--muted); }
    .ui-hero {
        padding: 1.25rem 0 1.65rem;
        border-bottom: 1px solid var(--line);
        margin-bottom: 1.15rem;
    }
    .ui-eyebrow, .section-kicker {
        color: var(--gold);
        font-size: .75rem;
        font-weight: 800;
        letter-spacing: .18em;
        text-transform: uppercase;
        margin-bottom: .55rem;
    }
    .ui-hero h1 {
        font-size: clamp(2.15rem, 5vw, 4rem);
        line-height: 1.08;
        margin: 0;
    }
    .ui-hero .hero-copy {
        color: #c4c8d4;
        font-size: 1rem;
        margin: .85rem 0 1.1rem;
    }
    .hero-chips { display: flex; flex-wrap: wrap; gap: .55rem; }
    .hero-chips span {
        border: 1px solid var(--line);
        border-radius: 999px;
        color: var(--gold);
        background: rgba(232, 201, 119, .055);
        padding: .32rem .68rem;
        font-size: .78rem;
        font-weight: 700;
    }
    .sidebar-title {
        color: var(--ink);
        font-family: "Noto Serif SC", "Songti SC", serif;
        font-size: 1.45rem;
        font-weight: 800;
        margin-bottom: 1rem;
    }
    .status-pill {
        border: 1px solid var(--line);
        border-radius: 10px;
        padding: .7rem .8rem;
        margin-top: .7rem;
        color: var(--gold);
        background: rgba(232, 201, 119, .06);
        font-size: .86rem;
        font-weight: 700;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: .35rem;
        border-bottom: 1px solid var(--line);
        overflow-x: auto;
    }
    .stTabs [data-baseweb="tab"] {
        color: #b8bdca;
        min-height: 3rem;
        padding: .55rem .85rem;
        white-space: nowrap;
    }
    .stTabs [aria-selected="true"] {
        color: var(--gold-strong) !important;
        background: rgba(232, 201, 119, .06);
    }
    .stTabs [data-baseweb="tab-highlight"] { background-color: var(--gold) !important; }
    [data-testid="stVerticalBlockBorderWrapper"] {
        background: linear-gradient(145deg, rgba(17, 24, 49, .90), rgba(10, 14, 29, .90));
        border-color: var(--line) !important;
        border-radius: 16px !important;
        box-shadow: 0 18px 55px rgba(0, 0, 0, .18);
    }
    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input,
    [data-testid="stTextArea"] textarea,
    [data-baseweb="select"] > div {
        color: var(--ink) !important;
        background: #0b1020 !important;
        border-color: rgba(196, 168, 103, .22) !important;
    }
    [data-testid="stTextInput"] input::placeholder,
    [data-testid="stTextArea"] textarea::placeholder { color: #757d91; }
    [data-testid="stBaseButton-primary"], .stButton > button {
        border: 1px solid rgba(232, 201, 119, .64) !important;
        border-radius: 10px !important;
        background: linear-gradient(135deg, #efd487, #c9a54f) !important;
        color: #11131b !important;
        font-weight: 800 !important;
        min-height: 2.8rem;
        box-shadow: 0 8px 25px rgba(201, 165, 79, .15);
    }
    .stButton > button:hover { filter: brightness(1.06); transform: translateY(-1px); }
    [data-testid="stMetric"] {
        background: rgba(14, 20, 40, .92);
        border: 1px solid var(--line);
        border-radius: 14px;
        padding: .9rem 1rem;
    }
    [data-testid="stMetricLabel"] p { color: var(--gold) !important; }
    [data-testid="stMetricValue"] { color: var(--ink) !important; font-family: "Noto Serif SC", serif; }
    [data-testid="stExpander"] {
        border-color: var(--line) !important;
        background: rgba(10, 14, 29, .76);
    }
    [data-testid="stAlert"] { border-radius: 12px; }
    .result-head {
        display: flex;
        justify-content: space-between;
        align-items: end;
        gap: 1rem;
        margin: 2rem 0 1rem;
        padding-top: 1.4rem;
        border-top: 1px solid var(--line);
    }
    .result-head h2 { margin: 0; font-size: 1.8rem; }
    .result-head p { margin: 0; color: var(--muted); }
    .focus-summary {
        border-left: 3px solid var(--gold);
        padding: .2rem 0 .2rem .9rem;
        margin: .8rem 0 1rem;
    }
    .focus-summary strong { color: var(--gold-strong); font-size: 1.08rem; }
    .yao-stack { display: grid; gap: .55rem; }
    .yao-line {
        display: grid;
        grid-template-columns: 2.6rem 3.8rem minmax(8rem, 1fr) auto;
        align-items: center;
        gap: .6rem;
        min-height: 3.15rem;
        padding: .65rem .8rem;
        border: 1px solid rgba(196, 168, 103, .15);
        border-radius: 10px;
        background: rgba(7, 10, 22, .68);
        color: #d9dce5;
    }
    .yao-line .symbol { color: var(--gold); font-size: 1.5rem; line-height: 1; }
    .yao-line .position { color: #8e96aa; font-size: .82rem; }
    .yao-line .detail { font-weight: 650; }
    .yao-line .state { color: #9ba3b6; font-size: .78rem; text-align: right; }
    .yao-line.focus {
        border-color: var(--gold);
        background: linear-gradient(90deg, rgba(232, 201, 119, .14), rgba(91, 140, 255, .08));
        box-shadow: inset 3px 0 0 var(--gold), 0 0 0 1px rgba(232, 201, 119, .08);
    }
    .yao-line.moving .symbol { color: #79a2ff; }
    .section-intro { margin: 1.4rem 0 .9rem; }
    .section-intro h2 { margin: 0 0 .35rem; font-size: 1.55rem; }
    .section-intro p { margin: 0; color: var(--muted); }
    .form-note {
        color: #8f97aa;
        font-size: .82rem;
        line-height: 1.65;
        padding-top: .4rem;
    }
    .chart-summary { color: #d9dce5; line-height: 1.75; }
    .chart-summary strong { color: var(--gold-strong); }
    .audit-label {
        color: var(--gold);
        font-size: .72rem;
        font-weight: 800;
        letter-spacing: .13em;
        text-transform: uppercase;
    }
    *:focus-visible { outline: 3px solid var(--blue) !important; outline-offset: 2px !important; }
    @media (max-width: 760px) {
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"] {
            box-sizing: border-box;
            min-width: 0 !important;
            width: 100vw !important;
            max-width: 100vw !important;
            overflow-x: hidden !important;
        }
        [data-testid="stAppViewContainer"] > .main .block-container,
        [data-testid="stMainBlockContainer"] {
            max-width: 100% !important;
            padding: 1.2rem .9rem 4rem !important;
            overflow-x: hidden;
        }
        [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; }
        [data-testid="stColumn"] {
            flex: 1 1 100% !important;
            min-width: 0 !important;
            width: 100% !important;
        }
        .ui-hero { padding-top: .5rem; }
        .ui-hero h1 { font-size: 2.25rem; }
        .ui-eyebrow { max-width: 100%; overflow-wrap: anywhere; }
        .ui-hero .hero-copy { max-width: 100%; overflow-wrap: anywhere; }
        .result-head { align-items: flex-start; flex-direction: column; }
        .yao-line { grid-template-columns: 2.2rem 3.2rem 1fr; }
        .yao-line .state { grid-column: 2 / -1; text-align: left; }
        [data-testid="stMetric"] { padding: .7rem .75rem; }
    }
    </style>
    <section class="ui-hero">
      <div class="ui-eyebrow">DETERMINISTIC DIVINATION ENGINE</div>
      <h1>数智易学</h1>
      <p class="hero-copy">让盘面先确定，让解释后发生。原典、规则与每次推演都有据可查。</p>
      <div class="hero-chips">
        <span>64 卦规则库</span><span>真太阳时</span><span>六爻与奇门</span><span>全链路审计</span>
      </div>
    </section>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_tracker() -> AuditTracker:
    return AuditTracker()


def get_deepseek_key() -> str:
    value = os.getenv("DEEPSEEK_API_KEY", "")
    try:
        value = st.secrets.get("DEEPSEEK_API_KEY", value)
    except FileNotFoundError:
        pass
    return value


def local_datetime(date_value: dt.date, time_value: dt.time, offset: float) -> dt.datetime:
    return dt.datetime.combine(
        date_value, time_value, tzinfo=dt.timezone(dt.timedelta(hours=offset))
    )


def render_section_intro(kicker: str, title: str, description: str) -> None:
    st.markdown(
        f"""
        <section class="section-intro">
          <div class="section-kicker">{html.escape(kicker)}</div>
          <h2>{html.escape(title)}</h2>
          <p>{html.escape(description)}</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_sixyao_lines(paipan: dict, focus: int | None) -> None:
    position_labels = {6: "上爻", 5: "五爻", 4: "四爻", 3: "三爻", 2: "二爻", 1: "初爻"}
    rendered_lines = []
    for number in range(6, 0, -1):
        line = paipan["lines_detail"][str(number)]
        marker = "⚊" if paipan["hexagram_code"][number - 1] == "1" else "⚋"
        state_tags = list(line["state_tags"])
        if line["is_shi"]:
            state_tags.insert(0, "世")
        elif line["is_ying"]:
            state_tags.insert(0, "应")
        tags = " · ".join(state_tags) or "静爻"
        css_classes = ["yao-line"]
        if focus == number:
            css_classes.append("focus")
        if line["is_moving"]:
            css_classes.append("moving")
        rendered_lines.append(
            f'<div class="{" ".join(css_classes)}">'
            f'<span class="symbol">{marker}</span>'
            f'<span class="position">{position_labels[number]}</span>'
            f'<span class="detail">{html.escape(line["najia"])} · {html.escape(line["relative"])}</span>'
            f'<span class="state">{html.escape(tags)}{" · 核心焦点" if focus == number else ""}</span>'
            '</div>'
        )
    st.markdown(f"<div class='yao-stack'>{''.join(rendered_lines)}</div>", unsafe_allow_html=True)


def render_qimen_chart(chart: dict) -> None:
    st.success(
        f"{chart['solar_term']} · {chart['yuan']} · {chart['dun']}{chart['ju_number']}局 · "
        f"值符 {chart['zhi_fu']['star']} · 值使 {chart['zhi_shi']['gate']}"
    )
    palaces = {item["position"]: item for item in chart["palaces"]}
    for row in ((4, 9, 2), (3, 5, 7), (8, 1, 6)):
        columns = st.columns(3)
        for column, position in zip(columns, row):
            palace = palaces[position]
            with column.container(border=True):
                st.markdown(f"**{palace['name']}{position}宫**")
                st.caption(
                    f"神：{palace['deity'] or '—'}　星：{'/'.join(palace['stars'])}　门：{palace['gate'] or '—'}"
                )
                st.write(
                    f"天盘：{'/'.join(palace['heaven_stems'])}　地盘：{'/'.join(palace['earth_stems'])}"
                )
                if palace["is_void"]:
                    st.warning("旬空")
    with st.expander("规则约定与完整结构"):
        st.write(chart["school"], chart["ju_method"], chart["middle_palace_rule"])
        st.json(chart)


def save_qimen_audit(chart: dict, query: str, raw_input: dict) -> str:
    run_id = str(uuid.uuid4())
    get_tracker().save_run_record(
        run_id,
        query,
        raw_input,
        chart,
        {"run_id": run_id, "chart_type": chart["chart_type"], "chart": chart},
        "已生成确定性奇门盘；奇门文本解读尚未调用 DeepSeek。",
        [{"check": "qimen_structure", "status": "passed"}],
        {"provider": "none", "mode": "deterministic"},
    )
    return run_id


tracker = get_tracker()
with st.sidebar:
    st.markdown('<div class="sidebar-title">时空坐标</div>', unsafe_allow_html=True)
    longitude = st.number_input("经度", -180.0, 180.0, 120.15, 0.01)
    latitude = st.number_input("纬度", -90.0, 90.0, 30.28, 0.01)
    timezone_offset = st.number_input("UTC 时区偏移", -12.0, 14.0, 8.0, 0.5)
    st.caption("当前支持手动精确经纬度；历法按节气时刻与真太阳时计算。")
    llm_status = "DeepSeek 已连接" if get_deepseek_key() else "离线确定性模式"
    st.markdown(f'<div class="status-pill">{llm_status}</div>', unsafe_allow_html=True)


sixyao_tab, asking_tab, lifelong_tab, history_tab = st.tabs(
    ["六爻问事", "问事奇门", "终身奇门", "历史复盘"]
)

with sixyao_tab:
    casting_input = {
        "longitude": longitude,
        "latitude": latitude,
        "timezone_offset_hours": timezone_offset,
    }
    render_section_intro(
        "CAST A HEXAGRAM",
        "六爻问事",
        "先固定问题与起卦数据，再生成可复核的盘面和受约束解读。",
    )
    with st.container(border=True):
        form_left, form_right = st.columns([1.05, 1], gap="large")
        with form_left:
            st.markdown('<div class="audit-label">01 · 明确问题</div>', unsafe_allow_html=True)
            query = st.text_area(
                "占问事项",
                placeholder="例如：未来三个月事业推进的关键节奏是什么？",
                key="sixyao_query",
                height=132,
            )
            cast_mode = st.radio("起卦方式", ["手摇卦", "数字起卦"], horizontal=True)
            st.markdown(
                '<div class="form-note">建议只问一件事，并写明时间范围。系统会保存规则版本与运行轨迹，便于事后复盘。</div>',
                unsafe_allow_html=True,
            )
        with form_right:
            st.markdown('<div class="audit-label">02 · 录入卦象</div>', unsafe_allow_html=True)
            if cast_mode == "手摇卦":
                labels = ("上爻（最上）", "五爻", "四爻", "三爻", "二爻", "初爻（最下）")
                format_line = {6: "老阴 ⚋×", 7: "少阳 ⚊", 8: "少阴 ⚋", 9: "老阳 ⚊○"}
                lines = []
                for row_start in range(0, 6, 2):
                    line_columns = st.columns(2)
                    for column_index, label in enumerate(labels[row_start:row_start + 2]):
                        index = row_start + column_index
                        lines.append(
                            line_columns[column_index].selectbox(
                                label,
                                [8, 7, 6, 9],
                                format_func=format_line.get,
                                key=f"manual_line_{index}",
                            )
                        )
                casting_input.update(mode="manual", lines=lines)
            else:
                number_columns = st.columns(3)
                numbers = [
                    number_columns[0].number_input("上卦数", 0, 999, 123),
                    number_columns[1].number_input("下卦数", 0, 999, 456),
                    number_columns[2].number_input("动爻数", 0, 999, 789),
                ]
                casting_input.update(mode="number", numbers=numbers)

        if st.button("开始排盘并生成解读", type="primary", use_container_width=True):
            try:
                with st.spinner("正在排盘、校验并生成受约束解读…"):
                    st.session_state["sixyao_result"] = run_divination_pipeline(
                        query,
                        casting_input,
                        interpreter=LLMInterpreter(api_key=get_deepseek_key()),
                        tracker=tracker,
                    )
            except (ValueError, CastingError, AstronomyCalculationError, PaipanError,
                    GuardrailValidationError, LLMInterpretationError) as error:
                st.error(f"系统已中止：{error}")

    result = st.session_state.get("sixyao_result")
    if result:
        paipan = result["paipan"]
        calendar = result["calendar"]
        changed_name = (paipan.get("changed_hexagram") or {}).get("name") or "无变卦"
        st.markdown(
            f"""
            <section class="result-head">
              <div><div class="section-kicker">RESULT OVERVIEW</div><h2>盘面总览</h2></div>
              <p>Run ID · {html.escape(result['run_id'][:8])}</p>
            </section>
            """,
            unsafe_allow_html=True,
        )
        columns = st.columns(4)
        columns[0].metric("本卦", paipan["name"])
        columns[1].metric("变卦", changed_name)
        columns[2].metric("日柱", calendar["day_ganzhi"])
        columns[3].metric("旬空", "、".join(calendar["xunkong"]))
        focus = paipan["focus_analysis"]["primary_focus"]
        chart_left, chart_right = st.columns([.72, 1.28], gap="large")
        with chart_left:
            with st.container(border=True):
                st.markdown('<div class="audit-label">核心判断</div>', unsafe_allow_html=True)
                focus_label = f"第 {focus} 爻" if focus else "用九／用六"
                st.markdown(
                    f"""
                    <div class="focus-summary">
                      <strong>{html.escape(focus_label)}</strong><br>
                      {html.escape(paipan['focus_analysis']['type'])}
                    </div>
                    <div class="chart-summary">
                      <strong>{html.escape(paipan['name'])}</strong> · {html.escape(paipan['palace'])}<br>
                      {html.escape(paipan['focus_analysis']['description'])}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        with chart_right:
            with st.container(border=True):
                st.markdown('<div class="audit-label">六爻盘面 · 上爻在上</div>', unsafe_allow_html=True)
                render_sixyao_lines(paipan, focus)

        report_left, audit_right = st.columns([1.6, .7], gap="large")
        with report_left:
            with st.container(border=True):
                st.markdown('<div class="audit-label">RULE-GROUNDED INTERPRETATION</div>', unsafe_allow_html=True)
                st.markdown("### 解读报告")
                st.markdown(result["llm_response"])
        with audit_right:
            with st.container(border=True):
                st.markdown('<div class="audit-label">证据与留痕</div>', unsafe_allow_html=True)
                if result["llm_metadata"]["mode"] == "offline":
                    st.info("当前为离线模式，仅展示确定性盘面与已核验原典。")
                else:
                    st.success("DeepSeek 解读已生成。")
                with st.expander("原典与排盘数据"):
                    st.write("卦辞：", paipan["judgement"])
                    st.json(paipan)
                with st.expander("规则校验轨迹"):
                    st.json(result["guardrail_log"])
                st.caption(f"完整 Run ID：{result['run_id']}")

with asking_tab:
    render_section_intro(
        "ASKING QIMEN",
        "问事奇门",
        "以提问时刻起局，展示值符、值使与九宫结构。",
    )
    asking_query = st.text_input("问事主题", key="qimen_query")
    category = st.selectbox("事项类别", ["综合", "事业", "合作", "出行", "学业", "关系"])
    use_now = st.checkbox("使用当前时间", value=True)
    if use_now:
        asking_time = dt.datetime.now(dt.timezone.utc).astimezone(
            dt.timezone(dt.timedelta(hours=timezone_offset))
        )
    else:
        date_value = st.date_input("起局日期", key="qimen_date")
        time_value = st.time_input("起局时间", key="qimen_time")
        asking_time = local_datetime(date_value, time_value, timezone_offset)
    if st.button("生成问事奇门九宫盘", use_container_width=True):
        if not asking_query.strip():
            st.warning("请先填写问事主题。")
        else:
            try:
                chart = QimenService.build_asking_chart(
                    asking_time, longitude, latitude, timezone_offset, category
                )
                run_id = save_qimen_audit(
                    chart,
                    asking_query,
                    {"datetime": asking_time.isoformat(), "longitude": longitude, "latitude": latitude},
                )
                st.session_state["asking_result"] = (run_id, chart)
            except (AstronomyCalculationError, QimenCalculationError) as error:
                st.error(f"奇门排盘中止：{error}")
    if "asking_result" in st.session_state:
        run_id, chart = st.session_state["asking_result"]
        render_qimen_chart(chart)
        st.caption(f"Run ID：{run_id}")

with lifelong_tab:
    render_section_intro(
        "LIFELONG QIMEN",
        "终身奇门",
        "以出生时空为基准，生成命盘、大运与流运结构。",
    )
    st.warning("出生时间与性别仅用于本地确定性计算；请自行评估隐私后再提交。")
    columns = st.columns(3)
    birth_date = columns[0].date_input("出生日期", value=dt.date(1990, 1, 1))
    birth_time = columns[1].time_input("出生时间", value=dt.time(12, 0))
    gender = columns[2].selectbox("性别（用于大运顺逆）", ["男", "女"])
    flow_year = st.number_input("流年起始年份", 1900, 2200, dt.date.today().year)
    if st.button("生成终身奇门结构", use_container_width=True):
        try:
            birth_datetime = local_datetime(birth_date, birth_time, timezone_offset)
            chart = QimenService.build_lifelong_chart(
                birth_datetime, longitude, latitude, gender, int(flow_year), timezone_offset
            )
            run_id = save_qimen_audit(
                chart,
                "终身奇门结构",
                {"birth_datetime": birth_datetime.isoformat(), "longitude": longitude,
                 "latitude": latitude, "gender": gender, "flow_year": int(flow_year)},
            )
            st.session_state["lifelong_result"] = (run_id, chart)
        except (AstronomyCalculationError, QimenCalculationError) as error:
            st.error(f"终身盘计算中止：{error}")
    if "lifelong_result" in st.session_state:
        run_id, chart = st.session_state["lifelong_result"]
        columns = st.columns(3)
        columns[0].metric("起运年龄", f"{chart['start_age']} 岁")
        columns[1].metric("大运方向", chart["luck_direction"])
        columns[2].metric("目标节令", chart["target_term"]["name"])
        render_qimen_chart(chart["birth_chart"])
        st.markdown("#### 大运与流运结构")
        st.dataframe(chart["luck_cycles"], use_container_width=True, hide_index=True)
        st.json({
            "五行显性分布": chart["five_element_distribution"],
            "流年": chart["annual_cycles"],
            "流月": chart["monthly_cycles"],
        })
        st.caption(f"Run ID：{run_id}")

with history_tab:
    render_section_intro(
        "AUDIT HISTORY",
        "历史复盘",
        "把当时的盘面、解读与后来发生的事实放回同一条记录。",
    )
    st.caption("审计记录保存在 SQLite；Streamlit Cloud 的本地磁盘重启后可能重置。")
    history = tracker.list_history(limit=30)
    if not history:
        st.info("暂无历史记录。")
    label_to_status = {"尚无结果": "pending", "应验": "verified", "未应验": "unverified", "部分应验": "partial"}
    status_to_label = {value: key for key, value in label_to_status.items()}
    for item in history:
        with st.expander(f"{item['created_at']} · {item['user_query']} · {item['run_id'][:8]}"):
            st.markdown(item["llm_response"])
            current = status_to_label[item["feedback"]["status"]]
            status = st.selectbox(
                "事后验证", list(label_to_status), index=list(label_to_status).index(current),
                key=f"feedback_status_{item['run_id']}",
            )
            notes = st.text_area(
                "实际事件与时间", value=item["feedback"]["notes"],
                key=f"feedback_notes_{item['run_id']}",
            )
            if st.button("保存反馈", key=f"feedback_save_{item['run_id']}"):
                tracker.record_user_feedback(item["run_id"], label_to_status[status], notes)
                st.success("反馈已保存。")
