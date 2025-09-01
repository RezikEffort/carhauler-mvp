const MAX_ROWS = 9;

// Must match backend defaults
const DEFAULTS = {
  truck_weight_lbs: 20000,
  trailer_weight_lbs: 18000,
  deck_height_ft: 5.0,
  truck_length_ft: 75.0,
  truck_width_ft: 8.5,
  weight_per_axle_lbs: 12000,
};
// ---- Feedback form configuration ----
const FEEDBACK_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSdBBiv32rnWWhIo2WS3C3k1tdKK5QFTUhFmgeNl-3ebh7qu_w/viewform";
const carsTbody = document.getElementById("carsTbody");
const addRowBtn = document.getElementById("addRow");
const clearRowsBtn = document.getElementById("clearRows");
const demoFillBtn = document.getElementById("demoFill");
const planBtn = document.getElementById("planBtn");
const resetProfileBtn = document.getElementById("resetProfile");

const statusEl = document.getElementById("status");
const resultsCard = document.getElementById("results");
const warningsEl = document.getElementById("warnings");
const totalsEl = document.getElementById("totals");
const decksEl = document.getElementById("decks");
const layoutBody = document.getElementById("layoutBody");
const chosenSummaryEl = document.getElementById("chosenSummary");
const deltaEl = document.getElementById("routeDelta");
const resolvedEl = document.getElementById("routeResolved");
const profileUsedEl = document.getElementById("profileUsed");

// Google Maps open buttons
const openPrimaryBtn = document.getElementById("openPrimary");
const openAltBtn = document.getElementById("openAlternative");
const openFallbackBtn = document.getElementById("openFallback");

// Legality UI
const badgesEl = document.getElementById("legalityBadges");
const legNotesEl = document.getElementById("legalityNotes");

const originInput = document.getElementById("origin");
const destinationInput = document.getElementById("destination");

// Profile inputs
const tractorWeightInput = document.getElementById("tractorWeight");
const trailerWeightInput = document.getElementById("trailerWeight");
const deckHeightInput   = document.getElementById("deckHeight");
const axleWeightInput   = document.getElementById("axleWeight");
const truckLengthInput  = document.getElementById("truckLength");
const truckWidthInput   = document.getElementById("truckWidth");

// ---- mobile class toggle (scopes CSS so desktop doesn't change) ----
function setMobileClass() {
  const isMobile = window.innerWidth <= 640;
  document.body.classList.toggle('is-mobile', isMobile);
}
window.addEventListener('resize', setMobileClass);
window.addEventListener('orientationchange', setMobileClass);
window.addEventListener('DOMContentLoaded', setMobileClass);


let MAP = null;
let LAYER_PRIMARY = null;
let LAYER_ALT = null;
let LAYER_FALLBACK = null;
let LAST_RESP = null;

function ensureMap() {
  if (MAP) return;
  MAP = L.map("map", { zoomControl: true });
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap",
  }).addTo(MAP);
}

function setProfileInputs(values = DEFAULTS) {
  tractorWeightInput.value = values.truck_weight_lbs;
  trailerWeightInput.value = values.trailer_weight_lbs;
  deckHeightInput.value    = values.deck_height_ft;
  axleWeightInput.value    = values.weight_per_axle_lbs;
  truckLengthInput.value   = values.truck_length_ft;
  truckWidthInput.value    = values.truck_width_ft;
}
function getProfileFromInputs() {
  const num = (el, def) => {
    const v = parseFloat(el.value);
    return Number.isFinite(v) ? v : def;
  };
  return {
    truck_weight_lbs:   num(tractorWeightInput, DEFAULTS.truck_weight_lbs),
    trailer_weight_lbs: num(trailerWeightInput, DEFAULTS.trailer_weight_lbs),
    deck_height_ft:     num(deckHeightInput,    DEFAULTS.deck_height_ft),
    truck_length_ft:    num(truckLengthInput,   DEFAULTS.truck_length_ft),
    truck_width_ft:     num(truckWidthInput,    DEFAULTS.truck_width_ft),
    weight_per_axle_lbs: num(axleWeightInput,   DEFAULTS.weight_per_axle_lbs),
  };
}

function rowTpl(idx, car = {}) {
  const make = car.make || "";
  const model = car.model || "";
  const year = car.year || "";
  const h = car.height_ft ?? "";
  const w = car.weight_lbs ?? "";
  return `
    <tr>
      <td>${idx+1}</td>
      <td><input placeholder="Make" value="${make}"></td>
      <td><input placeholder="Model" value="${model}"></td>
      <td><input type="number" placeholder="Year" value="${year}"></td>
      <td><input type="number" step="0.01" placeholder="Height" value="${h}"></td>
      <td><input type="number" step="1" placeholder="Weight" value="${w}"></td>
      <td>
        <button class="btn btn-ghost small btn-remove" onclick="removeRow(this)">
          <span class="icon" aria-hidden="true">
            <!-- crisp minus icon -->
            <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" focusable="false" aria-hidden="true">
              <rect x="5" y="11" width="14" height="2" rx="1"></rect>
            </svg>
          </span>
          <span class="label">Remove</span>
        </button>
      </td>
    </tr>
  `;
}



window.removeRow = (btn) => {
  btn.closest("tr").remove();
  renumber();
};
function renumber() {
  [...carsTbody.querySelectorAll("tr")].forEach((tr, i) => tr.children[0].textContent = i+1);
}
function addRow(car) {
  const rows = carsTbody.querySelectorAll("tr").length;
  if (rows >= MAX_ROWS) { alert(`Max ${MAX_ROWS} cars`); return; }
  carsTbody.insertAdjacentHTML("beforeend", rowTpl(rows, car));
}
function clearRows() { carsTbody.innerHTML = ""; }

function getCarsFromTable() {
  const cars = [];
  [...carsTbody.querySelectorAll("tr")].forEach(tr => {
    const [idx, makeTd, modelTd, yearTd, hTd, wTd] = tr.children;
    const make = makeTd.querySelector("input").value.trim();
    const model = modelTd.querySelector("input").value.trim();
    const yearStr = yearTd.querySelector("input").value.trim();
    const hStr = hTd.querySelector("input").value.trim();
    const wStr = wTd.querySelector("input").value.trim();

    if (!make || !model || !yearStr) return;
    const year = parseInt(yearStr, 10);
    if (!Number.isFinite(year) || year < 1950 || year > (new Date().getFullYear() + 1)) return;

    const car = { make, model, year };
    const h = parseFloat(hStr);
    if (Number.isFinite(h)) car.height_ft = h;
    const w = parseFloat(wStr);
    if (Number.isFinite(w)) car.weight_lbs = w;
    cars.push(car);
  });
  return cars;
}

function fmtSecs(s) {
  if (typeof s !== "number") return "n/a";
  const h = Math.floor(s/3600);
  const m = Math.round((s%3600)/60);
  return `${h}h ${m}m`;
}
function m2mi(m) { return m / 1609.34; }

// --- Google Maps helpers ---
function coordsFromPath(path) {
  if (!Array.isArray(path) || path.length < 2) return null;
  const [oLat, oLng] = path[0];
  const [dLat, dLng] = path[path.length - 1];
  return { origin: [oLat, oLng], dest: [dLat, dLng] };
}

function getOriginDestCoords(resp, preferAlt) {
  const g = resp?.geocoding;
  if (g && Array.isArray(g.origin_coord) && Array.isArray(g.destination_coord)) {
    return { origin: g.origin_coord, dest: g.destination_coord };
  }
  const path = preferAlt ? resp?.routing?.alternative_path : resp?.routing?.primary_path;
  const cd = coordsFromPath(path || []);
  if (cd) return cd;
  return null;
}

function sampleWaypoints(path, maxWpts) {
  if (!Array.isArray(path) || path.length < 3) return [];
  const cap = Math.min(maxWpts, Math.max(0, path.length - 2));
  if (cap <= 0) return [];
  const step = Math.max(1, Math.floor((path.length - 2) / cap));
  const out = [];
  for (let i = 1; i < path.length - 1 && out.length < cap; i += step) {
    const [lat, lng] = path[i];
    out.push(`${lat.toFixed(6)},${lng.toFixed(6)}`);
  }
  return out;
}

function buildGmapsUrl(origin, dest, waypoints) {
  const params = new URLSearchParams({
    api: "1",
    travelmode: "driving",
    origin: `${origin[0]},${origin[1]}`,
    destination: `${dest[0]},${dest[1]}`
  });
  if (waypoints && waypoints.length) {
    params.set("waypoints", waypoints.join("|"));
  }
  return `https://www.google.com/maps/dir/?${params.toString()}`;
}

function openInGoogleMaps(resp, preferAlt) {
  const path = preferAlt ? resp?.routing?.alternative_path : resp?.routing?.primary_path;
  const cds = getOriginDestCoords(resp, preferAlt);
  if (!cds) {
    alert("Could not determine origin/destination coordinates for Google Maps.");
    return;
  }
  const wpts = sampleWaypoints(path || [], 8);
  const url = buildGmapsUrl(cds.origin, cds.dest, wpts);
  window.open(url, "_blank");
}

function openFallbackInGoogleMaps(resp) {
  const fb = resp?.routing?.fallback;
  const g = resp?.geocoding;
  if (!fb || !fb.used) { alert("No fallback route computed."); return; }
  if (!Array.isArray(g?.origin_coord) || !Array.isArray(fb?.dest)) { alert("Missing fallback endpoints."); return; }
  const origin = g.origin_coord;
  const dest = fb.dest;  // staging point near drop-off
  const path = fb.path || [];
  const wpts = sampleWaypoints(path, 8);
  const url = buildGmapsUrl(origin, dest, wpts);
  window.open(url, "_blank");
}
// --------------------------------

function badge(label, leg) {
  let text = "Unknown";
  let cls = "badge-unknown";
  if (leg && leg.compliant === true) { text = "Legal"; cls = "badge-ok"; }
  else if (leg && leg.compliant === false) { text = "Has restrictions"; cls = "badge-warn"; }
  return `<span class="badge ${cls}">${label}: ${text}</span>`;
}

function showResults(resp) {
  LAST_RESP = resp;
  resultsCard.style.display = "block";

  // warnings
  warningsEl.innerHTML = "";
  const warns = resp?.routing?.warnings || [];
  if (warns.length === 0) warningsEl.innerHTML = `<li class="ok">No warnings</li>`;
  else warns.forEach(w => {
    const li = document.createElement("li");
    li.className = "warning";
    li.textContent = w;
    warningsEl.appendChild(li);
  });

  // map + deltas
  ensureMap();
  if (LAYER_PRIMARY) { MAP.removeLayer(LAYER_PRIMARY); LAYER_PRIMARY = null; }
  if (LAYER_ALT) { MAP.removeLayer(LAYER_ALT); LAYER_ALT = null; }
  if (LAYER_FALLBACK) { MAP.removeLayer(LAYER_FALLBACK); LAYER_FALLBACK = null; }

  const ps = resp?.routing?.primary_summary;
  const as = resp?.routing?.alternative_summary;
  const pPath = resp?.routing?.primary_path;
  const aPath = resp?.routing?.alternative_path;
  const fPath = resp?.routing?.fallback?.path;

  if (as && as.ok && typeof ps?.duration === "number" && typeof ps?.length === "number") {
    const dMeters = as.length - ps.length;
    const dMiles = dMeters / 1609.34;
    const dMinutes = (as.duration - ps.duration) / 60;
    const plusMiles = (dMiles >= 0 ? "+" : "") + dMiles.toFixed(1) + " mi";
    const plusMins  = (dMinutes >= 0 ? "+" : "") + Math.round(dMinutes) + " min";
    const primaryLine = `Primary: ${fmtSecs(ps.duration)}, ${(m2mi(ps.length)).toFixed(1)} mi`;
    const altLine     = `Alternative: ${fmtSecs(as.duration)}, ${(m2mi(as.length)).toFixed(1)} mi`;
    deltaEl.innerHTML = `<strong>Alternative vs primary:</strong> ${plusMiles} · ${plusMins}<br>${primaryLine} → ${altLine}`;
  } else {
    deltaEl.textContent = "";
  }

  const bounds = [];
  if (Array.isArray(pPath) && pPath.length >= 2) {
    const latlngsPrimary = pPath.map(([lat, lng]) => [lat, lng]);
    LAYER_PRIMARY = L.polyline(latlngsPrimary, { weight: 5, opacity: 0.9 }).addTo(MAP);
    bounds.push(...latlngsPrimary);
  }
  if (Array.isArray(aPath) && aPath.length >= 2) {
    const latlngsAlt = aPath.map(([lat, lng]) => [lat, lng]);
    LAYER_ALT = L.polyline(latlngsAlt, { weight: 5, opacity: 0.9, color: "#ff6a6a" }).addTo(MAP);
    bounds.push(...latlngsAlt);
  }
  if (Array.isArray(fPath) && fPath.length >= 2) {
    const latlngsFb = fPath.map(([lat, lng]) => [lat, lng]);
    LAYER_FALLBACK = L.polyline(latlngsFb, { weight: 4, opacity: 0.7, dashArray: "6 6" }).addTo(MAP);
    bounds.push(...latlngsFb);
  }
  if (bounds.length > 0) {
  MAP.fitBounds(bounds, { padding: [20, 20] });
  // ensure tiles/lines render correctly on mobile after layout changes
  setTimeout(() => { try { MAP.invalidateSize(true); } catch(e) {} }, 0);
}

  // enable/disable Google buttons
  openPrimaryBtn.disabled = !(Array.isArray(pPath) && pPath.length >= 2);
  openAltBtn.disabled = !(as && as.ok && Array.isArray(aPath) && aPath.length >= 2);
  openFallbackBtn.disabled = !(resp?.routing?.fallback?.used && Array.isArray(resp?.routing?.fallback?.dest));

  // legality badges + reasons
  const pl = resp?.routing?.primary_legality || null;
  const al = resp?.routing?.alternative_legality || null;
  const fl = resp?.routing?.fallback?.legality || null;

  badgesEl.innerHTML = [
    badge("Primary", pl),
    badge("Alternative", al),
    badge("Fallback", fl)
  ].join(" ");

  const unknownReasons = [];
  if (pl && pl.compliant === null) unknownReasons.push(`Primary: ${pl.reason || "No reason available."}`);
  if (al && al.compliant === null) unknownReasons.push(`Alternative: ${al.reason || "No reason available."}`);
  if (resp?.routing?.fallback?.used && fl && fl.compliant === null) unknownReasons.push(`Fallback: ${fl.reason || "No reason available."}`);
  legNotesEl.innerHTML = unknownReasons.length ? `<div class="small muted" style="margin-top:6px">${unknownReasons.join("<br>")}</div>` : "";

  // resolved address hint
  const g = resp?.geocoding;
  if (g && (g.origin_label || g.destination_label)) {
    resolvedEl.textContent = `Route: ${g.origin_label || g.origin_input} → ${g.destination_label || g.destination_input}`;
  } else {
    resolvedEl.textContent = "";
  }

  // totals
  const t = resp?.totals_for_here || {};
  totalsEl.innerHTML = `
    Height: <strong>${t.total_height_ft ?? "?"} ft</strong> (${t.total_height_m ?? "?"} m)<br>
    Weight: <strong>${t.total_weight_lbs ?? "?"} lbs</strong> (${t.total_weight_kg ?? "?"} kg)
  `;

  // profile used
  const pu = resp?.profile_used || {};
  profileUsedEl.innerHTML = `
    Tractor: ${pu.truck_weight_lbs ?? "?"} lbs &nbsp;·&nbsp;
    Trailer: ${pu.trailer_weight_lbs ?? "?"} lbs &nbsp;·&nbsp;
    Deck: ${pu.trailer_height_ft ?? "?"} ft<br>
    Length: ${pu.truck_length_ft ?? "?"} ft &nbsp;·&nbsp;
    Width: ${pu.truck_width_ft ?? "?"} ft &nbsp;·&nbsp;
    Axle limit: ${pu.weight_per_axle_lbs ?? "?"} lbs
  `;

  // deck heights
  const d = resp?.suggestion?.heights_by_deck || {};
  decksEl.innerHTML = `
    Lower loaded: <strong>${d.lower_loaded_ft ?? "?"} ft</strong><br>
    Upper loaded: <strong>${d.upper_loaded_ft ?? "?"} ft</strong><br>
    Upper deck offset: ${d.upper_deck_offset_ft ?? "?"} ft
  `;

  // chosen route summary
  const s = resp?.chosen_summary || resp?.routing?.primary_summary || {};
  chosenSummaryEl.innerHTML = `
    Mode: <span class="pill">${s.mode || "truck"}</span><br>
    Duration: <strong>${fmtSecs(s.duration)}</strong> &nbsp; Length: <strong>${m2mi(s.length).toFixed(1)} mi</strong><br>
    Decision: <em>${resp?.decision?.reason || ""}</em>
  `;

  // layout table
  layoutBody.innerHTML = "";
  const layout = resp?.suggestion?.layout || {};
  Object.keys(layout).sort().forEach(slot => {
    const entry = layout[slot];
    const car = entry?.car;
    const tr = document.createElement("tr");
    if (!entry || !car) {
      tr.innerHTML = `<td>${slot}</td><td>—</td><td class="muted"></td>`;
      layoutBody.appendChild(tr);
      return;
    }
    const loaded = entry.loaded_height_ft ?? 0;
    const veh = `${car.make} ${car.model} ${car.year}`;
    const spec = `car h=${car.height_ft} ft → loaded=${loaded.toFixed(2)} ft · w=${car.weight_lbs} lbs`;
    tr.innerHTML = `<td>${slot}</td><td>${veh}</td><td class="muted">${spec}</td>`;
    layoutBody.appendChild(tr);
  });
}

async function plan() {
  try {
    statusEl.textContent = "Planning...";
    const origin = originInput.value.trim();
    const destination = destinationInput.value.trim();
    const cars = getCarsFromTable();
    if (!origin || !destination) { alert("Enter origin and destination (address or lat,lng)."); return; }
    if (cars.length === 0) { alert("Add at least one car."); return; }

    const profile = getProfileFromInputs();

    const payload = {
      truck_weight_lbs: profile.truck_weight_lbs,
      trailer_weight_lbs: profile.trailer_weight_lbs,
      trailer_height_ft: profile.deck_height_ft,
      truck_length_ft: profile.truck_length_ft,
      truck_width_ft: profile.truck_width_ft,
      weight_per_axle_lbs: profile.weight_per_axle_lbs,
      shipped_hazardous_goods: null,
      tunnel_category: null,
      origin,
      destination,
      cars,
    };

    const res = await fetch("/plan-route", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await res.json();
    if (!res.ok || data.error) {
      statusEl.textContent = "Error planning route.";
      alert("Server error:\n" + JSON.stringify(data, null, 2));
      return;
    }

    statusEl.textContent = "Done";
    showResults(data);

  } catch (e) {
    console.error(e);
    statusEl.textContent = "Failed";
    alert("Failed: " + e.message);
  }
}

function demoFill() {
  clearRows();
  const demo = [
    { make:"Honda",     model:"Civic",    year:2020, height_ft:4.64, weight_lbs:2771 },
    { make:"Toyota",    model:"Camry",    year:2018, height_ft:4.74, weight_lbs:3340 },
    { make:"Tesla",     model:"Model 3",  year:2020, height_ft:4.73, weight_lbs:4032 },
    { make:"Honda",     model:"CR-V",     year:2020, height_ft:5.54, weight_lbs:3521 },
    { make:"Toyota",    model:"RAV4",     year:2020, height_ft:5.58, weight_lbs:3490 },
    { make:"Ford",      model:"F-150",    year:2021, height_ft:6.43, weight_lbs:4705 },
    { make:"Chevrolet", model:"Tahoe",    year:2020, height_ft:6.20, weight_lbs:5602 },
    { make:"Ford",      model:"Explorer", year:2020, height_ft:5.83, weight_lbs:4345 },
    { make:"Subaru",    model:"Outback",  year:2019, height_ft:5.54, weight_lbs:3686 },
  ];
  demo.forEach(car => addRow(car));
}

// wire up
addRowBtn.addEventListener("click", () => addRow({}));
clearRowsBtn.addEventListener("click", clearRows);
demoFillBtn.addEventListener("click", demoFill);
planBtn.addEventListener("click", plan);
resetProfileBtn.addEventListener("click", () => setProfileInputs(DEFAULTS));
openPrimaryBtn.addEventListener("click", () => { if (LAST_RESP) openInGoogleMaps(LAST_RESP, false); });
openAltBtn.addEventListener("click", () => { if (LAST_RESP) openInGoogleMaps(LAST_RESP, true); });
openFallbackBtn.addEventListener("click", () => { if (LAST_RESP) openFallbackInGoogleMaps(LAST_RESP); });

// Build info banner
fetch('/static/build.json')
  .then(r => r.json())
  .then(b => {
    document.getElementById('buildInfo').textContent =
      `${b.version || ''} ${b.commit ? '('+b.commit.substring(0,7)+')' : ''}`;
  })
  .catch(()=>{});

// init
setProfileInputs(DEFAULTS);
addRow({}); addRow({}); addRow({});

// --- Feedback: open the Google Form ---
document.getElementById("feedbackBtn").addEventListener("click", () => {
  window.open(FEEDBACK_FORM_URL, "_blank", "noopener");
});
document.getElementById("feedbackFooterLink").addEventListener("click", (e) => {
  e.preventDefault();
  window.open(FEEDBACK_FORM_URL, "_blank", "noopener");
});
