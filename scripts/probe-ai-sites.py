#!/usr/bin/env python3
"""Probe AI/social sites through real VLESS-over-WebSocket subscription nodes.

The probe performs the same three network layers as a client:
Cloudflare entry TLS -> WebSocket/VLESS tunnel -> target-site TLS/HTTP.
It never prints or writes the subscription token or UUID.
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import json
import os
import re
import ssl
import struct
import subprocess
import time
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

try:
    import websocket
except ImportError as error:  # pragma: no cover - operator-facing dependency check
    raise SystemExit("missing dependency: python3 -m pip install websocket-client") from error


DEFAULT_TARGETS = {
    "google": ("google.com", "/"),
    "youtube": ("www.youtube.com", "/"),
    "x": ("x.com", "/"),
    "grok": ("grok.com", "/"),
    "xai-api": ("api.x.ai", "/v1/models"),
    "chatgpt": ("chatgpt.com", "/"),
    "openai-api": ("api.openai.com", "/v1/models"),
    "claude": ("claude.ai", "/"),
    "anthropic-api": ("api.anthropic.com", "/v1/models"),
    "gemini": ("gemini.google.com", "/"),
    "gemini-api": ("generativelanguage.googleapis.com", "/v1beta/models"),
    "tiktok": ("www.tiktok.com", "/"),
    "instagram": ("www.instagram.com", "/"),
    "facebook": ("www.facebook.com", "/"),
    "reddit": ("www.reddit.com", "/"),
    "discord": ("discord.com", "/"),
}


@dataclass(frozen=True)
class Node:
    index: int
    label: str
    entry_ip: str
    entry_port: int
    user_id: str
    host: str
    sni: str
    path: str


@dataclass
class ProbeResult:
    node: int
    label: str
    entry_ip: str
    entry_port: int
    target: str
    hostname: str
    tls: bool
    status: int
    verdict: str
    latency_ms: float
    error: str = ""


def _decode_subscription(payload: bytes) -> str:
    text = payload.decode("utf-8", errors="replace").strip()
    if "://" in text:
        return text
    normalized = re.sub(r"\s+", "", text)
    normalized += "=" * ((4 - len(normalized) % 4) % 4)
    return base64.b64decode(normalized).decode("utf-8")


def _token_from_remote_kv(namespace_id: str, project_dir: str) -> str:
    process = subprocess.run(
        [
            "npx", "--yes", "wrangler@latest", "kv", "key", "get", "config.json",
            f"--namespace-id={namespace_id}", "--remote",
        ],
        cwd=project_dir,
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    start = process.stdout.find("{")
    if process.returncode or start < 0:
        raise RuntimeError(f"unable to read remote config.json: {process.stderr[-300:]}")
    config = json.loads(process.stdout[start:])
    token = str(config.get("优选订阅生成", {}).get("TOKEN", ""))
    if not token:
        raise RuntimeError("config.json does not contain subscription TOKEN")
    return token


def load_nodes(subscription_url: str, limit: int, timeout: float) -> list[Node]:
    request = urllib.request.Request(subscription_url, headers={"User-Agent": "v2rayN/ai-compatibility-probe"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        subscription = _decode_subscription(response.read())
    nodes: list[Node] = []
    for line in subscription.splitlines():
        line = line.strip()
        if not line.lower().startswith("vless://"):
            continue
        parsed = urllib.parse.urlsplit(line)
        query = urllib.parse.parse_qs(parsed.query)
        security = query.get("security", [""])[0].lower()
        transport = query.get("type", [""])[0].split("&", 1)[0].lower()
        if security != "tls" or transport != "ws":
            continue
        host = query.get("host", [query.get("sni", [""])[0]])[0]
        sni = query.get("sni", [host])[0]
        path = urllib.parse.unquote(query.get("path", ["/"])[0])
        if not parsed.hostname or not parsed.port or not parsed.username or not host:
            continue
        label = urllib.parse.unquote(parsed.fragment or f"node-{len(nodes) + 1}")
        nodes.append(Node(len(nodes) + 1, label, parsed.hostname, parsed.port, parsed.username, host, sni, path))
        if len(nodes) >= limit:
            break
    if not nodes:
        raise RuntimeError("subscription contains no supported VLESS + WS + TLS nodes")
    return nodes


def _vless_header(user_id: str, hostname: str, port: int = 443) -> bytes:
    host = hostname.encode("idna")
    if len(host) > 255:
        raise ValueError("target hostname is too long")
    return (
        b"\x00"
        + uuid.UUID(user_id).bytes
        + b"\x00"  # option length
        + b"\x01"  # TCP
        + struct.pack("!H", port)
        + b"\x02"  # domain-name address
        + bytes([len(host)])
        + host
    )


def probe(node: Node, target_name: str, hostname: str, path: str, timeout: float) -> ProbeResult:
    started = time.perf_counter()
    ws = None
    try:
        ws = websocket.create_connection(
            f"wss://{node.entry_ip}:{node.entry_port}{node.path}",
            host=node.host,
            timeout=timeout,
            sslopt={"cert_reqs": ssl.CERT_NONE, "server_hostname": node.sni},
            http_proxy_host=None,
        )
        ws.send_binary(_vless_header(node.user_id, hostname))

        incoming = ssl.MemoryBIO()
        outgoing = ssl.MemoryBIO()
        context = ssl.create_default_context()
        tls = context.wrap_bio(incoming, outgoing, server_side=False, server_hostname=hostname)
        first_response = True
        deadline = time.time() + timeout

        def flush_tls() -> None:
            while True:
                data = outgoing.read()
                if not data:
                    return
                ws.send_binary(data)

        def receive_tls() -> None:
            nonlocal first_response
            data = ws.recv()
            if isinstance(data, str):
                data = data.encode()
            if not data:
                raise ConnectionError("tunnel closed")
            if first_response:
                if len(data) < 2:
                    raise ConnectionError("short VLESS response header")
                option_length = data[1]
                data = data[2 + option_length :]
                first_response = False
            if data:
                incoming.write(data)

        while True:
            try:
                tls.do_handshake()
                break
            except ssl.SSLWantReadError:
                flush_tls()
                if time.time() >= deadline:
                    raise TimeoutError("target TLS handshake timeout")
                receive_tls()
        flush_tls()

        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {hostname}\r\n"
            "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36\r\n"
            "Accept: text/html,application/json,*/*\r\n"
            "Connection: close\r\n\r\n"
        ).encode()
        tls.write(request)
        flush_tls()

        plaintext = bytearray()
        while len(plaintext) < 128 * 1024 and time.time() < deadline:
            try:
                chunk = tls.read(64 * 1024)
                if not chunk:
                    break
                plaintext.extend(chunk)
                if b"\r\n\r\n" in plaintext:
                    break
            except ssl.SSLWantReadError:
                receive_tls()
            except ssl.SSLZeroReturnError:
                break

        match = re.match(rb"HTTP/\d(?:\.\d)?\s+(\d+)", bytes(plaintext))
        status = int(match.group(1)) if match else 0
        if 200 <= status < 400:
            verdict = "pass"
        elif 400 <= status < 500:
            verdict = "reachable_restricted"
        else:
            verdict = "fail"
        return ProbeResult(
            node.index,
            node.label,
            node.entry_ip,
            node.entry_port,
            target_name,
            hostname,
            True,
            status,
            verdict,
            round((time.perf_counter() - started) * 1000, 1),
        )
    except Exception as error:  # noqa: BLE001 - each target must produce a result
        return ProbeResult(
            node.index,
            node.label,
            node.entry_ip,
            node.entry_port,
            target_name,
            hostname,
            False,
            0,
            "fail",
            round((time.perf_counter() - started) * 1000, 1),
            str(error)[:200],
        )
    finally:
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass


def summarize(nodes: list[Node], results: list[ProbeResult]) -> dict:
    by_target: dict[str, dict] = {}
    for name in DEFAULT_TARGETS:
        rows = [result for result in results if result.target == name]
        if not rows:
            continue
        by_target[name] = {
            "pass": sum(row.verdict == "pass" for row in rows),
            "reachable_restricted": sum(row.verdict == "reachable_restricted" for row in rows),
            "fail": sum(row.verdict == "fail" for row in rows),
            "total": len(rows),
        }
    by_node = []
    for node in nodes:
        rows = [result for result in results if result.node == node.index]
        by_node.append(
            {
                "node": node.index,
                "label": node.label,
                "entry_ip": node.entry_ip,
                "entry_port": node.entry_port,
                "pass": sum(row.verdict == "pass" for row in rows),
                "reachable_restricted": sum(row.verdict == "reachable_restricted" for row in rows),
                "fail": sum(row.verdict == "fail" for row in rows),
                "total": len(rows),
            }
        )
    return {
        "generated_at": int(time.time() * 1000),
        "nodes": len(nodes),
        "targets": len({result.target for result in results}),
        "checks": len(results),
        "pass": sum(result.verdict == "pass" for result in results),
        "reachable_restricted": sum(result.verdict == "reachable_restricted" for result in results),
        "fail": sum(result.verdict == "fail" for result in results),
        "by_target": by_target,
        "by_node": by_node,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subscription-url", default=os.environ.get("EDGETUNNEL_SUBSCRIPTION_URL", ""))
    parser.add_argument("--host", default="mysimivv.pages.dev")
    parser.add_argument("--namespace-id", default="9471531f9f194116970143c0ff4e305e")
    parser.add_argument("--nodes", type=int, default=20)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=25)
    parser.add_argument("--targets", default=",".join(DEFAULT_TARGETS))
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"
    if args.subscription_url:
        subscription_url = args.subscription_url
    else:
        project_dir = str(Path(__file__).resolve().parents[1])
        token = _token_from_remote_kv(args.namespace_id, project_dir)
        subscription_url = f"https://{args.host}/sub?token={urllib.parse.quote(token)}"

    selected_targets = [name.strip() for name in args.targets.split(",") if name.strip()]
    unknown = [name for name in selected_targets if name not in DEFAULT_TARGETS]
    if unknown:
        raise SystemExit(f"unknown targets: {', '.join(unknown)}")

    nodes = load_nodes(subscription_url, max(1, min(40, args.nodes)), args.timeout)
    tasks = [
        (node, name, *DEFAULT_TARGETS[name])
        for node in nodes
        for name in selected_targets
    ]
    results: list[ProbeResult] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(16, args.workers))) as executor:
        futures = [
            executor.submit(probe, node, name, hostname, path, args.timeout)
            for node, name, hostname, path in tasks
        ]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda result: (result.node, result.target))

    report = {"summary": summarize(nodes, results), "results": [asdict(result) for result in results]}
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    print(output)
    return 1 if report["summary"]["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
