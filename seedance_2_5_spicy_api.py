import base64
import mimetypes
import os
import time
from dotenv import load_dotenv
import requests

# Load environment variables from .env file
load_dotenv()

PROVIDERS = {
    "byteplus": {
        "name": "BytePlus ModelArk (Official ByteDance)",
        "base_url": "https://ark.ap-southeast.bytepluses.com/api/v3",
        "env_key": "ARK_API_KEY",
        "auth_type": "bearer",
        "model_id": "seedance-2-5-260628",
        "docs_url": "https://docs.byteplus.com/en/docs/ModelArk/2607688",
    },
    "fal": {
        "name": "fal.ai (US Enterprise Queue)",
        "base_url": "https://queue.fal.run",
        "env_key": "FAL_KEY",
        "auth_type": "fal_key",
        "docs_url": "https://fal.ai/models/bytedance/seedance-2.5/us/text-to-video/api",
    },
    "wavespeed": {
        "name": "WaveSpeedAI (REST v3)",
        "base_url": "https://api.wavespeed.ai/api/v3",
        "env_key": "WAVESPEED_API_KEY",
        "auth_type": "bearer",
        "docs_url": "https://wavespeed.ai/seedance-2-5-api",
    },
    "replicate": {
        "name": "Replicate (bytedance/seedance-2.5)",
        "base_url": "https://api.replicate.com/v1",
        "env_key": "REPLICATE_API_TOKEN",
        "auth_type": "bearer",
        "docs_url": "https://replicate.com/bytedance/seedance-2.5/api",
    },
    "muapi": {
        "name": "MuAPI (Legacy Wrapper)",
        "base_url": "https://api.muapi.ai/api/v1",
        "env_key": "MUAPI_API_KEY",
        "auth_type": "x_api_key",
        "docs_url": "https://muapi.ai/docs/api-reference",
    },
}


class Seedance25SpicyAPI:
    def __init__(self, api_key=None, provider=None, base_url=None, model_id=None):
        """
        Initialize the Seedance 2.5 API client with multi-provider support.

        :param api_key: Provider API key. Defaults to the provider's env var
                        (ARK_API_KEY, FAL_KEY, WAVESPEED_API_KEY, REPLICATE_API_TOKEN, or MUAPI_API_KEY).
        :param provider: 'byteplus', 'fal', 'wavespeed', 'replicate', or 'muapi'.
                         Defaults to SEEDANCE_PROVIDER env var or 'muapi' (or auto-detected from set env keys).
        :param base_url: Optional custom base URL override.
        :param model_id: Optional model ID override (used by BytePlus ModelArk, default 'seedance-2-5-260628').
        """
        resolved_provider = (provider or os.getenv("SEEDANCE_PROVIDER") or "").strip().lower()
        if not resolved_provider:
            # Auto-detect if a reliable provider env key is set and MUAPI_API_KEY is not
            for p_key in ("byteplus", "fal", "wavespeed", "replicate", "muapi"):
                if os.getenv(PROVIDERS[p_key]["env_key"]):
                    resolved_provider = p_key
                    break
            else:
                resolved_provider = "muapi"

        if resolved_provider not in PROVIDERS:
            raise ValueError(
                f"Unsupported provider '{resolved_provider}'. Choose from: {', '.join(PROVIDERS.keys())}"
            )

        self.provider = resolved_provider
        self.provider_info = PROVIDERS[self.provider]
        env_var = self.provider_info["env_key"]

        # Only fall back to MUAPI_API_KEY if the provider is muapi
        self.api_key = api_key or os.getenv(env_var)
        if not self.api_key and self.provider == "muapi":
            self.api_key = os.getenv("MUAPI_API_KEY")

        if not self.api_key:
            raise ValueError(
                f"API Key is required for provider '{self.provider}'. "
                f"Set {env_var} in .env or pass api_key to the constructor."
            )

        self.base_url = (base_url or os.getenv("SEEDANCE_BASE_URL") or self.provider_info["base_url"]).rstrip("/")
        self.model_id = model_id or os.getenv("SEEDANCE_MODEL_ID") or self.provider_info.get("model_id", "seedance-2-5-260628")

        auth_type = self.provider_info["auth_type"]
        if auth_type == "bearer":
            self.headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        elif auth_type == "fal_key":
            self.headers = {
                "Authorization": f"Key {self.api_key}",
                "Content-Type": "application/json",
            }
        else:
            self.headers = {
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
            }

    def build_request_spec(self, mode: str, payload: dict) -> tuple[str, dict]:
        """
        Translates a canonical Seedance 2.5 task mode and payload into the
        target provider's exact (endpoint_url, provider_payload) tuple.
        """
        if self.provider == "wavespeed":
            route_map = {
                "text_to_video": "/bytedance/seedance-2.5/text-to-video",
                "image_to_video": "/bytedance/seedance-2.5/image-to-video",
                "first_last_frame": "/bytedance/seedance-2.5/image-to-video",
                "omni_reference": "/bytedance/seedance-2.5/reference-to-video",
                "video_edit": "/bytedance/seedance-2.5/video-edit",
                "video_extend": "/bytedance/seedance-2.5/video-extend",
                "motion_control": "/bytedance/seedance-2.5/motion-control",
            }
            endpoint = f"{self.base_url}{route_map[mode]}"
            ws_payload = dict(payload)
            if mode == "first_last_frame" and "images_list" in ws_payload:
                imgs = ws_payload.pop("images_list")
                if len(imgs) >= 1:
                    ws_payload["image_url"] = imgs[0]
                if len(imgs) >= 2:
                    ws_payload["last_image"] = imgs[1]
            return endpoint, ws_payload

        if self.provider == "fal":
            if payload.get("draft_request_id"):
                return (
                    f"{self.base_url}/bytedance/seedance-2.5/us/draft/complete",
                    {
                        "draft_request_id": payload["draft_request_id"],
                        "resolution": payload.get("resolution", "1080p"),
                    },
                )
            route_map = {
                "text_to_video": "/bytedance/seedance-2.5/us/text-to-video",
                "image_to_video": "/bytedance/seedance-2.5/us/image-to-video",
                "first_last_frame": "/bytedance/seedance-2.5/us/image-to-video",
                "omni_reference": "/bytedance/seedance-2.5/us/reference-to-video",
                "video_edit": "/bytedance/seedance-2.5/us/reference-to-video",
                "video_extend": "/bytedance/seedance-2.5/us/reference-to-video",
                "motion_control": "/bytedance/seedance-2.5/us/reference-to-video",
            }
            endpoint = f"{self.base_url}{route_map[mode]}"
            fal_payload = dict(payload)
            if mode == "first_last_frame" and "images_list" in fal_payload:
                imgs = fal_payload.pop("images_list")
                if len(imgs) >= 1:
                    fal_payload["image_url"] = imgs[0]
                if len(imgs) >= 2:
                    fal_payload["end_image_url"] = imgs[1]
            elif mode == "image_to_video" and "last_image" in fal_payload:
                fal_payload["end_image_url"] = fal_payload.pop("last_image")
            return endpoint, fal_payload

        if self.provider == "byteplus":
            endpoint = f"{self.base_url}/contents/generations/tasks"
            content = []
            if payload.get("draft_request_id"):
                content.append({
                    "type": "draft_task",
                    "draft_task": {"id": payload["draft_request_id"]},
                })
            else:
                if payload.get("prompt"):
                    content.append({"type": "text", "text": payload["prompt"]})
                if payload.get("image_url"):
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": payload["image_url"]},
                        "role": "first_frame",
                    })
                if payload.get("last_image"):
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": payload["last_image"]},
                        "role": "last_frame",
                    })
                if payload.get("video_url"):
                    content.append({
                        "type": "video_url",
                        "video_url": {"url": payload["video_url"]},
                    })
                imgs = payload.get("images_list") or []
                for idx, img_url in enumerate(imgs):
                    role = (
                        "first_frame"
                        if (mode == "first_last_frame" and idx == 0)
                        else ("last_frame" if (mode == "first_last_frame" and idx == 1) else "reference_image")
                    )
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": img_url},
                        "role": role,
                    })
                for vid_url in payload.get("videos_list") or []:
                    content.append({
                        "type": "video_url",
                        "video_url": {"url": vid_url},
                        "role": "reference_video",
                    })
                for aud_url in payload.get("audios_list") or []:
                    content.append({
                        "type": "audio_url",
                        "audio_url": {"url": aud_url},
                        "role": "reference_audio",
                    })

            bp_payload = {
                "model": self.model_id,
                "content": content,
                "resolution": payload.get("resolution", "720p"),
                "duration": payload.get("duration", 5),
                "generate_audio": payload.get("generate_audio", True),
                "camera_fixed": payload.get("camera_fixed", False),
                "draft": payload.get("draft", False),
            }
            if "aspect_ratio" in payload:
                bp_payload["ratio"] = payload["aspect_ratio"]
            if "seed" in payload and payload["seed"] is not None:
                bp_payload["seed"] = payload["seed"]
            if "omni_reference_task_type" in payload:
                bp_payload["omni_reference_task_type"] = payload["omni_reference_task_type"]
            return endpoint, bp_payload

        if self.provider == "replicate":
            endpoint = f"{self.base_url}/models/bytedance/seedance-2.5/predictions"
            rep_input = dict(payload)
            return endpoint, {"input": rep_input}

        # Default: muapi
        muapi_routes = {
            "text_to_video": "/seedance-2.5-spicy-text-to-video",
            "image_to_video": "/seedance-2.5-spicy-image-to-video",
            "first_last_frame": "/seedance-2.5-spicy-first-last-frame",
            "omni_reference": "/seedance-2.5-spicy-omni-reference",
            "video_edit": "/seedance-2.5-spicy-video-edit",
            "video_extend": "/seedance-2.5-spicy-video-extend",
            "motion_control": "/seedance-2.5-spicy-motion-control",
        }
        return f"{self.base_url}{muapi_routes[mode]}", payload

    def _normalize_submission_response(self, raw: dict) -> dict:
        """
        Ensures the returned dict always contains 'request_id' regardless of provider.
        """
        if not isinstance(raw, dict):
            return {"raw": raw}
        req_id = (
            raw.get("request_id")
            or raw.get("id")
            or (raw.get("data", {}) if isinstance(raw.get("data"), dict) else {}).get("id")
        )
        if req_id and "request_id" not in raw:
            raw = {**raw, "request_id": req_id}
        return raw

    def _normalize_status_response(self, raw: dict) -> dict:
        """
        Normalizes provider-specific status responses to include standard
        'status' ('processing' | 'completed' | 'failed') and 'outputs' list.
        """
        if not isinstance(raw, dict):
            return {"status": "processing", "raw": raw}

        out = dict(raw)
        # Unwrap WaveSpeed 'data' envelope if present
        data_obj = out.get("data") if isinstance(out.get("data"), dict) else out
        raw_status = str(data_obj.get("status") or out.get("status") or "").lower()

        if raw_status in ("completed", "succeeded", "success"):
            out["status"] = "completed"
        elif raw_status in ("failed", "error", "canceled", "cancelled", "expired"):
            out["status"] = "failed"
            if "error" not in out:
                out["error"] = data_obj.get("error") or out.get("detail") or "Task failed"
        elif raw_status:
            out["status"] = raw_status if self.provider == "muapi" else "processing"

        # Extract output video URLs across providers
        outputs = list(out.get("outputs") or data_obj.get("outputs") or [])
        if not outputs:
            # BytePlus ModelArk: content.video_url
            content_obj = data_obj.get("content")
            if isinstance(content_obj, dict) and content_obj.get("video_url"):
                outputs.append(content_obj["video_url"])
            # fal.ai: video.url
            video_obj = data_obj.get("video")
            if isinstance(video_obj, dict) and video_obj.get("url"):
                outputs.append(video_obj["url"])
            # Replicate: output (string or list)
            rep_out = data_obj.get("output")
            if isinstance(rep_out, str):
                outputs.append(rep_out)
            elif isinstance(rep_out, list):
                outputs.extend([x for x in rep_out if isinstance(x, str)])
            # Direct url fallback
            if not outputs and isinstance(data_obj.get("url"), str) and out.get("status") == "completed":
                outputs.append(data_obj["url"])

        if outputs:
            out["outputs"] = outputs
        return out

    def text_to_video(self, prompt, aspect_ratio="16:9", duration=5, resolution="720p",
                       generate_audio=True, camera_fixed=False, high_bitrate=False,
                       draft=False, draft_request_id=None):
        """
        Submits a Seedance 2.5 Spicy Text-to-Video task.
        """
        payload = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "duration": duration,
            "resolution": resolution,
            "generate_audio": generate_audio,
            "camera_fixed": camera_fixed,
            "high_bitrate": high_bitrate,
            "draft": draft,
        }
        if draft_request_id:
            payload["draft_request_id"] = draft_request_id
        endpoint, provider_payload = self.build_request_spec("text_to_video", payload)
        return self._post_request(endpoint, provider_payload)

    def image_to_video(self, prompt, image_url, last_image=None, duration=5, resolution="720p",
                        generate_audio=True, camera_fixed=False, high_bitrate=False,
                        draft=False, draft_request_id=None):
        """
        Submits a Seedance 2.5 Spicy Image-to-Video task.
        """
        payload = {
            "prompt": prompt,
            "image_url": image_url,
            "duration": duration,
            "resolution": resolution,
            "generate_audio": generate_audio,
            "camera_fixed": camera_fixed,
            "high_bitrate": high_bitrate,
            "draft": draft,
        }
        if last_image:
            payload["last_image"] = last_image
        if draft_request_id:
            payload["draft_request_id"] = draft_request_id
        endpoint, provider_payload = self.build_request_spec("image_to_video", payload)
        return self._post_request(endpoint, provider_payload)

    def first_last_frame(self, prompt, images_list, resolution="720p", duration=5, seed=-1,
                          high_bitrate=False, draft=False, draft_request_id=None):
        """
        Submits a Seedance 2.5 Spicy First & Last Frame task.
        """
        payload = {
            "prompt": prompt,
            "images_list": images_list,
            "resolution": resolution,
            "duration": duration,
            "seed": seed,
            "high_bitrate": high_bitrate,
            "draft": draft,
        }
        if draft_request_id:
            payload["draft_request_id"] = draft_request_id
        endpoint, provider_payload = self.build_request_spec("first_last_frame", payload)
        return self._post_request(endpoint, provider_payload)

    def omni_reference(self, prompt, images_list=None, videos_list=None, audios_list=None,
                        resolution="720p", duration=5, aspect_ratio="16:9",
                        omni_reference_task_type="auto", seed=-1, high_bitrate=False,
                        draft=False, draft_request_id=None):
        """
        Submits a Seedance 2.5 Spicy Omni Reference task.
        """
        payload = {
            "prompt": prompt,
            "resolution": resolution,
            "duration": duration,
            "aspect_ratio": aspect_ratio,
            "omni_reference_task_type": omni_reference_task_type,
            "seed": seed,
            "high_bitrate": high_bitrate,
            "draft": draft,
        }
        if images_list:
            payload["images_list"] = images_list
        if videos_list:
            payload["videos_list"] = videos_list
        if audios_list:
            payload["audios_list"] = audios_list
        if draft_request_id:
            payload["draft_request_id"] = draft_request_id
        endpoint, provider_payload = self.build_request_spec("omni_reference", payload)
        return self._post_request(endpoint, provider_payload)

    def video_edit(self, prompt, video_url, images_list=None, audios_list=None,
                    resolution="720p", duration=5, generate_audio=True, seed=-1,
                    high_bitrate=False):
        """
        Submits a Seedance 2.5 Spicy Video Edit task.
        """
        payload = {
            "prompt": prompt,
            "video_url": video_url,
            "resolution": resolution,
            "duration": duration,
            "generate_audio": generate_audio,
            "seed": seed,
            "high_bitrate": high_bitrate,
        }
        if images_list:
            payload["images_list"] = images_list
        if audios_list:
            payload["audios_list"] = audios_list
        endpoint, provider_payload = self.build_request_spec("video_edit", payload)
        return self._post_request(endpoint, provider_payload)

    def video_extend(self, prompt, video_url, last_image=None, resolution="720p", duration=5,
                      generate_audio=True, seed=-1, high_bitrate=False):
        """
        Submits a Seedance 2.5 Spicy Video Extend task.
        """
        payload = {
            "prompt": prompt,
            "video_url": video_url,
            "resolution": resolution,
            "duration": duration,
            "generate_audio": generate_audio,
            "seed": seed,
            "high_bitrate": high_bitrate,
        }
        if last_image:
            payload["last_image"] = last_image
        endpoint, provider_payload = self.build_request_spec("video_extend", payload)
        return self._post_request(endpoint, provider_payload)

    def motion_control(self, video_url, images_list=None, prompt=None, aspect_ratio="16:9",
                        duration=5, seed=-1, high_bitrate=False, generate_audio=False):
        """
        Submits a Seedance 2.5 Spicy Motion Control task.
        """
        payload = {
            "video_url": video_url,
            "aspect_ratio": aspect_ratio,
            "duration": duration,
            "seed": seed,
            "high_bitrate": high_bitrate,
            "generate_audio": generate_audio,
        }
        if images_list:
            payload["images_list"] = images_list
        if prompt:
            payload["prompt"] = prompt
        endpoint, provider_payload = self.build_request_spec("motion_control", payload)
        return self._post_request(endpoint, provider_payload)

    def _post_request(self, endpoint, payload):
        response = requests.post(endpoint, json=payload, headers=self.headers)
        response.raise_for_status()
        return self._normalize_submission_response(response.json())

    def upload_file(self, file_path):
        """
        Uploads a file (image, video, or audio) for use in generation tasks.
        For providers that accept Data URIs directly (fal, byteplus, replicate),
        returns a base64 data URI if no dedicated upload endpoint is used.
        """
        if self.provider in ("fal", "byteplus", "replicate"):
            mime_type, _ = mimetypes.guess_type(file_path)
            mime_type = mime_type or "application/octet-stream"
            with open(file_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            return {"url": f"data:{mime_type};base64,{b64}", "provider": self.provider}

        if self.provider == "wavespeed":
            endpoint = f"{self.base_url}/media/upload/binary"
            headers = {"Authorization": f"Bearer {self.api_key}"}
        else:
            endpoint = f"{self.base_url}/upload_file"
            headers = {"x-api-key": self.api_key}

        with open(file_path, "rb") as file_data:
            files = {"file": file_data}
            response = requests.post(endpoint, headers=headers, files=files)

        response.raise_for_status()
        return response.json()

    def get_result(self, request_id):
        """
        Polls for the result of a generation task across any configured provider.
        """
        if self.provider == "byteplus":
            endpoint = f"{self.base_url}/contents/generations/tasks/{request_id}"
        elif self.provider == "fal":
            endpoint = f"{self.base_url}/bytedance/seedance-2.5/requests/{request_id}/status"
        elif self.provider == "replicate":
            endpoint = f"{self.base_url}/predictions/{request_id}"
        else:
            # WaveSpeedAI and MuAPI both use /predictions/{request_id}/result
            endpoint = f"{self.base_url}/predictions/{request_id}/result"

        response = requests.get(endpoint, headers=self.headers)
        response.raise_for_status()
        raw_json = response.json()

        # If fal queue status returns COMPLETED with response_url and no video object yet, fetch result payload
        if self.provider == "fal" and isinstance(raw_json, dict):
            status_val = str(raw_json.get("status", "")).upper()
            if status_val == "COMPLETED" and raw_json.get("response_url") and "video" not in raw_json:
                try:
                    res_obj = requests.get(raw_json["response_url"], headers=self.headers)
                    if res_obj.ok:
                        raw_json = {**raw_json, **res_obj.json(), "status": "completed"}
                except Exception:
                    pass

        return self._normalize_status_response(raw_json)

    def wait_for_completion(self, request_id, poll_interval=5, timeout=600):
        """
        Waits for the video generation to complete and returns the result.
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            result = self.get_result(request_id)
            status = result.get("status")

            if status == "completed":
                return result
            elif status == "failed":
                raise Exception(f"Video generation failed: {result.get('error')}")

            print(f"Status: {status}. Waiting {poll_interval} seconds...")
            time.sleep(poll_interval)

        raise TimeoutError("Timed out waiting for video generation to complete.")


if __name__ == "__main__":
    try:
        api = Seedance25SpicyAPI()
        prompt = (
            "A high-contrast, adrenaline-fueled chase through a rain-soaked neon "
            "megacity at night, sparks and shattering glass in slow motion, "
            "aggressive handheld camera energy, exaggerated color grading, 4K cinematic quality."
        )

        print(f"Submitting Seedance 2.5 task via provider '{api.provider}' with prompt: {prompt}")
        submission = api.text_to_video(prompt=prompt, duration=5, resolution="1080p")
        request_id = submission.get("request_id")
        print(f"Task submitted. Request ID: {request_id}")

        print("Waiting for completion...")
        result = api.wait_for_completion(request_id)
        print(f"Generation completed! Video URL: {result.get('outputs', [result.get('url')])[0]}")

    except Exception as e:
        print(f"Error: {e}")
