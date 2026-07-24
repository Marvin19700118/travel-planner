const tripsList = document.getElementById("trips-list");
const tripsEmpty = document.getElementById("trips-empty");

function dayCountLabel(days) {
  return `${days} day${days === 1 ? "" : "s"}`;
}

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

  const deleteButton = document.createElement("button");
  deleteButton.textContent = "Delete";
  deleteButton.className = "trip-delete";
  deleteButton.addEventListener("click", async () => {
    deleteButton.disabled = true;
    await fetch(`/api/trips/${trip.trip_id}`, { method: "DELETE" });
    card.remove();
    if (!tripsList.children.length) {
      tripsEmpty.classList.remove("hidden");
    }
  });

  info.appendChild(title);
  info.appendChild(meta);
  info.appendChild(deleteButton);
  card.appendChild(img);
  card.appendChild(info);
  return card;
}

async function loadTrips() {
  const response = await fetch("/api/trips");
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
