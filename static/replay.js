// Replays a stored run's events through the exact same rendering functions
// the live view uses (addStep/showResult, from viewer.js), driven from a
// single fetched record instead of an EventSource -- ticket #9 requires
// this makes no new calls to any external place/weather/route/LLM service,
// which holds here since the only network call is to our own
// /api/plan/{run_id}/replay, itself just reading a stored file.

const replayError = document.getElementById("replay-error");

const STEP_DELAY_MS = 350;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function replay(runId) {
  let response;
  try {
    response = await fetch(`/api/plan/${encodeURIComponent(runId)}/replay`);
  } catch {
    replayError.textContent = "Couldn't load this run — check your connection and try again.";
    replayError.classList.remove("hidden");
    return;
  }
  if (!response.ok) {
    replayError.textContent = response.status === 404 ? "This run doesn't exist." : "Couldn't load this run.";
    replayError.classList.remove("hidden");
    return;
  }

  const record = await response.json();
  liveView.classList.remove("hidden");

  for (const event of record.events) {
    if (event.type === "final") {
      showResult(event.content);
      return;
    }
    if (event.type === "status") {
      continue;
    }
    addStep(event.type, describeEvent(event));
    await sleep(STEP_DELAY_MS);
  }
}

const runId = new URLSearchParams(window.location.search).get("run_id");
if (!runId) {
  replayError.textContent = "No run selected — go back and pick one from the list.";
  replayError.classList.remove("hidden");
} else {
  replay(runId);
}
