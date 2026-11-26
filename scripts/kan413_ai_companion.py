# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Lightweight mock AI companion fixture listening strictly on 127.0.0.1:11435."""

import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import sys

class CompanionHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Keep stdout clean
        pass

    def do_GET(self):
        # Ollama tags
        if self.path.startswith("/api/tags"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp = {
                "models": [
                    {"name": "llama3.2:latest", "modified_at": "2026-11-25T00:00:00Z", "size": 2000000000},
                    {"name": "qwen2.5-coder:latest", "modified_at": "2026-11-25T00:00:00Z", "size": 3000000000}
                ]
            }
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        # Gemini models
        if "/v1beta/models" in self.path:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp = {
                "models": [
                    {"name": "models/gemini-2.5-flash", "displayName": "Gemini 2.5 Flash"},
                    {"name": "models/gemini-2.5-pro", "displayName": "Gemini 2.5 Pro"}
                ]
            }
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        # OpenAI models
        if "/models" in self.path:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp = {
                "data": [
                    {"id": "gpt-4o", "object": "model", "owned_by": "openai"},
                    {"id": "gpt-4o-mini", "object": "model", "owned_by": "openai"}
                ]
            }
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len) if content_len > 0 else b""

        # Ollama completions
        if self.path.startswith("/api/chat") or self.path.startswith("/api/generate"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp = {
                "model": "llama3.2:latest",
                "message": {"role": "assistant", "content": "Live Ollama workout response."},
                "response": "Live Ollama workout response.",
                "done": True,
                "total_duration": 15000000
            }
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        # OpenAI chat completions
        if "/chat/completions" in self.path:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp = {
                "id": "chatcmpl-mock-1",
                "object": "chat.completion",
                "created": 1700000000,
                "model": "gpt-4o",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": "Live OpenAI workout response."},
                    "finish_reason": "stop"
                }],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
            }
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        # Gemini generateContent
        if "generateContent" in self.path:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp = {
                "candidates": [{
                    "content": {"parts": [{"text": "Live Gemini workout response."}], "role": "model"},
                    "finishReason": "STOP"
                }],
                "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 6, "totalTokenCount": 18}
            }
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 11435
    server = HTTPServer(("127.0.0.1", port), CompanionHandler)
    print(f"Mock AI Companion running on 127.0.0.1:{port}", flush=True)
    server.serve_forever()
