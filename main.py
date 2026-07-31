"""
main.py
卜卦系统 Pipeline 执行入口
"""
import uuid
from datetime import datetime
from engine.caster import Caster
from engine.astronomy import AstronomyService
from engine.paipan import PaipanEngine
from engine.guardrails import Guardrails, GuardrailValidationError

def run_divination_pipeline(user_query: str, casting_input: dict):
    run_id = str(uuid.uuid4())
    print(f"=== 开始运行卜卦 Pipeline [Run ID: {run_id}] ===")
    
    try:
        # Step 1: 输入校验与起卦
        print("[1/5] 执行起卦与边界校验...")
        cast_result = Caster.cast_manual(casting_input["lines"])
        
        # Step 2: 天文历法与真太阳时计算
        print("[2/5] 推算真太阳时与干支历法...")
        calendar_data = AstronomyService.get_ganzhi_calendar(
            dt=datetime.now(), 
            longitude=casting_input.get("longitude", 120.0)
        )
        
        # Step 3: 装卦与焦点爻提取
        print("[3/5] 构建排盘与提炼焦点爻...")
        engine = PaipanEngine(db_path="data/hexagrams_db.json")
        paipan_data = engine.build_paipan(cast_result, calendar_data)
        
        # Step 4: Guardrails 熔断校验
        print("[4/5] 执行 Guardrails 易学逻辑硬断言校验...")
        Guardrails.validate_paipan_data(paipan_data)
        print(" -> Guardrails 校验通过！")
        
        # Step 5: 构建 AI Context (准备交付给 LLM)
        print("[5/5] 构建结构化 AI Context...")
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
        
        print("\nPipeline 执行完毕，生成合格的 ai_context：")
        print(ai_context)
        return ai_context

    except GuardrailValidationError as e:
        print(f"❌ Guardrails 熔断拦截: {e}")
    except Exception as e:
        print(f"❌ 系统运行异常: {e}")

if __name__ == "__main__":
    # 模拟前端输入：用户占问跳槽，输入手摇卦（从上到下：6老阴, 7少阳, 8少阴, 7少阳, 7少阳, 9老阳）
    mock_input = {
        "lines": [6, 7, 8, 7, 7, 9],
        "longitude": 120.15  # 杭州经度
    }
    run_divination_pipeline(user_query="今年适合跳槽吗？", casting_input=mock_input)