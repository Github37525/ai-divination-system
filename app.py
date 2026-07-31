"""Streamlit：六爻、问事奇门、终身奇门与历史复盘。"""
from __future__ import annotations

import datetime as dt
import base64
import html
import json
import os
import secrets
import uuid
from pathlib import Path

import streamlit as st

from engine.astronomy import AstronomyCalculationError
from engine.caster import CastingError
from engine.conversation import (
    append_session_turn,
    session_memory_is_active,
    start_session_memory,
)
from engine.guardrails import GuardrailValidationError
from engine.llm_interpreter import LLMInterpretationError, LLMInterpreter
from engine.paipan import PaipanError
from engine.qimen import QimenCalculationError, QimenService
from engine.qimen_plain_language import summarize_asking_chart, summarize_lifelong_chart
from engine.tracker import AuditTracker
from main import (
    restore_divination_result,
    retry_divination_interpretation,
    run_divination_pipeline,
)


def render_cyber_hero() -> None:
    image_path = Path(__file__).resolve().parent / "assets" / "yi-cyber-hero.webp"
    image_data = base64.b64encode(image_path.read_bytes()).decode("ascii")
    st.iframe(
        f"""
        <!doctype html>
        <html lang="zh-CN">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width,initial-scale=1">
          <style>
            * {{ box-sizing: border-box; }}
            html, body {{ margin: 0; background: transparent; color: #f4efdf; }}
            body {{ font-family: Inter, "Noto Sans SC", "Microsoft YaHei", sans-serif; }}
            .hero {{
              position: relative; height: 318px; overflow: hidden; border-radius: 14px;
              background: #080c18; isolation: isolate;
            }}
            .hero::after {{
              content: ""; position: absolute; inset: 0; z-index: -1;
              background: linear-gradient(90deg, rgba(5,8,16,.98) 0%, rgba(5,8,16,.89) 36%,
                rgba(5,8,16,.28) 68%, rgba(5,8,16,.06) 100%);
            }}
            .hero-image {{
              position: absolute; inset: 0; z-index: -2; width: 100%; height: 100%;
              object-fit: cover; object-position: center; transform-origin: 70% 50%;
              will-change: transform;
            }}
            .content {{
              position: relative; display: flex; flex-direction: column; justify-content: center;
              width: min(650px, 64%); height: 100%; padding: 32px 38px;
            }}
            .system-state {{
              display: flex; align-items: center; gap: 9px; color: #e6ca78;
              font-size: 12px; font-weight: 800; letter-spacing: .13em;
            }}
            .signal {{ width: 7px; height: 7px; border-radius: 50%; background: #6fa0ff; box-shadow: 0 0 12px #6fa0ff; }}
            h1 {{
              margin: 13px 0 7px; font-family: "Noto Serif SC", "Songti SC", STSong, serif;
              color: #fff9e8; font-size: 48px; line-height: 1.08; letter-spacing: .04em; font-weight: 850;
            }}
            .subtitle {{ margin: 0; color: #d1d5df; font-size: 15px; line-height: 1.75; max-width: 38em; }}
            .protocols {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 20px; }}
            .protocols span {{
              padding: 6px 10px; border-radius: 999px; background: rgba(8,13,27,.68);
              color: #d7dbe5; font-size: 11px; border: 1px solid rgba(226,196,111,.28);
            }}
            .protocols strong {{ color: #e6ca78; font-weight: 800; }}
            @media (max-width: 720px) {{
              .hero {{ height: 300px; }}
              .content {{ width: 88%; padding: 25px 24px; }}
              h1 {{ font-size: 37px; }}
              .subtitle {{ font-size: 14px; }}
              .hero-image {{ object-position: 64% center; opacity: .62; }}
            }}
            @media (prefers-reduced-motion: reduce) {{ .hero-image {{ will-change: auto; }} }}
          </style>
        </head>
        <body>
          <section class="hero" aria-label="数智易学产品介绍">
            <img class="hero-image" src="data:image/webp;base64,{image_data}" alt="深色青铜易经时空仪器">
            <div class="content">
              <div class="system-state"><span class="signal"></span>RULE ENGINE · ONLINE</div>
              <h1>数智易学</h1>
              <p class="subtitle">让盘面先确定，让解释后发生。历法、卦象、原典与每次推演均可回看、核验与复盘。</p>
              <div class="protocols" aria-label="系统能力">
                <span><strong>64</strong> 卦规则库</span>
                <span><strong>384</strong> 爻原典</span>
                <span>真太阳时</span>
                <span>全链路审计</span>
              </div>
            </div>
          </section>
          <script src="https://cdn.jsdelivr.net/npm/gsap@3.13.0/dist/gsap.min.js"></script>
          <script>
            if (window.gsap) {{
              const media = gsap.matchMedia();
              media.add("(prefers-reduced-motion: no-preference)", () => {{
                gsap.fromTo(".hero-image", {{ scale: 1.01, x: 0 }}, {{
                  scale: 1.035, x: -5, duration: 9, ease: "sine.inOut", repeat: -1, yoyo: true
                }});
                gsap.from(".content > *", {{
                  y: 12, autoAlpha: .25, duration: .7, stagger: .08, ease: "power3.out"
                }});
                gsap.to(".signal", {{ autoAlpha: .38, duration: 1.1, repeat: -1, yoyo: true, ease: "sine.inOut" }});
              }});
            }}
          </script>
        </body>
        </html>
        """,
        height=326,
        width="stretch",
        tab_index=-1,
    )


st.set_page_config(page_title="数智易学", page_icon="☯️", layout="wide")
st.markdown(
    """
    <style>
    :root {
        --ink: #f2ecdc;
        --muted: #adb5c6;
        --night: #050711;
        --surface: #0a0f1d;
        --surface-raised: #0e1527;
        --line: rgba(205, 178, 105, .24);
        --gold: #d9bd6e;
        --gold-strong: #ebcf7c;
        --blue: #6f9fff;
        --success: #85d5aa;
    }
    .stApp {
        background:
            radial-gradient(circle at 84% 4%, rgba(56, 81, 148, .18), transparent 30rem),
            radial-gradient(circle at 9% 78%, rgba(103, 75, 36, .10), transparent 30rem),
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
        background: #080c17;
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
    iframe { border: 0; }
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
        border: 1px solid rgba(205, 178, 105, .22);
        border-radius: 10px;
        padding: .7rem .8rem;
        margin-top: .7rem;
        color: var(--gold);
        background: rgba(217, 189, 110, .055);
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
        background: rgba(217, 189, 110, .055);
    }
    .stTabs [data-baseweb="tab-highlight"] { background-color: var(--blue) !important; }
    [data-testid="stTab"] { color: #b8bdca; }
    [data-testid="stTab"][aria-selected="true"] {
        color: var(--gold-strong) !important;
        background: rgba(217, 189, 110, .055);
    }
    .react-aria-SelectionIndicator { background-color: var(--blue) !important; }
    [data-testid="stRadioOption"][data-selected="true"] > div > div > div:nth-child(1) {
        background: var(--blue) !important;
    }
    [data-testid="stRadioOption"][data-selected="true"] > div > div > div:nth-child(1) > div {
        background: #ffffff !important;
    }
    [data-testid="stVerticalBlockBorderWrapper"] {
        background: rgba(10, 15, 29, .92);
        border-color: var(--line) !important;
        border-radius: 14px !important;
        box-shadow: none;
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
    [data-testid="stTextArea"] textarea::placeholder { color: #9aa2b5; }
    .stButton > button {
        border: 1px solid rgba(134, 154, 194, .32) !important;
        border-radius: 10px !important;
        background: #10182a !important;
        color: #dbe2ef !important;
        font-weight: 750 !important;
        min-height: 2.8rem;
        box-shadow: none;
        transition: transform .18s cubic-bezier(.22,1,.36,1), background-color .18s ease;
    }
    [data-testid="stBaseButton-primary"] {
        border-color: rgba(217, 189, 110, .68) !important;
        background: #d6b964 !important;
        color: #10131c !important;
        font-weight: 850 !important;
    }
    .stButton > button:hover { background: #16213a !important; transform: translateY(-1px); }
    [data-testid="stBaseButton-primary"]:hover { background: #e0c675 !important; }
    .stButton > button:active { transform: translateY(0); }
    [data-testid="stMetric"] {
        background: rgba(12, 18, 34, .94);
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
        border: 1px solid rgba(217, 189, 110, .32);
        border-radius: 11px;
        background: rgba(217, 189, 110, .055);
        padding: .72rem .82rem;
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
        background: rgba(217, 189, 110, .095);
        box-shadow: 0 0 0 1px rgba(217, 189, 110, .08);
    }
    .yao-line.moving .symbol { color: #79a2ff; }
    .section-intro {
        display: flex; align-items: end; justify-content: space-between; gap: 1rem;
        margin: 1.6rem 0 1rem; padding-bottom: .8rem; border-bottom: 1px solid rgba(205,178,105,.16);
    }
    .section-intro h2 { margin: 0 0 .35rem; font-size: 1.55rem; }
    .section-intro p { margin: 0; color: var(--muted); }
    .section-kicker {
        flex: none; color: #8daef5; font-size: .72rem; font-weight: 750;
        letter-spacing: .09em; padding: .32rem .55rem; border-radius: 999px;
        background: rgba(91,140,255,.09);
    }
    .form-note {
        color: #8f97aa;
        font-size: .82rem;
        line-height: 1.65;
        padding-top: .4rem;
    }
    .chart-summary { color: #d9dce5; line-height: 1.75; }
    .chart-summary strong { color: var(--gold-strong); }
    .plain-conclusion {
        margin: .7rem 0 1rem;
        padding: 1rem 1.05rem;
        border: 1px solid rgba(217, 189, 110, .32);
        border-radius: 12px;
        background: rgba(217, 189, 110, .075);
        color: var(--ink);
        font-family: "Noto Serif SC", "Songti SC", serif;
        font-size: 1.12rem;
        font-weight: 750;
        line-height: 1.75;
    }
    .audit-label {
        color: var(--gold);
        font-size: .72rem;
        font-weight: 800;
        letter-spacing: .06em;
    }
    .coin-rule {
        margin: .65rem 0 .9rem;
        padding: .72rem .85rem;
        border: 1px solid rgba(232, 201, 119, .18);
        border-radius: 10px;
        background: rgba(232, 201, 119, .045);
        color: #b8becd;
        font-size: .82rem;
        line-height: 1.65;
    }
    .coin-rule strong { color: var(--gold-strong); }
    .throw-grid { display: grid; gap: .55rem; margin: .8rem 0; }
    .throw-card {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: .75rem;
        padding: .7rem .8rem;
        border: 1px solid rgba(196, 168, 103, .16);
        border-radius: 10px;
        background: rgba(7, 10, 22, .68);
    }
    .throw-meta { display: grid; gap: .16rem; }
    .throw-meta span { color: #8f97aa; font-size: .76rem; }
    .throw-meta strong { color: var(--ink); font-size: .95rem; }
    .coin-faces { display: flex; gap: .35rem; }
    .coin-face {
        display: grid;
        place-items: center;
        width: 2.15rem;
        height: 2.15rem;
        border: 1px solid rgba(232, 201, 119, .55);
        border-radius: 999px;
        color: #17130a;
        background: linear-gradient(145deg, #f0d888, #b88c36);
        font-size: .78rem;
        font-weight: 900;
        box-shadow: inset 0 0 0 3px rgba(255, 245, 195, .18);
    }
    .coin-face.reverse {
        color: #d8deee;
        border-color: #667291;
        background: linear-gradient(145deg, #39445f, #171d30);
        box-shadow: inset 0 0 0 3px rgba(255, 255, 255, .035);
    }
    .throw-card.latest {
        border-color: var(--gold);
        background: rgba(217, 189, 110, .075);
    }
    .throw-card.latest .coin-face { animation: coin-reveal .72s cubic-bezier(.2,.8,.2,1); }
    .throw-card.latest .coin-face:nth-child(2) { animation-delay: .08s; }
    .throw-card.latest .coin-face:nth-child(3) { animation-delay: .16s; }
    .source-legend {
        display: flex;
        flex-wrap: wrap;
        gap: .45rem;
        margin: .55rem 0 1rem;
    }
    .source-badge {
        border-radius: 999px;
        padding: .3rem .62rem;
        background: rgba(91, 140, 255, .11);
        color: #c9d8ff;
        font-size: .76rem;
        font-weight: 750;
    }
    .source-badge.classic { background: rgba(232, 201, 119, .11); color: var(--gold-strong); }
    .source-badge.local { background: rgba(92, 184, 136, .12); color: #aee5c7; }
    .source-badge.ai { background: rgba(166, 112, 224, .13); color: #dbc4f6; }
    .relation-list { display: grid; gap: .2rem; margin: .4rem 0 1rem; }
    .relation-row {
        display: grid;
        grid-template-columns: 4.4rem minmax(8rem, 1fr) minmax(12rem, 1.6fr);
        gap: .8rem;
        align-items: baseline;
        padding: .7rem .1rem;
        border-bottom: 1px solid rgba(196, 168, 103, .14);
    }
    .relation-row:last-child { border-bottom: 0; }
    .relation-label { color: var(--gold); font-weight: 800; }
    .relation-name { color: var(--ink); font-weight: 750; }
    .relation-meaning { color: #b9bfce; font-size: .86rem; }
    .conversation-turn {
        margin: .65rem 0;
        padding: .8rem .9rem;
        border-radius: 12px;
        background: rgba(91, 140, 255, .075);
    }
    .conversation-turn strong { color: #c9d8ff; }
    .conversation-answer { color: #d8dce6; line-height: 1.7; margin-top: .35rem; }
    @keyframes coin-reveal {
        0% { opacity: 0; transform: translateY(-1.2rem) rotateY(0deg) scale(.78); }
        70% { opacity: 1; transform: translateY(.12rem) rotateY(540deg) scale(1.05); }
        100% { opacity: 1; transform: translateY(0) rotateY(720deg) scale(1); }
    }
    @media (prefers-reduced-motion: reduce) {
        .throw-card.latest .coin-face { animation: none; }
        .stButton > button:hover { transform: none; }
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
        .relation-row { grid-template-columns: 3.8rem 1fr; }
        .relation-meaning { grid-column: 2; }
        [data-testid="stMetric"] { padding: .7rem .75rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)
render_cyber_hero()


COIN_LINE_LABELS = {
    6: "三反 · 老阴（动爻）",
    7: "一正二反 · 少阳（静爻）",
    8: "二正一反 · 少阴（静爻）",
    9: "三正 · 老阳（动爻）",
}
LINE_POSITION_LABELS = {1: "初爻", 2: "二爻", 3: "三爻", 4: "四爻", 5: "五爻", 6: "上爻"}


@st.cache_resource
def get_tracker() -> AuditTracker:
    audit = AuditTracker()
    audit.purge_expired()
    return audit


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


def activate_sixyao_result(result: dict, followups: list[dict] | None = None) -> None:
    """把一条六爻结果设为当前短期会话，不创建跨会话用户画像。"""
    st.session_state["sixyao_result"] = result
    memory = start_session_memory(result["run_id"], result["ai_context"]["user_query"])
    restored_turns = [
        {
            "question": item["user_question"],
            "answer": item["response"],
            "intent": item["intent"],
        }
        for item in (followups or [])[-8:]
    ]
    memory["turns"] = restored_turns
    st.session_state["sixyao_conversation_memory"] = memory
    st.session_state["sixyao_followups"] = list(followups or [])


def run_and_activate_sixyao(query: str, casting_input: dict, tracker: AuditTracker) -> None:
    with st.spinner("正在排盘、校验并生成受约束解读…"):
        result = run_divination_pipeline(
            query,
            casting_input,
            interpreter=LLMInterpreter(api_key=get_deepseek_key()),
            tracker=tracker,
        )
    activate_sixyao_result(result)


def record_as_markdown(record: dict) -> str:
    """生成可阅读、可离线保存的单次完整报告。"""
    feedback = record.get("feedback", {})
    return "\n".join(
        (
            f"# 数智易学运行报告 · {record['run_id'][:8]}",
            "",
            f"- 完整 Run ID：`{record['run_id']}`",
            f"- 创建时间：{record['created_at']}",
            f"- 占问事项：{record['user_query']}",
            f"- 事后验证：{feedback.get('status', 'pending')}",
            f"- 验证说明：{feedback.get('notes') or '无'}",
            "",
            "## 解读",
            "",
            record["llm_response"],
            "",
            "## 完整审计数据",
            "",
            "```json",
            json.dumps(record, ensure_ascii=False, indent=2),
            "```",
        )
    )


def render_section_intro(kicker: str, title: str, description: str) -> None:
    st.markdown(
        f"""
        <section class="section-intro">
          <div><h2>{html.escape(title)}</h2><p>{html.escape(description)}</p></div>
          <span class="section-kicker">{html.escape(kicker)}</span>
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


def render_virtual_throws(throws: list[dict]) -> None:
    cards = []
    for index, throw in enumerate(throws, start=1):
        coin_faces = "".join(
            f'<span class="coin-face{" reverse" if face == "反" else ""}" '
            f'aria-label="{face}面">{face}</span>'
            for face in throw["coins"]
        )
        latest_class = " latest" if index == len(throws) else ""
        cards.append(
            f'<div class="throw-card{latest_class}">'
            f'<div class="throw-meta"><span>第 {index} 摇 · {LINE_POSITION_LABELS[index]}</span>'
            f'<strong>{html.escape(COIN_LINE_LABELS[throw["value"]])}</strong></div>'
            f'<div class="coin-faces" role="img" aria-label="本次结果：{"、".join(throw["coins"])}">'
            f'{coin_faces}</div></div>'
        )
    if cards:
        st.markdown(f'<div class="throw-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def render_plain_conclusion(summary: dict) -> None:
    with st.container(border=True):
        st.markdown(
            f'<div class="audit-label">{html.escape(summary["label"])}</div>',
            unsafe_allow_html=True,
        )
        st.markdown("### 一眼结论")
        st.markdown(
            f'<div class="plain-conclusion">{html.escape(summary["headline"])}</div>',
            unsafe_allow_html=True,
        )
        action_column, risk_column = st.columns(2, gap="large")
        with action_column:
            st.markdown("#### 现在怎么做")
            for action in summary["actions"]:
                st.markdown(f"- {action}")
        with risk_column:
            st.markdown("#### 需要留意")
            for risk in summary["risks"]:
                st.markdown(f"- {risk}")
        with st.expander("这条结论是怎么得出的"):
            for basis in summary["basis"]:
                st.markdown(f"- {basis}")
            st.caption(summary["disclaimer"])


def render_provenance(result: dict) -> None:
    metadata = result.get("llm_metadata", {})
    ai_label = "AI 生成解释" if metadata.get("ai_generated") else "未使用 AI 生成"
    ai_class = "ai" if metadata.get("ai_generated") else "local"
    st.markdown(
        '<div class="source-legend" aria-label="内容来源分层">'
        '<span class="source-badge">确定性计算</span>'
        '<span class="source-badge classic">已核验原典</span>'
        '<span class="source-badge local">本地规则转译</span>'
        f'<span class="source-badge {ai_class}">{html.escape(ai_label)}</span>'
        '</div>',
        unsafe_allow_html=True,
    )


def render_related_hexagrams(paipan: dict) -> None:
    relations = paipan["related_hexagrams"]
    rows = []
    for relation in ("original", "changed", "mutual", "reversed", "opposite"):
        item = relations[relation]
        if item is None:
            label, name, meaning = "变卦", "无变卦", "本局无动爻，以本卦整体为主"
        else:
            label, name, meaning = item["label"], f"{item['symbol']} {item['name']}", item["meaning"]
            if relation != "original" and item["is_same_as_original"]:
                meaning += "；与本卦相同"
        rows.append(
            '<div class="relation-row">'
            f'<span class="relation-label">{html.escape(label)}</span>'
            f'<span class="relation-name">{html.escape(name)}</span>'
            f'<span class="relation-meaning">{html.escape(meaning)}</span>'
            '</div>'
        )
    with st.expander("本、变、互、综、错五卦关系", expanded=True):
        st.markdown('<div class="relation-list">' + "".join(rows) + '</div>', unsafe_allow_html=True)
        st.caption("五卦均由六爻编码确定性计算，再从同一份已核验六十四卦数据库映射；模型不参与卦象计算。")


def process_follow_up(result: dict, question: str, tracker: AuditTracker) -> None:
    memory = st.session_state.get("sixyao_conversation_memory")
    if (
        not session_memory_is_active(memory)
        or memory.get("active_run_id") != result["run_id"]
    ):
        memory = start_session_memory(result["run_id"], result["ai_context"]["user_query"])
    interpreter = LLMInterpreter(api_key=get_deepseek_key())
    with st.spinner("正在依据当前盘面回答…"):
        follow_up = interpreter.answer_follow_up(
            result["ai_context"],
            question,
            result["llm_response"],
            memory.get("turns", []),
        )
    tracker.save_follow_up(
        result["run_id"],
        question,
        follow_up["intent"],
        follow_up["answer"],
        interpreter.last_metadata,
    )
    memory = append_session_turn(
        memory, question, follow_up["answer"], follow_up["intent"]
    )
    st.session_state["sixyao_conversation_memory"] = memory
    st.session_state.setdefault("sixyao_followups", []).append(
        {
            "user_question": question,
            "intent": follow_up["intent"],
            "response": follow_up["answer"],
            "llm_metadata": dict(interpreter.last_metadata),
        }
    )


def render_follow_up(result: dict, tracker: AuditTracker) -> None:
    st.markdown("### 围绕本次结果继续问")
    st.caption("追问只解释当前 Run ID 的已核验盘面；30 分钟无操作后会话上下文自动失效。")
    quick_prompts = {
        "为什么这样判断": "这条结论为什么这样判断？",
        "现在怎么做": "结合当前盘面，现在可以怎么做？",
        "需要留意什么": "当前最需要留意的风险是什么？",
        "只讲核心爻": "只解释这次的核心爻。",
        "再说得直白些": "请用更直白的话再说一次。",
    }
    quick_question = None
    for column, (label, question) in zip(st.columns(5), quick_prompts.items()):
        if column.button(label, key=f"followup_{result['run_id']}_{label}", use_container_width=True):
            quick_question = question
    custom_question = st.text_input(
        "自定义追问",
        placeholder="例如：这个风险具体对应盘面的哪一项？",
        key=f"custom_followup_{result['run_id']}",
    )
    if st.button("发送追问", key=f"send_followup_{result['run_id']}"):
        quick_question = custom_question
    if quick_question is not None:
        if not quick_question.strip():
            st.warning("请先输入追问内容。")
        else:
            try:
                process_follow_up(result, quick_question, tracker)
            except (ValueError, LLMInterpretationError) as error:
                st.error(f"追问未完成：{error}")

    for turn in st.session_state.get("sixyao_followups", []):
        source = "AI 生成解释" if turn.get("llm_metadata", {}).get("ai_generated") else "本地规则转译"
        st.markdown(
            '<div class="conversation-turn">'
            f'<strong>你问：{html.escape(turn["user_question"])}</strong>'
            f'<div class="conversation-answer">{html.escape(turn["response"]).replace(chr(10), "<br>")}</div>'
            f'<span class="source-badge local">{html.escape(source)}</span>'
            '</div>',
            unsafe_allow_html=True,
        )


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
    can_cast = True
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
                hand_mode = st.radio(
                    "手摇卦方式",
                    ["记录正反面", "虚拟摇卦"],
                    horizontal=True,
                    key="hand_cast_mode",
                )
                st.markdown(
                    '<div class="coin-rule"><strong>三枚铜钱换算：</strong>正面计 3，反面计 2。'
                    '三反=老阴，一正二反=少阳，二正一反=少阴，三正=老阳。'
                    '第一次为初爻，依次向上。</div>',
                    unsafe_allow_html=True,
                )
                if hand_mode == "记录正反面":
                    labels = (
                        "第 6 次 · 上爻",
                        "第 5 次 · 五爻",
                        "第 4 次 · 四爻",
                        "第 3 次 · 三爻",
                        "第 2 次 · 二爻",
                        "第 1 次 · 初爻",
                    )
                    lines = []
                    for row_start in range(0, 6, 2):
                        line_columns = st.columns(2)
                        for column_index, label in enumerate(labels[row_start:row_start + 2]):
                            index = row_start + column_index
                            lines.append(
                                line_columns[column_index].selectbox(
                                    label,
                                    [6, 7, 8, 9],
                                    index=2,
                                    format_func=COIN_LINE_LABELS.get,
                                    key=f"manual_coin_line_{index}",
                                )
                            )
                    casting_input.update(mode="manual", lines=lines)
                else:
                    virtual_throws = list(st.session_state.get("virtual_coin_throws", []))
                    st.progress(
                        len(virtual_throws) / 6,
                        text=f"已完成 {len(virtual_throws)} / 6 摇",
                    )
                    action_columns = st.columns([1.5, 1])
                    shake_clicked = action_columns[0].button(
                        "摇一爻",
                        key="virtual_shake",
                        disabled=len(virtual_throws) >= 6,
                        use_container_width=True,
                    )
                    reset_clicked = action_columns[1].button(
                        "重新开始",
                        key="virtual_reset",
                        disabled=not virtual_throws,
                        use_container_width=True,
                    )
                    if shake_clicked:
                        coins = [secrets.choice(("正", "反")) for _ in range(3)]
                        fronts = coins.count("正")
                        virtual_throws.append(
                            {
                                "coins": coins,
                                # 三枚铜钱中正面每增加一枚，总值由 6 递增到 9。
                                # 留在页面层换算，避免 Streamlit 热更新时新 app 调用旧 Caster。
                                "value": 6 + fronts,
                            }
                        )
                        st.session_state["virtual_coin_throws"] = virtual_throws
                        st.rerun()
                    if reset_clicked:
                        st.session_state["virtual_coin_throws"] = []
                        st.session_state.pop("sixyao_result", None)
                        st.rerun()
                    render_virtual_throws(virtual_throws)
                    can_cast = len(virtual_throws) == 6
                    if can_cast:
                        lines = list(reversed([throw["value"] for throw in virtual_throws]))
                        casting_input.update(mode="manual", lines=lines)
                        st.success("六爻已完成，可以开始排盘。")
                    else:
                        casting_input.update(mode="manual", lines=[])
                        st.caption("请从初爻开始，共摇六次；每次结果会自动记录。")
            else:
                number_columns = st.columns(3)
                numbers = [
                    number_columns[0].number_input("上卦数", 0, 999, 123),
                    number_columns[1].number_input("下卦数", 0, 999, 456),
                    number_columns[2].number_input("动爻数", 0, 999, 789),
                ]
                casting_input.update(mode="number", numbers=numbers)

        cast_button_label = "开始排盘并生成解读" if can_cast else "完成六次摇卦后开始排盘"
        if st.button(
            cast_button_label,
            type="primary",
            use_container_width=True,
            disabled=not can_cast,
        ):
            if not query.strip():
                st.warning("请先写明占问事项，建议一次只问一件事。")
            else:
                similar = tracker.find_similar_recent(query, kind="sixyao")
                if similar:
                    st.session_state["repeat_divination_candidate"] = {
                        "new_query": query.strip(),
                        "run_id": similar["run_id"],
                        "previous_query": similar["user_query"],
                        "created_at": similar["created_at"],
                        "similarity": similar["similarity"],
                    }
                else:
                    try:
                        run_and_activate_sixyao(query, casting_input, tracker)
                    except (ValueError, CastingError, AstronomyCalculationError, PaipanError,
                            GuardrailValidationError, LLMInterpretationError) as error:
                        st.error(f"系统已中止：{error}")

        repeat_candidate = st.session_state.get("repeat_divination_candidate")
        if repeat_candidate and repeat_candidate.get("new_query") != query.strip():
            st.session_state.pop("repeat_divination_candidate", None)
            repeat_candidate = None
        if repeat_candidate:
            st.warning(
                f"最近24小时内已有相似占问：“{repeat_candidate['previous_query']}”"
                f"（{repeat_candidate['created_at']}）。建议先回看原结果，避免反复起卦只挑选满意答案。"
            )
            review_column, continue_column = st.columns(2)
            if review_column.button("查看上次结果", use_container_width=True):
                previous = tracker.get_run(repeat_candidate["run_id"])
                if previous:
                    try:
                        activate_sixyao_result(
                            restore_divination_result(previous), previous.get("followups", [])
                        )
                        st.session_state.pop("repeat_divination_candidate", None)
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))
            if continue_column.button("条件已变化，仍然重新起卦", use_container_width=True):
                try:
                    run_and_activate_sixyao(query, casting_input, tracker)
                    st.session_state.pop("repeat_divination_candidate", None)
                    st.rerun()
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
        render_provenance(result)
        render_related_hexagrams(paipan)
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
                st.markdown('<div class="audit-label">来源分层解读</div>', unsafe_allow_html=True)
                st.markdown("### 解读报告")
                if result.get("interpretation_status") == "failed":
                    st.warning("确定性盘面已保存，但 DeepSeek 解释失败。重试只会更新解释，不会重新起卦。")
                st.markdown(result["llm_response"])
        with audit_right:
            with st.container(border=True):
                st.markdown('<div class="audit-label">证据与留痕</div>', unsafe_allow_html=True)
                if result.get("interpretation_status") == "failed":
                    st.error("AI 解释待重试")
                    if st.button("只重试 DeepSeek 解释", key=f"retry_{result['run_id']}", use_container_width=True):
                        try:
                            with st.spinner("正在重试解释，盘面保持不变…"):
                                retried = retry_divination_interpretation(
                                    result,
                                    interpreter=LLMInterpreter(api_key=get_deepseek_key()),
                                    tracker=tracker,
                                )
                            activate_sixyao_result(
                                retried, st.session_state.get("sixyao_followups", [])
                            )
                            st.rerun()
                        except (ValueError, LLMInterpretationError) as error:
                            st.error(f"解释仍未完成：{error}")
                elif result["llm_metadata"]["mode"] == "offline":
                    st.info("当前为离线模式，仅展示确定性盘面与已核验原典。")
                else:
                    st.success("DeepSeek 解读已生成。")
                source = paipan.get("source", {})
                if source.get("url"):
                    st.markdown(f"[查看原典版本：{source.get('title', '《周易》')}]({source['url']})")
                    st.caption(
                        f"修订号 {source.get('revision_id')} · {source.get('revision_timestamp')} · "
                        f"文本版本 {source.get('text_variant', '未标注')}"
                    )
                with st.expander("原典与排盘数据"):
                    st.write("卦辞：", paipan["judgement"])
                    st.json(paipan)
                with st.expander("规则校验轨迹"):
                    st.json(result["guardrail_log"])
                st.caption(f"完整 Run ID：{result['run_id']}")
        render_follow_up(result, tracker)

with asking_tab:
    render_section_intro(
        "ASKING QIMEN",
        "问事奇门",
        "以提问时刻起局，展示值符、值使与九宫结构。",
    )
    asking_query = st.text_input("问事主题", key="qimen_query")
    category = st.selectbox("事项类别", ["综合", "事业", "合作", "出行", "学业", "关系"])
    st.caption("选择更准确的事项类别，可以让白话行动建议更具体。")
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
        render_plain_conclusion(summarize_asking_chart(chart))
        st.markdown("### 专业九宫盘")
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
        render_plain_conclusion(summarize_lifelong_chart(chart))
        st.markdown("### 专业盘面与时间结构")
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
    st.caption(
        "审计记录保存在 SQLite；默认保留365天。Streamlit Cloud 本地磁盘重启后仍可能重置，"
        "重要记录请及时导出。"
    )
    with st.expander("历史数据保留与清理"):
        setting_column, action_column = st.columns([1.2, 1])
        retention_days = setting_column.number_input(
            "自动保留天数",
            min_value=30,
            max_value=3650,
            value=tracker.get_retention_days(),
            step=30,
            help="超过保留期的记录会在应用启动或保存设置时惰性清理。",
        )
        if setting_column.button("保存保留期"):
            tracker.set_retention_days(int(retention_days))
            removed = tracker.purge_expired()
            st.success(f"保留期已更新；本次清理 {removed} 条过期记录。")
        if action_column.button("清空全部历史", type="secondary"):
            st.session_state["confirm_clear_history"] = True
        if st.session_state.get("confirm_clear_history"):
            st.warning("这会永久删除全部运行、反馈和追问记录。建议先逐条导出重要报告。")
            clear_confirmed = st.checkbox("我确认清空全部历史", key="clear_history_checkbox")
            confirm_column, cancel_column = st.columns(2)
            if confirm_column.button(
                "永久清空",
                disabled=not clear_confirmed,
                use_container_width=True,
            ):
                count = tracker.clear_history()
                for key in (
                    "confirm_clear_history", "sixyao_result", "sixyao_followups",
                    "sixyao_conversation_memory", "repeat_divination_candidate",
                ):
                    st.session_state.pop(key, None)
                st.success(f"已清空 {count} 条历史记录。")
                st.rerun()
            if cancel_column.button("取消", use_container_width=True):
                st.session_state.pop("confirm_clear_history", None)
                st.rerun()
    history = tracker.list_history(limit=30)
    if not history:
        st.info("暂无历史记录。")
    label_to_status = {"尚无结果": "pending", "应验": "verified", "未应验": "unverified", "部分应验": "partial"}
    status_to_label = {value: key for key, value in label_to_status.items()}
    for item in history:
        with st.expander(f"{item['created_at']} · {item['user_query']} · {item['run_id'][:8]}"):
            full_record = tracker.get_run(item["run_id"])
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
            if full_record:
                export_column, json_column, restore_column = st.columns(3)
                export_column.download_button(
                    "导出 Markdown",
                    data=record_as_markdown(full_record),
                    file_name=f"divination-{item['run_id'][:8]}.md",
                    mime="text/markdown",
                    key=f"export_md_{item['run_id']}",
                    use_container_width=True,
                )
                json_column.download_button(
                    "导出 JSON",
                    data=json.dumps(full_record, ensure_ascii=False, indent=2),
                    file_name=f"divination-{item['run_id'][:8]}.json",
                    mime="application/json",
                    key=f"export_json_{item['run_id']}",
                    use_container_width=True,
                )
                if "paipan_summary" in full_record.get("ai_context", {}):
                    if restore_column.button(
                        "作为当前结果",
                        key=f"restore_{item['run_id']}",
                        use_container_width=True,
                    ):
                        activate_sixyao_result(
                            restore_divination_result(full_record),
                            full_record.get("followups", []),
                        )
                        st.info("已恢复为当前六爻结果，请切换到“六爻问事”继续追问。")

            if st.button("删除这条记录", key=f"delete_{item['run_id']}"):
                st.session_state["confirm_delete_run"] = item["run_id"]
            if st.session_state.get("confirm_delete_run") == item["run_id"]:
                st.warning("删除后，该记录的反馈和追问也会一并永久删除。")
                delete_column, cancel_column = st.columns(2)
                if delete_column.button(
                    "确认永久删除",
                    key=f"confirm_delete_{item['run_id']}",
                    use_container_width=True,
                ):
                    tracker.delete_run(item["run_id"])
                    st.session_state.pop("confirm_delete_run", None)
                    if st.session_state.get("sixyao_result", {}).get("run_id") == item["run_id"]:
                        for key in (
                            "sixyao_result", "sixyao_followups", "sixyao_conversation_memory"
                        ):
                            st.session_state.pop(key, None)
                    st.rerun()
                if cancel_column.button(
                    "取消删除",
                    key=f"cancel_delete_{item['run_id']}",
                    use_container_width=True,
                ):
                    st.session_state.pop("confirm_delete_run", None)
                    st.rerun()
