---
name: athena-skill
description: 当无法通过上下文、代码、记忆获取所需信息时，用 ask 检索 Athena 安全知识库(威胁分析/利用手法/接口规则/踩坑纠偏)。触发：对模块动手挖洞前、PoC 跑不通、需查接口权限或调用前提、用户说"查知识库"。
---

# 前置

- **server 必须在跑**；`ATHENA_PROJECT_ID` 环境变量必须已设(pid 从中取)。
- Bash 里裸 `athena` 不在 PATH：每条命令先设 `A=<路径>/athena.py`，再用 `$A` 代替下文的 `athena`。
  路径：in-repo `athena-skill/athena.py`；用户 skills `~/.claude/skills/athena-skill/athena.py`。
- 配置项(base-url / project / caller)见 [CLI.md](./CLI.md)。

# 检索

问题用自然语言写清楚：带上模块名、API 名、权限名、报错原文。慢且耗 agent runtime，**一个问题只问一次**。

**CLI**（推荐，内部轮询一次出结果）：

```
athena ask "<问题>"
```

**curl**（无 CLI 时；需自己轮询任务）：

```bash
B=${ATHENA_BASE_URL:-http://127.0.0.1:8000}
C="X-Athena-Caller: ${ATHENA_CALLER:-athena-skill}"
P=$ATHENA_PROJECT_ID
TID=$(curl -s -X POST "$B/projects/$P/retrieve" -H 'Content-Type: application/json' -H "$C" \
  -d '{"message":"<问题>"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["retrieval_task_id"])')
curl -s "$B/projects/$P/retrieve/tasks/$TID"     # 轮询到 status=completed 读 .content(自行加 sleep/重试)
```

# 货架结构（帮助理解答案出处）

```
业务知识/
  业务威胁知识/模块/<模块>/  — 业务功能 / 安全威胁 / 攻击假设 / 攻击面 / 信任边界 / 威胁模型
  作业知识/模块/<模块>/      — 接口操作规则（权限/调用前提/配置，动手前必查）
  纠偏知识/模块/<模块>/      — 安全要求、已知误区、纠正认知
经验类知识/
  利用手法/     — 已实测的利用路径
  环境信息/     — 版本/权限/设备/错误码约束
  脚手架/       — 可复用调用骨架
  PoC-EXP/     — PoC / Exp
  成败经验/     — 走通或走死的路径
漏洞挖掘知识/   — 挖洞方法论
raw/            — 原始 API 文档（追溯出处用）
```
