(() => {
  const state = {
    mode: "text_to_video",
    provider: "byteplus",
    sandbox: true,
    providers: {},
    modes: {},
    tasks: [],
    activeTask: null,
    pollTimers: {},
  };

  const PRESETS = {
    cyberpunk: {
      mode: "text_to_video",
      prompt:
        "A high-contrast, adrenaline-fueled chase through a rain-soaked neon megacity at night, sparks and shattering glass in slow motion, aggressive handheld camera energy, 4K cinematic quality.",
      resolution: "1080p",
      duration: 5,
      aspect_ratio: "16:9",
    },
    dolly: {
      mode: "image_to_video",
      prompt:
        "Bold, high-energy dolly forward through a neon-drenched alley at night, shallow depth of field, wet pavement reflections.",
      image_url: "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=1280",
      resolution: "720p",
      duration: 5,
    },
    omni: {
      mode: "omni_reference",
      prompt:
        "Create a cinematic dusk sequence using [Image1] and [Image2] for lighting and architectural style, with smooth tracking motion.",
      images_list: [
        "https://images.unsplash.com/photo-1509198397868-475647b2a1e5?w=1280",
        "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=1280",
      ],
      resolution: "720p",
      duration: 6,
      aspect_ratio: "16:9",
    },
    edit: {
      mode: "video_edit",
      prompt: "Change the lighting to warm golden hour and add subtle volumetric fog across the background.",
      video_url: "https://assets.seedance-sandbox.local/sample/input-motion.mp4",
      resolution: "720p",
      duration: 5,
    },
  };

  // DOM Elements
  const el = (id) => document.getElementById(id);

  function parseListText(raw) {
    if (!raw) return [];
    return raw
      .split(/[\n,]+/)
      .map((s) => s.trim())
      .filter(Boolean);
  }

  function showToast(msg, type = "error") {
    const banner = el("feedback-banner");
    banner.textContent = msg;
    banner.className = `toast-banner ${type}`;
    setTimeout(() => {
      if (banner.textContent === msg) {
        banner.className = "toast-banner";
      }
    }, 6000);
  }

  function buildCurrentRequestObject() {
    const mode = state.mode;
    const req = {
      mode,
      provider: state.provider,
      mock: state.sandbox,
      resolution: el("resolution-select").value,
      duration: parseInt(el("duration-input").value || "5", 10),
      aspect_ratio: el("aspect-ratio-select").value,
      generate_audio: el("generate-audio-checkbox").checked,
      camera_fixed: el("camera-fixed-checkbox").checked,
      high_bitrate: el("high-bitrate-checkbox").checked,
      draft: el("draft-checkbox").checked,
      seed: parseInt(el("seed-input").value || "-1", 10),
    };

    const promptVal = el("prompt-input").value.trim();
    if (promptVal) req.prompt = promptVal;

    const draftId = el("draft-request-id-input").value.trim();
    if (draftId) req.draft_request_id = draftId;

    if (mode === "image_to_video") {
      req.image_url = el("image-url-input").value.trim();
      const lastImg = el("last-image-input").value.trim();
      if (lastImg) req.last_image = lastImg;
    } else if (mode === "first_last_frame") {
      req.images_list = parseListText(el("images-list-input").value);
    } else if (mode === "omni_reference") {
      req.omni_reference_task_type = el("omni-task-type-select").value;
      const imgs = parseListText(el("images-list-input").value);
      const vids = parseListText(el("videos-list-input").value);
      const auds = parseListText(el("audios-list-input").value);
      if (imgs.length) req.images_list = imgs;
      if (vids.length) req.videos_list = vids;
      if (auds.length) req.audios_list = auds;
    } else if (mode === "video_edit") {
      req.video_url = el("video-url-input").value.trim();
      const imgs = parseListText(el("images-list-input").value);
      const auds = parseListText(el("audios-list-input").value);
      if (imgs.length) req.images_list = imgs;
      if (auds.length) req.audios_list = auds;
    } else if (mode === "video_extend") {
      req.video_url = el("video-url-input").value.trim();
      const lastImg = el("last-image-input").value.trim();
      if (lastImg) req.last_image = lastImg;
    } else if (mode === "motion_control") {
      req.video_url = el("video-url-input").value.trim();
      const imgs = parseListText(el("images-list-input").value);
      if (imgs.length) req.images_list = imgs;
    }

    return req;
  }

  function computeProviderPreview(req) {
    const p = state.providers[state.provider] || {
      base_url: "https://ark.ap-southeast.bytepluses.com/api/v3",
      auth_header: "Authorization: Bearer <ARK_API_KEY>",
    };
    const mode = req.mode;

    if (state.provider === "byteplus") {
      const endpoint = `${p.base_url}/contents/generations/tasks`;
      const content = [];
      if (req.draft_request_id) {
        content.push({ type: "draft_task", draft_task: { id: req.draft_request_id } });
      } else {
        if (req.prompt) content.push({ type: "text", text: req.prompt });
        if (req.image_url) {
          content.push({ type: "image_url", image_url: { url: req.image_url }, role: "first_frame" });
        }
        if (req.last_image) {
          content.push({ type: "image_url", image_url: { url: req.last_image }, role: "last_frame" });
        }
        if (req.video_url) {
          content.push({ type: "video_url", video_url: { url: req.video_url } });
        }
        (req.images_list || []).forEach((u, i) => {
          const role =
            mode === "first_last_frame" && i === 0
              ? "first_frame"
              : mode === "first_last_frame" && i === 1
              ? "last_frame"
              : "reference_image";
          content.push({ type: "image_url", image_url: { url: u }, role });
        });
      }
      return {
        endpoint,
        auth: p.auth_header,
        body: {
          model: "seedance-2-5-260628",
          content,
          resolution: req.resolution,
          duration: req.duration,
          ratio: req.aspect_ratio,
          generate_audio: req.generate_audio,
          camera_fixed: req.camera_fixed,
          draft: req.draft,
        },
      };
    }

    if (state.provider === "fal") {
      const routeMap = {
        text_to_video: "/bytedance/seedance-2.5/us/text-to-video",
        image_to_video: "/bytedance/seedance-2.5/us/image-to-video",
        first_last_frame: "/bytedance/seedance-2.5/us/image-to-video",
        omni_reference: "/bytedance/seedance-2.5/us/reference-to-video",
        video_edit: "/bytedance/seedance-2.5/us/reference-to-video",
        video_extend: "/bytedance/seedance-2.5/us/reference-to-video",
        motion_control: "/bytedance/seedance-2.5/us/reference-to-video",
      };
      const path = req.draft_request_id ? "/bytedance/seedance-2.5/us/draft/complete" : routeMap[mode];
      const body = { ...req };
      delete body.mode;
      delete body.provider;
      delete body.mock;
      return { endpoint: `${p.base_url}${path}`, auth: p.auth_header, body };
    }

    if (state.provider === "wavespeed") {
      const routeMap = {
        text_to_video: "/bytedance/seedance-2.5/text-to-video",
        image_to_video: "/bytedance/seedance-2.5/image-to-video",
        first_last_frame: "/bytedance/seedance-2.5/image-to-video",
        omni_reference: "/bytedance/seedance-2.5/reference-to-video",
        video_edit: "/bytedance/seedance-2.5/video-edit",
        video_extend: "/bytedance/seedance-2.5/video-extend",
        motion_control: "/bytedance/seedance-2.5/motion-control",
      };
      const body = { ...req };
      delete body.mode;
      delete body.provider;
      delete body.mock;
      return { endpoint: `${p.base_url}${routeMap[mode]}`, auth: p.auth_header, body };
    }

    if (state.provider === "replicate") {
      const input = { ...req };
      delete input.mode;
      delete input.provider;
      delete input.mock;
      return {
        endpoint: `${p.base_url}/models/bytedance/seedance-2.5/predictions`,
        auth: p.auth_header,
        body: { input },
      };
    }

    // muapi
    const spec = state.modes[mode] || { endpoint: "/seedance-2.5-spicy-text-to-video" };
    const body = { ...req };
    delete body.mode;
    delete body.provider;
    delete body.mock;
    return {
      endpoint: `${p.base_url}${spec.endpoint}`,
      auth: p.auth_header,
      body,
    };
  }

  function updateInspectorAndCost() {
    const req = buildCurrentRequestObject();
    const preview = computeProviderPreview(req);
    const shortPath = preview.endpoint.replace(/^https?:\/\/[^/]+/, "");
    el("active-endpoint-pill").textContent = `POST ${shortPath}`;

    const inspectorText = `POST ${preview.endpoint}\n${preview.auth}\nContent-Type: application/json\n\n${JSON.stringify(
      preview.body,
      null,
      2
    )}`;
    el("request-inspector").textContent = inspectorText;

    // Update cost estimate
    const p = state.providers[state.provider];
    el("cost-provider-label").textContent = p ? p.name.split(" ")[0] : state.provider;
    if (state.sandbox) {
      const liveCost = estimateLiveCost(req, p);
      el("cost-estimate-value").textContent = `$0.00 Sandbox (Est. $${liveCost} Live)`;
    } else {
      const liveCost = estimateLiveCost(req, p);
      el("cost-estimate-value").textContent = `~$${liveCost} USD`;
    }
  }

  function estimateLiveCost(req, p) {
    if (!p) return "1.15";
    const dur = Math.max(4, req.duration > 0 ? req.duration : 5);
    const res = req.draft ? "480p" : req.resolution;
    const rateKey = `rate_${res}_per_sec`;
    const perSec = p[rateKey] || p.rate_720p_per_sec || 0.25;
    return (dur * perSec).toFixed(2);
  }

  function syncUIForModeAndProvider() {
    const mode = state.mode;
    const spec = state.modes[mode] || {
      label: "Text to Video",
      description: "Generate photorealistic 4K video directly from a text prompt.",
      duration_min: 4,
      duration_max: 16,
      supports_draft: true,
      supports_audio: true,
      supports_camera_fixed: true,
      supports_seed: false,
      supports_aspect_ratio: true,
    };

    // Update nav rail active state
    document.querySelectorAll(".mode-tab").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.mode === mode);
    });

    el("active-mode-title").textContent = spec.label;
    el("active-mode-desc").textContent = spec.description;
    el("duration-range-label").textContent = `${spec.duration_min}–${spec.duration_max}s`;

    // Show/hide mode-specific input sections
    const showSingleImages = mode === "image_to_video" || mode === "video_extend";
    el("group-single-images").classList.toggle("hidden", !showSingleImages);
    el("subgroup-image-url").classList.toggle("hidden", mode !== "image_to_video");

    const showVideoUrl = mode === "video_edit" || mode === "video_extend" || mode === "motion_control";
    el("group-video-url").classList.toggle("hidden", !showVideoUrl);

    const showImagesList =
      mode === "first_last_frame" ||
      mode === "omni_reference" ||
      mode === "video_edit" ||
      mode === "motion_control";
    el("group-images-list").classList.toggle("hidden", !showImagesList);
    if (mode === "first_last_frame") {
      el("images-list-label").textContent = "Start & End Frame Image URLs (Exactly 2 required)";
      el("images-list-hint").textContent = "Line 1: First Frame · Line 2: Last Frame";
    } else {
      el("images-list-label").textContent = "Reference Image URLs (One per line or comma-separated)";
      el("images-list-hint").textContent = "Up to 30 Reference Images";
    }

    const showOmniMedia = mode === "omni_reference" || mode === "video_edit";
    el("group-omni-media").classList.toggle("hidden", !showOmniMedia);
    el("subgroup-videos-list").classList.toggle("hidden", mode !== "omni_reference");

    el("subgroup-omni-type").classList.toggle("hidden", mode !== "omni_reference");
    el("subgroup-draft-id").classList.toggle("hidden", !spec.supports_draft);
    el("toggle-draft-wrap").classList.toggle("hidden", !spec.supports_draft);
    el("toggle-camera-wrap").classList.toggle("hidden", !spec.supports_camera_fixed);
    el("toggle-audio-wrap").classList.toggle("hidden", !spec.supports_audio);
    el("subgroup-seed").classList.toggle("hidden", !spec.supports_seed);
    el("subgroup-aspect-ratio").classList.toggle("hidden", !spec.supports_aspect_ratio);

    el("prompt-hint").textContent =
      mode === "motion_control" ? "Optional creative brief (roles auto-inferred if omitted)" : "Required for this workflow";

    // Update Provider Card & Header Key Label
    const p = state.providers[state.provider];
    if (p) {
      el("provider-card-name").textContent = p.name;
      el("provider-card-badge").textContent = p.badge;
      el("provider-card-notes").textContent = p.notes;
      el("provider-card-host").textContent = p.base_url;
      el("api-key-label").textContent = p.env_key;
      el("api-key-input").placeholder = state.sandbox
        ? "Optional in Sandbox Mode"
        : p.has_env_key
        ? "Loaded from .env (override optional)"
        : `Paste ${p.env_key}`;
    }

    const badge = el("mode-indicator-badge");
    if (state.sandbox) {
      badge.textContent = "FREE MOCK";
      badge.className = "sandbox-badge";
    } else {
      badge.textContent = "LIVE API";
      badge.className = "sandbox-badge live";
    }

    updateInspectorAndCost();
  }

  function renderTaskQueue() {
    const list = el("task-queue-list");
    el("queue-count-label").textContent = `${state.tasks.length} Task${state.tasks.length === 1 ? "" : "s"}`;
    if (!state.tasks.length) {
      list.innerHTML = `<div class="viewport-empty" style="padding: 12px;">No tasks submitted yet.</div>`;
      return;
    }

    list.innerHTML = "";
    state.tasks.forEach((task) => {
      const item = document.createElement("div");
      item.className = "task-item";

      const top = document.createElement("div");
      top.className = "task-item-top";

      const idSpan = document.createElement("span");
      idSpan.className = "task-id";
      idSpan.textContent = `${task.request_id} (${task.provider.toUpperCase()})`;

      const statusSpan = document.createElement("span");
      statusSpan.className = `status-tag ${task.status || "processing"}`;
      statusSpan.textContent = task.status || "processing";

      top.appendChild(idSpan);
      top.appendChild(statusSpan);

      const meta = document.createElement("div");
      meta.className = "field-hint";
      meta.textContent = `${task.mode_label || task.mode} · ${task.resolution || "720p"}${task.draft ? " [DRAFT]" : ""}`;

      const actions = document.createElement("div");
      actions.className = "task-actions";

      if (task.status === "completed" && task.outputs && task.outputs.length) {
        const viewBtn = document.createElement("button");
        viewBtn.type = "button";
        viewBtn.className = "btn-secondary";
        viewBtn.style.padding = "3px 8px";
        viewBtn.style.fontSize = "11px";
        viewBtn.textContent = "Load in Monitor";
        viewBtn.addEventListener("click", () => loadTaskInMonitor(task));
        actions.appendChild(viewBtn);
      }

      if (task.status === "completed" && task.draft) {
        const finBtn = document.createElement("button");
        finBtn.type = "button";
        finBtn.className = "btn-secondary";
        finBtn.style.padding = "3px 8px";
        finBtn.style.fontSize = "11px";
        finBtn.textContent = "Finalize 1080p";
        finBtn.addEventListener("click", () => triggerDraftFinalize(task));
        actions.appendChild(finBtn);
      }

      item.appendChild(top);
      item.appendChild(meta);
      if (actions.children.length) item.appendChild(actions);
      list.appendChild(item);
    });
  }

  function loadTaskInMonitor(task) {
    state.activeTask = task;
    const statusBadge = el("monitor-status-badge");
    statusBadge.textContent = (task.status || "completed").toUpperCase();
    statusBadge.className = `status-tag ${task.status || "completed"}`;

    const videoUrl = (task.outputs && task.outputs[0]) || task.url;
    if (videoUrl) {
      el("viewport-empty-text").classList.add("hidden");
      const video = el("output-video");
      video.classList.remove("hidden");
      if (video.getAttribute("src") !== videoUrl) {
        video.setAttribute("src", videoUrl);
        video.load();
        video.play().catch(() => {});
      }
      el("monitor-actions").classList.remove("hidden");
      el("download-video-link").href = videoUrl;
      const finBtn = el("finalize-draft-btn");
      finBtn.classList.toggle("hidden", !task.draft);
    }
  }

  function triggerDraftFinalize(task) {
    state.mode = task.mode;
    el("draft-checkbox").checked = false;
    el("resolution-select").value = "1080p";
    el("draft-request-id-input").value = task.request_id;
    syncUIForModeAndProvider();
    showToast(`Loaded Draft ID ${task.request_id} for 1080p finalization. Click Generate Video to render.`, "success");
  }

  async function pollTaskStatus(requestId, provider) {
    try {
      const headers = {};
      const apiKey = el("api-key-input").value.trim();
      if (apiKey) headers["X-Provider-Key"] = apiKey;

      const res = await fetch(`/api/status/${encodeURIComponent(requestId)}?provider=${encodeURIComponent(provider)}`, {
        headers,
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Polling failed");
      }

      const idx = state.tasks.findIndex((t) => t.request_id === requestId);
      if (idx !== -1) {
        state.tasks[idx] = { ...state.tasks[idx], ...data };
        renderTaskQueue();
        if (data.status === "completed") {
          loadTaskInMonitor(state.tasks[idx]);
          showToast(`Task ${requestId} completed!`, "success");
          return;
        }
        if (data.status === "failed") {
          showToast(`Task ${requestId} failed: ${data.error || "Unknown error"}`, "error");
          return;
        }
      }
      state.pollTimers[requestId] = setTimeout(() => pollTaskStatus(requestId, provider), 1200);
    } catch (err) {
      showToast(`Status check error: ${err.message}`, "error");
    }
  }

  async function submitGeneration() {
    const btn = el("generate-btn");
    btn.disabled = true;
    btn.textContent = "Submitting...";

    try {
      const req = buildCurrentRequestObject();
      const headers = { "Content-Type": "application/json" };
      const apiKey = el("api-key-input").value.trim();
      if (apiKey) headers["X-Provider-Key"] = apiKey;

      const res = await fetch("/api/generate", {
        method: "POST",
        headers,
        body: JSON.stringify(req),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to submit generation request");
      }

      const newTask = {
        request_id: data.request_id,
        provider: req.provider,
        mode: req.mode,
        mode_label: (state.modes[req.mode] || {}).label || req.mode,
        status: data.status || "processing",
        draft: req.draft,
        resolution: req.resolution,
        duration: req.duration,
        endpoint: data.endpoint,
        payload: data.payload,
      };
      state.tasks.unshift(newTask);
      renderTaskQueue();

      const statusBadge = el("monitor-status-badge");
      statusBadge.textContent = "PROCESSING";
      statusBadge.className = "status-tag processing";

      showToast(`Submitted task ${data.request_id} via ${req.provider.toUpperCase()}`, "success");
      pollTaskStatus(data.request_id, req.provider);
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "Generate Video";
    }
  }

  async function handleFileUpload(file) {
    if (!file) return;
    const btn = el("file-upload-btn");
    btn.disabled = true;
    btn.textContent = "Uploading...";

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("mock", String(state.sandbox));
      formData.append("provider", state.provider);

      const headers = {};
      const apiKey = el("api-key-input").value.trim();
      if (apiKey) headers["X-Provider-Key"] = apiKey;

      const res = await fetch("/api/upload", {
        method: "POST",
        headers,
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Upload failed");
      }

      const uploadedUrl = data.url || data.file_url;
      if (state.mode === "text_to_video") {
        state.mode = "image_to_video";
        el("image-url-input").value = uploadedUrl;
        syncUIForModeAndProvider();
      } else if (state.mode === "image_to_video") {
        el("image-url-input").value = uploadedUrl;
      } else if (state.mode === "video_edit" || state.mode === "video_extend" || state.mode === "motion_control") {
        if (file.type.startsWith("video/")) {
          el("video-url-input").value = uploadedUrl;
        } else {
          const cur = el("images-list-input").value.trim();
          el("images-list-input").value = cur ? `${cur}\n${uploadedUrl}` : uploadedUrl;
        }
      } else {
        const cur = el("images-list-input").value.trim();
        el("images-list-input").value = cur ? `${cur}\n${uploadedUrl}` : uploadedUrl;
      }

      updateInspectorAndCost();
      showToast(`Uploaded ${file.name} (${data.size_bytes} bytes)`, "success");
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "Upload File";
    }
  }

  async function init() {
    try {
      const res = await fetch("/api/config");
      const cfg = await res.json();
      state.providers = cfg.providers || {};
      state.modes = cfg.modes || {};
      if (cfg.default_provider) {
        state.provider = cfg.default_provider;
        el("provider-select").value = state.provider;
      }
    } catch (_) {}

    // Wire mode tabs
    document.querySelectorAll(".mode-tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.mode = btn.dataset.mode;
        const spec = state.modes[state.mode];
        if (spec) {
          const curDur = parseInt(el("duration-input").value || "5", 10);
          if (curDur < spec.duration_min || curDur > spec.duration_max) {
            el("duration-input").value = String(Math.min(Math.max(5, spec.duration_min), spec.duration_max));
          }
        }
        syncUIForModeAndProvider();
      });
    });

    // Wire provider selector
    el("provider-select").addEventListener("change", (e) => {
      state.provider = e.target.value;
      syncUIForModeAndProvider();
    });

    // Wire sandbox toggle
    el("sandbox-toggle").addEventListener("change", (e) => {
      state.sandbox = e.target.checked;
      syncUIForModeAndProvider();
    });

    // Wire Omni subtask auto-constraints
    el("omni-task-type-select").addEventListener("change", (e) => {
      const val = e.target.value;
      if (val === "edit") {
        el("aspect-ratio-select").value = "adaptive";
        el("duration-input").value = "-1";
      } else if (val === "extend") {
        el("aspect-ratio-select").value = "adaptive";
      }
      updateInspectorAndCost();
    });

    // Wire draft checkbox auto-480p
    el("draft-checkbox").addEventListener("change", (e) => {
      if (e.target.checked) {
        el("resolution-select").value = "480p";
      }
      updateInspectorAndCost();
    });

    // Wire all inputs to update live Request Inspector
    document.querySelectorAll("input, select, textarea").forEach((inp) => {
      inp.addEventListener("input", updateInspectorAndCost);
      inp.addEventListener("change", updateInspectorAndCost);
    });

    // Wire presets
    document.querySelectorAll(".preset-chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        const preset = PRESETS[chip.dataset.preset];
        if (!preset) return;
        state.mode = preset.mode;
        el("prompt-input").value = preset.prompt || "";
        if (preset.resolution) el("resolution-select").value = preset.resolution;
        if (preset.duration) el("duration-input").value = String(preset.duration);
        if (preset.aspect_ratio) el("aspect-ratio-select").value = preset.aspect_ratio;
        if (preset.image_url) el("image-url-input").value = preset.image_url;
        if (preset.video_url) el("video-url-input").value = preset.video_url;
        if (preset.images_list) el("images-list-input").value = preset.images_list.join("\n");
        syncUIForModeAndProvider();
      });
    });

    // Wire file upload
    el("file-upload-btn").addEventListener("click", () => el("file-upload-input").click());
    el("file-upload-input").addEventListener("change", (e) => {
      if (e.target.files && e.target.files[0]) {
        handleFileUpload(e.target.files[0]);
      }
    });

    // Wire generate button
    el("generate-btn").addEventListener("click", submitGeneration);

    // Wire finalize draft button in monitor
    el("finalize-draft-btn").addEventListener("click", () => {
      if (state.activeTask) triggerDraftFinalize(state.activeTask);
    });

    // Wire Copy cURL
    el("copy-curl-btn").addEventListener("click", () => {
      const req = buildCurrentRequestObject();
      const preview = computeProviderPreview(req);
      const curl = `curl -X POST "${preview.endpoint}" \\\n  -H "${preview.auth}" \\\n  -H "Content-Type: application/json" \\\n  -d '${JSON.stringify(
        preview.body,
        null,
        2
      )}'`;
      navigator.clipboard.writeText(curl).then(() => {
        showToast("Copied provider cURL command to clipboard!", "success");
      });
    });

    // Wire Provider Modal
    el("compare-providers-btn").addEventListener("click", () => {
      el("provider-modal").classList.add("open");
    });
    el("close-modal-btn").addEventListener("click", () => {
      el("provider-modal").classList.remove("open");
    });
    document.querySelectorAll(".select-provider-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.provider = btn.dataset.provider;
        el("provider-select").value = state.provider;
        el("provider-modal").classList.remove("open");
        syncUIForModeAndProvider();
        showToast(`Switched active provider to ${state.providers[state.provider]?.name || state.provider}`, "success");
      });
    });

    syncUIForModeAndProvider();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
