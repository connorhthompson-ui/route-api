const HOME = "435 E 79th St";
const WORK = "1221 Ave of the Americas";

const routesEl = document.getElementById("routes");
const refreshBtn = document.getElementById("refresh");
const swapBtn = document.getElementById("swap");
const subtitleEl = document.getElementById("subtitle");

let direction = "to_work"; // "to_work" | "to_home"

// Official MTA subway bullet colors.
const SUBWAY_COLORS = {
  1: "#EE352E", 2: "#EE352E", 3: "#EE352E",
  4: "#00933C", 5: "#00933C", 6: "#00933C",
  7: "#B933AD",
  A: "#0039A6", C: "#0039A6", E: "#0039A6",
  B: "#FF6319", D: "#FF6319", F: "#FF6319", M: "#FF6319",
  G: "#6CBE45",
  J: "#996633", Z: "#996633",
  L: "#A7A9AC",
  N: "#FCCC0A", Q: "#FCCC0A", R: "#FCCC0A", W: "#FCCC0A",
  S: "#808183",
};

function legIcon(leg) {
  return leg.mode; // "walk" | "subway" | "bus"
}

function legLabel(leg) {
  if (leg.mode === "walk") return "W";
  if (leg.mode === "bus") return leg.line || "Bus";
  return leg.line || "?";
}

function legIconStyle(leg) {
  if (leg.mode !== "subway") return "";
  const color = SUBWAY_COLORS[leg.line];
  return color ? ` style="background:${color}"` : "";
}

function updateSubtitle() {
  const [from, to] = direction === "to_work" ? [HOME, WORK] : [WORK, HOME];
  subtitleEl.textContent = `${from} → ${to}`;
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
          <span class="leg-icon ${legIcon(leg)}"${legIconStyle(leg)}>${legLabel(leg)}</span>
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
  updateSubtitle();
  routesEl.innerHTML = '<p class="status">Loading routes&hellip;</p>';
  try {
    const res = await fetch(`/best-route?direction=${direction}`);
    if (!res.ok) throw new Error(`Server returned ${res.status}`);
    const routes = await res.json();
    renderRoutes(routes);
  } catch (err) {
    routesEl.innerHTML = `<p class="error">Couldn't load routes: ${err.message}</p>`;
  }
}

refreshBtn.addEventListener("click", loadRoutes);

swapBtn.addEventListener("click", () => {
  direction = direction === "to_work" ? "to_home" : "to_work";
  loadRoutes();
});

loadRoutes();

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("service-worker.js").catch(() => {});
  });
}
