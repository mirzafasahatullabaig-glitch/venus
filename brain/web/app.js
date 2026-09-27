"use strict";

const $ = (id) => document.getElementById(id);
const KEY_STORE = "venus_api_key";

// Restore a remembered key (per-viewer convenience only).
try { $("apikey").value = localStorage.getItem(KEY_STORE) || ""; } catch (_) {}

let controller = null;               // AbortController for the active run
const bubbles = {};                  // turn index -> body element

function setRunning(on) {
  $("start").disabled = on;
  $("stop").disabled = !on;
}

function setStatus(text, isErr) {
  const el = $("status");
  el.textContent = text;
  el.classList.toggle("err", !!isErr);
}

function clearTranscript() {
  $("transcript").innerHTML = "";
  for (const k of Object.keys(bubbles)) delete bubbles[k];
}

function ensureBubble(index, bot, model, body) {
  if (bubbles[index]) return bubbles[index];
  const wrap = document.createElement("div");
  wrap.className = `bubble ${bot}`;
  const who = document.createElement("div");
  who.className = "who";
  who.innerHTML = `<b>${bot.toUpperCase()}</b> · ${body || ""} · ${model || ""}`;
  const bodyEl = document.createElement("div");
  bodyEl.className = "text";
  wrap.appendChild(who);
  wrap.appendChild(bodyEl);
  $("transcript").appendChild(wrap);
  bubbles[index] = { bodyEl, whoEl: who };
  return bubbles[index];
}

function handleEvent(ev) {
  if (ev.type === "turn_start") {
    ensureBubble(ev.index, ev.bot, ev.model, ev.body);
    setStatus(`${ev.bot} thinking…`);
  } else if (ev.type === "token") {
    const b = ensureBubble(ev.index, ev.bot);
    b.bodyEl.textContent += ev.text;
    window.scrollTo(0, document.body.scrollHeight);
  } else if (ev.type === "turn_end") {
    const b = bubbles[ev.index];
    if (b) {
      const meta = document.createElement("span");
      meta.className = "meta";
      const tok = ev.tokens != null ? `${ev.tokens} tok · ` : "";
      meta.textContent = `${tok}${ev.latency_s}s`;
      b.whoEl.appendChild(meta);
    }
  } else if (ev.type === "done") {
    setStatus(ev.converged ? "converged early ✓" : `done · ${ev.turns} turns`);
  } else if (ev.type === "saved") {
    loadRuns();
  } else if (ev.type === "error") {
    setStatus("error: " + ev.message, true);
  }
}

// Parse a text/event-stream body incrementally (fetch, so we can POST + auth).
async function streamRun(body, key) {
  controller = new AbortController();
  const resp = await fetch("/run", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Authorization": "Bearer " + key },
    body: JSON.stringify(body),
    signal: controller.signal,
  });
  if (!resp.ok) {
    const detail = await resp.text().catch(() => resp.statusText);
    throw new Error(`HTTP ${resp.status}: ${detail}`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) !== -1) {
      const frame = buf.slice(0, i);
      buf = buf.slice(i + 2);
      const line = frame.split("\n").find((l) => l.startsWith("data:"));
      if (line) handleEvent(JSON.parse(line.slice(5).trim()));
    }
  }
}

async function start() {
  const key = $("apikey").value.trim();
  if (!key) { setStatus("enter the API key first", true); return; }
  try { localStorage.setItem(KEY_STORE, key); } catch (_) {}

  const personas = {};
  if ($("p1").value.trim()) personas.bot1 = $("p1").value;
  if ($("p2").value.trim()) personas.bot2 = $("p2").value;

  const body = {
    task: $("task").value,
    turn_limit: parseInt($("turns").value, 10) || 8,
    stop_marker: $("marker").value || null,
    personas,
  };

  clearTranscript();
  setStatus("starting…");
  setRunning(true);
  try {
    await streamRun(body, key);
  } catch (err) {
    if (err.name !== "AbortError") setStatus("error: " + err.message, true);
    else setStatus("stopped");
  } finally {
    setRunning(false);
    controller = null;
  }
}

function stop() {
  if (controller) controller.abort();
}

async function loadRuns() {
  const key = $("apikey").value.trim();
  if (!key) return;
  try {
    const resp = await fetch("/runs", { headers: { "Authorization": "Bearer " + key } });
    if (!resp.ok) return;
    const runs = await resp.json();
    const ul = $("runs");
    ul.innerHTML = "";
    for (const r of runs) {
      const li = document.createElement("li");
      const name = document.createElement("span");
      name.className = "name";
      name.textContent = r.name;
      name.title = r.task;
      name.onclick = () => viewRun(r.name);
      const tag = document.createElement("span");
      tag.className = "tag";
      tag.textContent = `${r.turns} turns · ${r.converged ? "converged" : "limit"}`;
      li.appendChild(name);
      li.appendChild(tag);
      ul.appendChild(li);
    }
    if (!runs.length) ul.innerHTML = '<li class="tag">no runs yet</li>';
  } catch (_) {}
}

async function viewRun(name) {
  const key = $("apikey").value.trim();
  const resp = await fetch("/runs/" + encodeURIComponent(name), {
    headers: { "Authorization": "Bearer " + key },
  });
  if (!resp.ok) { setStatus("could not load run", true); return; }
  const rec = await resp.json();
  clearTranscript();
  rec.turns.forEach((t, i) => {
    ensureBubble(i, t.bot, t.model, "");
    bubbles[i].bodyEl.textContent = t.text;
    const meta = document.createElement("span");
    meta.className = "meta";
    const tok = t.tokens != null ? `${t.tokens} tok · ` : "";
    meta.textContent = `${tok}${t.latency_s}s`;
    bubbles[i].whoEl.appendChild(meta);
  });
  setStatus(`viewing ${name} · ${rec.converged ? "converged" : "hit limit"}`);
}

$("start").onclick = start;
$("stop").onclick = stop;
$("refresh").onclick = loadRuns;
$("apikey").onchange = loadRuns;
loadRuns();
