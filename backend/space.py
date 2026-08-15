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

# 1. Importujemy router i dekoratory z Twojego backendu
from app.api.v1.endpoints import router as api_router

# 2. Tworzymy minimalny interfejs Gradio
with gr.Blocks(title="LazyProf API") as demo:
    gr.Markdown("# 🚀 LazyProf Backend API is running")

# 3. Inicjalizujemy aplikację Gradio
app = demo.app

# 4. Podpinamy Twój router FastAPI bezpośrednio pod aplikację
app.include_router(api_router, prefix="/api/v1")

@app.get("/health")
async def health_check():
    return {"status": "ok", "app": "LazyProf Backend"}