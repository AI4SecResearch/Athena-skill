# Athena CLI 参考

`athena` 直接跑 `athena.py`(标准库,无依赖)。当前只用 `ask`,其余命令暂时屏蔽。命令↔API 映射见 `athena.py` 头部注释。

# 调用

`athena.py` 已可执行(shebang `python3`)。裸 `athena` 不在 PATH：每条 Bash 命令开头先把 `A` 指向 skill 目录里的 `athena.py` 绝对路径，再用 `$A` 代 `athena`。skill 在 Claude Code 标准位置，路径固定，不依赖 cwd：

```bash
A=~/.claude/skills/athena-skill/athena.py
# 开发态(in-repo)用源码相对路径：A=athena-skill/athena.py
# 若已把软链建到 PATH（ln -sf …/athena.py ~/.local/bin/athena）：A=athena

$A ask "<问题>"
```

# Config

默认 server `http://127.0.0.1:8000`；K8s pod 内未设 `ATHENA_BASE_URL` 时自动指向集群内 `athena-api` Service（`/api/athena` 前缀，plain HTTP，绕开 ingress 自签证书）。用 env 或 subcommand 前的全局 flag 覆盖:

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
