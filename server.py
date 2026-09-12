#!/usr/bin/env python3
"""
扫雷服务器：静态文件 + 全局共享成就榜
- 静态文件（index.html 等）
- GET  /api/leaderboard              返回榜单
- POST /api/leaderboard  {name,time,difficulty}  提交成绩
榜单集中存于本目录 leaderboard.json，所有访问者共享，自动排序。
"""
import json, os, threading, mimetypes, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
LEADER_FILE = os.path.join(BASE, "leaderboard.json")
MAX_PER_DIFF = 10     # 每难度保留前 N 名
LOCK = threading.Lock()
DIFFS = {"easy": "初级 9×9", "mid": "中级 16×16", "hard": "高级 30×16"}
VALID_DIFFS = set(DIFFS)


def load_board():
    if not os.path.exists(LEADER_FILE):
        return {d: [] for d in VALID_DIFFS}
    try:
        with open(LEADER_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {d: [] for d in VALID_DIFFS}
        return {d: data.get(d, []) for d in VALID_DIFFS}
    except Exception:
        return {d: [] for d in VALID_DIFFS}


def save_board(board):
    tmp = LEADER_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(board, f, ensure_ascii=False, indent=2)
    os.replace(tmp, LEADER_FILE)


def submit_score(name, time_s, diff):
    name = (name or "匿名").strip()[:20] or "匿名"
    try:
        time_s = int(time_s)
    except (TypeError, ValueError):
        return None, "时间格式错误"
    if time_s < 1:
        return None, "时间无效"
    if diff not in VALID_DIFFS:
        return None, "未知难度"
    with LOCK:
        board = load_board()
        lst = board[diff]
        lst.append({"name": name, "time": time_s})
        raw = {e["name"]: e for e in lst}  # 同名只保留最新
        lst = list(raw.values())
        lst.sort(key=lambda x: x["time"])
        board[diff] = lst[:MAX_PER_DIFF]
        save_board(board)
    return board, None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[{self.client_address[0]}] {fmt % args}")

    def _send(self, code, body, ctype="text/plain; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path.rstrip("/") == "/api/leaderboard":
            board = load_board()
            out = {d: {"label": DIFFS[d], "scores": board[d]} for d in VALID_DIFFS}
            self._send(200, json.dumps(out, ensure_ascii=False),
                       "application/json; charset=utf-8")
            return
        if path == "/":
            path = "/index.html"
        rel = urllib.parse.unquote(path.lstrip("/"))
        full = os.path.realpath(os.path.join(BASE, rel))
        if not full.startswith(BASE + os.sep) and full != os.path.realpath(BASE):
            self._send(403, "Forbidden"); return
        if os.path.isdir(full):
            full = os.path.join(full, "index.html")
        if not os.path.isfile(full):
            self._send(404, "Not Found"); return
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/json", "application/javascript"):
            ctype += "; charset=utf-8"
        with open(full, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store" if full.endswith(".html") else "max-age=30")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if urllib.parse.urlparse(self.path).path.rstrip("/") != "/api/leaderboard":
            self._send(404, "Not Found"); return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            name, time_s, diff = data.get("name", ""), data.get("time", 0), data.get("difficulty", "")
        except Exception:
            self._send(400, "Bad Request"); return
        board, err = submit_score(name, time_s, diff)
        if board is None:
            self._send(400, err); return
        out = {d: {"label": DIFFS[d], "scores": board[d]} for d in VALID_DIFFS}
        self._send(200, json.dumps(out, ensure_ascii=False),
                   "application/json; charset=utf-8")


def main():
    port = 9120
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"🌟 扫雷服务器(共享积分榜): http://0.0.0.0:{port}/  数据文件: {LEADER_FILE}")
    server.serve_forever()


if __name__ == "__main__":
    main()