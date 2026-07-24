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

  const exportLink = document.createElement("a");
  exportLink.href = `/export.html?trip_id=${encodeURIComponent(trip.trip_id)}`;
  exportLink.className = "trip-export";
  exportLink.textContent = "Export";

  const deleteButton = document.createElement("button");
  deleteButton.textContent = "Delete";
  deleteButton.className = "trip-delete";
  deleteButton.addEventListener("click", async () => {
    deleteButton.disabled = true;
    let response;
    try {
      response = await fetch(`/api/trips/${trip.trip_id}`, { method: "DELETE" });
    } catch {
      tripsError.textContent = "Couldn't delete — check your connection and try again.";
      tripsError.classList.remove("hidden");
      deleteButton.disabled = false;
      return;
    }
    if (!response.ok) {
      tripsError.textContent = "Couldn't delete — please try again.";
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
    tripsError.textContent = "Couldn't load saved trips — check your connection and try again.";
    tripsError.classList.remove("hidden");
    return;
  }
  if (!response.ok) {
    tripsError.textContent = "Couldn't load saved trips — please try again.";
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
}

loadTrips();
