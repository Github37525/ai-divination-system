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
- P0 Experience API：安全随机承诺、幂等单爻、手机体感/点按摇卦和电脑实时协同
- P0 生产化：Redis/Valkey 临时会话、分层限流、刷新恢复与 DeepSeek 后台异步解释
- 原生微信小程序 MVP：体感/点按摇卦、震动动画、断点恢复、异步解读和本机卦例

规则来源与流派约定见 [data/SOURCES.md](data/SOURCES.md) 和 [docs/QIMEN_RULES.md](docs/QIMEN_RULES.md)。
下一阶段的 H5、微信小程序、原生 App、手机体感摇卦和电脑手机协同规划见 [PRD v3.0](divination_system_prd_v3.md)。

## 本地运行

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

手机摇卦与电脑协同使用独立服务，另开一个终端运行：

```powershell
python -m experience
```

浏览器访问 `http://127.0.0.1:8770/`。手机真机需要通过 HTTPS 地址访问，才能在主流浏览器中申请设备运动权限。若要从 Streamlit 侧边栏进入该服务，可设置 `EXPERIENCE_PUBLIC_URL` 为其公开 HTTPS 地址。

临时会话默认保留 30 分钟、配对入口默认 5 分钟。配置 `REDIS_URL` 后，会话、配对、幂等结果和限流窗口使用 Redis/Valkey 共享；未配置时仅为本地开发使用进程内存。手机和电脑页面会在当前标签页的 `sessionStorage` 中保存短时凭证，以便刷新后恢复，不写入长期浏览器存储。

## 微信小程序

原生小程序工程位于 [`miniprogram`](miniprogram)。用微信开发者工具导入该目录，将 `project.config.json` 的 `touristappid` 换成实际 AppID，并在微信公众平台把生产服务域名加入 `request` 合法域名。详细运行方式和当前边界见 [`miniprogram/README.md`](miniprogram/README.md)。

小程序只保存短时会话凭证及最多 20 条本机卦例。DeepSeek 密钥、随机种子、排盘逻辑和异步任务全部留在服务端。体感和震动效果必须用真机验收，开发者工具模拟器不能作为最终依据。

## Experience API 部署

仓库根目录的 `render.yaml` 定义了支持 HTTPS/WSS 的 Render Web Service 和免费 Render Key Value（Valkey），并通过私网注入 `REDIS_URL`。免费 Key Value 不提供磁盘持久化，但 Web Service 冷启动和普通重新部署不再清除其中尚未过期的临时会话；正式长期历史仍应使用持久数据库。

六爻完成接口先返回确定性盘面（HTTP `202`），DeepSeek 在后台生成；客户端通过 `GET /v1/cast-sessions/{id}/result` 获取最终解释。默认限流为：每 IP 每分钟创建 10 次、每会话每分钟锁爻 30 次、每 IP 每小时最多 12 次 DeepSeek，AI 并发最多 2。可通过 `EXPERIENCE_*` 环境变量调整。

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
python -m compileall -q app.py main.py engine experience tests
python -m pip check
Get-ChildItem miniprogram -Recurse -Filter *.js | ForEach-Object { node --check $_.FullName }
```

详细完成状态见 [docs/COMPLETION_MATRIX.md](docs/COMPLETION_MATRIX.md)。
