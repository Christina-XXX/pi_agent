# DeepSeek Agent

一个基于 [DeepSeek API](https://api-docs.deepseek.com/zh-cn/) 的**通用 AI 智能体**，开箱即用、零第三方依赖，支持工具调用（读写文件、执行命令、搜索、抓取网页），并可根据任务自动选择模型。

## ✨ 特性

- 🚀 零依赖：只用 Python 3 标准库，克隆即用
- 🧰 工具调用：读写文件、列目录、正则搜索、执行 shell、抓取网页
- 🧠 自动选模型：`auto` 模式按任务自动在 `deepseek-flash` / `deepseek-v4-pro` 之间选择，也可手动指定
- 💬 两种模式：单次任务 与 交互式对话（`-i`）
- 🔌 可扩展：把自定义工具丢进 `tools/` 目录即可自动加载
- 🔐 安全：API Key 通过环境变量 / `.env` 注入，绝不入库

## 📦 快速开始

```bash
# 1. 克隆仓库
git clone <你的仓库地址>
cd deepseek-agent

# 2. 配置 API Key（二选一）
cp .env.example .env      # 然后编辑 .env 填入你的 key
# 或者
export DEEPSEEK_API_KEY=sk-xxxx

# 3. 运行（无需安装任何依赖）
python agent.py "帮我看看当前目录有哪些文件，统计代码行数"
```

### 常用命令

```bash
python agent.py "写一个快速排序并跑通测试"          # 默认 auto 选模型
python agent.py -m pro "证明根号2是无理数"           # 强制用 pro 推理
python agent.py -m flash "总结这个网页 https://..."   # 强制用 flash
python agent.py -i                                 # 交互式对话
python agent.py --models                           # 查看可用模型
python agent.py --help                             # 全部参数
```

也可以这样启动：

```bash
python -m deepseek_agent "你的任务"
```

## 🧰 内置工具

| 工具 | 说明 |
|------|------|
| `read_file` / `write_file` | 读写文件 |
| `list_dir` | 列出目录 |
| `search_files` | 正则搜索文件内容 |
| `shell` | 执行命令行（默认需确认，`-y` 自动批准） |
| `fetch_url` | 抓取网页文本 |

## 🔌 自定义工具

在项目根目录的 `tools/` 文件夹放入 `.py` 文件即可，参考 [`tools/example_tools.py`](tools/example_tools.py)：

```python
from deepseek_agent.tools import REGISTRY

@REGISTRY.tool(
    name="current_time",
    description="获取当前时间。",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
def current_time():
    from datetime import datetime
    return datetime.now().isoformat()
```

## ⚙️ 模型说明

DeepSeek 当前模型（详见[模型与价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing)）：

| 别名 | 真实模型 | 特点 |
|------|----------|------|
| `flash` | `deepseek-flash` | 默认。快、便宜，支持工具调用 / 思考 / 图像理解 |
| `pro` | `deepseek-v4-pro` | 推理更强，更贵，适合复杂推理任务 |
| `auto` | 自动路由 | 命中“证明/推理/算法/复杂分析”等关键词时用 pro，否则用 flash |

## 🔐 安全提示

- **切勿把 `.env` 或真实 API Key 提交到仓库**（`.env` 已在 `.gitignore` 中）。
- `shell` 工具能力强大，请只在可信环境使用；`--no-shell` 可完全禁用。

## 🤝 团队协作（同一仓库）

1. 由一名成员创建 GitHub 仓库并把代码推上去（见下方“发布到 GitHub”）。
2. 其他成员 `git clone` 后，各自用**自己的** API Key（`cp .env.example .env`）。
3. 大家一起改代码、加工具，通过 Git 分支 + Pull Request 协作。

## 🌍 发布到 GitHub

本机已 `git init` 并完成首次提交。推送到 GitHub：

```bash
# 1) 在 github.com 手动新建一个空仓库（如 deepseek-agent，不要勾选 README/.gitignore）
# 2) 配置身份并推送
git remote add origin https://github.com/<你的用户名>/deepseek-agent.git
git branch -M main
git push -u origin main
```

> 提示：如本机访问 GitHub 不稳定，可使用 `https://ghproxy.com/` 等镜像或科学上网；也可以先在网页上创建仓库后，用 GitHub Desktop 推送。

## 📁 项目结构

```
deepseek-agent/
├── agent.py              # 入口
├── deepseek_agent/       # 核心包
│   ├── cli.py            # 命令行
│   ├── client.py         # DeepSeek API 客户端（流式）
│   ├── config.py         # 配置与模型路由
│   ├── loop.py           # Agent 主循环
│   ├── tools.py          # 工具系统
│   └── prompts.py        # 系统提示词
├── tools/                # 自定义工具（自动加载）
├── .env.example          # 配置模板
└── README.md
```

## 📄 License

[MIT](LICENSE)
