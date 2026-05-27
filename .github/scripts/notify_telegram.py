"""Push a markdown routine report to Telegram, split into Telegram-sized chunks."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

MAX_LEN = 3800
API = "https://api.telegram.org/bot{token}/sendMessage"


def split_chunks(text: str, max_len: int = MAX_LEN) -> list[str]:
    """Greedy line-based split. Tries to keep section headers as a chunk boundary."""
    chunks: list[str] = []
    current: list[str] = []
    cur_len = 0
    for line in text.split("\n"):
        line_len = len(line) + 1
        starts_section = line.startswith("## ")
        if current and (cur_len + line_len > max_len or (starts_section and cur_len > max_len * 0.6)):
            chunks.append("\n".join(current).rstrip())
            current = [line]
            cur_len = line_len
        else:
            current.append(line)
            cur_len += line_len
    if current:
        chunks.append("\n".join(current).rstrip())
    return [c for c in chunks if c.strip()]


def to_telegram_markdown(text: str) -> str:
    """Convert GitHub-flavored bold (**x**) to Telegram MarkdownV1 bold (*x*)."""
    return text.replace("**", "*")


def send(token: str, chat_id: str, text: str, parse_mode: str | None) -> dict:
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": "true",
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    data = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(API.format(token=token), data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {"ok": False, "description": body, "status": e.code}


def send_with_fallback(token: str, chat_id: str, text: str) -> bool:
    """Try Markdown, then plain text. Returns True on success."""
    md = to_telegram_markdown(text)
    r = send(token, chat_id, md, "Markdown")
    if r.get("ok"):
        return True
    print(f"  markdown failed: {r.get('description')}", file=sys.stderr)
    r = send(token, chat_id, text, None)
    if r.get("ok"):
        return True
    print(f"  plain failed: {r.get('description')}", file=sys.stderr)
    return False


def main() -> int:
    token = os.environ["BOT_TOKEN"]
    chat_id = os.environ["CHAT_ID"]
    file_path = os.environ["FILE"]
    repo = os.environ.get("REPO", "")
    sha = os.environ.get("SHA", "")[:7]

    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()

    chunks = split_chunks(text)
    print(f"Split {file_path} ({len(text)} chars) into {len(chunks)} chunks", file=sys.stderr)

    ok = 0
    for i, chunk in enumerate(chunks, 1):
        print(f"chunk {i}/{len(chunks)} ({len(chunk)} chars)...", file=sys.stderr)
        if send_with_fallback(token, chat_id, chunk):
            ok += 1
        time.sleep(1)

    footer_lines = []
    if repo and file_path:
        footer_lines.append(f"📌 Full report: https://github.com/{repo}/blob/main/{file_path}")
    if sha:
        footer_lines.append(f"🔖 Commit: {sha}")
    if footer_lines:
        if send_with_fallback(token, chat_id, "\n".join(footer_lines)):
            ok += 1

    total = len(chunks) + (1 if footer_lines else 0)
    print(f"Sent {ok}/{total} messages", file=sys.stderr)
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
