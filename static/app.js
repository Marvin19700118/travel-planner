const form = document.getElementById("plan-form");

const OFFLINE_MESSAGE = "你目前離線 — 規劃行程需要網路連線，請重新連線後再試一次。";

form.addEventListener("submit", async (submitEvent) => {
  submitEvent.preventDefault();

  stepList.innerHTML = "";
  resultView.classList.add("hidden");
  liveView.classList.remove("hidden");

  if (!navigator.onLine) {
    addStep("error", OFFLINE_MESSAGE);
    return;
  }

  const formData = new FormData(form);
  const preferences = formData.getAll("preferences");
  const body = {
    city: formData.get("city"),
    origin: formData.get("origin"),
    start_date: formData.get("start_date"),
    days: Number(formData.get("days")),
    preferences,
  };

  let response;
  try {
    response = await fetch("/api/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    addStep("error", OFFLINE_MESSAGE);
    return;
  }
  if (!response.ok) {
    addStep("error", "無法開始規劃 — 請檢查輸入內容。");
    return;
  }
  const { run_id } = await response.json();

  const source = new EventSource(`/api/plan/${run_id}/stream`);
  source.onmessage = (message) => {
    const event = JSON.parse(message.data);
    if (event.type === "final") {
      showResult(event.content);
      source.close();
      return;
    }
    if (event.type === "status") {
      return;
    }
    addStep(event.type, describeEvent(event));
  };
  source.onerror = () => {
    addStep("error", "與規劃服務的連線中斷了。");
    source.close();
  };
});

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // Non-fatal: the app works fine without an installed service worker,
      // just without the fast-repeat-load / offline-shell benefits.
    });
  });
  // Live-discovered 2026-07-24: sw.js's skipWaiting() activates a new
  // worker immediately, but this tab's already-loaded HTML/JS is still the
  // old version until it reloads -- without this, a returning user with a
  // pinned/open tab could keep submitting against a stale form (e.g.
  // missing a brand-new required field) indefinitely. `reloaded` survives
  // repeated "controllerchange" events but resets on an actual reload, so
  // this can never loop.
  let reloaded = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (reloaded) return;
    reloaded = true;
    window.location.reload();
  });
}
