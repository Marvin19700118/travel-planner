const tripsList = document.getElementById("trips-list");
const tripsEmpty = document.getElementById("trips-empty");
const tripsError = document.getElementById("trips-error");

function renderTripCard(trip) {
  const card = document.createElement("div");
  card.className = "trip-card";

  const img = document.createElement("img");
  img.className = "trip-cover";
  img.alt = `${trip.city} cover`;
  img.src = trip.cover_image_url || "/icon-512.png";

  const info = document.createElement("div");
  info.className = "trip-info";

  const title = document.createElement("h3");
  title.textContent = trip.city;

  const meta = document.createElement("p");
  meta.textContent = `${dayCountLabel(trip.days)} · ${trip.start_date}`;

  // Older saved trips (before infeasible/failed_max_iterations could be
  // saved) have no status field at all -- skip the badge rather than show
  // an empty pill.
  let badge = null;
  if (trip.status) {
    badge = document.createElement("span");
    badge.className = `run-status run-status-${trip.status}`;
    badge.textContent = STATUS_LABELS[trip.status] || trip.status;
  }

  const exportLink = document.createElement("a");
  exportLink.href = `/export.html?trip_id=${encodeURIComponent(trip.trip_id)}`;
  exportLink.className = "trip-export";
  exportLink.textContent = "匯出";

  const deleteButton = document.createElement("button");
  deleteButton.textContent = "刪除";
  deleteButton.className = "trip-delete";
  deleteButton.addEventListener("click", async () => {
    deleteButton.disabled = true;
    let response;
    try {
      response = await fetch(`/api/trips/${trip.trip_id}`, { method: "DELETE" });
    } catch {
      tripsError.textContent = "無法刪除 — 請檢查網路連線後再試一次。";
      tripsError.classList.remove("hidden");
      deleteButton.disabled = false;
      return;
    }
    if (!response.ok) {
      tripsError.textContent = "無法刪除 — 請再試一次。";
      tripsError.classList.remove("hidden");
      deleteButton.disabled = false;
      return;
    }
    tripsError.classList.add("hidden");
    card.remove();
    if (!tripsList.children.length) {
      tripsEmpty.classList.remove("hidden");
    }
  });

  info.appendChild(title);
  info.appendChild(meta);
  if (badge) {
    info.appendChild(badge);
  }
  info.appendChild(exportLink);
  info.appendChild(deleteButton);
  card.appendChild(img);
  card.appendChild(info);
  return card;
}

async function loadTrips() {
  let response;
  try {
    response = await fetch("/api/trips");
  } catch {
    tripsError.textContent = "無法載入已儲存的行程 — 請檢查網路連線後再試一次。";
    tripsError.classList.remove("hidden");
    return;
  }
  if (!response.ok) {
    tripsError.textContent = "無法載入已儲存的行程 — 請再試一次。";
    tripsError.classList.remove("hidden");
    return;
  }
  tripsError.classList.add("hidden");
  const savedTrips = await response.json();

  if (!savedTrips.length) {
    tripsEmpty.classList.remove("hidden");
    return;
  }

  savedTrips.forEach((trip) => tripsList.appendChild(renderTripCard(trip)));
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

loadTrips();
