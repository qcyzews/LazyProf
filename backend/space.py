# /backend/space.py
import os
import sys
import gradio as gr
import spaces

# Wymuszenie braku SSR
os.environ["GRADIO_SSR_MODE"] = "false"

@spaces.GPU
def _dummy_gpu_check():
    pass

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Importujemy router z Twojego backendu
from app.api.v1.endpoints import router as api_router

# 1. Tworzymy interfejs Gradio
with gr.Blocks(title="LazyProf API") as demo:
    gr.Markdown("# 🚀 LazyProf Backend API is running")

# 2. Pobieramy wbudowaną w Gradio aplikację FastAPI i dopinamy Twój router
app = demo.app

app.include_router(api_router, prefix="/api/v1")

@app.get("/health")
async def health_check():
    return {"status": "ok", "app": "LazyProf Backend"}

# 3. KLUCZOWE: launch() blokuje proces i utrzymuje kontener w stanie działania na HF
demo.launch(server_name="0.0.0.0", server_port=7860, ssr_mode=False)