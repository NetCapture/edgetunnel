#!/usr/bin/env python3
"""Observe the real public egress IP behind each subscription entry node.

This performs Cloudflare entry TLS -> WebSocket -> VLESS -> target TLS and
requests cloudflare.com/cdn-cgi/trace through the tunnel. Subscription tokens
and UUIDs are used in memory and are never included in output.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import json
import os
import re
import ssl
import struct
import sys
import time
import urllib.parse
import uuid
from pathlib import Path


def load_ai_probe_module():
    path = Path(__file__).with_name("probe-ai-sites.py")
    spec = importlib.util.spec_from_file_location("edgetunnel_ai_probe", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


AI_PROBE = load_ai_probe_module()


def observe_egress(node, timeout: float) -> dict:
    started = time.perf_counter()
    websocket = None
    target = "cloudflare.com"
    try:
        websocket = AI_PROBE.websocket.create_connection(
            f"wss://{node.entry_ip}:{node.entry_port}{node.path}",
            host=node.host,
            timeout=timeout,
            sslopt={"cert_reqs": ssl.CERT_NONE, "server_hostname": node.sni},
            http_proxy_host=None,
        )
        target_bytes = target.encode()
        vless_header = (
            b"\x00"
            + uuid.UUID(node.user_id).bytes
            + b"\x00\x01"
            + struct.pack("!H", 443)
            + b"\x02"
            + bytes([len(target_bytes)])
            + target_bytes
        )
        websocket.send_binary(vless_header)

        incoming = ssl.MemoryBIO()
        outgoing = ssl.MemoryBIO()
        tls = ssl.create_default_context().wrap_bio(
            incoming,
            outgoing,
            server_side=False,
            server_hostname=target,
        )
        first_response = True
        deadline = time.time() + timeout

        def flush_tls() -> None:
            while True:
                data = outgoing.read()
                if not data:
                    return
                websocket.send_binary(data)

        def receive_tls() -> None:
            nonlocal first_response
            data = websocket.recv()
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

        tls.write(
            b"GET /cdn-cgi/trace HTTP/1.1\r\n"
            b"Host: cloudflare.com\r\n"
            b"User-Agent: Mozilla/5.0\r\n"
            b"Connection: close\r\n\r\n"
        )
        flush_tls()
        plaintext = bytearray()
        while len(plaintext) < 128 * 1024 and time.time() < deadline:
            try:
                chunk = tls.read(64 * 1024)
                if not chunk:
                    break
                plaintext.extend(chunk)
            except ssl.SSLWantReadError:
                try:
                    receive_tls()
                except ConnectionError:
                    break
            except (ssl.SSLZeroReturnError, ssl.SSLError):
                break

        response = bytes(plaintext)
        status_match = re.match(rb"HTTP/\d(?:\.\d)?\s+(\d+)", response)
        status = int(status_match.group(1)) if status_match else 0
        body = response.split(b"\r\n\r\n", 1)[-1].decode(errors="replace")
        fields = {
            key: value.strip()
            for key, value in re.findall(r"(?m)^([a-z]+)=(.*)$", body)
        }
        egress_ip = fields.get("ip", "")
        if status != 200 or not egress_ip:
            raise RuntimeError(f"invalid trace response: HTTP {status}")
        return {
            "node": node.index,
            "label": node.label,
            "entry_ip": node.entry_ip,
            "entry_port": node.entry_port,
            "egress_ip": egress_ip,
            "country": fields.get("loc", ""),
            "colo": fields.get("colo", ""),
            "status": status,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "error": "",
        }
    except Exception as error:  # noqa: BLE001 - each node must yield evidence
        return {
            "node": node.index,
            "label": node.label,
            "entry_ip": node.entry_ip,
            "entry_port": node.entry_port,
            "egress_ip": "",
            "country": "",
            "colo": "",
            "status": 0,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "error": str(error)[:200],
        }
    finally:
        if websocket is not None:
            try:
                websocket.close()
            except Exception:
                pass


def summarize(results: list[dict], minimum_unique: int) -> dict:
    distribution: dict[tuple[str, str, str], list[int]] = {}
    for result in results:
        if not result["egress_ip"]:
            continue
        key = (result["egress_ip"], result["country"], result["colo"])
        distribution.setdefault(key, []).append(result["node"])
    unique = len(distribution)
    return {
        "nodes": len(results),
        "successful": sum(bool(result["egress_ip"]) for result in results),
        "failed": sum(not result["egress_ip"] for result in results),
        "unique_egress_ips": unique,
        "minimum_unique_required": minimum_unique,
        "meets_minimum": unique >= minimum_unique,
        "distribution": [
            {
                "egress_ip": key[0],
                "country": key[1],
                "colo": key[2],
                "nodes": len(node_indexes),
                "node_indexes": node_indexes,
            }
            for key, node_indexes in sorted(distribution.items())
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--subscription-url",
        default=os.environ.get("EDGETUNNEL_SUBSCRIPTION_URL", ""),
    )
    parser.add_argument("--host", default="mysimivv.pages.dev")
    parser.add_argument(
        "--namespace-id",
        default="9471531f9f194116970143c0ff4e305e",
    )
    parser.add_argument("--nodes", type=int, default=20)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=25)
    parser.add_argument("--minimum-unique", type=int, default=1)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"
    if args.subscription_url:
        subscription_url = args.subscription_url
    else:
        project_dir = str(Path(__file__).resolve().parents[1])
        token = AI_PROBE._token_from_remote_kv(args.namespace_id, project_dir)
        subscription_url = (
            f"https://{args.host}/sub?token={urllib.parse.quote(token)}"
        )

    nodes = AI_PROBE.load_nodes(
        subscription_url,
        max(1, min(40, args.nodes)),
        args.timeout,
    )
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, min(16, args.workers))
    ) as executor:
        results = list(
            executor.map(
                lambda node: observe_egress(node, args.timeout),
                nodes,
            )
        )
    results.sort(key=lambda result: result["node"])
    report = {
        "generated_at": int(time.time() * 1000),
        "summary": summarize(results, max(1, args.minimum_unique)),
        "results": results,
    }
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if report["summary"]["meets_minimum"] and not report["summary"]["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
