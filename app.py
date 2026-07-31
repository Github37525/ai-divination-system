"""
app.py - Streamlit 可视化前端与部署入口
"""
import streamlit as st
import datetime
import uuid

# 导入底层引擎模块
from engine.caster import Caster, CastingError
from engine.astronomy import AstronomyService
from engine.paipan import PaipanEngine
from engine.guardrails import Guardrails, GuardrailValidationError
from engine.llm_interpreter import LLMInterpreter
from engine.tracker import AuditTracker

# 页面基本配置
st.set_page_config(
    page_title="数智易学 - 确定性排盘与AI解卦系统",
    page_icon="☯️",
    layout="centered"
)

st.title("☯️ 数智易学排盘系统")
st.caption("基于确定性规则引擎 + 天文真太阳时 + 大模型 CoT 严密解读")

st.divider()

# 侧边栏：选择起卦方式与经纬度
with st.sidebar:
    st.header("⚙️ 起卦设置")
    cast_mode = st.radio("选择起卦模式", ["手摇卦 (摇爻)", "数字起卦"])
    
    st.subheader("📍 地理位置 (计算真太阳时)")
    city_lng = st.number_input("经度 (如杭州 120.15, 新疆 87.6)", value=120.15, step=0.1)

# 主界面：输入占问事项
user_query = st.text_input("🔮 请输入您要占问的事项", placeholder="例如：下半年事业发展趋势如何？")

casting_input = {}

if cast_mode == "手摇卦 (摇爻)":
    st.markdown("#### 请从初爻（最下方）到上爻（最上方）选择六爻状态：")
    col1, col2 = st.columns(2)
    
    with col1:
        line1 = st.selectbox("初爻 (最下)", [7, 8, 9, 6], format_func=lambda x: {7:"少阳 (—)", 8:"少阴 (- -)", 9:"老阳 (— O 动)", 6:"老阴 (- - X 动)"}[x])
        line2 = st.selectbox("二爻", [7, 8, 9, 6], format_func=lambda x: {7:"少阳 (—)", 8:"少阴 (- -)", 9:"老阳 (— O 动)", 6:"老阴 (- - X 动)"}[x])
        line3 = st.selectbox("三爻", [7, 8, 9, 6], format_func=lambda x: {7:"少阳 (—)", 8:"少阴 (- -)", 9:"老阳 (— O 动)", 6:"老阴 (- - X 动)"}[x])
    with col2:
        line4 = st.selectbox("四爻", [7, 8, 9, 6], format_func=lambda x: {7:"少阳 (—)", 8:"少阴 (- -)", 9:"老阳 (— O 动)", 6:"老阴 (- - X 动)"}[x])
        line5 = st.selectbox("五爻", [7, 8, 9, 6], format_func=lambda x: {7:"少阳 (—)", 8:"少阴 (- -)", 9:"老阳 (— O 动)", 6:"老阴 (- - X 动)"}[x])
        line6 = st.selectbox("上爻 (最上)", [7, 8, 9, 6], format_func=lambda x: {7:"少阳 (—)", 8:"少阴 (- -)", 9:"老阳 (— O 动)", 6:"老阴 (- - X 动)"}[x])
        
    casting_input = {"mode": "manual", "lines": [line6, line5, line4, line3, line2, line1], "longitude": city_lng}

else:
    st.markdown("#### 请输入 3 个 0-999 之间的随机数字：")
    c1, c2, c3 = st.columns(3)
    n1 = c1.number_input("数字 1 (上卦)", min_value=0, max_value=999, value=123)
    n2 = c2.number_input("数字 2 (下卦)", min_value=0, max_value=999, value=456)
    n3 = c3.number_input("数字 3 (动爻)", min_value=0, max_value=999, value=789)
    casting_input = {"mode": "number", "numbers": [n1, n2, n3], "longitude": city_lng}

st.divider()

# 提交按钮与 Pipeline 执行
if st.button("🚀 开始起卦与 AI 解读", type="primary", use_container_width=True):
    if not user_query.strip():
        st.warning("⚠️ 请先输入您要占问的事项！")
    else:
        run_id = str(uuid.uuid4())
        
        with st.spinner("正在通过确定性规则引擎排盘与计算真太阳时..."):
            try:
                # 1. 起卦处理
                if casting_input["mode"] == "manual":
                    cast_res = Caster.cast_manual(casting_input["lines"])
                else:
                    cast_res = Caster.cast_number(casting_input["numbers"])
                
                # 2. 天文历法
                calendar_data = AstronomyService.get_ganzhi_calendar(datetime.datetime.now(), city_lng)
                
                # 3. 排盘与焦点爻
                engine = PaipanEngine(db_path="data/hexagrams_db.json")
                paipan_data = engine.build_paipan(cast_res, calendar_data)
                
                # 4. Guardrails 硬校验
                Guardrails.validate_paipan_data(paipan_data)
                
            except (CastingError, GuardrailValidationError, Exception) as e:
                st.error(f"❌ 系统校验熔断：{str(e)}")
                st.stop()
        
        # 显示排盘客观结果
        st.success("✅ 确定性排盘完成 (已通过 Guardrails 硬校验)")
        
        col_res1, col_res2, col_res3 = st.columns(3)
        col_res1.metric("本卦/宫位", f"{paipan_data['name']}", paipan_data['palace'])
        col_res2.metric("日柱干支", calendar_data['day_ganzhi'])
        col_res3.metric("核心焦点爻", f"第 {paipan_data['focus_analysis']['primary_focus']} 爻")
        
        with st.expander("📖 查看系统调取的原典卦爻辞 (已防AI幻觉)"):
            st.json({
                "卦辞原典": paipan_data["judgement"],
                "焦点爻辞": paipan_data["lines_detail"][str(paipan_data["focus_analysis"]["primary_focus"])]
            })

        # 5. 调用 AI 进行三段式解读
        with st.spinner("🤖 正在调用 AI 进行三段式思维链 (CoT) 严密解读..."):
            ai_context = {
                "run_id": run_id,
                "user_query": user_query,
                "paipan_summary": {
                    "卦名": paipan_data["name"],
                    "宫位": paipan_data["palace"],
                    "干支": calendar_data["day_ganzhi"],
                    "焦点爻": paipan_data["focus_analysis"],
                    "卦辞原典": paipan_data["judgement"],
                    "焦点爻辞": paipan_data["lines_detail"][str(paipan_data["focus_analysis"]["primary_focus"])]
                }
            }
            interpreter = LLMInterpreter()
            llm_response = interpreter.interpret(ai_context)
            
            # 落库审计
            tracker = AuditTracker()
            tracker.save_run_record(run_id, user_query, casting_input, paipan_data, ai_context, llm_response)

        st.markdown("### 📝 AI 解读报告")
        st.markdown(llm_response)
        
        st.caption(f"追踪 ID (Run ID): {run_id}")