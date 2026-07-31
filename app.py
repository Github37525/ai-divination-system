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
st.title("☯️ 数智易学排盘系统")
st.caption("确定性规则排盘 · 原典可查 · DeepSeek 受约束解读 · 全链路可追溯")


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
    st.header("📍 时间与位置")
    longitude = st.number_input("经度", -180.0, 180.0, 120.15, 0.01)
    latitude = st.number_input("纬度", -90.0, 90.0, 30.28, 0.01)
    timezone_offset = st.number_input("UTC 时区偏移", -12.0, 14.0, 8.0, 0.5)
    st.caption("当前支持手动精确经纬度；历法按节气时刻与真太阳时计算。")
    if get_deepseek_key():
        st.success("DeepSeek：已配置")
    else:
        st.info("DeepSeek：离线模式")


sixyao_tab, asking_tab, lifelong_tab, history_tab = st.tabs(
    ["六爻问事", "问事奇门", "终身奇门", "历史复盘"]
)

with sixyao_tab:
    query = st.text_input("占问事项", placeholder="请描述一个具体、可复盘的问题", key="sixyao_query")
    cast_mode = st.radio("起卦方式", ["手摇卦", "数字起卦"], horizontal=True)
    casting_input = {
        "longitude": longitude,
        "latitude": latitude,
        "timezone_offset_hours": timezone_offset,
    }
    if cast_mode == "手摇卦":
        labels = ("上爻（最上）", "五爻", "四爻", "三爻", "二爻", "初爻（最下）")
        format_line = {6: "老阴 ⚋×", 7: "少阳 ⚊", 8: "少阴 ⚋", 9: "老阳 ⚊○"}
        columns = st.columns(3)
        lines = [
            columns[index % 3].selectbox(
                label, [8, 7, 6, 9], format_func=format_line.get, key=f"manual_line_{index}"
            )
            for index, label in enumerate(labels)
        ]
        casting_input.update(mode="manual", lines=lines)
    else:
        columns = st.columns(3)
        numbers = [
            columns[0].number_input("数字 1（上卦）", 0, 999, 123),
            columns[1].number_input("数字 2（下卦）", 0, 999, 456),
            columns[2].number_input("数字 3（动爻）", 0, 999, 789),
        ]
        casting_input.update(mode="number", numbers=numbers)

    if st.button("开始六爻排盘与解读", type="primary", use_container_width=True):
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
        columns = st.columns(4)
        columns[0].metric("本卦", paipan["name"])
        columns[1].metric("宫位", paipan["palace"])
        columns[2].metric("日柱", calendar["day_ganzhi"])
        columns[3].metric("旬空", "、".join(calendar["xunkong"]))
        focus = paipan["focus_analysis"]["primary_focus"]
        st.markdown("#### 六爻盘面（上爻在上）")
        for number in range(6, 0, -1):
            line = paipan["lines_detail"][str(number)]
            marker = "⚊" if paipan["hexagram_code"][number - 1] == "1" else "⚋"
            tags = " · ".join(line["state_tags"]) or "平"
            content = (
                f"{marker}　第{number}爻　{line['najia']} {line['relative']}　{tags}"
                f"{'　← 核心焦点' if focus == number else ''}"
            )
            if focus == number:
                st.markdown(
                    f"<div style='border:2px solid #c9a227;border-radius:8px;padding:10px;background:#fff8dc'>{html.escape(content)}</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.code(content, language=None)
        with st.expander("原典与排盘数据"):
            st.write("卦辞：", paipan["judgement"])
            st.json(paipan)
        st.markdown("### DeepSeek 解读报告")
        st.markdown(result["llm_response"])
        if result["llm_metadata"]["mode"] == "offline":
            st.info("未配置密钥：本次只展示确定性盘面与已核验原典。")
        with st.expander(f"调试轨迹 · {result['run_id']}"):
            st.json(result["guardrail_log"])

with asking_tab:
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
