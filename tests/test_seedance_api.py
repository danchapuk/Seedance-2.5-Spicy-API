import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from seedance_2_5_spicy_api import PROVIDERS, Seedance25SpicyAPI
from server import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# 1. Multi-Provider SDK Unit Tests
# ---------------------------------------------------------------------------

def test_missing_api_key_raises(monkeypatch):
    for p in PROVIDERS.values():
        monkeypatch.delenv(p["env_key"], raising=False)
    monkeypatch.delenv("SEEDANCE_PROVIDER", raising=False)
    with pytest.raises(ValueError, match="API Key is required"):
        Seedance25SpicyAPI(api_key=None, provider="byteplus")


@patch("seedance_2_5_spicy_api.requests.post")
@patch("seedance_2_5_spicy_api.requests.get")
def test_byteplus_modelark_provider_translation_and_polling(mock_get, mock_post):
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {"id": "cgt-byteplus-999", "status": "queued"},
    )
    api = Seedance25SpicyAPI(api_key="ark-test-key", provider="byteplus")
    assert api.headers["Authorization"] == "Bearer ark-test-key"

    res = api.text_to_video(prompt="Neon street in Tokyo", resolution="1080p", duration=5, draft=True)
    assert res["request_id"] == "cgt-byteplus-999"

    called_url = mock_post.call_args[0][0]
    called_json = mock_post.call_args[1]["json"]
    assert called_url == "https://ark.ap-southeast.bytepluses.com/api/v3/contents/generations/tasks"
    assert called_json["model"] == "seedance-2-5-260628"
    assert called_json["content"] == [{"type": "text", "text": "Neon street in Tokyo"}]
    assert called_json["draft"] is True

    # Test BytePlus status normalization (succeeded -> completed, content.video_url -> outputs)
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "id": "cgt-byteplus-999",
            "status": "succeeded",
            "content": {"video_url": "https://tos.byteplus.com/output.mp4"},
        },
    )
    status_res = api.get_result("cgt-byteplus-999")
    assert status_res["status"] == "completed"
    assert status_res["outputs"] == ["https://tos.byteplus.com/output.mp4"]


@patch("seedance_2_5_spicy_api.requests.post")
@patch("seedance_2_5_spicy_api.requests.get")
def test_fal_provider_routes_and_draft_completion(mock_get, mock_post):
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {"request_id": "fal-req-123"},
    )
    api = Seedance25SpicyAPI(api_key="fal-secret", provider="fal")
    assert api.headers["Authorization"] == "Key fal-secret"

    # Standard I2V with last_image -> end_image_url
    api.image_to_video(
        prompt="Slow camera push",
        image_url="https://example.com/start.jpg",
        last_image="https://example.com/end.jpg",
    )
    url, kwargs = mock_post.call_args[0][0], mock_post.call_args[1]["json"]
    assert url == "https://queue.fal.run/bytedance/seedance-2.5/us/image-to-video"
    assert kwargs["image_url"] == "https://example.com/start.jpg"
    assert kwargs["end_image_url"] == "https://example.com/end.jpg"

    # Draft completion route on fal.ai
    api.text_to_video(prompt="Ignored", resolution="1080p", draft_request_id="fal-draft-001")
    draft_url, draft_json = mock_post.call_args[0][0], mock_post.call_args[1]["json"]
    assert draft_url == "https://queue.fal.run/bytedance/seedance-2.5/us/draft/complete"
    assert draft_json == {"draft_request_id": "fal-draft-001", "resolution": "1080p"}

    # Status normalization for fal.ai (video.url -> outputs)
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {"status": "COMPLETED", "video": {"url": "https://v3.fal.media/out.mp4"}},
    )
    st = api.get_result("fal-req-123")
    assert st["status"] == "completed"
    assert st["outputs"] == ["https://v3.fal.media/out.mp4"]


@patch("seedance_2_5_spicy_api.requests.post")
@patch("seedance_2_5_spicy_api.requests.get")
def test_wavespeed_provider_routes_and_polling(mock_get, mock_post):
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {"code": 200, "data": {"id": "ws-pred-777", "status": "created"}},
    )
    api = Seedance25SpicyAPI(api_key="ws-key", provider="wavespeed")
    res = api.omni_reference(
        prompt="Combine [Image1] and [Video1]",
        images_list=["https://example.com/i1.jpg"],
        videos_list=["https://example.com/v1.mp4"],
    )
    assert res["request_id"] == "ws-pred-777"
    assert mock_post.call_args[0][0] == "https://api.wavespeed.ai/api/v3/bytedance/seedance-2.5/reference-to-video"

    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "code": 200,
            "data": {"id": "ws-pred-777", "status": "completed", "outputs": ["https://cdn.wavespeed.ai/v.mp4"]},
        },
    )
    st = api.get_result("ws-pred-777")
    assert st["status"] == "completed"
    assert st["outputs"] == ["https://cdn.wavespeed.ai/v.mp4"]


@patch("seedance_2_5_spicy_api.requests.post")
@patch("seedance_2_5_spicy_api.requests.get")
def test_replicate_provider_unified_endpoint(mock_get, mock_post):
    mock_post.return_value = MagicMock(
        status_code=201,
        json=lambda: {"id": "rep-pred-42", "status": "starting"},
    )
    api = Seedance25SpicyAPI(api_key="r8_token", provider="replicate")
    res = api.video_extend(prompt="Continue driving along the cliff", video_url="https://example.com/car.mp4")
    assert res["request_id"] == "rep-pred-42"
    assert mock_post.call_args[0][0] == "https://api.replicate.com/v1/models/bytedance/seedance-2.5/predictions"
    assert "input" in mock_post.call_args[1]["json"]

    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {"id": "rep-pred-42", "status": "succeeded", "output": "https://replicate.delivery/out.mp4"},
    )
    st = api.get_result("rep-pred-42")
    assert st["status"] == "completed"
    assert st["outputs"] == ["https://replicate.delivery/out.mp4"]


@patch("seedance_2_5_spicy_api.requests.post")
def test_all_seven_methods_on_muapi_legacy(mock_post):
    mock_post.return_value = MagicMock(status_code=200, json=lambda: {"request_id": "mu-123"})
    api = Seedance25SpicyAPI(api_key="mu-key", provider="muapi")

    api.text_to_video("prompt")
    assert mock_post.call_args[0][0].endswith("/seedance-2.5-spicy-text-to-video")

    api.image_to_video("prompt", "https://example.com/a.jpg")
    assert mock_post.call_args[0][0].endswith("/seedance-2.5-spicy-image-to-video")

    api.first_last_frame("prompt", ["https://example.com/1.jpg", "https://example.com/2.jpg"])
    assert mock_post.call_args[0][0].endswith("/seedance-2.5-spicy-first-last-frame")

    api.omni_reference("prompt", images_list=["https://example.com/1.jpg"])
    assert mock_post.call_args[0][0].endswith("/seedance-2.5-spicy-omni-reference")

    api.video_edit("prompt", "https://example.com/v.mp4")
    assert mock_post.call_args[0][0].endswith("/seedance-2.5-spicy-video-edit")

    api.video_extend("prompt", "https://example.com/v.mp4")
    assert mock_post.call_args[0][0].endswith("/seedance-2.5-spicy-video-extend")

    api.motion_control("https://example.com/v.mp4", images_list=["https://example.com/p.jpg"], prompt="Recast")
    assert mock_post.call_args[0][0].endswith("/seedance-2.5-spicy-motion-control")


def test_wait_for_completion_success_and_failure():
    api = Seedance25SpicyAPI(api_key="test-key", provider="byteplus")
    with patch.object(
        api,
        "get_result",
        side_effect=[
            {"status": "processing"},
            {"status": "completed", "outputs": ["https://example.com/final.mp4"]},
        ],
    ):
        res = api.wait_for_completion("req-1", poll_interval=0.01, timeout=1)
        assert res["outputs"] == ["https://example.com/final.mp4"]

    with patch.object(api, "get_result", return_value={"status": "failed", "error": "Quota exceeded"}):
        with pytest.raises(Exception, match="Quota exceeded"):
            api.wait_for_completion("req-2", poll_interval=0.01, timeout=1)


# ---------------------------------------------------------------------------
# 2. FastAPI Web Studio Interface & Sandbox End-to-End Tests
# ---------------------------------------------------------------------------

def test_web_studio_index_and_config():
    res = client.get("/")
    assert res.status_code == 200
    assert "Seedance 2.5 Studio" in res.text

    cfg = client.get("/api/config").json()
    assert set(cfg["providers"].keys()) == {"byteplus", "fal", "wavespeed", "replicate", "muapi"}
    assert len(cfg["modes"]) == 7


@pytest.mark.parametrize("provider", ["byteplus", "fal", "wavespeed", "replicate", "muapi"])
def test_sandbox_generation_and_polling_across_all_providers(provider):
    gen_res = client.post(
        "/api/generate",
        json={
            "mode": "text_to_video",
            "provider": provider,
            "prompt": "Cinematic drone shot over volcanic coastline at dusk",
            "resolution": "720p",
            "duration": 5,
            "draft": True,
            "mock": True,
        },
    )
    assert gen_res.status_code == 200
    body = gen_res.json()
    req_id = body["request_id"]
    assert body["provider"] == provider
    assert body["mock"] is True

    # Poll 1 -> processing
    p1 = client.get(f"/api/status/{req_id}?provider={provider}").json()
    assert p1["status"] == "processing"

    # Poll 2 -> completed with playable video URL
    p2 = client.get(f"/api/status/{req_id}?provider={provider}").json()
    assert p2["status"] == "completed"
    assert p2["outputs"] == ["/static/sandbox_preview.mp4"]


def test_validation_guardrails_in_server():
    # First & Last Frame requires exactly 2 images
    bad_flf = client.post(
        "/api/generate",
        json={
            "mode": "first_last_frame",
            "provider": "byteplus",
            "prompt": "Transition",
            "images_list": ["https://example.com/only-one.jpg"],
            "mock": True,
        },
    )
    assert bad_flf.status_code == 400
    assert "exactly 2 image URLs" in bad_flf.json()["detail"]

    # Omni Reference edit mode requires aspect_ratio='adaptive' and duration=-1
    bad_omni = client.post(
        "/api/generate",
        json={
            "mode": "omni_reference",
            "provider": "byteplus",
            "prompt": "Edit scene",
            "omni_reference_task_type": "edit",
            "aspect_ratio": "16:9",
            "duration": 5,
            "mock": True,
        },
    )
    assert bad_omni.status_code == 400
    assert "adaptive" in bad_omni.json()["detail"]

    valid_omni_edit = client.post(
        "/api/generate",
        json={
            "mode": "omni_reference",
            "provider": "byteplus",
            "prompt": "Edit scene",
            "omni_reference_task_type": "edit",
            "aspect_ratio": "adaptive",
            "duration": -1,
            "mock": True,
            "instant_mock": True,
        },
    )
    assert valid_omni_edit.status_code == 200
    assert valid_omni_edit.json()["status"] == "completed"


def test_sandbox_file_upload():
    res = client.post(
        "/api/upload",
        files={"file": ("test_frame.jpg", b"fake-jpeg-bytes", "image/jpeg")},
        data={"mock": "true", "provider": "byteplus"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["mock"] is True
    assert data["filename"] == "test_frame.jpg"
    assert "test_frame.jpg" in data["url"]


def test_cli_help_and_subcommands():
    cli_path = Path(__file__).resolve().parent.parent / "skills" / "seedance-2.5-spicy" / "seedance_2_5_spicy_cli.py"
    proc = subprocess.run([sys.executable, str(cli_path), "--help"], capture_output=True, text=True, check=True)
    assert "--provider" in proc.stdout
    assert "upload" in proc.stdout
