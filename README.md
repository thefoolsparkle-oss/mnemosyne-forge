# 造枝 Mnemosyne Forge

> 忆界 / Mnemosyne Realm 生态下的 AI 原创角色创作系统

输入模糊角色灵感，通过多轮对话逐步补全设定，最终导出 Character Card V2 标准角色卡。支持联网搜索素材、Stability AI 生图、ElevenLabs 专属音色、世界观生成、与忆界树桥接。

## 启动

```powershell
.\run_dev.ps1
```

浏览器打开 http://127.0.0.1:8010，登录后开始创作。

停止服务器：

```powershell
Stop-Process -Id (Get-Content .server.pid)
```

## 配置

创建 `.env`：

```env
DEEPSEEK_API_KEY=sk-xxx      # LLM（必填）
STABILITY_API_KEY=sk-xxx     # 生图（可选）
ELEVENLABS_API_KEY=xxx       # 专属音色（可选）
FISH_API_KEY=xxx             # Fish Audio（可选）
```

`config.yaml` 中可切换 LLM provider、语音 provider、生图参数。

## 功能

- **多 Agent 协作**：Guide / Designer / Consistency / Export
- **快速生成**：一键生成完整角色卡，跳过逐轮对话
- **账号系统**：与忆界树共享用户数据库
- **搜索增强**：DuckDuckGo 联网搜索，结果转为可采纳的创作方向
- **图像生成**：Stability AI 三候选生图，Visual Identity Agent + Prompt Director + Image Critic
- **专属音色**：ElevenLabs Voice Design 三候选，选择后锁定为角色专属 voice_id
- **声音备选**：Edge TTS（免费自动匹配）、Fish Audio（需 reference_id）
- **世界观生成**：LLM 生成世界观 + 世界书条目
- **角色卡导出**：Character Card V2 JSON + Markdown，含绑定资产
- **角色库**：可恢复、删除历史角色，资产历史面板

## 技术栈

Python 3.11+ / FastAPI / SQLite / Pydantic V2 / httpx / ddgs / Stability AI / ElevenLabs
