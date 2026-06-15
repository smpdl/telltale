from __future__ import annotations

import os

import uvicorn


os.environ.setdefault("GRADIO_SSR_MODE", "false")

uvicorn.run(
    "app:app",
    host="0.0.0.0",
    port=int(os.getenv("PORT", "7860")),
    proxy_headers=True,
)
