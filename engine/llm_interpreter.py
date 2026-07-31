"""
engine/llm_interpreter.py
负责构建三段式 Prompt、注入合规护栏，并调用大模型生成解读
"""
import os
import json
from typing import Dict, Any

class LLMInterpreter:
    def __init__(self, api_key: str = None, model_name: str = "gpt-4o"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model_name = model_name

    def build_system_prompt(self) -> str:
        """构建系统级 Prompt：强约束角色定位、思维链 (CoT) 与合规护栏"""
        return """你是专业、严谨的传统易学典籍翻译与现实问题分析助手。

### 【核心原则与禁令】
1. 严禁改动、伪造或自行编造任何卦名、爻词与卦辞！你收到的原文数据已通过系统数据库硬校验。
2. 必须遵循【三段式思维链 (CoT)】顺序输出，不得跳跃推理或强行凑合。
3. 绝对禁止对医疗健康、法律诉讼、金融投资交易、生死等问题给出 100% 确定性的操作指令或后果承诺。

### 【三段式思维链 (CoT) 输出结构】
请严格按照以下三个章节输出内容：

#### 一、 盘面事实陈述
- 简述本局卦名、世应位置、旬空及代码提炼出的【核心焦点爻】客观状态。

#### 二、 典籍语义解析
- 结合系统提供的卦辞与【核心焦点爻】爻辞，解释其在传统易学典籍中的本意与象义。

#### 三、 现实问题映射与建议
- 将前两步的客观推演映射至用户占问的实际问题，分析变量与可能的发展趋势。
- 结尾必须附带固定提示：“【免责声明】本解读基于传统易学典籍与逻辑模型推演，仅供文化体验与决策参考。”
"""

    def build_user_prompt(self, ai_context: Dict[str, Any]) -> str:
        """将校验通过的结构化 ai_context 转化为 User Prompt"""
        summary = ai_context["paipan_summary"]
        focus = summary["焦点爻"]
        
        prompt_text = f"""【用户占问事项】：{ai_context['user_query']}

【系统校验通过的排盘数据】：
- 卦名/宫位：{summary['卦名']} ({summary['宫位']})
- 日柱干支：{summary['干支']}
- 核心焦点爻：第 {focus['primary_focus']} 爻 ({focus['type']} - {focus['description']})
- 卦辞原文：{summary['卦辞原典']}
- 焦点爻辞原文：{summary['焦点爻辞']['line_name']} - {summary['焦点爻辞']['text']}

请根据上述客观数据，按照【三段式思维链】输出你的解卦分析。"""
        return prompt_text

    def interpret(self, ai_context: Dict[str, Any]) -> str:
        """
        调用 LLM 生成解读文本（此处以 Mock / Standard API 接口演示）
        """
        system_prompt = self.build_system_prompt()
        user_prompt = self.build_user_prompt(ai_context)
        summary = ai_context["paipan_summary"]
        focus = summary["焦点爻"]

        # 实际生产环境在此处调用 OpenAI / Claude / 本地 LLM API
        # response = client.chat.completions.create(
        #     model=self.model_name,
        #     messages=[
        #         {"role": "system", "content": system_prompt},
        #         {"role": "user", "content": user_prompt}
        #     ],
        #     temperature=0.3  # 保持较低随机性，确保解卦严谨
        # )
        
        # 演示用 Mock 输出：
        mock_response = f"""#### 一、 盘面事实陈述
本次占问事项为“{ai_context['user_query']}”。排盘结果为【{summary['卦名']}】，属于【{summary['宫位']}】。本局根据规则引擎提炼，核心焦点在于第 {focus['primary_focus']} 爻（{focus['type']}），系本局推演的主要变量。

#### 二、 典籍语义解析
卦辞记载：“{summary['卦辞原典']}”。
焦点爻（{summary['焦点爻辞']['line_name']}）爻辞记载：“{summary['焦点爻辞']['text']}”。
此爻象表明在事物发展的初始或关键阶段，蕴含着特定潜伏与积蓄的力量，不宜急于求成。

#### 三、 现实问题映射与建议
结合您占问的实际问题，当前阶段不宜采取冒进动作。建议先积蓄自身实力，等待时机成熟。

【免责声明】本解读基于传统易学典籍与逻辑模型推演，仅供文化体验与决策参考。"""
        return mock_response
