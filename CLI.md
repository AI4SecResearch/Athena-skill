# Athena CLI 参考

`athena` 直接跑 `athena.py`(标准库,无依赖)。当前只用 `ask`,其余命令暂时屏蔽。命令↔API 映射见 `athena.py` 头部注释。

# 调用

`athena.py` 已可执行(shebang `python3`)。每条 Bash 命令先 `A=<路径>`,再用 `$A` 代 `athena`:

```bash
A=athena-skill/athena.py; $A ask "<问题>"
```

路径:in-repo `athena-skill/athena.py`;用户 skills `~/.claude/skills/athena-skill/athena.py`。

# Config

默认 server `http://127.0.0.1:8000`。用 env 或 subcommand 前的全局 flag 覆盖:

| | env | flag |
|---|---|---|
| server URL | `ATHENA_BASE_URL` | `--base-url` |
| project id | `ATHENA_PROJECT_ID` | `--project` |
| 调用方标识 | `ATHENA_CALLER` | — |

`ATHENA_CALLER` 自报家门,进 `X-Athena-Caller` 头供查询观测过滤,默认 `athena-skill`;agent 想区分身份时覆盖(如 `argo/api`)。

pid 从 `ATHENA_PROJECT_ID` 取,环境变量没有就传 `--project <pid>`。server 必须在跑。

# 注

- `ask`:stdout 出结果,`task_id=...` 到 stderr(轮询在 CLI 内)。
- 4xx→exit 1、5xx→exit 2,`detail` 到 stderr;server 没起打印"服务未运行"。
