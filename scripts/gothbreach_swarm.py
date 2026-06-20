#!/usr/bin/env python3
"""
Gothbreach Swarm Orchestrator — рой агентов с multi-provider council.
Слушает на 127.0.0.1:20132, принимает OpenAI-совместимые запросы.
Каждый запрос проходит через: planner → parallel executors → reviewer.
"""

import json, os, sys, time, asyncio, aiohttp, uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

COUNCIL_PORT = int(os.environ.get("COUNCIL_PORT", "20132"))
OPENCODE_PROXY = os.environ.get("OPENCODE_PROXY", "http://127.0.0.1:20131")

# ─── CONFIG ─────────────────────────────────────────────────────
MODELS = {
    "planner":     {"model": "deepseek-v4-pro",   "temp": 0.3},
    "architect":   {"model": "deepseek-v4-pro",   "temp": 0.3},
    "implementer": {"model": "kimi-k2.7-code",    "temp": 0.2},
    "tester":      {"model": "deepseek-v4-flash", "temp": 0.2},
    "reviewer":    {"model": "deepseek-v4-pro",   "temp": 0.3},
    "debugger":    {"model": "deepseek-v4-pro",   "temp": 0.4},
}

SYSTEM_PROMPTS = {
    "planner": "Ты — планировщик. Разбей задачу на 3-5 независимых модулей. Формат JSON: {\"tasks\": [{\"id\": 1, \"name\": \"...\", \"description\": \"...\", \"files\": [\"...\"]}]}",
    "implementer": "Ты — реализатор. Напиши код для своей подзадачи. Только код, без объяснений.",
    "reviewer": "Ты — ревьюер. Проверь код на баги, уязвимости, качество. Формат: {\"status\": \"pass/fail\", \"issues\": [], \"score\": 0-100}",
}

class SwarmCouncil:
    """Multi-provider council + swarm orchestrator"""
    
    def __init__(self):
        self.session = None
    
    async def _query(self, model_cfg, messages, timeout=60):
        """Query a single model via opencode proxy"""
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        payload = {
            "model": model_cfg["model"],
            "messages": messages,
            "temperature": model_cfg.get("temp", 0.3),
            "max_tokens": 16384,
        }
        
        try:
            async with self.session.post(
                f"{OPENCODE_PROXY}/v1/chat/completions",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                data = await resp.json()
                return data.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            return f"ERROR: {e}"
    
    async def council(self, task, models_list):
        """Parallel multi-model council — все модели одновременно"""
        tasks = []
        for m in models_list:
            cfg = MODELS.get(m, {"model": "deepseek-v4-flash", "temp": 0.3})
            sys_prompt = SYSTEM_PROMPTS.get(m, "Ты — эксперт. Ответь на задачу.")
            messages = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": task}
            ]
            tasks.append(self._query(cfg, messages))
        
        results = await asyncio.gather(*tasks)
        return dict(zip(models_list, results))
    
    async def swarm(self, task):
        """Полный swarm pipeline: plan → parallel → review"""
        
        # Phase 1: PLAN
        sys.stderr.write(f"[SWARM] Phase 1: Planning...\n")
        plan_raw = await self._query(
            MODELS["planner"],
            [{"role": "system", "content": SYSTEM_PROMPTS["planner"]},
             {"role": "user", "content": f"Разбей на подзадачи: {task}"}],
            timeout=120
        )
        
        # Parse plan
        try:
            plan = json.loads(plan_raw)
            subtasks = plan.get("tasks", [])
        except:
            subtasks = [{"id": 1, "name": task, "description": task, "files": []}]
        
        sys.stderr.write(f"[SWARM] Plan: {len(subtasks)} subtasks\n")
        
        # Phase 2: PARALLEL EXECUTION
        sys.stderr.write(f"[SWARM] Phase 2: Executing {len(subtasks)} subtasks in parallel...\n")
        impl_tasks = []
        for st in subtasks:
            impl_tasks.append(self._query(
                MODELS["implementer"],
                [{"role": "system", "content": SYSTEM_PROMPTS["implementer"]},
                 {"role": "user", "content": f"Task: {st.get('name', st)} ({st.get('description', '')})\nFiles: {st.get('files', [])}"}],
                timeout=120
            ))
        
        results = await asyncio.gather(*impl_tasks)
        code_results = {f"task_{st.get('id', i)}": r for i, (st, r) in enumerate(zip(subtasks, results))}
        
        # Phase 3: REVIEW
        sys.stderr.write(f"[SWARM] Phase 3: Reviewing...\n")
        combined_code = "\n\n".join([f"# Task {k}\n{v}" for k, v in code_results.items()])
        review = await self._query(
            MODELS["reviewer"],
            [{"role": "system", "content": SYSTEM_PROMPTS["reviewer"]},
             {"role": "user", "content": f"Проверь код:\n{combined_code[:8000]}"}],
            timeout=60
        )
        
        return {
            "plan": plan_raw,
            "subtasks": subtasks,
            "code": code_results,
            "review": review,
            "summary": f"✅ {len(subtasks)} tasks completed\n📊 Review: {review[:200]}"
        }

# ─── HTTP HANDLER ──────────────────────────────────────────────
swarm = SwarmCouncil()

class SwarmHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write(f"[Council] {args[0]} {args[1]} {args[2]}\n")
    
    def _json(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
    
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/v1/models":
            models = [{"id": k, "object": "model"} for k in MODELS.keys()]
            self._json(200, {"object": "list", "data": models})
        elif path == "/health":
            self._json(200, {"status": "ok", "mode": "swarm-council"})
        else:
            self._json(404, {"error": "not_found"})
    
    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/v1/chat/completions":
            self._handle_chat()
        elif path == "/v1/swarm":
            self._handle_swarm()
        elif path == "/v1/council":
            self._handle_council()
        else:
            self._json(404, {"error": "not_found"})
    
    def _handle_chat(self):
        """Обычный чат через OpenCode proxy"""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length))
        except:
            self._json(400, {"error": "invalid body"})
            return
        
        model = body.get("model", "deepseek-v4-pro")
        messages = body.get("messages", [])
        
        # Перенаправляем в opencode proxy
        import urllib.request
        data = json.dumps({"model": model, "messages": messages}).encode()
        req = urllib.request.Request(
            f"{OPENCODE_PROXY}/v1/chat/completions",
            data=data, headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            resp = urllib.request.urlopen(req, timeout=120)
            result = json.loads(resp.read().decode())
            self._json(200, result)
        except Exception as e:
            self._json(502, {"error": str(e)})
    
    def _handle_council(self):
        """Multi-model council — все модели параллельно"""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length))
        except:
            self._json(400, {"error": "invalid body"})
            return
        
        task = body.get("task", body.get("messages", [{}])[-1].get("content", ""))
        models = body.get("models", ["planner", "architect", "reviewer"])
        
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(swarm.council(task, models))
        loop.close()
        
        self._json(200, {"council": result})
    
    def _handle_swarm(self):
        """Полный swarm — plan → parallel → review"""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length))
        except:
            self._json(400, {"error": "invalid body"})
            return
        
        task = body.get("task", body.get("messages", [{}])[-1].get("content", ""))
        
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(swarm.swarm(task))
        loop.close()
        
        # Форматируем ответ как chat.completion
        code_block = "\n".join([f"**{k}**:\n```python\n{v[:500]}\n```" for k,v in result['code'].items()])
        content = f"""## 🤖 Swarm Execution: {len(result['subtasks'])} subtasks

### 📋 Plan
{result['plan'][:1000]}

### 💻 Code
{code_block}

### 🔍 Review
{result['review'][:500]}
"""
        
        self._json(200, {
            "id": f"swarm-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "swarm-orchestrator",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop"
            }],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        })

def main():
    server = HTTPServer(("127.0.0.1", COUNCIL_PORT), SwarmHandler)
    print(f"\n{'='*60}")
    print(f"  🤖 Gothbreach Swarm Council")
    print(f"  Слушает: http://127.0.0.1:{COUNCIL_PORT}")
    print(f"  Прокси: {OPENCODE_PROXY}")
    print(f"{'='*60}")
    print(f"\n  Endpoints:")
    print(f"    POST /v1/chat/completions — обычный чат")
    print(f"    POST /v1/council — multi-model council")
    print(f"    POST /v1/swarm — полный рой (plan→execute→review)")
    print(f"    GET  /v1/models — список моделей")
    print(f"{'='*60}\n")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nСтоп.")
        server.server_close()

if __name__ == "__main__":
    main()
