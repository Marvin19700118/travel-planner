const runsList = document.getElementById("runs-list");
const runsEmpty = document.getElementById("runs-empty");
const runsError = document.getElementById("runs-error");

function renderRunCard(run) {
  const card = document.createElement("div");
  card.className = "run-card";

  const info = document.createElement("div");
  info.className = "run-info";

  const title = document.createElement("h3");
  title.textContent = run.request.city;

  const meta = document.createElement("p");
  meta.textContent = `${run.request.days} 天 · ${run.request.start_date}`;

  const badge = document.createElement("span");
  badge.className = `run-status run-status-${run.status}`;
  badge.textContent = STATUS_LABELS[run.status] || run.status;

  const replayLink = document.createElement("a");
  replayLink.href = `/replay.html?run_id=${encodeURIComponent(run.run_id)}`;
  replayLink.className = "run-replay";
  replayLink.textContent = "重播 →";

  info.appendChild(title);
  info.appendChild(meta);
  info.appendChild(badge);
  card.appendChild(info);
  card.appendChild(replayLink);
  return card;
}

async function loadRuns() {
  let response;
  try {
    response = await fetch("/api/runs");
  } catch {
    runsError.textContent = "無法載入歷史紀錄 — 請檢查網路連線後再試一次。";
    runsError.classList.remove("hidden");
    return;
  }
  if (!response.ok) {
    runsError.textContent = "無法載入歷史紀錄 — 請再試一次。";
    runsError.classList.remove("hidden");
    return;
  }
  runsError.classList.add("hidden");
  const runs = await response.json();

  if (!runs.length) {
    runsEmpty.classList.remove("hidden");
    return;
  }

  runs.forEach((run) => runsList.appendChild(renderRunCard(run)));
}

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
  // See app.js for why this reload is needed -- sw.js's skipWaiting()
  // activates a new worker immediately, but this tab's already-loaded
  // HTML/JS is still the old version until it reloads.
  let reloaded = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (reloaded) return;
    reloaded = true;
    window.location.reload();
  });
}

loadRuns();
