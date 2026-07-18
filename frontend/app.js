const routesEl = document.getElementById("routes");
const refreshBtn = document.getElementById("refresh");

function legIcon(leg) {
  return leg.mode; // "walk" | "subway" | "bus"
}

function legLabel(leg) {
  if (leg.mode === "walk") return "W";
  if (leg.mode === "bus") return "B";
  return leg.line || "S";
}

function renderRoutes(routes) {
  if (!routes.length) {
    routesEl.innerHTML = '<p class="status">No routes found.</p>';
    return;
  }

  const fastest = routes.reduce((a, b) =>
    a.total_duration_min <= b.total_duration_min ? a : b
  );

  routesEl.innerHTML = routes
    .map((route) => {
      const isFastest = route.id === fastest.id;
      const legs = route.legs
        .map(
          (leg) => `
        <li class="leg">
          <span class="leg-icon ${legIcon(leg)}">${legLabel(leg)}</span>
          <span>${leg.description}</span>
          <span class="leg-duration">${leg.duration_min} min</span>
        </li>`
        )
        .join("");

      return `
        <article class="route-card ${isFastest ? "fastest" : ""}">
          <div class="route-card-header">
            <div>
              ${isFastest ? '<span class="badge">Fastest</span><br/>' : ""}
              <span class="route-label">${route.label}</span>
            </div>
            <div class="route-duration">${route.total_duration_min}<span> min</span></div>
          </div>
          <ul class="legs">${legs}</ul>
        </article>`;
    })
    .join("");
}

async function loadRoutes() {
  routesEl.innerHTML = '<p class="status">Loading routes&hellip;</p>';
  try {
    const res = await fetch("/best-route");
    if (!res.ok) throw new Error(`Server returned ${res.status}`);
    const routes = await res.json();
    renderRoutes(routes);
  } catch (err) {
    routesEl.innerHTML = `<p class="error">Couldn't load routes: ${err.message}</p>`;
  }
}

refreshBtn.addEventListener("click", loadRoutes);

loadRoutes();

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("service-worker.js").catch(() => {});
  });
}
