#!/usr/bin/env python3
"""
Gothbreach OpenCode Go Proxy — использует OpenCode Zen API как OpenAI-совместимый эндпоинт.
Позволяет использовать OpenCode Go подписку ($5-10/мес) с любым OpenAI-совместимым клиентом.

Usage:
  python gothbreach_oc_proxy.py
  # Прокси слушает на http://127.0.0.1:20131
  # Используй как OpenAI API: http://127.0.0.1:20131/v1
  
ENV:
  OPENCODE_API_KEY: ключ OpenCode (если нужен)
  PROXY_PORT: порт (default: 20131)
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
import ssl
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

OPENCODE_BASE = "https://opencode.ai/zen/go/v1"
PROXY_PORT = int(os.environ.get("PROXY_PORT", "20131"))
API_KEY = os.environ.get("OPENCODE_API_KEY", "")

ctx = ssl.create_default_context()

MODEL_MAP = {
    # OpenCode Go model names → OpenCode Zen API model names
    "deepseek-v4-flash": "deepseek-v4-flash",
    "deepseek-v4-pro": "deepseek-v4-pro",
    "deepseek-v3": "deepseek-v3",
    "kimi-k2.7-code": "kimi-k2.7-code",
    "kimi-k2.5": "kimi-k2.5",
    "minimax-m3": "minimax-m3",
    "minimax-m2.7": "minimax-m2.7",
    "gemini-2.5-flash": "gemini-2.5-flash",
    "gemini-2.5-pro": "gemini-2.5-pro",
    "glm-5.2": "glm-5.2",
    "glm-5.1": "glm-5.1",
    "qwen3.7-plus": "qwen3.7-plus",
    "qwen3.7-max": "qwen3.7-max",
    "qwen3.6-plus": "qwen3.6-plus",
    "gpt-5.5": "gpt-5.5",
    "gpt-5.4": "gpt-5.4",
    "gpt-5.4-mini": "gpt-5.4-mini",
    "claude-opus-4-8": "claude-opus-4-8",
    "claude-sonnet-4-6": "claude-sonnet-4-6",
    "claude-haiku-4-5": "claude-haiku-4-5",
}

class OCProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        sys.stderr.write(f"[OC-Proxy] {args[0]} {args[1]} {args[2]}\n")
    
    def _set_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
    
    def do_OPTIONS(self):
        self.send_response(200)
        self._set_cors()
        self.end_headers()
    
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/v1/models":
            self._handle_models()
        elif path == "/health":
            self._send_json(200, {"status": "ok", "proxy": "gothbreach-oc-proxy"})
        else:
            self._send_json(404, {"error": "not_found"})
    
    def _handle_models(self):
        models = [{"id": k, "object": "model", "created": int(time.time()), "owned_by": "opencode-go"} for k in MODEL_MAP.keys()]
        self._send_json(200, {"object": "list", "data": models})
    
    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/v1/chat/completions":
            self._handle_chat()
        else:
            self._send_json(404, {"error": "not_found"})
    
    def _handle_chat(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            req = json.loads(body)
        except Exception as e:
            self._send_json(400, {"error": f"invalid request: {e}"})
            return
        
        model = req.get("model", "deepseek-v4-flash")
        messages = req.get("messages", [])
        stream = req.get("stream", False)
        max_tokens = req.get("max_tokens", 4096)
        temperature = req.get("temperature", 0.7)
        
        oc_model = MODEL_MAP.get(model, model)
        
        # Forward to OpenCode Zen API
        oc_req = {
            "model": oc_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }
        
        if stream:
            self._handle_stream(oc_req, model)
        else:
            self._handle_sync(oc_req, model)
    
    def _handle_sync(self, oc_req, model):
        try:
            data = json.dumps(oc_req).encode()
            headers = {"Content-Type": "application/json"}
            if API_KEY:
                headers["Authorization"] = f"Bearer {API_KEY}"
            
            req = urllib.request.Request(
                f"{OPENCODE_BASE}/chat/completions",
                data=data, headers=headers, method="POST"
            )
            resp = urllib.request.urlopen(req, timeout=60, context=ctx)
            result = json.loads(resp.read().decode())
            
            # Normalize to OpenAI format
            openai_resp = {
                "id": result.get("id", f"oc-{int(time.time())}"),
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": result.get("choices", [{}])[0].get("message", {}).get("content", ""),
                        },
                        "finish_reason": result.get("choices", [{}])[0].get("finish_reason", "stop"),
                    }
                ],
                "usage": result.get("usage", {}),
            }
            self._send_json(200, openai_resp)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode() if e.fp else str(e)
            self._send_json(e.code, {"error": f"OpenCode API: {err_body[:200]}"})
        except Exception as e:
            self._send_json(500, {"error": str(e)})
    
    def _handle_stream(self, oc_req, model):
        try:
            data = json.dumps(oc_req).encode()
            headers = {"Content-Type": "application/json"}
            if API_KEY:
                headers["Authorization"] = f"Bearer {API_KEY}"
            
            req = urllib.request.Request(
                f"{OPENCODE_BASE}/chat/completions",
                data=data, headers=headers, method="POST"
            )
            resp = urllib.request.urlopen(req, timeout=120, context=ctx)
            
            self.send_response(200)
            self._set_cors()
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            
            buffer = ""
            while True:
                chunk = resp.read(4096)
                if not chunk:
                    break
                chunk_str = chunk.decode("utf-8", errors="replace")
                # Rewrite model name in streamed chunks
                chunk_str = chunk_str.replace('"model":"' + oc_req["model"] + '"', '"model":"' + model + '"')
                self.wfile.write(chunk_str.encode())
                self.wfile.flush()
            
            self.wfile.write(b"\n")
            self.wfile.flush()
        except Exception as e:
            try:
                self.wfile.write(f"data: {{\"error\": \"{e}\"}}\n\n".encode())
                self.wfile.flush()
            except:
                pass
    
    def _send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self._set_cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    server = HTTPServer(("127.0.0.1", PROXY_PORT), OCProxyHandler)
    print(f"\n{'='*60}")
    print(f"  🚀 Gothbreach OC Proxy")
    print(f"  Прокси слушает: http://127.0.0.1:{PROXY_PORT}")
    print(f"  OpenCode Zen: {OPENCODE_BASE}")
    print(f"  Моделей: {len(MODEL_MAP)}")
    print(f"{'='*60}")
    print(f"\n  Используй как OpenAI API:")
    print(f"    API Base: http://127.0.0.1:{PROXY_PORT}/v1")
    print(f"    API Key: любая (не проверяется)")
    print(f"    Models: {', '.join(list(MODEL_MAP.keys())[:5])}...")
    print(f"\n  Для абуза OpenCode Go подписки:")
    print(f"    Укажи OPENCODE_API_KEY=твой_ключ в ENV")
    print(f"    Или используй IP-based доступ (если настроено)")
    print(f"{'='*60}\n")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nProxy остановлен.")
        server.server_close()


if __name__ == "__main__":
    main()
