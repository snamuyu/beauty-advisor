/* Beauty Advisor 前端逻辑：调用 /analyze 与 /recommend，渲染诊断报告和推荐视频 */

const $ = (id) => document.getElementById(id);

const DIM_LABELS = [
  ["maturity", "成熟度"],
  ["volume", "量感"],
  ["curvature", "曲直度"],
  ["width", "宽窄度"],
];

let currentReport = null;

async function api(path, body, timeoutMs = 90000) {
  // 前端超时兜底：后端若长时间不响应，中止请求并提示，避免一直停留在加载状态
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    const text = await res.text();
    let data = null;
    try {
      data = JSON.parse(text);
    } catch (_) {
      /* 非 JSON 响应 */
    }
    if (!res.ok) {
      const detail =
        (data && (data.detail || data.message)) || `请求失败（HTTP ${res.status}）`;
      throw new Error(detail);
    }
    return data;
  } catch (err) {
    if (err.name === "AbortError") {
      throw new Error("请求超时，请检查网络后重试");
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

function showLoading(text) {
  $("loading-text").textContent = text;
  $("loading-mask").hidden = false;
}

function hideLoading() {
  $("loading-mask").hidden = true;
}

function setAnalyzeEnabled(enabled) {
  $("analyze-btn").disabled = !enabled;
}

/* ---------- 图片上传 ---------- */

function handleFile(file) {
  if (!file || !file.type.startsWith("image/")) {
    alert("请选择图片文件");
    return;
  }
  const reader = new FileReader();
  reader.onload = (e) => {
    $("preview").src = e.target.result;
    $("preview").hidden = false;
    $("dropzone-hint").hidden = true;
    setAnalyzeEnabled(true);
  };
  reader.readAsDataURL(file);
}

$("file-input").addEventListener("change", (e) => handleFile(e.target.files[0]));

const dropzone = $("dropzone");
dropzone.addEventListener("click", () => $("file-input").click());
dropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropzone.classList.add("dragover");
});
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("dragover");
  handleFile(e.dataTransfer.files[0]);
});

/* ---------- 风格诊断 ---------- */

$("analyze-btn").addEventListener("click", async () => {
  const img = $("preview").src;
  if (!img) return;
  const base64 = img.split(",")[1] || img;
  setAnalyzeEnabled(false);
  showLoading("正在分析照片，请稍候…");
  try {
    const report = await api("/analyze", { image_base64: base64 }, 120000);
    currentReport = report;
    renderReport(report);
    $("result-card").hidden = false;
    $("recommend-card").hidden = true;
    $("result-card").scrollIntoView({ behavior: "smooth" });
  } catch (err) {
    alert("诊断失败：" + err.message);
  } finally {
    hideLoading();
    setAnalyzeEnabled(true);
  }
});

function renderReport(report) {
  $("style-tag").textContent = report.style_tag || "未识别";
  renderChips($("keyword-chips"), report.keywords || []);
  renderRadar(report.dimensions || {});
  renderBars(report.dimensions || {});
  $("positioning-reason").textContent = report.positioning_reason || "";
  $("celebrity-refs").textContent = (report.celebrity_refs || []).length
    ? "风格参考：" + report.celebrity_refs.join("、")
    : "";
  renderMakeup(report.makeup_advice || []);
  renderHair(report.hair_advice || {});
  $("summary").textContent = report.summary || "";
}

function renderChips(container, items) {
  container.innerHTML = "";
  items.forEach((item) => {
    const span = document.createElement("span");
    span.className = "chip";
    span.textContent = item;
    container.appendChild(span);
  });
}

function renderBars(dims) {
  const bars = $("dimension-bars");
  bars.innerHTML = "";
  DIM_LABELS.forEach(([key, label]) => {
    const value = Math.max(0, Math.min(1, Number(dims[key]) || 0));
    const row = document.createElement("div");
    row.className = "bar-row";
    row.innerHTML =
      `<span>${label}</span>` +
      `<div class="bar-track"><div class="bar-fill" data-w="${Math.round(value * 100)}"></div></div>` +
      `<span class="bar-value">${Math.round(value * 100)}%</span>`;
    bars.appendChild(row);
  });
  requestAnimationFrame(() => {
    bars.querySelectorAll(".bar-fill").forEach((fill) => {
      fill.style.width = fill.dataset.w + "%";
    });
  });
}

function renderMakeup(items) {
  const wrap = $("makeup-advice");
  wrap.innerHTML = "";
  items.forEach((item) => {
    const div = document.createElement("div");
    div.className = "advice-item";
    div.innerHTML =
      `<div class="area">${escapeHtml(item.area || "")}</div>` +
      `<div class="action">${escapeHtml(item.action || "")}</div>` +
      (item.reason ? `<div class="reason">${escapeHtml(item.reason)}</div>` : "");
    wrap.appendChild(div);
  });
}

function renderHair(advice) {
  const wrap = $("hair-advice");
  wrap.innerHTML = "";
  [
    ["length", "长度"],
    ["curl", "卷度"],
    ["bangs", "刘海"],
  ].forEach(([key, label]) => {
    if (!advice[key]) return;
    const div = document.createElement("div");
    div.innerHTML = `<strong>${label}：</strong>${escapeHtml(advice[key])}`;
    wrap.appendChild(div);
  });
}

function renderRadar(dims) {
  const canvas = $("radar");
  const ctx = canvas.getContext("2d");
  const size = canvas.width;
  const cx = size / 2;
  const cy = size / 2;
  const radius = Math.min(size * 0.34, 120);
  const count = DIM_LABELS.length;

  ctx.clearRect(0, 0, size, size);

  // 网格（0.25 / 0.5 / 0.75 / 1.0）
  for (let level = 1; level <= 4; level++) {
    const r = radius * (level / 4);
    ctx.beginPath();
    for (let i = 0; i <= count; i++) {
      const angle = -Math.PI / 2 + (i % count) * ((Math.PI * 2) / count);
      const x = cx + Math.cos(angle) * r;
      const y = cy + Math.sin(angle) * r;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.strokeStyle = level === 4 ? "#e0c6cf" : "#f0e0e6";
    ctx.lineWidth = 1;
    ctx.stroke();
  }

  // 轴线与标签
  DIM_LABELS.forEach(([key, label], i) => {
    const angle = -Math.PI / 2 + i * ((Math.PI * 2) / count);
    const x = cx + Math.cos(angle) * radius;
    const y = cy + Math.sin(angle) * radius;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(x, y);
    ctx.strokeStyle = "#f0e0e6";
    ctx.stroke();

    const lx = cx + Math.cos(angle) * (radius + 26);
    const ly = cy + Math.sin(angle) * (radius + 26);
    const value = Math.round((Number(dims[key]) || 0) * 100);
    ctx.font = "13px PingFang SC, Microsoft YaHei, sans-serif";
    ctx.fillStyle = "#3d2b35";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(`${label} ${value}%`, lx, ly);
  });

  // 数据多边形
  ctx.beginPath();
  DIM_LABELS.forEach(([key], i) => {
    const angle = -Math.PI / 2 + i * ((Math.PI * 2) / count);
    const r = radius * Math.max(0.02, Math.min(1, Number(dims[key]) || 0));
    const x = cx + Math.cos(angle) * r;
    const y = cy + Math.sin(angle) * r;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.closePath();
  ctx.fillStyle = "rgba(214, 90, 122, 0.25)";
  ctx.fill();
  ctx.strokeStyle = "#d65a7a";
  ctx.lineWidth = 2;
  ctx.stroke();

  DIM_LABELS.forEach(([key], i) => {
    const angle = -Math.PI / 2 + i * ((Math.PI * 2) / count);
    const r = radius * Math.max(0.02, Math.min(1, Number(dims[key]) || 0));
    ctx.beginPath();
    ctx.arc(cx + Math.cos(angle) * r, cy + Math.sin(angle) * r, 3.5, 0, Math.PI * 2);
    ctx.fillStyle = "#d65a7a";
    ctx.fill();
  });
}

/* ---------- 推荐视频 ---------- */

$("recommend-btn").addEventListener("click", async () => {
  if (!currentReport) return;
  const face = (currentReport.face_info || {}).face_shape || "";
  const profile = {
    face_shape: face,
    pain_points: [],
    style_tag: currentReport.style_tag || "",
    keywords: currentReport.keywords || [],
    top_n: 5,
  };
  showLoading("正在匹配推荐视频…");
  try {
    const data = await api("/recommend", profile, 45000);
    renderVideos(data.results || []);
    $("recommend-card").hidden = false;
    $("recommend-card").scrollIntoView({ behavior: "smooth" });
  } catch (err) {
    alert("推荐失败：" + err.message);
  } finally {
    hideLoading();
  }
});

function isAndroid() {
  return /Android/i.test(navigator.userAgent || "");
}

function buildSmartLink(url) {
  /* 智能链接：能唤起 App 就唤起（Android intent 自带网页兜底），否则直接用网页链接。
     iOS 端直接用官方链接即可——Universal Link 已装 App 会唤起、未装则打开网页。 */
  if (!url) return "";
  if (url.includes("xiaohongshu.com")) {
    const m = url.match(/\/explore\/([0-9a-zA-Z]+)/);
    const noteId = m ? m[1] : "";
    if (isAndroid() && noteId) {
      return (
        `intent://explore/${noteId}#Intent;` +
        `scheme=xhsdiscover;package=com.xingin.xhs;` +
        `S.browser_fallback_url=${encodeURIComponent(url)};end`
      );
    }
    return url; // iOS Universal Link / 桌面网页
  }
  if (url.includes("bilibili.com")) {
    const m = url.match(/\/video\/(BV[0-9A-Za-z]+)/);
    const bvid = m ? m[1] : "";
    if (isAndroid() && bvid) {
      return (
        `intent://video/${bvid}#Intent;` +
        `scheme=bilibili;package=tv.danmaku.bili;` +
        `S.browser_fallback_url=${encodeURIComponent(url)};end`
      );
    }
    return url; // iOS Universal Link / 桌面网页
  }
  return url;
}

function renderVideos(videos) {
  const grid = $("video-grid");
  grid.innerHTML = "";
  $("video-empty").hidden = videos.length > 0;
  videos.forEach((v) => {
    const card = document.createElement("div");
    card.className = "video-card";
    const cats = (v.categories || []).map(
      (c) => `<span class="v-cat">${escapeHtml(c)}</span>`
    ).join("");
    const reasons = (v.reasons || []).map(
      (r) => `<li>${escapeHtml(r)}</li>`
    ).join("");
    const url = v.url || "";
    const host = url.includes("xiaohongshu.com")
      ? "xhs"
      : url.includes("bilibili.com")
      ? "bili"
      : "";
      const platformBadge =
        host === "xhs"
          ? `<span class="v-platform xhs">小红书笔记</span>`
          : host === "bili"
          ? `<span class="v-platform bili">B站视频</span>`
          : "";
      const smartUrl = buildSmartLink(url);
      const isIntent = smartUrl.indexOf("intent://") === 0;
      const link = url
        ? `<a class="v-link" href="${escapeHtml(smartUrl)}"${isIntent ? "" : ' target="_blank" rel="noopener"'} title="${
            host === "xhs"
              ? "已安装小红书将唤起 App，未安装则打开网页"
              : host === "bili"
              ? "已安装哔哩哔哩将唤起 App，未安装则打开网页"
              : ""
          }">${host === "xhs" ? "查看笔记 →" : "观看视频 →"}</a>`
        : "";
    card.innerHTML =
      `<div class="v-top">` +
      `<p class="v-title">${escapeHtml(v.title || v.video_id || "未命名视频")}</p>` +
      `<span class="v-score">${escapeHtml(v.match_strength_cn || "")} ${Number(v.score || 0).toFixed(2)}</span>` +
      `</div>` +
      platformBadge +
      (v.uploader ? `<div class="v-uploader">UP 主：${escapeHtml(v.uploader)}</div>` : "") +
      (cats ? `<div class="v-cats">${cats}</div>` : "") +
      (v.summary ? `<p class="v-summary">${escapeHtml(v.summary)}</p>` : "") +
      (reasons ? `<ul class="v-reasons">${reasons}</ul>` : "") +
      link;
    grid.appendChild(card);
  });
}

function escapeHtml(text) {
  return String(text == null ? "" : text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
