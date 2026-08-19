#!/usr/bin/env python3
"""Athena knowledge-shelf CLI — thin wrapper over the HTTP API (docs/api/).
Retrieval's async poll is closed inside `ask`; caller gets clean markdown on
stdout. Stdlib only. Env: ATHENA_BASE_URL, ATHENA_PROJECT_ID, ATHENA_API_KEY,
ATHENA_RETRIEVE_TIMEOUT.

K8s: 在 pod 内运行且未设 ATHENA_BASE_URL 时，优先用 k8s 注入的 Service
发现变量 `ATHENA_API_SERVICE_HOST` / `ATHENA_API_SERVICE_PORT` 拼出直连地址
（同命名空间 pod 自动注入，与 k8s 环境一致，Service 改名/迁命名空间自动跟随）；
env 缺失时退到 ClusterDNS `athena-api.secflow-ns.svc.cluster.local:8000`。
均带 `/api/athena` 前缀（CLI 走 base_url+path 裸拼接，故前缀并入 base_url；
直连 Service 是 plain HTTP，不经 ingress 自签证书）。仅需设 ATHENA_PROJECT_ID。"""

# 命令 ↔ API 映射 ({pid}=project id,取自 ATHENA_PROJECT_ID;路径均货架相对,如 业务知识/模块A/登录鉴权.md):
#   ask "<MESSAGE>"                             → POST /projects/{pid}/retrieve  (+轮询 GET .../retrieve/tasks/{id})

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


_CONFIG: dict = {}


def _base_url() -> str:
    configured = _CONFIG.get("base_url") or os.environ.get("ATHENA_BASE_URL")
    if configured:
        return configured.rstrip("/")
    # K8s pod: 优先用 kubelet 给同命名空间 pod 注入的 Service 发现变量
    # （ATHENA_API_SERVICE_HOST/PORT），与 k8s 环境一致，Service 改名/迁命名空间自动跟随。
    # 仅在 env 缺失时退到 ClusterDNS（写死 <svc>.<ns>.svc.cluster.local）。
    if os.environ.get("KUBERNETES_SERVICE_HOST"):
        host = os.environ.get("ATHENA_API_SERVICE_HOST")
        port = os.environ.get("ATHENA_API_SERVICE_PORT") or "8000"
        if host:
            return f"http://{host}:{port}/api/athena"
        return "http://athena-api.secflow-ns.svc.cluster.local:8000/api/athena"
    return "http://127.0.0.1:8000"


def _auth_headers() -> dict[str, str]:
    # 调用方标识：默认 athena-skill，agent 可用 ATHENA_CALLER 覆盖自报家门。
    headers = {"X-Athena-Caller": os.environ.get("ATHENA_CALLER", "athena-skill")}
    key = _CONFIG.get("api_key") or os.environ.get("ATHENA_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    sys.exit(code)


def _request(method: str, path: str, *, body: dict | None = None,
             query: dict | None = None, raw: bytes | None = None,
             content_type: str | None = None) -> tuple[int, dict | list | str]:
    """Return (status, parsed_json_or_text). Raises on connection failure.

    ``body`` → JSON; ``raw``+``content_type`` → arbitrary bytes (multipart 等).
    """
    url = _base_url() + path
    if query:
        url = f"{url}?{urllib.parse.urlencode(query, doseq=True)}"
    data = None
    headers = _auth_headers()
    if raw is not None:
        data = raw
        if content_type:
            headers["Content-Type"] = content_type
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
        return status, _parse_err(raw)
    except urllib.error.URLError as exc:
        _die(f"athena: 服务未运行或不可达 ({_base_url()}): {exc.reason}", 2)
    status = resp.status  # type: ignore[possibly-undefined]
    return status, _parse_body(raw)


def _parse_body(raw: bytes) -> dict | list | str:
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return text


def _parse_err(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace")
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and "detail" in obj:
            return str(obj["detail"])
        return text
    except (json.JSONDecodeError, ValueError):
        return text or "(no body)"


def _check_http(status: int, payload: object) -> None:
    if status >= 400:
        detail = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        _die(f"athena: HTTP {status}: {detail}", 1 if status < 500 else 2)


def _project(arg: str | None) -> str:
    pid = arg or os.environ.get("ATHENA_PROJECT_ID")
    if not pid:
        _die("athena: 缺少 project_id。设置 ATHENA_PROJECT_ID 环境变量或传 --project。", 1)
    return pid


# --- subcommands ---------------------------------------------------------

# def cmd_projects(_args: argparse.Namespace) -> int:
#     items: list = []
#     cursor: str | None = None
#     while True:
#         status, payload = _request("GET", "/projects", query={"cursor": cursor} if cursor else None)
#         _check_http(status, payload)
#         if isinstance(payload, dict):
#             items.extend(payload.get("items", []))
#             cursor = payload.get("next_cursor")
#             if not cursor:
#                 break
#         elif isinstance(payload, list):  # bare-array fallback
#             items.extend(payload)
#             break
#         else:
#             break
#     if not items:
#         print("(无项目)")
#         return 0
#     for it in items:
#         pid = it.get("project_id", "?")
#         name = it.get("name", "?")
#         st = it.get("initialization_status", "?")
#         domain = it.get("domain")
#         tail = f" ({domain})" if domain else ""
#         print(f"{pid} | {name} | {st}{tail}")
#     return 0


# def cmd_shelf(args: argparse.Namespace) -> int:
#     pid = _project(args.project)
#     status, payload = _request("GET", f"/projects/{pid}/knowledge/index",
#                                query={"dir": args.dir or "", "recursive": "true" if args.recursive else "false"})
#     _check_http(status, payload)
#     _print_index(payload, indent=0)
#     return 0
#
#
# def _print_index(node: dict, indent: int) -> None:
#     pad = "  " * indent
#     for d in node.get("directories", []):
#         cnt = d.get("document_count", 0)
#         print(f"{pad}{d.get('path', d.get('name', '?'))}/ ({cnt} docs)")
#         if d.get("children"):
#             _print_index(d, indent + 1)
#     for doc in node.get("documents", []):
#         path = doc.get("path", "?")
#         desc = doc.get("description") or ""
#         topics = doc.get("topic") or []
#         ttag = f" [{', '.join(topics)}]" if topics else ""
#         desc_part = f" — {desc}" if desc else ""
#         print(f"{pad}- {path}{desc_part}{ttag}")
#
#
# def cmd_read(args: argparse.Namespace) -> int:
#     pid = _project(args.project)
#     status, payload = _request("GET", f"/projects/{pid}/knowledge/file",
#                                query={"path": args.path})
#     _check_http(status, payload)
#     if isinstance(payload, dict):
#         sys.stdout.write(payload.get("content", ""))
#         if not payload.get("content", "").endswith("\n"):
#             sys.stdout.write("\n")
#     return 0
#
#
# def cmd_concepts(args: argparse.Namespace) -> int:
#     pid = _project(args.project)
#     status, payload = _request("GET", f"/projects/{pid}/knowledge/concepts",
#                                query={"query": args.query})
#     _check_http(status, payload)
#     if not isinstance(payload, dict):
#         return 0
#     if payload.get("status") != "available":
#         print(f"(concept index {payload.get('status', 'unavailable')})")
#         return 0
#     matches = payload.get("matches", [])
#     if not matches:
#         print("(无匹配)")
#         return 0
#     for m in matches:
#         aliases = m.get("aliases", [])
#         head = aliases[0] if aliases else m.get("group_id", "?")
#         for mention in m.get("mentions", []):
#             print(f"{head} → {mention.get('document_path', '?')}")
#     return 0


def cmd_ask(args: argparse.Namespace) -> int:
    pid = _project(args.project)
    message = args.message.strip()
    if not message:
        _die("athena: 问题不能为空", 1)
    status, payload = _request("POST", f"/projects/{pid}/retrieve",
                                body={"message": message})
    _check_http(status, payload)
    task_id = payload.get("retrieval_task_id") if isinstance(payload, dict) else None
    if not task_id:
        _die(f"athena: 未返回 task id: {payload}", 2)

    timeout = int(os.environ.get("ATHENA_RETRIEVE_TIMEOUT", "180"))
    deadline = time.monotonic() + timeout
    backoff = 1.0
    while True:
        status, payload = _request("GET", f"/projects/{pid}/retrieve/tasks/{task_id}")
        _check_http(status, payload)
        st = payload.get("status") if isinstance(payload, dict) else None
        if st == "completed":
            content = payload.get("content", "")
            sys.stdout.write(content)
            if not content.endswith("\n"):
                sys.stdout.write("\n")
            print(f"task_id={task_id}", file=sys.stderr)
            return 0
        if st == "failed":
            err = payload.get("error_class", "unknown")
            _die(f"athena: 检索失败 ({err})", 1)
        if time.monotonic() >= deadline:
            _die(f"athena: 检索超时 ({timeout}s),task_id={task_id}", 2)
        time.sleep(min(backoff, 5.0))
        backoff *= 2
    # unreachable


# def cmd_raw(args: argparse.Namespace) -> int:
#     pid = _project(args.project)
#     body = {
#         "retrieval_task_id": args.task_id,
#         "knowledge_ref": {"scope": "project", "path": args.knowledge_path},
#         "raw_ref": args.raw_ref,
#         "content_budget_tokens": args.budget,
#     }
#     status, payload = _request("POST", f"/projects/{pid}/retrieve/raw", body=body)
#     _check_http(status, payload)
#     if not isinstance(payload, dict):
#         return 0
#     content = payload.get("content", "")
#     sys.stdout.write(content)
#     if not content.endswith("\n"):
#         sys.stdout.write("\n")
#     if payload.get("truncated"):
#         print(f"\n(truncated, used_tokens={payload.get('used_tokens', '?')})", file=sys.stderr)
#     return 0
#
#
# def _multipart(fields: dict[str, str | None], file_field: str,
#                filename: str, content: bytes) -> tuple[bytes, str]:
#     """Build a multipart/form-data body (stdlib only). Returns (body, content_type)."""
#     boundary = "----athena" + os.urandom(16).hex()
#     crlf = b"\r\n"
#     out: list[bytes] = []
#     for name, value in fields.items():
#         if value is None:
#             continue
#         out.append(f"--{boundary}".encode() + crlf)
#         out.append(f'Content-Disposition: form-data; name="{name}"'.encode() + crlf + crlf)
#         out.append(value.encode("utf-8") + crlf)
#     out.append(f"--{boundary}".encode() + crlf)
#     out.append(
#         f'Content-Disposition: form-data; name="{file_field}"; '
#         f'filename="{filename}"'.encode() + crlf
#     )
#     out.append(b"Content-Type: text/markdown; charset=utf-8" + crlf + crlf)
#     out.append(content + crlf)
#     out.append(f"--{boundary}--".encode() + crlf)
#     return b"".join(out), f"multipart/form-data; boundary={boundary}"
#
#
# def cmd_remember(args: argparse.Namespace) -> int:
#     pid = _project(args.project)
#     content = sys.stdin.read()
#     if not content:
#         _die("athena: remember 需从 stdin 读入正文", 1)
#     # 文件名决定 ext 派发；CLI 只递 markdown，故确保 .md 后缀（passthrough）。
#     filename = args.path or "upload.md"
#     if os.path.splitext(filename)[1].lower() not in (".md", ".txt"):
#         filename = f"{filename}.md"
#     fields: dict[str, str | None] = {
#         "classes": ",".join(args.classes) if args.classes else None,
#         "source": args.source,
#     }
#     body, ctype = _multipart(fields, "file", filename, content.encode("utf-8"))
#     status, payload = _request(
#         "POST", f"/projects/{pid}/gate/remember",
#         raw=body, content_type=ctype,
#     )
#     _check_http(status, payload)
#     task_id = payload.get("intake_task_id") if isinstance(payload, dict) else None
#     if not task_id:
#         _die(f"athena: 未返回 intake_task_id: {payload}", 2)
#
#     timeout = int(os.environ.get("ATHENA_INTAKE_TIMEOUT", "300"))
#     deadline = time.monotonic() + timeout
#     backoff = 1.0
#     while True:
#         status, payload = _request("GET", f"/projects/{pid}/gate/tasks/{task_id}")
#         _check_http(status, payload)
#         st = payload.get("status") if isinstance(payload, dict) else None
#         if st == "succeeded":
#             verdict = payload.get("verdict", "?")
#             if verdict == "admit":
#                 raw_path = payload.get("raw_path", "")
#                 classes = payload.get("classes") or []
#                 print(f"admit → {raw_path} (classes: {', '.join(classes) or '—'})")
#             else:
#                 print(f"reject → {payload.get('reason', '(no reason)')}")
#             print(f"task_id={task_id}", file=sys.stderr)
#             return 0
#         if st == "failed":
#             err = payload.get("error_class") or payload.get("reason") or "unknown"
#             _die(f"athena: 门禁失败 ({err})", 1)
#         if time.monotonic() >= deadline:
#             _die(f"athena: 门禁超时 ({timeout}s),task_id={task_id}", 2)
#         time.sleep(min(backoff, 5.0))
#         backoff *= 2


# --- argparse ------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="athena",
        description="Athena 知识货架 CLI(给 Claude Code skill 用)",
    )
    parser.add_argument("--base-url", default=None,
                        help="Athena server URL(默认 ATHENA_BASE_URL；未设时 K8s pod 内用注入的 athena-api Service 地址，本地 http://127.0.0.1:8000)")
    parser.add_argument("--api-key", default=None,
                        help="可选鉴权(默认 ATHENA_API_KEY)")
    parser.add_argument("--project", default=None,
                        help="项目 ID(默认 ATHENA_PROJECT_ID)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # projects 命令已注释:强制从 ATHENA_PROJECT_ID 取 pid。
    # p = sub.add_parser("projects", help="列出所有项目")
    # p.set_defaults(func=cmd_projects)

    # 暂时屏蔽:只保留 ask。其余命令连同函数一并注释,需要时解注即可。
    # p = sub.add_parser("shelf", help="浏览知识货架目录(结构化)")
    # p.add_argument("dir", nargs="?", default="", help="货架相对目录(默认根)")
    # p.add_argument("--recursive", action="store_true", help="返回整棵子树")
    # p.set_defaults(func=cmd_shelf)

    # p = sub.add_parser("read", help="读单篇 .md 文档正文")
    # p.add_argument("path", help="货架相对路径,如 业务知识/模块A/登录鉴权.md")
    # p.set_defaults(func=cmd_read)

    # p = sub.add_parser("concepts", help="概念检索")
    # p.add_argument("query", help="检索词")
    # p.set_defaults(func=cmd_concepts)

    p = sub.add_parser("ask", help="自然语言检索(内部轮询,一次出结果)")
    p.add_argument("message", help="检索问题")
    p.set_defaults(func=cmd_ask)

    # p = sub.add_parser("raw", help="下钻已完成检索的 raw 证据")
    # p.add_argument("task_id", help="athena ask 末行 stderr 的 task_id")
    # p.add_argument("knowledge_path", help="检索答案证据链里的项目知识路径")
    # p.add_argument("raw_ref", help="raw/*.md 相对路径")
    # p.add_argument("--budget", type=int, default=1600, help="content_budget_tokens (1..32000, 默认 1600)")
    # p.set_defaults(func=cmd_raw)

    # p = sub.add_parser("remember", help="沉淀知识走门禁入库(POST /gate/remember,内部轮询)")
    # p.add_argument("path", nargs="?", default="", help="上传文件名(可省略,默认 upload.md)")
    # p.add_argument("--source", help="来源标注: 文档|工具|经验")
    # p.add_argument("--classes", nargs="*", help="建议分类(可选)")
    # p.set_defaults(func=cmd_remember)

    args = parser.parse_args(argv)
    _CONFIG.update(base_url=args.base_url, api_key=args.api_key)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
