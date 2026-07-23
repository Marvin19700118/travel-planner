const form = document.getElementById("plan-form");
const liveView = document.getElementById("live-view");
const stepList = document.getElementById("step-list");
const resultView = document.getElementById("result-view");
const resultTitle = document.getElementById("result-title");
const resultMessage = document.getElementById("result-message");
const itineraryEl = document.getElementById("itinerary");

const STATUS_TITLES = {
  done: "Your itinerary is ready",
  infeasible: "This one doesn't quite fit",
  no_results: "Couldn't find what you're looking for",
  failed_max_iterations: "Ran out of attempts",
};

function addStep(type, text) {
  const li = document.createElement("li");
  li.className = `step ${type}`;
  const label = document.createElement("div");
  label.className = "step-label";
  label.textContent = type;
  const body = document.createElement("div");
  body.textContent = text;
  li.appendChild(label);
  li.appendChild(body);
  stepList.appendChild(li);
  li.scrollIntoView({ behavior: "smooth", block: "end" });
}

function describeEvent(event) {
  switch (event.type) {
    case "thought":
      return event.content.text;
    case "action":
      return `Calling ${event.content.action.tool}…`;
    case "observation":
      return JSON.stringify(event.content.observation.result);
    case "reflection":
      return event.content.text;
    case "error":
      return event.content.message;
    default:
      return "";
  }
}

function renderItinerary(dayAllocations) {
  itineraryEl.innerHTML = "";
  if (!dayAllocations) return;
  Object.keys(dayAllocations)
    .sort()
    .forEach((day) => {
      const block = document.createElement("div");
      block.className = "day-block";
      const heading = document.createElement("h3");
      heading.textContent = day;
      const list = document.createElement("ul");
      dayAllocations[day].forEach((stop) => {
        const li = document.createElement("li");
        li.textContent = `${stop.name} (${stop.duration_hr}h, ${stop.preference})`;
        list.appendChild(li);
      });
      block.appendChild(heading);
      block.appendChild(list);
      itineraryEl.appendChild(block);
    });
}

function showResult(finalContent) {
  resultView.classList.remove("hidden");
  resultView.className = `card status-${finalContent.status}`;
  resultTitle.textContent = STATUS_TITLES[finalContent.status] || "Result";
  resultMessage.textContent = finalContent.final_report;
  renderItinerary(finalContent.day_allocations);
}

form.addEventListener("submit", async (submitEvent) => {
  submitEvent.preventDefault();

  stepList.innerHTML = "";
  resultView.classList.add("hidden");
  liveView.classList.remove("hidden");

  const formData = new FormData(form);
  const preferences = formData.getAll("preferences");
  const body = {
    city: formData.get("city"),
    start_date: formData.get("start_date"),
    days: Number(formData.get("days")),
    preferences,
  };

  const response = await fetch("/api/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
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
