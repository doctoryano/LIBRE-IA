"""
Model adapter layer: selects implementation based on ADAPTER_RUNTIME env

Supported runtimes:
 - echo (default) -> EchoAdapter (simulated)
 - hf -> HFAdapter (HuggingFace Inference API)
 - vllm -> VLLMAdapter (requires vllm installed & GPU)
 - ggml -> GGMLAdapter (invokes llama.cpp/ggml binary)

Selection:
 - Set ADAPTER_RUNTIME env var to 'vllm' or 'ggml' or 'hf' to prefer that runtime.
 - If preferred runtime not available, auto-falls back to 'echo'.
"""
from __future__ import annotations
import os
import asyncio
from typing import AsyncGenerator, Optional

# Echo adapter
class BaseAdapter:
    def name(self) -> str: return "base"
    def info(self): return {}
    async def generate_stream(self, prompt: str, session_id: Optional[str] = None) -> AsyncGenerator[str, None]:
        yield ""

class EchoAdapter(BaseAdapter):
    def name(self) -> str: return "echo"
    def info(self): return {"type":"echo"}
    async def generate_stream(self, prompt: str, session_id: Optional[str] = None):
        reply = "IA LIBRE (simulada): " + prompt[::-1]
        words = reply.split()
        for i in range(0, len(words), 5):
            await asyncio.sleep(0.1)
            yield " ".join(words[i:i+5]) + " "

# HF adapter (non-streaming example)
class HFAdapter(BaseAdapter):
    def __init__(self, token: str = None, model: str = "gpt-neo-2.7B"):
        import aiohttp
        self.token = token or os.environ.get("HF_API_TOKEN")
        self.model = model
        if not self.token:
            raise RuntimeError("HF_API_TOKEN not provided")
    def name(self): return f"hf-{self.model}"
    def info(self): return {"type":"hf", "model":self.model}
    async def generate_stream(self, prompt, session_id=None):
        import aiohttp
        url = f"https://api-inference.huggingface.co/models/{self.model}"
        headers = {"Authorization": f"Bearer {self.token}"}
        payload = {"inputs": prompt, "parameters": {"max_new_tokens": 256}}
        async with aiohttp.ClientSession() as sess:
            async with sess.post(url, headers=headers, json=payload, timeout=120) as resp:
                if resp.status != 200:
                    txt = await resp.text()
                    raise RuntimeError(f"HF error {resp.status}: {txt}")
                data = await resp.json()
                gen = ""
                if isinstance(data, list) and data and "generated_text" in data[0]:
                    gen = data[0]["generated_text"]
                elif isinstance(data, dict) and "generated_text" in data:
                    gen = data["generated_text"]
                else:
                    gen = str(data)
                for i in range(0, len(gen.split()), 8):
                    await asyncio.sleep(0.05)
                    yield " ".join(gen.split()[i:i+8]) + " "

# vLLM adapter skeleton (requires vllm installed)
class VLLMAdapter(BaseAdapter):
    def __init__(self, model: str = "meta-llama/Llama-2-7b-chat-hf"):
        # vllm integration is environment dependent; this is a skeleton
        try:
            import vllm  # type: ignore
            self.vllm = vllm
            self.model = model
        except Exception as e:
            raise RuntimeError("vllm not available") from e
    def name(self): return f"vllm-{self.model}"
    def info(self): return {"type":"vllm", "model":self.model}
    async def generate_stream(self, prompt, session_id=None):
        # Minimal blocking implementation disguised as async
        from concurrent.futures import ThreadPoolExecutor
        def run_blocking():
            # user must implement vllm client usage here
            client = self.vllm.Client(self.model)
            resp = client.generate(prompt)
            return resp
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=1) as ex:
            result = await loop.run_in_executor(ex, run_blocking)
            # result -> yield chunks (this part depends on vllm API)
            yield str(result)

# GGML / llama.cpp adapter (invokes local binary)
class GGMLAdapter(BaseAdapter):
    def __init__(self, binary_path: str = "llama_cpp.exe"):
        import shutil
        self.binary = binary_path
        if not shutil.which(self.binary):
            # try common names
            raise RuntimeError(f"llama binary not found: {self.binary}")
    def name(self): return f"ggml-cli:{self.binary}"
    def info(self): return {"type":"ggml", "binary": self.binary}
    async def generate_stream(self, prompt, session_id=None):
        # invoke subprocess and stream stdout
        import subprocess, shlex
        args = [self.binary, "-p", prompt, "--n_predict", "256"]
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            while True:
                chunk = proc.stdout.read(512)
                if not chunk:
                    break
                yield chunk
            proc.wait(timeout=1)
        except Exception:
            proc.kill()
            raise

def get_adapter() -> BaseAdapter:
    pref = os.environ.get("ADAPTER_RUNTIME", "auto").lower()
    # order: pref -> auto detect
    if pref == "hf":
        try:
            return HFAdapter(token=os.environ.get("HF_API_TOKEN"), model=os.environ.get("HF_MODEL","gpt-neo-2.7B"))
        except Exception:
            pass
    if pref == "vllm":
        try:
            return VLLMAdapter(model=os.environ.get("VLLM_MODEL","meta-llama/Llama-2-7b-chat-hf"))
        except Exception:
            pass
    if pref == "ggml":
        try:
            return GGMLAdapter(binary_path=os.environ.get("GGML_BIN","llama_cpp"))
        except Exception:
            pass
    # Auto-detect: prefer vllm if installed, else ggml if binary present, else hf if token present, else echo
    try:
        return VLLMAdapter(model=os.environ.get("VLLM_MODEL","meta-llama/Llama-2-7b-chat-hf"))
    except Exception:
        pass
    import shutil
    if shutil.which(os.environ.get("GGML_BIN","llama_cpp")):
        try:
            return GGMLAdapter(binary_path=os.environ.get("GGML_BIN","llama_cpp"))
        except Exception:
            pass
    if os.environ.get("HF_API_TOKEN"):
        try:
            return HFAdapter(token=os.environ.get("HF_API_TOKEN"), model=os.environ.get("HF_MODEL","gpt-neo-2.7B"))
        except Exception:
            pass
    return EchoAdapter()