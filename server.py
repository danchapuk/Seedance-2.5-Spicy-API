import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from fastapi import FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from seedance_2_5_spicy_api import PROVIDERS, Seedance25SpicyAPI

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

def _ensure_sandbox_preview():
    preview_file = STATIC_DIR / "sandbox_preview.mp4"
    if not preview_file.exists():
        import subprocess
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x180:d=1",
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
                    "-c:a", "aac", "-b:a", "32k", str(preview_file),
                ],
                capture_output=True,
                check=False,
            )
        except Exception:
            pass

_ensure_sandbox_preview()

app = FastAPI(
    title="Seedance 2.5 Spicy Studio API",
    description="Multi-Provider Web Studio Interface & REST Backend for ByteDance's Seedance 2.5 API (BytePlus ModelArk, fal.ai, WaveSpeedAI, Replicate, MuAPI)",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MOCK_TASKS: Dict[str, Dict[str, Any]] = {}
TASK_HISTORY: List[Dict[str, Any]] = []

PROVIDER_PRICING: Dict[str, Dict[str, Any]] = {
    "byteplus": {
        "id": "byteplus",
        "name": "BytePlus ModelArk (Official)",
        "badge": "Official / Lowest Cost",
        "env_key": "ARK_API_KEY",
        "base_url": PROVIDERS["byteplus"]["base_url"],
        "auth_header": "Authorization: Bearer <ARK_API_KEY>",
        "rate_480p_per_sec": 0.10,
        "rate_720p_per_sec": 0.23,
        "rate_1080p_per_sec": 0.45,
        "rate_4k_per_sec": 0.70,
        "docs_url": PROVIDERS["byteplus"]["docs_url"],
        "notes": "First-party ByteDance international cloud API. Supports 480p drafts (valid 7 days), 30s clips, and 50 multimodal references.",
    },
    "fal": {
        "id": "fal",
        "name": "fal.ai (US Enterprise)",
        "badge": "Best US Infrastructure",
        "env_key": "FAL_KEY",
        "base_url": PROVIDERS["fal"]["base_url"],
        "auth_header": "Authorization: Key <FAL_KEY>",
        "rate_480p_per_sec": 0.22,
        "rate_720p_per_sec": 0.47,
        "rate_1080p_per_sec": 0.75,
        "rate_4k_per_sec": 1.10,
        "docs_url": PROVIDERS["fal"]["docs_url"],
        "notes": "US-hosted enterprise queue with zero cold starts, native /draft/complete endpoint, and official ByteDance partnership.",
    },
    "wavespeed": {
        "id": "wavespeed",
        "name": "WaveSpeedAI (REST v3)",
        "badge": "Drop-In REST / Fast",
        "env_key": "WAVESPEED_API_KEY",
        "base_url": PROVIDERS["wavespeed"]["base_url"],
        "auth_header": "Authorization: Bearer <WAVESPEED_API_KEY>",
        "rate_480p_per_sec": 0.18,
        "rate_720p_per_sec": 0.36,
        "rate_1080p_per_sec": 0.60,
        "rate_4k_per_sec": 0.95,
        "docs_url": PROVIDERS["wavespeed"]["docs_url"],
        "notes": "Verified Hugging Face provider with dedicated endpoints for all 7 Seedance 2.5 workflows and /predictions/{id}/result polling.",
    },
    "replicate": {
        "id": "replicate",
        "name": "Replicate",
        "badge": "Unified Multimodal",
        "env_key": "REPLICATE_API_TOKEN",
        "base_url": PROVIDERS["replicate"]["base_url"],
        "auth_header": "Authorization: Bearer <REPLICATE_API_TOKEN>",
        "rate_480p_per_sec": 0.20,
        "rate_720p_per_sec": 0.40,
        "rate_1080p_per_sec": 0.68,
        "rate_4k_per_sec": 1.00,
        "docs_url": PROVIDERS["replicate"]["docs_url"],
        "notes": "Single unified bytedance/seedance-2.5 prediction endpoint accepting text, 30 images, 10 videos, and 10 audio files.",
    },
    "muapi": {
        "id": "muapi",
        "name": "MuAPI (Legacy)",
        "badge": "Legacy Wrapper",
        "env_key": "MUAPI_API_KEY",
        "base_url": PROVIDERS["muapi"]["base_url"],
        "auth_header": "x-api-key: <MUAPI_API_KEY>",
        "rate_480p_per_sec": 0.12,
        "rate_720p_per_sec": 0.25,
        "rate_1080p_per_sec": 0.50,
        "rate_4k_per_sec": 0.85,
        "docs_url": PROVIDERS["muapi"]["docs_url"],
        "notes": "Original repository default wrapper.",
    },
}

MODE_SPECS: Dict[str, Dict[str, Any]] = {
    "text_to_video": {
        "id": "text_to_video",
        "label": "Text to Video",
        "short": "T2V",
        "endpoint": "/seedance-2.5-spicy-text-to-video",
        "base_cost": 0.60,
        "duration_min": 4,
        "duration_max": 16,
        "supports_draft": True,
        "supports_audio": True,
        "supports_camera_fixed": True,
        "supports_seed": False,
        "supports_aspect_ratio": True,
        "aspect_ratios": ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "adaptive"],
        "description": "Generate photorealistic 4K video directly from a high-contrast text prompt.",
    },
    "image_to_video": {
        "id": "image_to_video",
        "label": "Image to Video",
        "short": "I2V",
        "endpoint": "/seedance-2.5-spicy-image-to-video",
        "base_cost": 0.60,
        "duration_min": 4,
        "duration_max": 16,
        "supports_draft": True,
        "supports_audio": True,
        "supports_camera_fixed": True,
        "supports_seed": False,
        "supports_aspect_ratio": False,
        "description": "Animate a source image into a cinematic clip with optional last-frame target control.",
    },
    "first_last_frame": {
        "id": "first_last_frame",
        "label": "First & Last Frame",
        "short": "F&L",
        "endpoint": "/seedance-2.5-spicy-first-last-frame",
        "base_cost": 1.87,
        "duration_min": 4,
        "duration_max": 30,
        "supports_draft": True,
        "supports_audio": False,
        "supports_camera_fixed": False,
        "supports_seed": True,
        "supports_aspect_ratio": False,
        "description": "Synthesize a seamless transition between an exact start frame and end frame (up to 30 seconds).",
    },
    "omni_reference": {
        "id": "omni_reference",
        "label": "Omni Reference",
        "short": "OMNI",
        "endpoint": "/seedance-2.5-spicy-omni-reference",
        "base_cost": 1.87,
        "duration_min": 4,
        "duration_max": 30,
        "supports_draft": True,
        "supports_audio": False,
        "supports_camera_fixed": False,
        "supports_seed": True,
        "supports_aspect_ratio": True,
        "aspect_ratios": ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "9:21", "adaptive"],
        "description": "Blend up to 30 reference images, 10 video clips, and 10 audio files into a unified guided generation.",
    },
    "video_edit": {
        "id": "video_edit",
        "label": "Video Edit",
        "short": "EDIT",
        "endpoint": "/seedance-2.5-spicy-video-edit",
        "base_cost": 1.87,
        "duration_min": 4,
        "duration_max": 30,
        "supports_draft": False,
        "supports_audio": True,
        "supports_camera_fixed": False,
        "supports_seed": True,
        "supports_aspect_ratio": False,
        "description": "Rewrite lighting, weather, style, or subject details of an input video via natural-language instructions.",
    },
    "video_extend": {
        "id": "video_extend",
        "label": "Video Extend",
        "short": "EXT",
        "endpoint": "/seedance-2.5-spicy-video-extend",
        "base_cost": 1.87,
        "duration_min": 4,
        "duration_max": 30,
        "supports_draft": False,
        "supports_audio": True,
        "supports_camera_fixed": False,
        "supports_seed": True,
        "supports_aspect_ratio": False,
        "description": "Continue an existing video smoothly from its final frame with optional target frame interpolation.",
    },
    "motion_control": {
        "id": "motion_control",
        "label": "Motion Control",
        "short": "MOT",
        "endpoint": "/seedance-2.5-spicy-motion-control",
        "base_cost": 1.65,
        "duration_min": 4,
        "duration_max": 30,
        "supports_draft": False,
        "supports_audio": True,
        "supports_camera_fixed": False,
        "supports_seed": True,
        "supports_aspect_ratio": True,
        "aspect_ratios": ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "9:21", "adaptive"],
        "description": "Recast performers and environments in a reference video while preserving choreography and camera trajectories.",
    },
}


class GenerateRequest(BaseModel):
    mode: str = Field(..., description="One of the 7 Seedance 2.5 generation modes")
    provider: str = Field(default="byteplus", description="Provider: byteplus, fal, wavespeed, replicate, or muapi")
    prompt: Optional[str] = None
    aspect_ratio: str = "16:9"
    duration: int = 5
    resolution: str = "720p"
    generate_audio: bool = True
    camera_fixed: bool = False
    high_bitrate: bool = False
    draft: bool = False
    draft_request_id: Optional[str] = None
    seed: int = -1
    image_url: Optional[str] = None
    last_image: Optional[str] = None
    video_url: Optional[str] = None
    images_list: Optional[List[str]] = None
    videos_list: Optional[List[str]] = None
    audios_list: Optional[List[str]] = None
    omni_reference_task_type: str = "auto"
    mock: bool = True
    instant_mock: bool = False


def _resolve_api_client(provider: str = "byteplus", header_key: Optional[str] = None) -> Seedance25SpicyAPI:
    provider = (provider or "byteplus").strip().lower()
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
    env_var = PROVIDERS[provider]["env_key"]
    key = (header_key or "").strip() or os.getenv(env_var)
    if not key and provider == "muapi":
        key = os.getenv("MUAPI_API_KEY")
    if not key:
        raise HTTPException(
            status_code=401,
            detail=f"Missing API key for provider '{provider}'. Provide X-Provider-Key in the studio header, set {env_var} in .env, or enable Sandbox Mode.",
        )
    return Seedance25SpicyAPI(api_key=key, provider=provider)


def _validate_and_build_payload(req: GenerateRequest) -> Dict[str, Any]:
    if req.mode not in MODE_SPECS:
        raise HTTPException(status_code=400, detail=f"Unsupported generation mode: {req.mode}")
    if req.provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {req.provider}")

    spec = MODE_SPECS[req.mode]
    if req.resolution not in ("480p", "720p", "1080p", "4k"):
        raise HTTPException(status_code=400, detail="Resolution must be one of: 480p, 720p, 1080p, 4k")

    is_omni_edit = req.mode == "omni_reference" and req.omni_reference_task_type == "edit"
    if not is_omni_edit:
        if req.duration < spec["duration_min"] or req.duration > spec["duration_max"]:
            raise HTTPException(
                status_code=400,
                detail=f"Duration for {spec['label']} must be between {spec['duration_min']} and {spec['duration_max']} seconds.",
            )

    if req.mode == "text_to_video":
        if not req.prompt or not req.prompt.strip():
            raise HTTPException(status_code=400, detail="Prompt is required for Text-to-Video.")
        payload: Dict[str, Any] = {
            "prompt": req.prompt.strip(),
            "aspect_ratio": req.aspect_ratio,
            "duration": req.duration,
            "resolution": req.resolution,
            "generate_audio": req.generate_audio,
            "camera_fixed": req.camera_fixed,
            "high_bitrate": req.high_bitrate,
            "draft": req.draft,
        }
        if req.draft_request_id:
            payload["draft_request_id"] = req.draft_request_id.strip()
        return payload

    if req.mode == "image_to_video":
        if not req.prompt or not req.prompt.strip():
            raise HTTPException(status_code=400, detail="Prompt is required for Image-to-Video.")
        if not req.image_url or not req.image_url.strip():
            raise HTTPException(status_code=400, detail="image_url is required for Image-to-Video.")
        payload = {
            "prompt": req.prompt.strip(),
            "image_url": req.image_url.strip(),
            "duration": req.duration,
            "resolution": req.resolution,
            "generate_audio": req.generate_audio,
            "camera_fixed": req.camera_fixed,
            "high_bitrate": req.high_bitrate,
            "draft": req.draft,
        }
        if req.last_image and req.last_image.strip():
            payload["last_image"] = req.last_image.strip()
        if req.draft_request_id:
            payload["draft_request_id"] = req.draft_request_id.strip()
        return payload

    if req.mode == "first_last_frame":
        if not req.prompt or not req.prompt.strip():
            raise HTTPException(status_code=400, detail="Prompt is required for First & Last Frame.")
        imgs = [u.strip() for u in (req.images_list or []) if u and u.strip()]
        if len(imgs) != 2:
            raise HTTPException(
                status_code=400,
                detail="First & Last Frame requires exactly 2 image URLs: [first_frame, last_frame].",
            )
        payload = {
            "prompt": req.prompt.strip(),
            "images_list": imgs,
            "resolution": req.resolution,
            "duration": req.duration,
            "seed": req.seed,
            "high_bitrate": req.high_bitrate,
            "draft": req.draft,
        }
        if req.draft_request_id:
            payload["draft_request_id"] = req.draft_request_id.strip()
        return payload

    if req.mode == "omni_reference":
        if not req.prompt or not req.prompt.strip():
            raise HTTPException(status_code=400, detail="Prompt is required for Omni Reference.")
        task_type = req.omni_reference_task_type or "auto"
        if task_type not in ("auto", "reference", "edit", "extend"):
            raise HTTPException(status_code=400, detail="omni_reference_task_type must be auto, reference, edit, or extend.")
        if task_type in ("edit", "extend") and req.aspect_ratio != "adaptive":
            raise HTTPException(
                status_code=400,
                detail=f"Omni Reference task_type='{task_type}' requires aspect_ratio='adaptive'.",
            )
        if task_type == "edit" and req.duration != -1:
            raise HTTPException(
                status_code=400,
                detail="Omni Reference task_type='edit' requires duration=-1.",
            )
        imgs = [u.strip() for u in (req.images_list or []) if u and u.strip()]
        vids = [u.strip() for u in (req.videos_list or []) if u and u.strip()]
        auds = [u.strip() for u in (req.audios_list or []) if u and u.strip()]
        if len(imgs) > 30:
            raise HTTPException(status_code=400, detail="Omni Reference accepts up to 30 images.")
        if len(vids) > 10:
            raise HTTPException(status_code=400, detail="Omni Reference accepts up to 10 videos.")
        if len(auds) > 10:
            raise HTTPException(status_code=400, detail="Omni Reference accepts up to 10 audio files.")

        payload = {
            "prompt": req.prompt.strip(),
            "resolution": req.resolution,
            "duration": req.duration,
            "aspect_ratio": req.aspect_ratio,
            "omni_reference_task_type": task_type,
            "seed": req.seed,
            "high_bitrate": req.high_bitrate,
            "draft": req.draft,
        }
        if imgs:
            payload["images_list"] = imgs
        if vids:
            payload["videos_list"] = vids
        if auds:
            payload["audios_list"] = auds
        if req.draft_request_id:
            payload["draft_request_id"] = req.draft_request_id.strip()
        return payload

    if req.mode == "video_edit":
        if not req.prompt or not req.prompt.strip():
            raise HTTPException(status_code=400, detail="Prompt is required for Video Edit.")
        if not req.video_url or not req.video_url.strip():
            raise HTTPException(status_code=400, detail="video_url is required for Video Edit.")
        imgs = [u.strip() for u in (req.images_list or []) if u and u.strip()]
        auds = [u.strip() for u in (req.audios_list or []) if u and u.strip()]
        payload = {
            "prompt": req.prompt.strip(),
            "video_url": req.video_url.strip(),
            "resolution": req.resolution,
            "duration": req.duration,
            "generate_audio": req.generate_audio,
            "seed": req.seed,
            "high_bitrate": req.high_bitrate,
        }
        if imgs:
            payload["images_list"] = imgs
        if auds:
            payload["audios_list"] = auds
        return payload

    if req.mode == "video_extend":
        if not req.prompt or not req.prompt.strip():
            raise HTTPException(status_code=400, detail="Prompt is required for Video Extend.")
        if not req.video_url or not req.video_url.strip():
            raise HTTPException(status_code=400, detail="video_url is required for Video Extend.")
        payload = {
            "prompt": req.prompt.strip(),
            "video_url": req.video_url.strip(),
            "resolution": req.resolution,
            "duration": req.duration,
            "generate_audio": req.generate_audio,
            "seed": req.seed,
            "high_bitrate": req.high_bitrate,
        }
        if req.last_image and req.last_image.strip():
            payload["last_image"] = req.last_image.strip()
        return payload

    if req.mode == "motion_control":
        if not req.video_url or not req.video_url.strip():
            raise HTTPException(status_code=400, detail="video_url is required for Motion Control.")
        imgs = [u.strip() for u in (req.images_list or []) if u and u.strip()]
        payload = {
            "video_url": req.video_url.strip(),
            "aspect_ratio": req.aspect_ratio,
            "duration": req.duration,
            "seed": req.seed,
            "high_bitrate": req.high_bitrate,
            "generate_audio": req.generate_audio,
        }
        if imgs:
            payload["images_list"] = imgs
        if req.prompt and req.prompt.strip():
            payload["prompt"] = req.prompt.strip()
        return payload

    raise HTTPException(status_code=400, detail=f"Unhandled mode: {req.mode}")


@app.get("/api/config")
def get_config():
    providers_out = {}
    default_provider = "byteplus"
    found_key = False
    for pid, pmeta in PROVIDER_PRICING.items():
        val = os.getenv(pmeta["env_key"], "")
        has_key = bool(val)
        if has_key and not found_key:
            default_provider = pid
            found_key = True
        providers_out[pid] = {
            **pmeta,
            "has_env_key": has_key,
        }

    return {
        "default_provider": default_provider,
        "has_any_env_key": found_key,
        "providers": providers_out,
        "modes": MODE_SPECS,
    }


@app.post("/api/generate")
def generate_video(
    req: GenerateRequest,
    x_provider_key: Optional[str] = Header(default=None),
    x_muapi_key: Optional[str] = Header(default=None),
):
    canonical_payload = _validate_and_build_payload(req)
    spec = MODE_SPECS[req.mode]
    resolved_header_key = x_provider_key or x_muapi_key

    # Build exact provider endpoint & translated payload using SDK adapter
    preview_client = Seedance25SpicyAPI(api_key="sandbox-preview-key", provider=req.provider)
    provider_endpoint, provider_payload = preview_client.build_request_spec(req.mode, canonical_payload)

    if req.mock:
        request_id = f"mock-{req.provider}-{spec['short'].lower()}-{uuid.uuid4().hex[:8]}"
        now = time.time()
        task_record = {
            "request_id": request_id,
            "provider": req.provider,
            "provider_name": PROVIDER_PRICING[req.provider]["name"],
            "mode": req.mode,
            "mode_label": spec["label"],
            "endpoint": provider_endpoint,
            "payload": provider_payload,
            "canonical_payload": canonical_payload,
            "mock": True,
            "created_at": now,
            "polls": 0,
            "instant_mock": req.instant_mock,
            "status": "completed" if req.instant_mock else "processing",
            "draft": bool(canonical_payload.get("draft")),
            "resolution": canonical_payload.get("resolution", "720p"),
            "duration": canonical_payload.get("duration", 5),
        }
        if req.instant_mock:
            task_record["outputs"] = ["/static/sandbox_preview.mp4"]
            task_record["url"] = "/static/sandbox_preview.mp4"
        MOCK_TASKS[request_id] = task_record
        TASK_HISTORY.insert(0, task_record)
        return {
            "request_id": request_id,
            "provider": req.provider,
            "status": task_record["status"],
            "mode": req.mode,
            "mock": True,
            "endpoint": provider_endpoint,
            "payload": provider_payload,
        }

    # Live call via selected provider
    api = _resolve_api_client(req.provider, resolved_header_key)
    try:
        if req.mode == "text_to_video":
            res = api.text_to_video(**canonical_payload)
        elif req.mode == "image_to_video":
            res = api.image_to_video(**canonical_payload)
        elif req.mode == "first_last_frame":
            res = api.first_last_frame(**canonical_payload)
        elif req.mode == "omni_reference":
            res = api.omni_reference(**canonical_payload)
        elif req.mode == "video_edit":
            res = api.video_edit(**canonical_payload)
        elif req.mode == "video_extend":
            res = api.video_extend(**canonical_payload)
        elif req.mode == "motion_control":
            res = api.motion_control(**canonical_payload)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported mode: {req.mode}")
    except requests.HTTPError as exc:
        err_body = exc.response.text if exc.response is not None else str(exc)
        status_code = exc.response.status_code if exc.response is not None else 502
        raise HTTPException(status_code=status_code, detail=f"{req.provider} API error: {err_body}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Request failed: {exc}")

    request_id = res.get("request_id") or f"live-{uuid.uuid4().hex[:8]}"
    record = {
        "request_id": request_id,
        "provider": req.provider,
        "provider_name": PROVIDER_PRICING[req.provider]["name"],
        "mode": req.mode,
        "mode_label": spec["label"],
        "endpoint": provider_endpoint,
        "payload": provider_payload,
        "canonical_payload": canonical_payload,
        "mock": False,
        "created_at": time.time(),
        "status": res.get("status", "processing"),
        "draft": bool(canonical_payload.get("draft")),
        "resolution": canonical_payload.get("resolution", "720p"),
        "duration": canonical_payload.get("duration", 5),
        "raw_response": res,
    }
    TASK_HISTORY.insert(0, record)
    return {
        **res,
        "request_id": request_id,
        "provider": req.provider,
        "mode": req.mode,
        "mock": False,
        "endpoint": provider_endpoint,
        "payload": provider_payload,
    }


@app.post("/api/upload")
async def upload_media(
    file: UploadFile = File(...),
    mock: bool = Form(default=True),
    provider: str = Form(default="byteplus"),
    x_provider_key: Optional[str] = Header(default=None),
    x_muapi_key: Optional[str] = Header(default=None),
):
    filename = file.filename or "uploaded_media.bin"
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    if mock:
        mock_url = f"https://assets.seedance-sandbox.local/{provider}/{uuid.uuid4().hex[:8]}/{filename}"
        return {
            "url": mock_url,
            "filename": filename,
            "size_bytes": len(content),
            "provider": provider,
            "mock": True,
        }

    api = _resolve_api_client(provider, x_provider_key or x_muapi_key)
    suffix = Path(filename).suffix or ".bin"
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        result = api.upload_file(tmp_path)
        return {
            **result,
            "filename": filename,
            "size_bytes": len(content),
            "provider": provider,
            "mock": False,
        }
    except requests.HTTPError as exc:
        err_body = exc.response.text if exc.response is not None else str(exc)
        status_code = exc.response.status_code if exc.response is not None else 502
        raise HTTPException(status_code=status_code, detail=f"{provider} upload error: {err_body}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.get("/api/status/{request_id}")
def get_task_status(
    request_id: str,
    provider: str = Query(default="byteplus"),
    x_provider_key: Optional[str] = Header(default=None),
    x_muapi_key: Optional[str] = Header(default=None),
):
    if request_id in MOCK_TASKS:
        task = MOCK_TASKS[request_id]
        task["polls"] += 1
        elapsed = time.time() - task["created_at"]
        if task["instant_mock"] or task["polls"] >= 2 or elapsed >= 1.5:
            task["status"] = "completed"
            video_url = "/static/sandbox_preview.mp4"
            task["outputs"] = [video_url]
            task["url"] = video_url
            return {
                "request_id": request_id,
                "provider": task["provider"],
                "provider_name": task["provider_name"],
                "status": "completed",
                "mock": True,
                "mode": task["mode"],
                "mode_label": task["mode_label"],
                "draft": task["draft"],
                "resolution": task["resolution"],
                "duration": task["duration"],
                "endpoint": task["endpoint"],
                "payload": task["payload"],
                "outputs": [video_url],
                "url": video_url,
            }
        return {
            "request_id": request_id,
            "provider": task["provider"],
            "provider_name": task["provider_name"],
            "status": "processing",
            "mock": True,
            "mode": task["mode"],
            "mode_label": task["mode_label"],
            "draft": task["draft"],
            "resolution": task["resolution"],
            "duration": task["duration"],
            "endpoint": task["endpoint"],
            "payload": task["payload"],
        }

    api = _resolve_api_client(provider, x_provider_key or x_muapi_key)
    try:
        result = api.get_result(request_id)
        return result
    except requests.HTTPError as exc:
        err_body = exc.response.text if exc.response is not None else str(exc)
        status_code = exc.response.status_code if exc.response is not None else 502
        raise HTTPException(status_code=status_code, detail=f"{provider} status error: {err_body}")


@app.get("/api/history")
def get_history(limit: int = Query(default=20, ge=1, le=100)):
    return {"tasks": TASK_HISTORY[:limit]}


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
def serve_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>Seedance 2.5 Studio</h1><p>Static UI files not found.</p>", status_code=200)
    return FileResponse(str(index_file))
