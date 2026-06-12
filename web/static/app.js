/* Doctrine web client: setup form, canvas renderer, polling loop. */
"use strict";

const $ = (id) => document.getElementById(id);

const COLORS = {
  player: "#56b4e9",
  enemy: "#e69f00",
  terrain: { ".": "#161b25", f: "#18261d", m: "#262b38", w: "#0f1d2b" },
  resources: { "^": "#e3c34c", T: "#5dbb63", "*": "#d678c2", "%": "#e8743b" },
};

const state = {
  meta: null,
  allocation: {},
  mapId: -1,
  terrain: null, // offscreen canvas
  mapW: 120,
  mapH: 80,
  polling: null,
  lastPhase: "setup",
  paused: false,
  speed: 1,
};

/* ---------- API helpers ---------- */

async function api(path, body) {
  const opts = body
    ? { method: "POST", body: JSON.stringify(body),
        headers: { "Content-Type": "application/json" } }
    : undefined;
  const res = await fetch(path, opts);
  return res.json();
}

/* ---------- Profile header ---------- */

function renderProfile(p) {
  $("p-level").textContent = p.level;
  const pct = Math.min(100, (100 * p.xp) / p.xp_needed);
  $("p-xpbar").style.width = pct + "%";
  $("p-record").textContent = `${p.wins}V ${p.losses}D`;
}

/* ---------- Setup view ---------- */

function budgetLeft() {
  const spent = Object.values(state.allocation).reduce((a, b) => a + b, 0);
  return state.meta.budget - spent;
}

function renderSetup() {
  const meta = state.meta;
  renderProfile(meta.profile);
  $("budget").textContent = budgetLeft();
  $("next-unlock").textContent = meta.next_unlock
    ? `Prochain déblocage : ${meta.next_unlock.label} (niveau ${meta.next_unlock.level}).`
    : "";
  const box = $("skills");
  box.innerHTML = "";
  for (const skill of meta.skills) {
    const val = state.allocation[skill.key] || 0;
    const row = document.createElement("div");
    row.className = "skill-row";
    const tag = skill.kind !== "base"
      ? `<span class="tag">${skill.kind === "affinity" ? "affinité" : "niv. avancé"}</span>`
      : "";
    const pips = Array.from({ length: skill.max }, (_, i) =>
      `<span class="pip${i < val ? " on" : ""}"></span>`).join("");
    row.innerHTML = `
      <div class="skill-name">${skill.label}${tag}</div>
      <div class="skill-ctl">
        <div class="pips">${pips}</div>
        <button data-k="${skill.key}" data-d="-1"
          ${val <= 0 ? "disabled" : ""}>−</button>
        <span class="skill-val">${val}</span>
        <button data-k="${skill.key}" data-d="1"
          ${val >= skill.max || budgetLeft() <= 0 ? "disabled" : ""}>+</button>
      </div>
      <div class="skill-desc">${skill.description}</div>`;
    box.appendChild(row);
  }
}

$("skills").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-k]");
  if (!btn) return;
  const key = btn.dataset.k;
  const delta = parseInt(btn.dataset.d, 10);
  const cur = state.allocation[key] || 0;
  state.allocation[key] = cur + delta;
  renderSetup();
});

$("btn-start").addEventListener("click", async () => {
  await api("/api/start", {
    skills: state.allocation,
    idle: $("idle-toggle").checked,
  });
  showGame();
});

/* ---------- View switching ---------- */

function showSetup() {
  $("setup-view").hidden = false;
  $("game-view").hidden = true;
  $("recap-overlay").hidden = true;
  api("/api/meta").then((m) => {
    state.meta = m;
    // Drop allocation points on skills that no longer exist.
    const valid = new Set(m.skills.map((s) => s.key));
    for (const k of Object.keys(state.allocation)) {
      if (!valid.has(k)) delete state.allocation[k];
    }
    renderSetup();
  });
}

function showGame() {
  $("setup-view").hidden = true;
  $("game-view").hidden = false;
  $("recap-overlay").hidden = true;
}

/* ---------- Rules overlay ---------- */

$("btn-rules").addEventListener("click", () => {
  $("rules-overlay").hidden = false;
});
$("btn-close-rules").addEventListener("click", () => {
  $("rules-overlay").hidden = true;
});
$("rules-overlay").addEventListener("click", (e) => {
  if (e.target === $("rules-overlay")) $("rules-overlay").hidden = true;
});

/* ---------- Controls ---------- */

document.querySelectorAll(".ctrl[data-speed]").forEach((btn) => {
  btn.addEventListener("click", () => {
    state.speed = parseFloat(btn.dataset.speed);
    api("/api/control", { speed: state.speed });
    document.querySelectorAll(".ctrl[data-speed]").forEach((b) =>
      b.classList.toggle("active", b === btn));
  });
});

$("btn-pause").addEventListener("click", () => {
  state.paused = !state.paused;
  api("/api/control", { pause: state.paused });
  $("btn-pause").textContent = state.paused ? "▶" : "⏸";
});

$("btn-stop").addEventListener("click", async () => {
  await api("/api/control", { stop: true });
  showSetup();
});
$("btn-config").addEventListener("click", async () => {
  await api("/api/control", { stop: true });
  showSetup();
});
$("btn-next").addEventListener("click", async () => {
  await api("/api/control", { next: true });
  $("recap-overlay").hidden = true;
});

/* ---------- Map rendering ---------- */

const CELL = 8;
const canvas = $("map");
const ctx = canvas.getContext("2d");

async function loadMap() {
  const m = await api("/api/map");
  if (!m.rows || !m.rows.length) return;
  state.mapId = m.match_id;
  state.mapW = m.width;
  state.mapH = m.height;
  canvas.width = m.width * CELL;
  canvas.height = m.height * CELL;
  const off = document.createElement("canvas");
  off.width = canvas.width;
  off.height = canvas.height;
  const octx = off.getContext("2d");
  for (let y = 0; y < m.height; y++) {
    const row = m.rows[y];
    for (let x = 0; x < m.width; x++) {
      octx.fillStyle = COLORS.terrain[row[x]] || "#10141d";
      octx.fillRect(x * CELL, y * CELL, CELL, CELL);
    }
  }
  state.terrain = off;
}

function maskBit(mask, x, y) {
  const row = mask[y];
  if (!row) return 0;
  const nibble = parseInt(row[x >> 2], 16);
  return (nibble >> (x & 3)) & 1;
}

function drawGame(s) {
  if (!state.terrain) return;
  ctx.fillStyle = "#07090d";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(state.terrain, 0, 0);
  // Fog of war: hide unexplored, dim explored but not visible.
  for (let y = 0; y < state.mapH; y++) {
    for (let x = 0; x < state.mapW; x++) {
      if (!maskBit(s.explored, x, y)) {
        ctx.fillStyle = "#07090d";
        ctx.fillRect(x * CELL, y * CELL, CELL, CELL);
      } else if (!maskBit(s.visible, x, y)) {
        ctx.fillStyle = "rgba(7, 9, 13, 0.5)";
        ctx.fillRect(x * CELL, y * CELL, CELL, CELL);
      }
    }
  }
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  // Deposits as glyphs.
  ctx.font = `bold ${CELL}px monospace`;
  for (const [x, y, sym] of s.deposits) {
    ctx.fillStyle = COLORS.resources[sym] || "#999";
    ctx.fillText(sym, x * CELL + CELL / 2, y * CELL + CELL / 2 + 1);
  }
  // Buildings: filled squares with their letter.
  for (const [, sym, x, y, team, complete] of s.buildings) {
    const color = team === 0 ? COLORS.player : COLORS.enemy;
    ctx.globalAlpha = complete ? 1 : 0.45;
    ctx.fillStyle = color;
    ctx.fillRect(x * CELL - 1, y * CELL - 1, CELL + 2, CELL + 2);
    ctx.fillStyle = "#06121c";
    ctx.font = `bold ${CELL}px monospace`;
    ctx.fillText(sym, x * CELL + CELL / 2, y * CELL + CELL / 2 + 1);
    ctx.globalAlpha = 1;
  }
  // Units: glowing letters.
  ctx.font = `bold ${CELL + 2}px monospace`;
  for (const [, sym, x, y, team] of s.units) {
    const color = team === 0 ? COLORS.player : COLORS.enemy;
    ctx.shadowColor = color;
    ctx.shadowBlur = 6;
    ctx.fillStyle = color;
    ctx.fillText(sym, x * CELL + CELL / 2, y * CELL + CELL / 2 + 1);
  }
  ctx.shadowBlur = 0;
}

/* ---------- HUD ---------- */

function fmtTime(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function renderHud(s) {
  $("hud-time").textContent = fmtTime(s.seconds || 0);
  $("hud-opponent").textContent = s.ai_profile
    ? `adversaire : ${s.ai_profile}` : "";
  for (let i = 0; i < 2; i++) {
    const t = s.teams[i];
    const card = $("team-" + i);
    const stocks = Object.entries(t.stocks)
      .map(([sym, n]) =>
        `<span class="res"><b style="color:${COLORS.resources[sym]}">${sym}</b>${n}</span>`)
      .join("");
    card.innerHTML = `
      <div class="head"><span class="nm">${t.name}${t.is_player ? " (vous)" : ""}</span>
        <span>${t.score}</span></div>
      <div class="stocks">${stocks}</div>
      <div class="sub">${t.units} unités · ${t.buildings} bâtiments${t.alive ? "" : " · DÉTRUIT"}</div>`;
  }
  const ul = $("events");
  ul.innerHTML = (s.events || [])
    .slice()
    .reverse()
    .map(([t, msg]) => `<li><span class="t">${fmtTime(t)}</span>${msg}</li>`)
    .join("");
}

/* ---------- Recap overlay ---------- */

const RESULT_LABEL = {
  victoire: "VICTOIRE !",
  defaite: "DÉFAITE...",
  egalite: "ÉGALITÉ",
};

function renderRecap(s) {
  const r = s.recap;
  if (!r) return;
  $("recap-overlay").hidden = false;
  const title = $("recap-title");
  title.textContent = RESULT_LABEL[r.result] || r.result;
  title.className = r.result;
  $("recap-sub").textContent =
    `${r.duration_min} min (${r.reason}) · adversaire ${r.ai_profile} · graine ${r.seed}`;
  const head = `<thead><tr><td></td><td>Bleus</td><td>Rouges</td></tr></thead>`;
  $("recap-table").innerHTML = head + "<tbody>" + r.rows
    .map((row) => `<tr><td>${row[0]}</td><td>${row[1]}</td><td>${row[2]}</td></tr>`)
    .join("") + "</tbody>";
  let xpLine = `+${r.xp} xp`;
  if (r.level_up) {
    xpLine += ` <span class="up">· NIVEAU ${s.profile.level} ATTEINT !</span>`;
  }
  $("recap-xp").innerHTML = xpLine;
  $("recap-countdown").textContent = r.next_in != null
    ? `Prochaine bataille dans ${Math.ceil(r.next_in)}s`
    : "";
}

/* ---------- Polling loop ---------- */

async function poll() {
  let s;
  try {
    s = await api("/api/state");
  } catch {
    return; // server briefly unavailable, retry next tick
  }
  renderProfile(s.profile);
  if (s.phase === "setup" && state.lastPhase !== "setup") {
    showSetup();
  } else if (s.phase === "playing") {
    if ($("game-view").hidden) showGame();
    $("recap-overlay").hidden = true;
    if (s.match_id !== state.mapId) await loadMap();
    if (!document.hidden) {
      drawGame(s);
      renderHud(s);
    }
  } else if (s.phase === "recap") {
    if ($("game-view").hidden) showGame();
    renderRecap(s);
  }
  state.lastPhase = s.phase;
}

function startPolling() {
  if (state.polling) clearInterval(state.polling);
  state.polling = setInterval(poll, 150);
}

showSetup();
startPolling();
