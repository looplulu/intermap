#!/usr/bin/env python3
"""
数字交互引擎 Demo HTTP 服务器

解决 file:// 协议下 blob URL 无法播放视频的问题。
用法：
    python3 serve_demo.py
然后访问 http://localhost:8000
"""

import http.server
import socketserver
import os
import sys
import json
import urllib.parse
import urllib.request

PORT = int(os.environ.get("PORT", "8000"))
DIR = os.path.dirname(os.path.abspath(__file__))
OCR_SPACE_URL = "https://api.ocr.space/parse/image"
OCR_SPACE_API_KEY = os.environ.get("OCR_SPACE_API_KEY", "helloworld")

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIR, **kwargs)

    def do_POST(self):
        if self.path not in ("/api/analyze_base64", "/intermap/api/analyze_base64"):
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length).decode("utf-8", errors="replace")
        fields = urllib.parse.parse_qs(raw_body)
        image_base64 = (fields.get("image_base64") or [""])[0]
        if not image_base64:
            self._send_json({"error": "missing image_base64"}, status=400)
            return

        try:
            result = analyze_with_ocr_space(image_base64)
            self._send_json(result)
        except Exception as exc:
            self._send_json({"error": str(exc), "ocr_texts": [], "ocr_count": 0}, status=502)

    def _send_json(self, data, status=200):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
    
    def log_message(self, format, *args):
        print(f"[{self.address_string()}] {args[0]} {args[1]} {args[2]}")


def analyze_with_ocr_space(image_base64):
    data = urllib.parse.urlencode({
        "apikey": OCR_SPACE_API_KEY,
        "base64Image": "data:image/jpeg;base64," + image_base64,
        "language": "chs",
        "OCREngine": "2",
        "scale": "true",
        "isOverlayRequired": "false",
    }).encode("utf-8")
    req = urllib.request.Request(
        OCR_SPACE_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        parsed = json.loads(resp.read().decode("utf-8", errors="replace"))

    texts = []
    for item in parsed.get("ParsedResults") or []:
        text = item.get("ParsedText") or ""
        texts.extend([line.strip() for line in text.splitlines() if line.strip()])

    return {
        "provider": "ocr.space",
        "ocr_texts": texts,
        "ocr_count": len(texts),
        "raw": parsed,
    }

def main():
    print(f"╔══════════════════════════════════╗")
    print(f"║  数字交互引擎 Demo 服务器        ║")
    print(f"║  目录: {DIR}")
    print(f"║  地址: http://localhost:{PORT}")
    print(f"║  OCR: OCR.space ({'env key' if os.environ.get('OCR_SPACE_API_KEY') else 'demo key'})")
    print(f"║  Ctrl+C 停止服务器              ║")
    print(f"╚══════════════════════════════════╝")
    
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n服务器已停止")
            httpd.server_close()

if __name__ == "__main__":
    main()
