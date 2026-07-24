const runsList = document.getElementById("runs-list");
const runsEmpty = document.getElementById("runs-empty");
const runsError = document.getElementById("runs-error");

const STATUS_LABELS = {
  done: "Done",
  infeasible: "Didn't fit",
  no_results: "No results",
  failed_max_iterations: "Ran out of attempts",
  in_progress: "In progress",
};

function renderRunCard(run) {
  const card = document.createElement("div");
  card.className = "run-card";

  const info = document.createElement("div");
  info.className = "run-info";

  const title = document.createElement("h3");
  title.textContent = run.request.city;

  const meta = document.createElement("p");
  meta.textContent = `${run.request.days} day(s) · ${run.request.start_date}`;

  const badge = document.createElement("span");
  badge.className = `run-status run-status-${run.status}`;
  badge.textContent = STATUS_LABELS[run.status] || run.status;

  const replayLink = document.createElement("a");
  replayLink.href = `/replay.html?run_id=${encodeURIComponent(run.run_id)}`;
  replayLink.className = "run-replay";
  replayLink.textContent = "Replay →";

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
    runsError.textContent = "Couldn't load past runs — check your connection and try again.";
    runsError.classList.remove("hidden");
    return;
  }
  if (!response.ok) {
    runsError.textContent = "Couldn't load past runs — please try again.";
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
}

loadRuns();
