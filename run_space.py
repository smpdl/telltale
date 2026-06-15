from __future__ import annotations

import os

os.environ.setdefault("GRADIO_SSR_MODE", "false")

from app import launch_app


if __name__ == "__main__":
    launch_app()
