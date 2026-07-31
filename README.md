# 数智易学排盘系统

确定性六爻与时家奇门排盘系统。历法、排盘、焦点和冲空规则由代码计算；DeepSeek 只解释已校验的数据，不能改写原典。

## 已实现

- 64 卦、384 爻原典与八宫纳甲规则库（含来源与哈希）
- 真太阳时、四柱、精确节气边界、旬空、六神、月破与日冲
- 伏神、暗动/日破/冲空则实、空破并见和多动爻焦点
- 时家转盘奇门拆补法九宫盘，以及出生盘、大运和流运结构
- DeepSeek JSON Output、离线模式、合规过滤和原典本地回填
- 本卦、变卦、互卦、综卦、错卦五层确定性推导与来源标记
- 追问式解读、同题提醒、失败原记录重试与三十分钟会话记忆
- SQLite 审计、历史查询、单条/批量清理、保留期、导出和四状态反馈
- 传统易经与赛博仪器融合的 Streamlit 四入口界面，含减弱动态偏好适配

规则来源与流派约定见 [data/SOURCES.md](data/SOURCES.md) 和 [docs/QIMEN_RULES.md](docs/QIMEN_RULES.md)。

## 本地运行

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

不配置密钥也能使用完整确定性排盘，解读区会明确显示离线模式。需要 DeepSeek 时设置：

```powershell
$env:DEEPSEEK_API_KEY = "你的 DeepSeek 密钥"
python -m streamlit run app.py
```

## Streamlit Community Cloud

1. 仓库选择 `Github37525/ai-divination-system`，分支 `main`，入口 `app.py`。
2. 可使用 Streamlit Cloud 当前提供的 Python 版本；历法后端为纯 Python，不依赖平台原生扩展。
3. 在 Secrets 中添加（不要写入 Git）：

```toml
DEEPSEEK_API_KEY = "你的 DeepSeek 密钥"
```

4. 重新部署后查看 Manage app 日志。SQLite 历史保存在实例本地磁盘，Community Cloud 重启后可能重置；正式长期保存应换成外部持久数据库。

## 验证

```powershell
python -m unittest discover -s tests -v
python -m compileall -q app.py main.py engine tests
python -m pip check
```

详细完成状态见 [docs/COMPLETION_MATRIX.md](docs/COMPLETION_MATRIX.md)。
