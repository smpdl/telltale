from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import gradio as gr
from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from telltale.server import api


os.environ.setdefault("GRADIO_SSR_MODE", "false")
WEB_DIR = Path(__file__).parent / "telltale" / "web"
DIST_DIR = WEB_DIR / "dist"
ASSETS_DIR = DIST_DIR / "assets"
SOURCE_INDEX = WEB_DIR / "index.html"
ErrorCode = Literal["bad_request", "not_found", "illegal_action", "server_error"]


class ErrorPayload(BaseModel):
    code: ErrorCode
    message: str


class StartRequest(BaseModel):
    seed: int | None = None
    model_mode: Literal["mock", "zero_gpu", "llama_server", "llama_cpp"] | None = None
    tts_enabled: bool = False
    stt_enabled: bool = False


class ActionRequest(BaseModel):
    run_id: str = Field(min_length=1)
    action: Literal["fold", "check", "call", "bet", "raise", "all_in"]
    amount: int = Field(default=0, ge=0)
    utterance: str = ""


class RewardRequest(BaseModel):
    run_id: str = Field(min_length=1)
    perk_id: str = Field(min_length=1)


class ContinueRequest(BaseModel):
    run_id: str = Field(min_length=1)


def create_gradio_app() -> gr.Blocks:
    with gr.Blocks(title="Telltale API", fill_height=True) as demo:
        gr.Markdown(
            """
            # Telltale backend

            The player-facing game UI is served at `/`. This hidden Gradio mount exists for
            Hugging Face/Gradio compatibility and lightweight backend inspection.
            """
        )
        start = gr.Button("Start llama.cpp backend run", variant="primary")
        state_json = gr.JSON(label="Public state")

        def on_start() -> dict[str, Any]:
            return api.start_run()

        start.click(on_start, inputs=[], outputs=state_json)

    return demo


def create_app() -> gr.Server:
    app = gr.Server(title="Telltale", docs_url="/api/docs", redoc_url=None)
    app.add_exception_handler(HTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)

    @app.post("/api/start")
    def start_run(request: StartRequest):
        settings: dict[str, Any] = {
            "tts_enabled": request.tts_enabled,
            "stt_enabled": request.stt_enabled,
        }
        if request.model_mode is not None:
            settings["model_mode"] = request.model_mode
        return _api_call(
            lambda: api.start_run(
                seed=request.seed,
                settings=settings,
            )
        )

    @app.get("/api/floors")
    def list_floors():
        return _api_call(api.list_floors)

    @app.get("/api/state/{run_id}")
    def get_state(run_id: str):
        return _api_call(lambda: api.get_state(run_id))

    @app.post("/api/action")
    def submit_action(request: ActionRequest):
        return _api_call(
            lambda: api.submit_player_action(
                request.run_id,
                request.action,
                amount=request.amount,
                utterance=request.utterance,
            )
        )

    @app.post("/api/reward")
    def choose_reward(request: RewardRequest):
        return _api_call(lambda: api.choose_reward(request.run_id, request.perk_id))

    @app.post("/api/continue")
    def continue_run(request: ContinueRequest):
        return _api_call(lambda: api.continue_until_player_turn(request.run_id))

    @app.get("/api/trace/{run_id}")
    def export_trace(run_id: str):
        return _api_call(lambda: api.export_trace(run_id))

    @app.post("/api/transcribe/{run_id}")
    async def transcribe_audio(run_id: str, request: Request):
        audio = await request.body()
        return _api_call(lambda: api.transcribe_player_audio(run_id, audio))

    @app.get("/api/audio/{audio_id}")
    def get_audio(audio_id: str):
        result = _api_call(lambda: api.get_tts_audio(audio_id))
        if isinstance(result, JSONResponse):
            return result
        return FileResponse(result["path"], media_type=result["mime_type"])

    if ASSETS_DIR.exists():
        app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")
    public_assets = WEB_DIR / "public" / "assets"
    if public_assets.exists():
        app.mount("/game-assets", StaticFiles(directory=public_assets), name="game-assets")

    @app.get("/")
    def index() -> Response:
        index_path = DIST_DIR / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        if SOURCE_INDEX.exists():
            return FileResponse(SOURCE_INDEX)
        return JSONResponse({"message": "Build the React frontend with `cd telltale/web && npm run build`."})

    gr.mount_gradio_app(app, create_gradio_app(), path="/gradio", footer_links=[])

    @app.get("/{path:path}")
    def spa_fallback(path: str) -> Response:
        if path.startswith(("api/", "gradio/")):
            raise HTTPException(status_code=404, detail=f"Unknown path: /{path}")
        static_path = DIST_DIR / path
        if static_path.is_file():
            return FileResponse(static_path)
        public_path = WEB_DIR / "public" / path
        if public_path.is_file():
            return FileResponse(public_path)
        index_path = DIST_DIR / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        raise HTTPException(status_code=404, detail="React frontend has not been built.")

    return app


def _error(code: ErrorCode, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": ErrorPayload(code=code, message=message).model_dump()},
    )


def _api_call(callback: Any) -> dict[str, Any] | JSONResponse:
    try:
        return callback()
    except KeyError as error:
        return _error("not_found", _clean_message(error), 404)
    except ValueError as error:
        message = _clean_message(error)
        code: ErrorCode = "illegal_action" if "not legal" in message else "bad_request"
        return _error(code, message, 400)
    except Exception as error:
        return _error("server_error", _clean_message(error), 500)


async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    code: ErrorCode = "not_found" if exc.status_code == 404 else "bad_request"
    return _error(code, str(exc.detail), exc.status_code)


async def _validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _error("bad_request", "Request validation failed.", 422)


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, KeyError):
        return _error("not_found", _clean_message(exc), 404)
    if isinstance(exc, ValueError):
        message = _clean_message(exc)
        code: ErrorCode = "illegal_action" if "not legal" in message else "bad_request"
        return _error(code, message, 400)
    return _error("server_error", _clean_message(exc), 500)


def _clean_message(error: Exception) -> str:
    text = str(error)
    if len(text) >= 2 and text[0] == text[-1] == "'":
        return text[1:-1]
    return text or error.__class__.__name__


app = create_app()


if __name__ == "__main__":
    app.launch(ssr_mode=False, _frontend=False, show_error=True)
