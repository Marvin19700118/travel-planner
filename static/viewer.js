// Shared rendering for a run's step list, result, and interactive map.
// Used by both the live view (app.js, driven by an EventSource) and the
// replay view (replay.js, driven by stored events) so the two visually
// match exactly and never drift apart.

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
  done: "你的行程已經準備好了",
  infeasible: "這個行程不太合適",
  no_results: "找不到符合條件的地點",
  failed_max_iterations: "已用完嘗試次數",
};

// Display labels only -- the underlying event.type / preference key stays
// the English identifier the backend uses (CSS class names, stored data),
// this map is purely for what the user reads.
const STEP_LABELS = {
  thought: "想法",
  action: "行動",
  observation: "觀察",
  reflection: "反思",
  error: "錯誤",
};

const PREFERENCE_LABELS = {
  museum: "博物館",
  nature: "自然風景",
  food: "美食",
  historic: "歷史景點",
  shopping: "購物",
  night_market: "夜市",
  hiking: "健行",
  golf: "高爾夫",
};

function addStep(type, text) {
  const li = document.createElement("li");
  li.className = `step ${type}`;
  const label = document.createElement("div");
  label.className = "step-label";
  label.textContent = STEP_LABELS[type] || type;
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
      return `正在呼叫 ${event.content.action.tool}…`;
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
        const preferenceLabel = PREFERENCE_LABELS[stop.preference] || stop.preference;
        li.textContent = `${stop.name}（${stop.duration_hr} 小時，${preferenceLabel}）`;
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

  // Show the map whenever there's an actual day allocation to draw, not
  // just for a fully-fit "done" result -- a best-effort infeasible/
  // failed_max_iterations itinerary is still worth seeing on a map
  // (maintainer decision, 2026-07-24).
  if (finalContent.day_allocations && Object.keys(finalContent.day_allocations).length) {
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
      content: `<strong>${stop.name}</strong><br>${stop.address || ""}<br>${stop.duration_hr} 小時`,
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
    showMapUnavailable("地圖尚未在此部署設定。");
    return;
  }

  try {
    await loadMapsScript();
  } catch {
    showMapUnavailable("無法載入地圖。");
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
