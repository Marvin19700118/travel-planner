const exportError = document.getElementById("export-error");
const exportContent = document.getElementById("export-content");
const exportCover = document.getElementById("export-cover");
const exportTitle = document.getElementById("export-title");
const exportMeta = document.getElementById("export-meta");
const exportDays = document.getElementById("export-days");
const printButton = document.getElementById("print-button");

const STATIC_MAP_SIZE = "600x300";
// A day realistically holds only a handful of stops (search results are
// capped -- see agent/tools.py's _MAX_RESULTS_PER_CATEGORY), and Static
// Maps API marker labels only support a single character, so numbering
// past 9 would silently misrender; day sizes in practice never get close.
const MARKER_LABELS = "123456789";

function buildStaticMapUrl(stops, polyline, mapsApiKey) {
  const params = new URLSearchParams();
  params.set("size", STATIC_MAP_SIZE);
  params.set("key", mapsApiKey);
  stops.forEach((stop, index) => {
    const label = MARKER_LABELS[index] || "";
    params.append("markers", `color:0xff8c66|label:${label}|${stop.lat},${stop.lng}`);
  });
  if (polyline) {
    params.append("path", `color:0xff8c66|weight:4|enc:${polyline}`);
  }
  return `https://maps.googleapis.com/maps/api/staticmap?${params.toString()}`;
}

function renderStop(stop) {
  const li = document.createElement("li");
  li.className = "export-stop";

  const img = document.createElement("img");
  img.className = "export-thumb";
  img.alt = "";
  img.src = stop.photo_url || "/icon-512.png";

  const info = document.createElement("div");
  const name = document.createElement("strong");
  name.textContent = stop.name;
  const detail = document.createElement("span");
  detail.textContent = `${stop.duration_hr} 小時${stop.address ? " · " + stop.address : ""}`;
  info.appendChild(name);
  info.appendChild(detail);

  li.appendChild(img);
  li.appendChild(info);
  return li;
}

function appendMapUnavailable(block, message) {
  const unavailable = document.createElement("p");
  unavailable.className = "export-map-unavailable";
  unavailable.textContent = message;
  block.appendChild(unavailable);
}

function renderDay(day, stops, polyline, mapsApiKey) {
  const block = document.createElement("section");
  block.className = "export-day";

  const heading = document.createElement("h2");
  heading.textContent = day;
  block.appendChild(heading);

  if (mapsApiKey) {
    const map = document.createElement("img");
    map.className = "export-map";
    map.alt = `${day} 路線地圖`;
    // A failed Static Maps request (bad key restriction, quota, network)
    // must never leave a broken-image icon in a printed page -- swap in
    // the same text fallback used when no key is configured at all.
    map.addEventListener(
      "error",
      () => {
        map.remove();
        appendMapUnavailable(block, "無法載入這一天的地圖。");
      },
      { once: true }
    );
    map.src = buildStaticMapUrl(stops, polyline, mapsApiKey);
    block.appendChild(map);
  } else {
    appendMapUnavailable(block, "地圖尚未在此部署設定。");
  }

  const list = document.createElement("ul");
  list.className = "export-stops";
  stops.forEach((stop) => list.appendChild(renderStop(stop)));
  block.appendChild(list);

  exportDays.appendChild(block);
}

function showError(message) {
  exportError.textContent = message;
  exportError.classList.remove("hidden");
}

async function loadStaticMapsApiKey() {
  // A failed /api/config fetch should only disable the map, never the rest
  // of the page (cover, itinerary, thumbnails don't depend on it) --
  // matches the resilience pattern already established in viewer.js's
  // loadMapsConfig. Deliberately reads staticMapsApiKey, not mapsApiKey --
  // Maps Static API and Maps JavaScript API can be restricted to separate
  // keys (live-confirmed necessary: the JS-only key 403'd on Static Maps).
  try {
    const response = await fetch("/api/config");
    if (!response.ok) return null;
    const config = await response.json();
    return config.staticMapsApiKey || null;
  } catch {
    return null;
  }
}

async function loadExport(tripId) {
  let tripResponse;
  try {
    tripResponse = await fetch(`/api/trips/${tripId}`);
  } catch {
    showError("無法載入這筆行程 — 請檢查網路連線後再試一次。");
    return;
  }

  if (!tripResponse.ok) {
    showError(tripResponse.status === 404 ? "這筆行程不存在。" : "無法載入這筆行程。");
    return;
  }

  const trip = await tripResponse.json();
  const mapsApiKey = await loadStaticMapsApiKey();

  exportCover.src = trip.cover_image_url || "/icon-512.png";
  exportCover.alt = `${trip.city} 封面圖`;
  exportTitle.textContent = trip.city;
  exportMeta.textContent = `${dayCountLabel(trip.days)} · ${trip.start_date}`;

  Object.keys(trip.day_allocations)
    .sort()
    .forEach((day) => {
      const polyline = (trip.day_polylines || {})[day] || null;
      renderDay(day, trip.day_allocations[day], polyline, mapsApiKey);
    });

  exportContent.classList.remove("hidden");
}

printButton.addEventListener("click", () => window.print());

const tripId = new URLSearchParams(window.location.search).get("trip_id");
if (!tripId) {
  showError("尚未選擇行程 — 請回上一頁從已儲存的行程中選一筆。");
} else {
  loadExport(tripId);
}
