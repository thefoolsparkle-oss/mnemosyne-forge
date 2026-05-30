# 造枝 Mnemosyne Forge

> 忆界 / Mnemosyne Realm 生态下的 AI 原创角色创作系统

造枝是一个本地运行的 AI 原创角色创作工具。通过多轮对话，将你的模糊角色灵感逐步转化为结构化 OC 草稿，并导出为 Character Card V2 标准角色卡。

## 当前版本

**v0.1** — 核心对话闭环

- 输入角色灵感 → AI 智能追问 → 草稿实时更新 → 导出标准角色卡
- 多 Agent 协作：Guide（采访追问）、Designer（设定抽取）、Consistency（一致性检查）、Export（角色卡生成）

## 安装

```powershell
# 1. 克隆或进入项目目录
cd mnemosyne-forge

# 2. 安装依赖
py -m pip install -r requirements.txt
```

## 配置 API Key

在项目根目录创建 `.env` 文件，填入你的 API Key：

```env
# 至少配置一个
DEEPSEEK_API_KEY=sk-your-key-here
OPENAI_API_KEY=sk-your-key-here
KIMI_API_KEY=sk-your-key-here
```

默认使用 DeepSeek。在 `config.yaml` 中修改 `llm.default_provider` 切换模型。

支持的模型提供商：

| 提供商 | 所需环境变量 | 说明 |
|--------|-------------|------|
| deepseek | `DEEPSEEK_API_KEY` | DeepSeek Chat，默认 |
| openai | `OPENAI_API_KEY` | GPT-4o / GPT-4o-mini |
| kimi | `KIMI_API_KEY` | Moonshot v1 |

> Gemini 使用非标准 API 格式，v0.1 暂不原生支持。可通过 one-api / new-api 等代理工具将 Gemini 暴露为 OpenAI 兼容接口后使用。

## 启动

```powershell
.\run_dev.ps1
```

或手动启动：

```powershell
py -m uvicorn app.server:app --host 127.0.0.1 --port 8010 --reload
```

打开浏览器访问 http://127.0.0.1:8010

## 使用流程

1. 打开页面，输入你的角色灵感，例如：「一个被神抛弃后生活在现代都市的冷淡女性」
2. AI 会开始追问，帮你逐步补全角色设定
3. 右侧面板实时显示角色草稿的每个字段
4. 当角色设定足够完整时，点击「导出角色卡 V2」生成标准 JSON

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/api/sessions` | 创建创作会话 |
| POST | `/api/sessions/{id}/messages` | 发送消息 |
| GET | `/api/sessions/{id}/draft` | 获取角色草稿 |
| GET | `/api/sessions/{id}/messages` | 获取消息历史 |
| POST | `/api/sessions/{id}/export/card-v2` | 导出角色卡 |

## 技术栈

- Python 3.11+ / FastAPI / SQLite
- 原生 HTML + CSS + JavaScript
- Pydantic V2 / httpx / PyYAML

## 后续路线图

| 版本 | 内容 |
|------|------|
| v0.2 | 角色卡质量增强（自动生成开场白、示例对话、多版本问候语） |
| v0.3 | 多 Agent 架构强化（独立 Agent 实例、更精确的阶段判断） |
| v0.4 | 搜索增强创作（联网搜索素材并转化为创作灵感） |
| v0.5 | 世界观与世界书生成 |
| v0.6 | 与忆界树桥接（角色导入长期记忆聊天系统） |
| v0.7 | 角色画像生成 |
| v0.8 | 角色声音合成 |

## 项目结构

```
mnemosyne-forge/
├── app/               # 后端 Python 模块
│   ├── server.py      # FastAPI 入口
│   ├── config.py      # 配置读取
│   ├── llm_client.py  # LLM 调用封装
│   ├── db.py          # SQLite 数据库
│   ├── oc_models.py   # Pydantic 数据模型
│   ├── oc_session.py  # 创作会话管理（Orchestrator）
│   ├── oc_guide.py    # 引导 Agent
│   ├── oc_designer.py # 设定整理 Agent
│   ├── oc_consistency.py  # 一致性检查 Agent
│   ├── oc_export.py   # 角色卡导出 Agent
│   └── oc_*.py        # 预留模块（搜索、世界观、生图、声音、桥接）
├── web/               # 前端
│   ├── index.html
│   ├── app.js
│   └── style.css
├── data/              # SQLite 数据库（运行时生成）
├── exports/           # 导出的角色卡 JSON
├── config.yaml        # 项目配置
├── requirements.txt
└── run_dev.ps1
```
