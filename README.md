# mubu-mcp — 幕布 MCP 服务器

> **把幕布（Mubu）大纲笔记接入任意 AI 助手**。读、搜、导出，以及最重要的：**Markdown 一键创建/写回幕布文档 —— 目录自动创建、文件名自动生成、内容真正落库。**

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![MCP](https://img.shields.io/badge/MCP-Model%20Context%20Protocol-6a5acd.svg)](https://modelcontextprotocol.io/)
[![幕布](https://img.shields.io/badge/幕布-mubu.com-2f9e44.svg)](https://mubu.com)

`mubu-mcp` 是一个基于 [Model Context Protocol](https://modelcontextprotocol.io/) 的服务器，通过官方网页版同款 API 与幕布通信，让 Claude、Cursor、**豆包（Doubao）** 等任意 MCP 宿主直接操作你的幕布大纲。

---

## ✨ 亮点（v1.1）

- **🎯 内容真正写入幕布** — 逆向实现官方网页版同款 `colla/events` 写入协议。官方 MCP 需「领航员（Max）」会员，本项目**普通账号即可用**，创建即落库、读回即验证。
- **📁 指定目录自动创建** — `folder_path="工作/项目A/子目录"` 已存在则复用，不存在则逐级自动创建。
- **🏷️ 文件名自动生成** — 不传 `name` 时自动生成 `mbmcp_20260916_121530` 格式，也可显式覆盖。
- **♻️ Upsert 同名去重** — 同目录同名文档存在则覆盖、不存在则创建，归档/同步零重复。
- **📝 Markdown Round-trip** — 标题、层级、复选框（`[x]`/`[ ]`）无损互转，导出支持 Markdown / OPML / FreeMind。
- **🔍 内容级搜索** — 按名称或文档正文搜索。
- **🗄️ 零配置缓存** — SQLite 内置开箱即用；可选 Redis / MongoDB / CosmosDB 适配器。
- **🧩 标准 MCP** — 工具 + 资源 + 提示词，适配任何 MCP 宿主（Claude Desktop / Cursor / 豆包 / 任意客户端）。

## 🚀 快速开始

```bash
# 1. 安装
pip install -e .

# 2. 配置凭据（仅需手机号+密码；member_id 自动生成，无需配置）
export MUBU_PHONE="你的手机号"
export MUBU_PASSWORD="你的密码"

# 3. 启动（stdio，供 MCP 宿主使用）
mubu-mcp

# 也可用 streamable HTTP（远程访问）
mubu-mcp --transport http --port 3000
```

或写入 `~/.workbuddy/.env.mubu`（`MUBU_PHONE` / `MUBU_PASSWORD`），服务器自动读取。

## 🤖 与豆包（Doubao）工作任务集成

豆包桌面客户端支持自定义 MCP 连接器，接入后即可在对话中直接指挥幕布。**全程 GUI 操作，约 3 分钟。**

### 第 1 步：安装并启动检查

```powershell
cd C:\你的路径\mcp_mubu
pip install -e . --no-build-isolation
mubu-mcp --version   # 能看到版本号即安装成功
```

### 第 2 步：准备凭据

连接器启动进程**不会自动读取项目 `.env`**，凭据必须以环境变量形式填进连接器。用手机号+密码即可，`MUBU_MEMBER_ID` 留空（v1.1 起自动生成）。

### 第 3 步：在豆包中注册连接器

1. 打开豆包桌面客户端并**登录**。
2. 点击左侧边栏 **「技能 · 连接器 · 伙伴」**（未登录时不显示）。
3. 进入 **「连接器」** 页面 → 右上角 **「+ 新建」** → **「新建自定义连接器」**。
4. 按下表填写：

| 字段 | 值 |
|------|-----|
| 服务器名称 | `mubu-mcp` |
| 传输类型 | **STDIO**（本地进程） |
| 命令 | `C:\你的路径\mcp_mubu\.venv\Scripts\mubu-mcp.exe`（指向实际安装路径） |
| 参数 | （留空） |

5. 添加环境变量：

| 环境变量 | 值 |
|----------|-----|
| `MUBU_PHONE` | 你的幕布手机号 |
| `MUBU_PASSWORD` | 你的幕布密码 |

6. 保存。若提示「连接器运行失败」，到连接器列表找到 `mubu-mcp` 点击 **「重新启动」**。

### 第 4 步：验证

在豆包对话中直接说：

- 「列出我幕布里有哪些文件夹和文档」
- 「把下面这段 Markdown 保存到幕布目录 `工作/周报`，文件名用 `周报_本周`」—— 目录不存在会自动创建
- 「把这篇文档内容写回幕布文档 xxx」（按 doc_id 更新）

AI 会自动调用 `mubu_*` 工具完成，返回文档 ID 与落库结果。

> 说明：自定义连接器依赖本机进程，仅在当前电脑可用；HTTP 传输方式需服务常驻（`mubu-mcp --transport http --port 3000` 后台运行后填 `http://localhost:3000/mcp`）。

## 🔧 MCP 工具

| 工具 | 说明 |
|------|------|
| `mubu_login` / `mubu_whoami` | 登录 / 查看认证状态 |
| `mubu_list` | 列出目录内容 |
| `mubu_create_folder` / `mubu_create_doc` | 创建目录 / 空文档 |
| `mubu_create_doc_from_markdown` | **Markdown 创建文档**：`name` 空自动命名，`folder_path` 自动建目录 |
| `mubu_upsert_doc_markdown` | **同名去重保存**：存在则覆盖，否则创建 |
| `mubu_save_doc_markdown` | **按 doc_id 写回**：空壳原地写入；已有内容自动重建并提示新 id |
| `mubu_get_doc` / `mubu_get_doc_raw` | 读取文档（Markdown / 原始 JSON） |
| `mubu_move` / `mubu_rename` / `mubu_delete` | 整理 |
| `mubu_search` | 按名称 / 正文搜索 |
| `mubu_export_markdown` / `mubu_export_opml` / `mubu_export_freeplane` | 导出 |
| `mubu_import_markdown` | Markdown → Mubu JSON（dry run） |
| `mubu_export_tree` | 导出整个目录树 |
| `mubu_cache_info` / `mubu_cache_clear` | 缓存管理 |

### 资源与提示词

- 资源：`mubu://status`（认证与缓存状态）、`mubu://doc/{doc_id}`（按 ID 取文档）
- 提示词：`mubu_setup_guide`（配置向导）、`mubu_work_with_doc`（加载文档编辑）、`mubu_sync_markdown`（导入 Markdown）

## 🔍 深入：写入协议（技术细节）

幕布文档内容无法通过 `create_doc` 的 content 参数写入（接口接受但恒为空文档）。本项目通过分析官方网页版请求，确定了真正的写入通道：

```
POST https://api2.mubu.com/v3/api/colla/events
```

- `memberId`：随机 16 位数字（与网页版每次会话一致），**无需人工获取**
- `version`：等于服务器当前 `baseVersion`（`document/edit/get` 返回），提交后 `latestVersion` 递增
- 事件类型：`create`（建根/追加子节点）、`update`（改根文本）、`nameChanged`（改文档名）
- 节点：10 位短随机 id + `<span>HTML</span>` 文本 + 毫秒时间戳

基于该协议，`mubu_save_doc_markdown` 采用三分支写回策略：

| 文档状态 | 策略 | doc_id |
|---|---|---|
| 空壳（无节点） | `create` 根节点原地写入 | 不变 |
| 有根无子 | `update` 根 + `create` 子节点 | 不变 |
| 已有子节点 | 删除 + 重建同名同目录 | 变化（返回消息提示新 id） |

## ⚠️ 已知边界

- 备注（`> 引用`）写入时暂不落库；复选框映射为幕布待办完成状态
- 已有子节点的文档无法原地全量替换（官方无可用 delete 事件），走删除+重建
- 图片/附件节点不支持 Markdown round-trip
- 非官方集成，使用与网页版相同的端点（仅供个人账号使用）

## 🗄️ 缓存后端

| 后端 | 安装 | 环境变量 |
|------|------|----------|
| **SQLite**（默认） | 内置 | `MUBU_CACHE_BACKEND=sqlite` |
| Redis | `pip install "mubu-mcp[redis]"` | `MUBU_REDIS_URL` 等 |
| MongoDB | `pip install "mubu-mcp[mongo]"` | `MUBU_MONGO_URI` 等 |
| CosmosDB | `pip install "mubu-mcp[cosmos]"` | `MUBU_COSMOS_ENDPOINT` 等 |

自定义后端：实现 `mubu_mcp.cache.base.CacheBackend` 抽象类即可（`get/set/delete/exists/clear`）。

## 🏗️ 项目结构

```
mubu-mcp/
├── pyproject.toml
├── README.md
└── src/mubu_mcp/
    ├── __main__.py          # CLI 入口
    ├── server.py            # MCP 服务器（工具/资源/提示词）
    ├── mubu_client.py       # 幕布 API 客户端（含 colla/events 写入）
    ├── mubu_convert.py      # Markdown / OPML / FreeMind 转换
    ├── mubu_config.py       # 配置与常量
    └── cache/               # 可插拔缓存（SQLite/Redis/Mongo/Cosmos）
```

## 🌱 Roadmap（欢迎 PR）

- [ ] 已有子节点文档的原地全量替换（破解 delete 事件）
- [ ] 备注（`> 引用`）落库
- [ ] 更多 MCP 宿主的一键配置脚本
- [ ] 豆包技能版（`mubu-mcp` skill）示例归档模板

## 📄 License

[MIT](LICENSE)

---

**用起来**：`pip install -e .` → 配好手机号密码 → 接进你的 AI 客户端，说一句「帮我把这份纪要归档到幕布」，剩下的交给 mubu-mcp。
