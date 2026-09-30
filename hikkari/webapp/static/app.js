const $ = (s) => document.querySelector(s);
let TOKEN = localStorage.getItem("hikkari_web_token") || new URLSearchParams(location.search).get("token") || "";
window.HIKKARI_ROLE = "view";

async function api(path, opts = {}) {
  if (window.HIKKARI_ROLE !== "admin") {
    // view role may only call status
    if (!path.startsWith("/api/status")) {
      throw new Error("forbidden");
    }
  }
  const headers = Object.assign({}, opts.headers || {});
  if (TOKEN) headers["Authorization"] = "Bearer " + TOKEN;
  if (opts.json) {
    headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(opts.json);
    delete opts.json;
  }
  const r = await fetch(path, { ...opts, headers });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
}

function showApp() {
  $("#auth").classList.add("hidden");
  $("#app").classList.remove("hidden");
}

function lockViewerUI() {
  document.querySelectorAll("nav button").forEach((btn) => {
    if (btn.dataset.tab !== "dash") btn.remove();
  });
  ["tab-modules", "tab-config", "tab-run", "tab-media"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.remove();
  });
  document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
  const dash = document.getElementById("tab-dash");
  if (dash) dash.classList.add("active");
}

async function tryAuth(token) {
  TOKEN = token;
  // probe status first without role gate
  const headers = { Authorization: "Bearer " + TOKEN };
  const r = await fetch("/api/status", { headers });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.statusText);
  localStorage.setItem("hikkari_web_token", TOKEN);
  window.HIKKARI_ROLE = data.role || "view";
  showApp();
  if (window.HIKKARI_ROLE !== "admin") {
    lockViewerUI();
  } else {
    loadModules();
  }
  renderDash(data);
  $("#sideStatus").textContent =
    "v" + data.version + " · " + window.HIKKARI_ROLE + " · @" + (data.user.username || data.user.id);
}

$("#authBtn").onclick = async () => {
  $("#authErr").textContent = "";
  try {
    await tryAuth($("#tokenInput").value.trim());
  } catch (e) {
    $("#authErr").textContent = e.message || String(e);
  }
};

if (TOKEN) {
  tryAuth(TOKEN).catch(() => {
    localStorage.removeItem("hikkari_web_token");
    TOKEN = "";
  });
}

document.querySelectorAll("nav button").forEach((btn) => {
  btn.onclick = () => {
    if (window.HIKKARI_ROLE !== "admin" && btn.dataset.tab !== "dash") return;
    document.querySelectorAll("nav button").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    btn.classList.add("active");
    const tab = $("#tab-" + btn.dataset.tab);
    if (tab) tab.classList.add("active");
  };
});

function renderDash(data) {
  const cards = [
    ["Версия", data.version],
    ["Uptime", data.uptime + "s"],
    ["Аккаунт", data.user.name || data.user.id],
    ["Роль", data.role === "admin" ? "admin" : "обзор"],
  ];
  if (data.role === "admin" && data.modules != null) {
    cards.splice(1, 0, ["Модулей", data.modules]);
  }
  $("#dashCards").innerHTML = cards
    .map(([l, v]) => `<div class="stat"><div class="v">${v}</div><div class="l">${l}</div></div>`)
    .join("");
}

let MODULES = [];
async function loadModules() {
  if (window.HIKKARI_ROLE !== "admin") return;
  const data = await api("/api/modules");
  MODULES = data.modules || [];
  drawModules();
  const sel = $("#cfgMod");
  if (!sel) return;
  sel.innerHTML = MODULES.filter((m) => m.has_config)
    .map((m) => `<option value="${m.class}">${m.name}</option>`)
    .join("");
  if (sel.value) loadConfig(sel.value);
}

function drawModules() {
  if (window.HIKKARI_ROLE !== "admin") return;
  const q = ($("#modFilter") && $("#modFilter").value || "").toLowerCase();
  const coreOnly = $("#coreOnly") && $("#coreOnly").checked;
  const list = MODULES.filter((m) => {
    if (coreOnly && !m.core) return false;
    const hay = (m.name + " " + m.class + " " + (m.commands || []).join(" ")).toLowerCase();
    return !q || hay.includes(q);
  });
  const box = $("#modList");
  if (!box) return;
  box.innerHTML = list
    .map(
      (m) => `<div class="item">
      <div>
        <div><b>${m.name}</b> ${m.core ? '<span class="badge">core</span>' : '<span class="badge">ext</span>'}</div>
        <div class="meta">${(m.commands || []).slice(0, 8).join(" · ") || "—"}</div>
      </div>
      <div>
        ${m.has_config ? `<button data-cfg="${m.class}">Конфиг</button>` : ""}
      </div>
    </div>`
    )
    .join("");
  box.querySelectorAll("[data-cfg]").forEach((b) => {
    b.onclick = () => {
      if (window.HIKKARI_ROLE !== "admin") return;
      $("#cfgMod").value = b.dataset.cfg;
      document.querySelector('[data-tab="config"]')?.click();
      loadConfig(b.dataset.cfg);
    };
  });
}
if ($("#modFilter")) $("#modFilter").oninput = drawModules;
if ($("#coreOnly")) $("#coreOnly").onchange = drawModules;

async function loadConfig(name) {
  if (window.HIKKARI_ROLE !== "admin") return;
  const data = await api("/api/modules/" + encodeURIComponent(name) + "/config");
  const box = $("#cfgOpts");
  if (!box) return;
  box.innerHTML = (data.options || [])
    .map((o) => {
      const val = typeof o.value === "object" ? JSON.stringify(o.value) : o.value ?? "";
      return `<div class="item cfg-row">
        <label>${o.key}</label>
        <div class="doc">${o.doc || ""} ${o.validator ? "(" + o.validator + ")" : ""}</div>
        <input data-key="${o.key}" value="${String(val).replace(/"/g, "&quot;")}" />
        <button data-save="${o.key}" class="primary">Сохранить</button>
      </div>`;
    })
    .join("") || "<p class='hint'>Нет опций</p>";
  box.querySelectorAll("[data-save]").forEach((btn) => {
    btn.onclick = async () => {
      if (window.HIKKARI_ROLE !== "admin") return;
      const key = btn.dataset.save;
      const input = box.querySelector(`input[data-key="${key}"]`);
      try {
        await api("/api/modules/" + encodeURIComponent(name) + "/config", {
          method: "POST",
          json: { key, value: input.value },
        });
        btn.textContent = "OK";
        setTimeout(() => (btn.textContent = "Сохранить"), 1000);
      } catch (e) {
        alert(e.message);
      }
    };
  });
}
if ($("#cfgMod")) $("#cfgMod").onchange = (e) => loadConfig(e.target.value);

if ($("#cmdRun"))
  $("#cmdRun").onclick = async () => {
    if (window.HIKKARI_ROLE !== "admin") return;
    $("#cmdOut").textContent = "…";
    try {
      const res = await api("/api/command", {
        method: "POST",
        json: { command: $("#cmdName").value, args: $("#cmdArgs").value },
      });
      $("#cmdOut").textContent = JSON.stringify(res, null, 2);
    } catch (e) {
      $("#cmdOut").textContent = e.message;
    }
  };

if ($("#uploadBtn"))
  $("#uploadBtn").onclick = async () => {
    if (window.HIKKARI_ROLE !== "admin") return;
    const f = $("#fileIn").files[0];
    if (!f) return alert("Выбери файл");
    const fd = new FormData();
    fd.append("file", f);
    $("#upOut").textContent = "Uploading…";
    try {
      const r = await fetch("/api/upload", {
        method: "POST",
        headers: { Authorization: "Bearer " + TOKEN },
        body: fd,
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error || r.statusText);
      $("#upOut").textContent = JSON.stringify(data, null, 2);
    } catch (e) {
      $("#upOut").textContent = e.message;
    }
  };
