const form = document.getElementById("plan-form");

const OFFLINE_MESSAGE = "You're offline — planning a trip needs a connection. Reconnect and try again.";

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
    addStep("error", "Couldn't start planning — please check your inputs.");
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
    addStep("error", "Lost connection to the planner.");
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
}
