const form = document.getElementById("plan-form");
const liveView = document.getElementById("live-view");
const stepList = document.getElementById("step-list");
const resultView = document.getElementById("result-view");
const resultTitle = document.getElementById("result-title");
const resultMessage = document.getElementById("result-message");
const itineraryEl = document.getElementById("itinerary");
const mapSection = document.getElementById("map-section");
const mapTabs = document.getElementById("map-tabs");
const mapDiv = document.getElementById("map");
const mapUnavailable = document.getElementById("map-unavailable");

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

  if (finalContent.status === "done") {
    showMap(finalContent.day_allocations, finalContent.day_polylines);
  } else {
    mapSection.classList.add("hidden");
  }
}

// --- Interactive map (ticket #4) ------------------------------------------
// The map only ever draws data the backend already computed (day
// allocations + the Directions polyline captured during the planning loop)
// — it never issues its own route-calculation call.

let mapsApiKey = null;
let map = null;
let activeOverlays = [];

async function loadMapsConfig() {
  try {
    const response = await fetch("/api/config");
    const config = await response.json();
    mapsApiKey = config.mapsApiKey || null;
  } catch {
    mapsApiKey = null;
  }
}

function loadMapsScript() {
  return new Promise((resolve, reject) => {
    if (window.google && window.google.maps) {
      resolve();
      return;
    }
    const script = document.createElement("script");
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(mapsApiKey)}&libraries=geometry`;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("failed to load Google Maps"));
    document.head.appendChild(script);
  });
}

function clearOverlays() {
  activeOverlays.forEach((overlay) => overlay.setMap(null));
  activeOverlays = [];
}

function renderDay(day, dayAllocations, dayPolylines) {
  clearOverlays();
  const stops = dayAllocations[day] || [];
  const bounds = new google.maps.LatLngBounds();

  stops.forEach((stop) => {
    const position = { lat: stop.lat, lng: stop.lng };
    const marker = new google.maps.Marker({ position, map, title: stop.name });
    const infoWindow = new google.maps.InfoWindow({
      content: `<strong>${stop.name}</strong><br>${stop.address || ""}<br>${stop.duration_hr}h`,
    });
    marker.addListener("click", () => infoWindow.open(map, marker));
    activeOverlays.push(marker);
    bounds.extend(position);
  });

  const polyline = dayPolylines ? dayPolylines[day] : null;
  if (polyline) {
    const path = google.maps.geometry.encoding.decodePath(polyline);
    const line = new google.maps.Polyline({ path, map, strokeColor: "#ff8c66", strokeWeight: 4 });
    activeOverlays.push(line);
  }

  if (!bounds.isEmpty()) {
    map.fitBounds(bounds);
  }
}

function renderMapTabs(dayAllocations, dayPolylines) {
  mapTabs.innerHTML = "";
  const days = Object.keys(dayAllocations).sort();
  days.forEach((day, index) => {
    const button = document.createElement("button");
    button.textContent = day;
    button.setAttribute("role", "tab");
    button.setAttribute("aria-selected", index === 0 ? "true" : "false");
    button.addEventListener("click", () => {
      [...mapTabs.children].forEach((b) => b.setAttribute("aria-selected", "false"));
      button.setAttribute("aria-selected", "true");
      renderDay(day, dayAllocations, dayPolylines);
    });
    mapTabs.appendChild(button);
  });
  if (days.length) {
    renderDay(days[0], dayAllocations, dayPolylines);
  }
}

function showMapUnavailable(message) {
  mapUnavailable.textContent = message;
  mapUnavailable.classList.remove("hidden");
  mapDiv.classList.add("hidden");
  mapTabs.classList.add("hidden");
}

async function showMap(dayAllocations, dayPolylines) {
  if (!dayAllocations || !Object.keys(dayAllocations).length) {
    mapSection.classList.add("hidden");
    return;
  }
  mapSection.classList.remove("hidden");

  if (!mapsApiKey) {
    showMapUnavailable("Map isn't configured on this deployment yet.");
    return;
  }

  try {
    await loadMapsScript();
  } catch {
    showMapUnavailable("Couldn't load the map.");
    return;
  }

  mapUnavailable.classList.add("hidden");
  mapDiv.classList.remove("hidden");
  mapTabs.classList.remove("hidden");

  if (!map) {
    map = new google.maps.Map(mapDiv, { zoom: 12, center: { lat: 0, lng: 0 } });
  }
  renderMapTabs(dayAllocations, dayPolylines);
}

loadMapsConfig();

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
