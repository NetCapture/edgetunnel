#!/usr/bin/env python3
"""List archived EdgeTunnel anomalies from the public GitHub JSONL archive."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import time
import urllib.parse
import urllib.request


DEFAULT_INDEX_URL = (
    "https://raw.githubusercontent.com/hhhaiai/Picture/"
    "main/data/mysimivv/index.json"
)


def fetch_json(url: str, timeout: float) -> dict:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "edgetunnel-ai-maintenance/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def fetch_jsonl(url: str, timeout: float) -> list[dict]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "edgetunnel-ai-maintenance/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        text = response.read().decode("utf-8", errors="replace")
    rows = []
    for line_number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as error:
            rows.append(
                {
                    "v": 0,
                    "ts": 0,
                    "outcome": "archive_parse_error",
                    "status": 0,
                    "error": f"line {line_number}: {error.msg}",
                }
            )
    return rows


def raw_file_url(index_url: str, path: str) -> str:
    parsed = urllib.parse.urlsplit(index_url)
    parts = parsed.path.strip("/").split("/")
    if parsed.hostname == "raw.githubusercontent.com" and len(parts) >= 3:
        owner, repository, branch = parts[:3]
        encoded_path = "/".join(urllib.parse.quote(part) for part in path.split("/"))
        return f"https://raw.githubusercontent.com/{owner}/{repository}/{branch}/{encoded_path}"
    raise ValueError("index URL must use raw.githubusercontent.com")


def is_anomaly(row: dict, include_disconnects: bool) -> bool:
    outcome = str(row.get("outcome", "")).lower()
    status = int(row.get("status") or 0)
    if outcome in {"error", "archive_parse_error"} or status >= 500:
        return True
    return include_disconnects and outcome == "client_disconnected"


def normalize_anomaly(row: dict, archive_path: str) -> dict:
    node = row.get("node") if isinstance(row.get("node"), dict) else {}
    return {
        "id": row.get("id"),
        "ts": int(row.get("ts") or 0),
        "time": (
            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(row.get("ts") or 0) / 1000))
            if row.get("ts")
            else None
        ),
        "kind": row.get("kind", "unknown"),
        "method": row.get("method", ""),
        "status": int(row.get("status") or 0),
        "outcome": row.get("outcome", "unknown"),
        "requests": int(row.get("requests") or 0),
        "bytes_up": int(row.get("up") or 0),
        "bytes_down": int(row.get("down") or 0),
        "duration_ms": int(row.get("duration") or 0),
        "country": row.get("country", ""),
        "colo": row.get("colo", ""),
        "node_ip": node.get("ip", ""),
        "node_port": int(node.get("port") or 0),
        "node_group": node.get("group", ""),
        "error": row.get("error", ""),
        "archive_path": archive_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index-url", default=DEFAULT_INDEX_URL)
    parser.add_argument("--files", type=int, default=20)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--since-hours", type=float, default=72)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--include-disconnects", action="store_true")
    parser.add_argument("--fail-on-anomaly", action="store_true")
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    index = fetch_json(args.index_url, args.timeout)
    files = list(index.get("files") or [])[: max(1, args.files)]
    cutoff = int((time.time() - max(0, args.since_hours) * 3600) * 1000)

    def load(entry: dict) -> tuple[str, list[dict]]:
        path = str(entry.get("path", ""))
        return path, fetch_jsonl(raw_file_url(args.index_url, path), args.timeout)

    loaded: list[tuple[str, list[dict]]] = []
    fetch_errors = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, min(12, args.workers))
    ) as executor:
        future_to_entry = {executor.submit(load, entry): entry for entry in files}
        for future in concurrent.futures.as_completed(future_to_entry):
            entry = future_to_entry[future]
            try:
                loaded.append(future.result())
            except Exception as error:  # noqa: BLE001 - surface every archive failure
                fetch_errors.append(
                    {
                        "path": entry.get("path", ""),
                        "error": str(error)[:300],
                    }
                )

    scanned_rows = 0
    anomalies = []
    for path, rows in loaded:
        scanned_rows += len(rows)
        for row in rows:
            if int(row.get("ts") or 0) < cutoff:
                continue
            if is_anomaly(row, args.include_disconnects):
                anomalies.append(normalize_anomaly(row, path))
    anomalies.sort(key=lambda row: row["ts"], reverse=True)
    total_anomaly_count = len(anomalies)
    anomalies = anomalies[: max(1, args.limit)]

    result = {
        "source": args.index_url,
        "index_updated_at": int(index.get("updatedAt") or 0),
        "archive_totals": index.get("totals") or {},
        "window_hours": args.since_hours,
        "scanned_files": len(loaded),
        "scanned_rows": scanned_rows,
        "fetch_errors": fetch_errors,
        "anomaly_count": total_anomaly_count,
        "returned_anomaly_count": len(anomalies),
        "anomalies": anomalies,
    }
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            separators=(",", ":") if args.compact else None,
            indent=None if args.compact else 2,
        )
    )
    if fetch_errors:
        return 2
    if args.fail_on_anomaly and anomalies:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
