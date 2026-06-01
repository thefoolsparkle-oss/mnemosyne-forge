# 造枝 Mnemosyne Forge

> 忆界 / Mnemosyne Realm 生态下的 AI 原创角色创作系统

通过多轮对话将模糊角色灵感逐步转化为结构化 OC 草稿，导出为 Character Card V2 标准角色卡。支持联网搜索素材、世界观生成、Stability AI 生图、声音匹配。

## 功能

- **多 Agent 协作**：Guide（采访追问）、Designer（设定抽取）、Consistency（一致性检查）、Export（角色卡生成）
- **快速生成**：一键跳过对话，直接生成完整角色卡
- **账号系统**：与忆界树共享用户数据库，支持注册/登录/游客
- **搜索增强**：DuckDuckGo 联网搜索，结果提炼为可选创作方向
- **世界观生成**：LLM 生成完整世界观 + 世界书条目
- **图像生成**：Stability AI (Stable Diffusion) 生成立绘
- **声音匹配**：7 种声线模板按性格自动匹配
- **角色卡预览**：导出前预览卡片内容，下载 JSON + Markdown
- **角色库**：可恢复、删除历史角色

## 安装

```powershell
cd mnemosyne-forge
py -m pip install -r requirements.txt
```

## 配置

创建 `.env`：

```env
DEEPSEEK_API_KEY=sk-your-key
STABILITY_API_KEY=sk-your-key   # 生图需要
```

`config.yaml` 中可切换 LLM provider（deepseek/openai/kimi），配置搜索/生图/声音。

## 启动

```powershell
powershell -ExecutionPolicy Bypass -File .\run_dev.ps1
```

打开 http://127.0.0.1:8010

如果不需要公网隧道，也可以直接启动后端：

```powershell
python -m uvicorn app.server:app --host 127.0.0.1 --port 8010 --reload
```

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/api/auth/register` | 注册 |
| POST | `/api/auth/login` | 登录 |
| POST | `/api/auth/guest` | 游客模式 |
| POST | `/api/sessions` | 创建会话 |
| POST | `/api/sessions/{id}/messages` | 发送消息 |
| GET | `/api/sessions/{id}/draft` | 获取草稿 |
| GET | `/api/sessions/{id}/messages` | 历史消息 |
| POST | `/api/sessions/{id}/export/card-v2` | 导出角色卡 |
| POST | `/api/sessions/{id}/search` | 搜索素材 |
| POST | `/api/sessions/{id}/world` | 生成世界观 |
| POST | `/api/sessions/{id}/image` | 生成立绘 |
| GET | `/api/sessions/{id}/voice-profile` | 声音匹配 |
| POST | `/api/sessions/{id}/import-to-mnemosyne` | 导入忆界树 |

## 技术栈

Python 3.11+ / FastAPI / SQLite / Pydantic V2 / httpx / ddgs / Stability AI

## 项目结构

```
mnemosyne-forge/
├── app/
│   ├── server.py      # FastAPI 入口
│   ├── auth.py        # 账号系统
│   ├── config.py      # 配置读取
│   ├── llm_client.py  # LLM 调用（支持多 provider、Agent 路由）
│   ├── db.py          # SQLite
│   ├── oc_models.py   # 数据模型
│   ├── oc_session.py  # Orchestrator
│   ├── oc_guide.py    # Guide Agent
│   ├── oc_designer.py # Designer Agent
│   ├── oc_consistency.py  # Consistency Agent
│   ├── oc_export.py   # Export Agent
│   ├── oc_search.py   # Search Agent
│   ├── oc_world.py    # 世界观生成
│   ├── oc_image_gen.py    # Stability AI 生图
│   ├── oc_voice_gen.py    # 声音匹配
│   └── mnemosyne_bridge.py # 忆界树桥接
├── web/               # 前端
├── config.yaml
└── run_dev.ps1
```
