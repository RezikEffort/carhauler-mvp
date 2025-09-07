// app.js — Year→Make→Model UI with UX polish (inline spinner, enabled selects),
// CarAPI-backed options, per-row spec chips, client-side estimates fallback,
// legacy route + smarter placement. Keeps all existing features.

// ------------------------------
// Config & constants
// ------------------------------
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

// Per-slot offsets (sent to server for smarter loaded heights)
const SLOT_OFFSETS_FT = { T1_HEAD: 2.0, T2_FRONT: 2.6, T3_MID: 2.8, T4_REAR: 2.5 };

// Orientation rules (sent to server)
const ORIENTATION_RULES = {
  allow_reversed: true,
  top_only: true,
  min_height_for_benefit_ft: 5.6,
  reverse_bonus_ft: 0.30,
};

// Feedback form
const FEEDBACK_FORM_URL =
  "https://docs.google.com/forms/d/e/1FAIpQLSdBBiv32rnWWhIo2WS3C3k1tdKK5QFTUhFmgeNl-3ebh7qu_w/viewform";

// ------------------------------
// DOM refs
// ------------------------------
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

// Inputs
const originInput = document.getElementById("origin");
const destinationInput = document.getElementById("destination");

// Profile inputs
const tractorWeightInput = document.getElementById("tractorWeight");
const trailerWeightInput = document.getElementById("trailerWeight");
const deckHeightInput = document.getElementById("deckHeight");
const axleWeightInput = document.getElementById("axleWeight");
const truckLengthInput = document.getElementById("truckLength");
const truckWidthInput = document.getElementById("truckWidth");

// ------------------------------
// Mobile helper (adds body.is-mobile)
// ------------------------------
function setMobileClass() {
  const isMobile = window.innerWidth <= 640;
  document.body.classList.toggle("is-mobile", isMobile);
}
window.addEventListener("resize", setMobileClass);
window.addEventListener("orientationchange", setMobileClass);
window.addEventListener("DOMContentLoaded", setMobileClass);

// ------------------------------
// Years + simple cache for option APIs
// ------------------------------
const YEARS_MIN = 1990;
const YEARS_MAX = new Date().getFullYear() + 1;
function yearsList(desc = true) {
  const out = [];
  for (let y = YEARS_MIN; y <= YEARS_MAX; y++) out.push(y);
  return desc ? out.reverse() : out;
}

// Remember last chosen year to prefill new rows
let LAST_YEAR = null;

// Basic response cache
const API_CACHE = new Map();
async function getJSON(url, { signal } = {}) {
  if (API_CACHE.has(url)) return API_CACHE.get(url);
  const r = await fetch(url, { signal });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j?.detail || `HTTP ${r.status}`);
  API_CACHE.set(url, j);
  return j;
}
async function postJSON(url, payload, { signal } = {}) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j?.detail || `HTTP ${r.status}`);
  return j;
}

// ------------------------------
// UX helpers: loading / error states for <select>
// (keep select enabled; show top "Loading…" option; tiny inline spinner)
// ------------------------------
function setSelectLoading(selectEl, msg = "Loading…") {
  const wrap = selectEl.closest(".select-wrap");
  if (wrap) wrap.classList.add("is-loading");
  // Insert a top "Loading…" option if not present
  let loadingOpt = selectEl.querySelector('option[data-loading="1"]');
  if (!loadingOpt) {
    loadingOpt = document.createElement("option");
    loadingOpt.value = "";
    loadingOpt.textContent = msg;
    loadingOpt.setAttribute("data-loading", "1");
    selectEl.insertBefore(loadingOpt, selectEl.firstChild);
  }
  if (!selectEl.value) selectEl.selectedIndex = 0;
}
function clearSelectLoading(selectEl, placeholder = "Select…") {
  const wrap = selectEl.closest(".select-wrap");
  if (wrap) wrap.classList.remove("is-loading");
  const loadingOpt = selectEl.querySelector('option[data-loading="1"]');
  if (loadingOpt) loadingOpt.remove();
  if (!selectEl.options.length) {
    selectEl.innerHTML = `<option value="">${placeholder}</option>`;
  }
}
function setSelectError(selectEl, placeholder = "Failed — retry") {
  const wrap = selectEl.closest(".select-wrap");
  if (wrap) wrap.classList.remove("is-loading");
  selectEl.innerHTML = `<option value="">${placeholder}</option>`;
}

// Abort management per row
function newAbortFor(tr, key) {
  tr._ac = tr._ac || {};
  if (tr._ac[key]) {
    try { tr._ac[key].abort(); } catch {}
  }
  tr._ac[key] = new AbortController();
  return tr._ac[key];
}

// ------------------------------
// CarAPI-backed option loaders
// ------------------------------
async function loadMakes(selectEl, year = null, { signal } = {}) {
  setSelectLoading(selectEl, "Loading makes…");
  const url = year ? `/vehicle-options/makes?year=${encodeURIComponent(year)}` : `/vehicle-options/makes`;
  try {
    const data = await getJSON(url, { signal });
    const makes = Array.isArray(data) ? data : (data.makes ?? data.options ?? data.data ?? []);
    if (signal?.aborted) return;
    // Rebuild options (keep select enabled)
    const opts = ['<option value="">Select make…</option>'];
    for (const m of makes) opts.push(`<option value="${m}">${m}</option>`);
    selectEl.innerHTML = opts.join("");
  } catch (e) {
    if (e.name === "AbortError") return;
    console.warn(e);
    setSelectError(selectEl, "Failed — retry");
    return;
  } finally {
    if (!signal?.aborted) clearSelectLoading(selectEl, "Select make…");
  }
}

async function loadModels(selectEl, year, make, { signal } = {}) {
  selectEl.innerHTML = `<option value="">Select model…</option>`;
  if (!make) return;
  setSelectLoading(selectEl, "Loading models…");
  const url =
    Number.isFinite(year) && year
      ? `/vehicle-options/models?year=${encodeURIComponent(year)}&make=${encodeURIComponent(make)}`
      : `/vehicle-options/models?make=${encodeURIComponent(make)}`;
  try {
    const data = await getJSON(url, { signal });
    const models = Array.isArray(data) ? data : (data.models ?? data.options ?? data.data ?? []);
    if (signal?.aborted) return;
    const opts = ['<option value="">Select model…</option>'];
    for (const m of models) opts.push(`<option value="${m}">${m}</option>`);
    selectEl.innerHTML = opts.join("");
  } catch (e) {
    if (e.name === "AbortError") return;
    console.warn(e);
    setSelectError(selectEl, "Failed — retry");
    return;
  } finally {
    if (!signal?.aborted) clearSelectLoading(selectEl, "Select model…");
  }
}

async function autofillSpecs(year, make, model, { signal } = {}) {
  const endpoints = ["/vehicle-options/vehicle-specs", "/vehicle-specs"];
  for (const ep of endpoints) {
    try {
      return await postJSON(ep, { year, make, model }, { signal });
    } catch (_) {}
  }
  throw new Error("Spec lookup failed");
}

// ------------------------------
// Client-side estimate fallback (segment medians)
// ------------------------------
const SEGMENT_MEDIANS = {
  "Sedan":          { height_ft: 4.75, weight_lbs: 3300 },
  "Hatchback":      { height_ft: 4.70, weight_lbs: 3000 },
  "Coupe":          { height_ft: 4.60, weight_lbs: 3100 },
  "Convertible":    { height_ft: 4.55, weight_lbs: 3200 },
  "Wagon":          { height_ft: 5.00, weight_lbs: 3600 },
  "SUV/Crossover":  { height_ft: 5.70, weight_lbs: 4200 },
  "Pickup":         { height_ft: 6.30, weight_lbs: 4700 },
  "Van":            { height_ft: 6.40, weight_lbs: 4800 },
  "Default":        { height_ft: 5.00, weight_lbs: 3500 },
};
function classifySegment(make, model) {
  const mm = `${make} ${model}`.toLowerCase();
  if (/(f-?150|silverado|sierra|ram\s?(\d{3,4})|tacoma|tundra|ridgeline|colorado|ranger)/.test(mm)) return "Pickup";
  if (/(suv|rav4|cr[-\s]?v|pilot|highlander|yukon|escape|explorer|outback|forester|cx-|x[3-7]|gle|gls|q[357]|equinox|rogue|murano|santa fe|tucson)/.test(mm)) return "SUV/Crossover";
  if (/(van|sprinter|transit|sienna|odyssey|caravan|pacifica)/.test(mm)) return "Van";
  if (/(wagon|touring|estate|allroad|outback)/.test(mm)) return "Wagon";
  if (/(convertible|spider|spyder|cabrio|roadster)/.test(mm)) return "Convertible";
  if (/(coupe|2dr)/.test(mm)) return "Coupe";
  if (/(hatch|5dr)/.test(mm)) return "Hatchback";
  return "Sedan";
}
function estimateSpecs(year, make, model) {
  const seg = classifySegment(make, model);
  const base = SEGMENT_MEDIANS[seg] || SEGMENT_MEDIANS.Default;
  return { ...base, source: "Estimate", notes: `segment median: ${seg}` };
}

// ------------------------------
// Per-row spec chip helpers
// ------------------------------
function setSpecChip(tr, kind, detail = "") {
  const chip = tr.querySelector(".spec-chip");
  if (!chip) return;
  chip.classList.remove("chip-api", "chip-est", "chip-manual");
  let label = "Filled from: ";
  if (kind === "api") { chip.classList.add("chip-api"); label += detail || "CarAPI"; }
  else if (kind === "estimate") { chip.classList.add("chip-est"); label += detail || "Estimate"; }
  else if (kind === "manual") { chip.classList.add("chip-manual"); label = "Manual override"; }
  chip.textContent = label;
  chip.style.display = "block";
}
function clearSpecChip(tr) {
  const chip = tr.querySelector(".spec-chip");
  if (chip) chip.style.display = "none";
}
window.onManualOverride = (inp) => {
  const tr = inp.closest("tr");
  setSpecChip(tr, "manual");
};

// ------------------------------
// Row-level event handlers (wired in rowTpl)
// ------------------------------
window.onYearChanged = async (sel) => {
  const tr = sel.closest("tr");
  const year = parseInt(sel.value, 10);
  LAST_YEAR = Number.isFinite(year) ? year : LAST_YEAR;

  const makeSel = tr.querySelector("select.make");
  const modelSel = tr.querySelector("select.model");
  const hIn = tr.querySelector("input.height");
  const wIn = tr.querySelector("input.weight");

  // Clear model + specs on year change
  modelSel.innerHTML = `<option value="">Select model…</option>`;
  hIn.value = ""; wIn.value = ""; clearSpecChip(tr);

  // Abort any in-flight loads and start fresh
  const acMakes = newAbortFor(tr, "makes");
  try { await loadMakes(makeSel, Number.isFinite(year) ? year : null, { signal: acMakes.signal }); }
  catch (e) { if (e.name !== "AbortError") console.warn(e); }

  // If a make is already chosen, reload models with new year filter
  const make = makeSel.value;
  if (make) {
    const acModels = newAbortFor(tr, "models");
    try { await loadModels(modelSel, Number.isFinite(year) ? year : null, make, { signal: acModels.signal }); }
    catch (e) { if (e.name !== "AbortError") console.warn(e); }
  }
};

window.onMakeChanged = async (sel) => {
  const tr = sel.closest("tr");
  const yearSel = tr.querySelector("select.year");
  const modelSel = tr.querySelector("select.model");
  const hIn = tr.querySelector("input.height");
  const wIn = tr.querySelector("input.weight");

  modelSel.innerHTML = `<option value="">Select model…</option>`;
  hIn.value = ""; wIn.value = ""; clearSpecChip(tr);

  const year = parseInt(yearSel.value, 10);
  const make = sel.value;
  if (!make) return;

  const acModels = newAbortFor(tr, "models");
  try { await loadModels(modelSel, Number.isFinite(year) ? year : null, make, { signal: acModels.signal }); }
  catch (e) { if (e.name !== "AbortError") console.warn(e); }
};

window.onModelChanged = async (sel) => {
  const tr = sel.closest("tr");
  const year = parseInt(tr.querySelector("select.year").value, 10);
  const make = tr.querySelector("select.make").value;
  const model = sel.value;
  const hIn = tr.querySelector("input.height");
  const wIn = tr.querySelector("input.weight");
  if (!year || !make || !model) return;

  const acSpecs = newAbortFor(tr, "specs");
  let api = null;
  try {
    api = await autofillSpecs(year, make, model, { signal: acSpecs.signal });
  } catch (e) {
    if (e.name !== "AbortError") console.warn(e);
  }
  if (acSpecs.signal.aborted) return;

  let usedAPI = false, usedEst = false;
  let height = api?.height_ft;
  let weight = api?.weight_lbs;

  if (height == null || weight == null) {
    const est = estimateSpecs(year, make, model);
    if (height == null) { height = est.height_ft; usedEst = true; }
    if (weight == null) { weight = est.weight_lbs; usedEst = true; }
  } else {
    usedAPI = true;
  }

  if (height != null) hIn.value = height;
  if (weight != null) wIn.value = weight;

  if (usedAPI && usedEst) setSpecChip(tr, "api", "CarAPI (with estimate fill)");
  else if (usedAPI) setSpecChip(tr, "api", api?.source || "CarAPI");
  else setSpecChip(tr, "estimate", "Estimate");

  statusEl.textContent = usedAPI
    ? `Filled from ${api?.source || "CarAPI"}${api?.notes ? " (" + api.notes + ")" : ""}`
    : `Filled from Estimate`;
};

// ------------------------------
// Map helpers (Leaflet)
// ------------------------------
let MAP = null, LAYER_PRIMARY = null, LAYER_ALT = null, LAYER_FALLBACK = null, LAST_RESP = null;

function ensureMap() {
  if (MAP) return;
  MAP = L.map("map", { zoomControl: true });
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap",
  }).addTo(MAP);
}

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
    destination: `${dest[0]},${dest[1]}`,
  });
  if (waypoints && waypoints.length) params.set("waypoints", waypoints.join("|"));
  return `https://www.google.com/maps/dir/?${params.toString()}`;
}
function openInGoogleMaps(resp, preferAlt) {
  const path = preferAlt ? resp?.routing?.alternative_path : resp?.routing?.primary_path;
  const cds = getOriginDestCoords(resp, preferAlt);
  if (!cds) { alert("Could not determine origin/destination coordinates for Google Maps."); return; }
  const wpts = sampleWaypoints(path || [], 8);
  const url = buildGmapsUrl(cds.origin, cds.dest, wpts);
  window.open(url, "_blank");
}
function openFallbackInGoogleMaps(resp) {
  const fb = resp?.routing?.fallback;
  const g = resp?.geocoding;
  if (!fb || !fb.used) { alert("No fallback route computed."); return; }
  if (!Array.isArray(g?.origin_coord) || !Array.isArray(fb?.dest)) { alert("Missing fallback endpoints."); return; }
  const origin = g.origin_coord, dest = fb.dest;
  const path = fb.path || [];
  const wpts = sampleWaypoints(path, 8);
  const url = buildGmapsUrl(origin, dest, wpts);
  window.open(url, "_blank");
}

// ------------------------------
// Profile helpers
// ------------------------------
function setProfileInputs(values = DEFAULTS) {
  tractorWeightInput.value = values.truck_weight_lbs;
  trailerWeightInput.value = values.trailer_weight_lbs;
  deckHeightInput.value = values.deck_height_ft;
  axleWeightInput.value = values.weight_per_axle_lbs;
  truckLengthInput.value = values.truck_length_ft;
  truckWidthInput.value = values.truck_width_ft;
}
function getProfileFromInputs() {
  const num = (el, def) => {
    const v = parseFloat(el.value);
    return Number.isFinite(v) ? v : def;
  };
  return {
    truck_weight_lbs: num(tractorWeightInput, DEFAULTS.truck_weight_lbs),
    trailer_weight_lbs: num(trailerWeightInput, DEFAULTS.trailer_weight_lbs),
    deck_height_ft: num(deckHeightInput, DEFAULTS.deck_height_ft),
    truck_length_ft: num(truckLengthInput, DEFAULTS.truck_length_ft),
    truck_width_ft: num(truckWidthInput, DEFAULTS.truck_width_ft),
    weight_per_axle_lbs: num(axleWeightInput, DEFAULTS.weight_per_axle_lbs),
  };
}

// ------------------------------
// Row template (Year → Make → Model) + spec chip
// ------------------------------
function rowTpl(idx, car = {}) {
  const make = car.make || "";
  const model = car.model || "";
  const year = car.year || (LAST_YEAR ?? "");
  const h = car.height_ft ?? "";
  const w = car.weight_lbs ?? "";

  const yearOpts =
    ['<option value="">Select year…</option>']
      .concat(yearsList().map((y) => `<option value="${y}" ${y == year ? "selected" : ""}>${y}</option>`))
      .join("");

  return `
    <tr>
      <td>${idx + 1}</td>

      <td>
        <div class="select-wrap">
          <select class="year select-light" aria-label="Year" onchange="onYearChanged(this)">
            ${yearOpts}
          </select>
        </div>
      </td>

      <td>
        <div class="select-wrap">
          <select class="make select-light" aria-label="Make" onchange="onMakeChanged(this)">
            ${make ? `<option value="${make}" selected>${make}</option>` : `<option value="">Select make…</option>`}
          </select>
        </div>
      </td>

      <td>
        <div class="select-wrap">
          <select class="model select-light" aria-label="Model" onchange="onModelChanged(this)">
            ${model ? `<option value="${model}" selected>${model}</option>` : `<option value="">Select model…</option>`}
          </select>
        </div>
      </td>

      <td>
        <input class="height" type="number" step="0.01" placeholder="Height (ft)" value="${h}" oninput="onManualOverride(this)">
      </td>

      <td>
        <input class="weight" type="number" step="1" placeholder="Weight (lbs)" value="${w}" oninput="onManualOverride(this)">
        <div class="spec-chip small muted" style="display:none; margin-top:4px;"></div>
      </td>

      <td>
        <button class="btn btn-ghost small btn-remove" onclick="removeRow(this)">
          <span class="icon" aria-hidden="true">
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

window.removeRow = (btn) => { btn.closest("tr").remove(); renumber(); };
function renumber() {
  [...carsTbody.querySelectorAll("tr")].forEach((tr, i) => (tr.children[0].textContent = i + 1));
}

function addRow(car) {
  const rows = carsTbody.querySelectorAll("tr").length;
  if (rows >= MAX_ROWS) { alert(`Max ${MAX_ROWS} cars`); return; }
  carsTbody.insertAdjacentHTML("beforeend", rowTpl(rows, car));
  const tr = carsTbody.lastElementChild;

  const yearSel = tr.querySelector("select.year");
  const makeSel = tr.querySelector("select.make");
  const modelSel = tr.querySelector("select.model");

  (async () => {
    // Always load makes (unfiltered) so the user can pick make first if they want.
    const acMakes = newAbortFor(tr, "makes");
    try { await loadMakes(makeSel, null, { signal: acMakes.signal }); }
    catch (e) { if (e.name !== "AbortError") console.warn(e); }

    // If a year is preselected, refresh the makes with that year context (cached hits are instant)
    const yearVal = parseInt(yearSel.value, 10);
    if (Number.isFinite(yearVal)) {
      const acMakes2 = newAbortFor(tr, "makes");
      try { await loadMakes(makeSel, yearVal, { signal: acMakes2.signal }); }
      catch (e) { if (e.name !== "AbortError") console.warn(e); }
    }

    // If row was seeded with a car, restore and load models
    if (car.make) makeSel.value = car.make;

    if (makeSel.value) {
      const acModels = newAbortFor(tr, "models");
      try { await loadModels(modelSel, Number.isFinite(yearVal) ? yearVal : null, makeSel.value, { signal: acModels.signal }); }
      catch (e) { if (e.name !== "AbortError") console.warn(e); }
      if (car.model) modelSel.value = car.model;

      // Autofill specs if we have year+make+model and missing numbers
      if (modelSel.value && (car.height_ft == null || car.weight_lbs == null) && Number.isFinite(yearVal)) {
        const acSpecs = newAbortFor(tr, "specs");
        try {
          const api = await autofillSpecs(yearVal, makeSel.value, modelSel.value, { signal: acSpecs.signal });
          if (!acSpecs.signal.aborted) {
            let usedAPI = false, usedEst = false;
            let height = api?.height_ft, weight = api?.weight_lbs;
            if (height == null || weight == null) {
              const est = estimateSpecs(yearVal, makeSel.value, modelSel.value);
              if (height == null) { height = est.height_ft; usedEst = true; }
              if (weight == null) { weight = est.weight_lbs; usedEst = true; }
            } else usedAPI = true;
            if (height != null) tr.querySelector("input.height").value = height;
            if (weight != null) tr.querySelector("input.weight").value = weight;
            if (usedAPI && usedEst) setSpecChip(tr, "api", "CarAPI (with estimate fill)");
            else if (usedAPI) setSpecChip(tr, "api", api?.source || "CarAPI");
            else setSpecChip(tr, "estimate", "Estimate");
          }
        } catch (e) { if (e.name !== "AbortError") console.warn(e); }
      }
    }
  })();
}

function clearRows() { carsTbody.innerHTML = ""; }

// Reads the table in Year → Make → Model order
function getCarsFromTable() {
  const cars = [];
  [...carsTbody.querySelectorAll("tr")].forEach((tr) => {
    const [idx, yearTd, makeTd, modelTd, hTd, wTd] = tr.children;

    const yearStr = yearTd.querySelector("select.year").value.trim();
    const make = makeTd.querySelector("select.make").value.trim();
    const model = modelTd.querySelector("select.model").value.trim();
    if (!make || !model || !yearStr) return;

    const year = parseInt(yearStr, 10);
    if (!Number.isFinite(year) || year < 1950 || year > new Date().getFullYear() + 1) return;

    const car = { make, model, year };

    const h = parseFloat(hTd.querySelector("input.height").value);
    if (Number.isFinite(h)) car.height_ft = h;
    const w = parseFloat(wTd.querySelector("input.weight").value);
    if (Number.isFinite(w)) car.weight_lbs = w;

    cars.push(car);
  });
  return cars;
}

// ------------------------------
// Render helpers
// ------------------------------
function fmtSecs(s) {
  if (typeof s !== "number") return "n/a";
  const h = Math.floor(s / 3600);
  const m = Math.round((s % 3600) / 60);
  return `${h}h ${m}m`;
}
function m2mi(m) { return m / 1609.34; }

function badge(label, leg) {
  let text = "Unknown";
  let cls = "badge-unknown";
  if (leg && leg.compliant === true) { text = "Legal"; cls = "badge-ok"; }
  else if (leg && leg.compliant === false) { text = "Has restrictions"; cls = "badge-warn"; }
  return `<span class="badge ${cls}">${label}: ${text}</span>`;
}

// Render smarter placement (server-computed loaded heights + orientation)
function renderPlacementAssignmentsFromNewAlgo(placement, carsInput) {
  const srvHeights = placement?.heights_by_deck || {};
  const lowerMaxSlot = placement?.max_loaded?.lower?.slot_id || null;
  const upperMaxSlot = placement?.max_loaded?.upper?.slot_id || null;

  // Deck heights (from smarter algo)
  decksEl.innerHTML = `
    Lower loaded: <strong>${(srvHeights.lower_loaded_ft ?? 0).toFixed(2)} ft</strong><br>
    Upper loaded: <strong>${(srvHeights.upper_loaded_ft ?? 0).toFixed(2)} ft</strong><br>
    Upper deck offset: <span class="muted">per-slot</span>
  `;

  const assigns = Array.isArray(placement?.assignments) ? [...placement.assignments] : [];
  if (!assigns.length) {
    layoutBody.innerHTML = `<tr><td colspan="3" class="muted">No assignments returned.</td></tr>`;
    return;
  }

  // Display by slot label
  assigns.sort((a, b) =>
    String(a.slot_id).localeCompare(String(b.slot_id), undefined, { numeric: true })
  );

  layoutBody.innerHTML = "";
  for (const a of assigns) {
    const car = carsInput.find((c) => `${c.make} ${c.model} ${c.year}` === a.car_id) || {};
    const veh = [car.make, car.model, car.year].filter(Boolean).join(" ") || a.car_id;
    const loaded = typeof a.loaded_ft === "number" ? a.loaded_ft : null;
    const off = typeof a.offset_ft === "number" ? a.offset_ft : null;
    const revPill = a.orientation === "reversed" ? ' <span class="pill">rev</span>' : "";

    const isLower = String(a.slot_id).toUpperCase().startsWith("B");
    const isMaxLower = lowerMaxSlot && a.slot_id === lowerMaxSlot;
    const isMaxTop = upperMaxSlot && a.slot_id === upperMaxSlot;
    const maxBadge = isLower
      ? isMaxLower ? ' <span class="badge badge-warn">MAX LOWER</span>' : ""
      : isMaxTop ? ' <span class="badge badge-warn">MAX TOP</span>' : "";

    const spec = [
      `car h=${car.height_ft ?? "?"} ft`,
      loaded != null ? `→ loaded=${loaded.toFixed(2)} ft` : "",
      maxBadge,
      `· w=${car.weight_lbs ?? "?"} lbs`,
      off != null ? `· offset=${off.toFixed(2)} ft` : "",
      revPill,
    ].filter(Boolean).join(" ");

    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${a.slot_id}</td><td>${veh}</td><td class="muted">${spec}</td>`;
    layoutBody.appendChild(tr);
  }

  // Merge any placement warnings
  const w = placement?.warnings || [];
  if (w.length) {
    const existing = new Set([...warningsEl.querySelectorAll("li")].map((li) => li.textContent));
    w.forEach((msg) => {
      if (!existing.has(msg)) {
        const li = document.createElement("li");
        li.className = "warning";
        li.textContent = msg;
        warningsEl.appendChild(li);
      }
    });
  }
}

// ------------------------------
// Results rendering (maps + summaries)
// ------------------------------
function showResults(resp) {
  LAST_RESP = resp;
  resultsCard.style.display = "block";

  // warnings
  warningsEl.innerHTML = "";
  const warns = resp?.routing?.warnings || [];
  if (warns.length === 0) warningsEl.innerHTML = `<li class="ok">No warnings</li>`;
  else warns.forEach((w) => {
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
    const plusMins = (dMinutes >= 0 ? "+" : "") + Math.round(dMinutes) + " min";
    const primaryLine = `Primary: ${fmtSecs(ps.duration)}, ${m2mi(ps.length).toFixed(1)} mi`;
    const altLine = `Alternative: ${fmtSecs(as.duration)}, ${m2mi(as.length).toFixed(1)} mi`;
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

  badgesEl.innerHTML = [badge("Primary", pl), badge("Alternative", al), badge("Fallback", fl)].join(" ");

  const unknownReasons = [];
  if (pl && pl.compliant === null) unknownReasons.push(`Primary: ${pl.reason || "No reason available."}`);
  if (al && al.compliant === null) unknownReasons.push(`Alternative: ${al.reason || "No reason available."}`);
  if (resp?.routing?.fallback?.used && fl && fl.compliant === null)
    unknownReasons.push(`Fallback: ${fl.reason || "No reason available."}`);
  legNotesEl.innerHTML = unknownReasons.length
    ? `<div class="small muted" style="margin-top:6px">${unknownReasons.join("<br>")}</div>`
    : "";

  // resolved address hint
  const g = resp?.geocoding;
  resolvedEl.textContent =
    g && (g.origin_label || g.destination_label)
      ? `Route: ${g.origin_label || g.origin_input} → ${g.destination_label || g.destination_input}`
      : "";

  // totals sent to HERE
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

  // legacy decks (will be overridden by smarter placement if present)
  const d = resp?.suggestion?.heights_by_deck || {};
  decksEl.innerHTML = `
    Lower loaded: <strong>${d.lower_loaded_ft ?? "?"} ft</strong><br>
    Upper loaded: <strong>${d.upper_loaded_ft ?? "?"} ft</strong><br>
    Upper deck offset: ${d.upper_deck_offset_ft ?? "?"} ft
  `;

  layoutBody.innerHTML = "";
}

// ------------------------------
// Plan button
// ------------------------------
async function plan() {
  try {
    statusEl.textContent = "Planning...";
    const origin = originInput.value.trim();
    const destination = destinationInput.value.trim();
    const cars = getCarsFromTable();
    if (!origin || !destination) { alert("Enter origin and destination (address or lat,lng)."); return; }
    if (cars.length === 0) { alert("Add at least one car."); return; }

    const profile = getProfileFromInputs();

    // 1) Legacy route call (maps + legality + totals)
    const routePayload = {
      truck_weight_lbs: profile.truck_weight_lbs,
      trailer_weight_lbs: profile.trailer_weight_lbs,
      trailer_height_ft: profile.deck_height_ft,
      truck_length_ft: profile.truck_length_ft,
      truck_width_ft: profile.truck_width_ft,
      weight_per_axle_lbs: profile.weight_per_axle_lbs,
      shipped_hazardous_goods: null,
      tunnel_category: null,
      origin, destination, cars,
    };
    const routeRes = await fetch("/plan-route", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(routePayload),
    });
    const routeData = await routeRes.json();
    if (!routeRes.ok || routeData.error) {
      statusEl.textContent = "Error planning route.";
      alert("Server error (plan-route):\n" + JSON.stringify(routeData, null, 2));
      return;
    }

    // 2) New placement call (per-slot offsets + orientation)
    const placementCars = cars.map((c, i) => ({
      id: `${c.make} ${c.model} ${c.year}`,
      length_ft: 15.0,
      width_ft: 6.2,
      height_ft: Number(c.height_ft || 0),
      weight_lbs: Number(c.weight_lbs || 0),
      drop_order: i + 1,
    }));

    let placementData = null;
    try {
      const placementRes = await fetch("/placement-plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          cars: placementCars,
          max_iters: 400,
          deck_height_ft: profile.deck_height_ft,
          slot_offsets_ft: SLOT_OFFSETS_FT,
          orientation_rules: ORIENTATION_RULES,
        }),
      });
      placementData = await placementRes.json();
      if (!placementRes.ok || placementData.error) {
        console.warn("placement-plan error:", placementData);
        placementData = null;
      }
    } catch (e) { console.warn("placement-plan fetch failed:", e); }

    // Render legacy bits
    showResults(routeData);

    // Override layout/decks with smarter placement
    if (placementData && Array.isArray(placementData.assignments)) {
      renderPlacementAssignmentsFromNewAlgo(placementData, cars);
    }

    statusEl.textContent = "Done";
  } catch (e) {
    console.error(e);
    statusEl.textContent = "Failed";
    alert("Failed: " + e.message);
  }
}

// ------------------------------
// Demo & wiring
// ------------------------------
function demoFill() {
  clearRows();
  const demo = [
    { make: "Honda", model: "Civic", year: 2020, height_ft: 4.64, weight_lbs: 2771 },
    { make: "Toyota", model: "Camry", year: 2018, height_ft: 4.74, weight_lbs: 3340 },
    { make: "Tesla", model: "Model 3", year: 2020, height_ft: 4.73, weight_lbs: 4032 },
    { make: "Honda", model: "CR-V", year: 2020, height_ft: 5.54, weight_lbs: 3521 },
    { make: "Toyota", model: "RAV4", year: 2020, height_ft: 5.58, weight_lbs: 3490 },
    { make: "Ford", model: "F-150", year: 2021, height_ft: 6.43, weight_lbs: 4705 },
    { make: "Chevrolet", model: "Tahoe", year: 2020, height_ft: 6.2, weight_lbs: 5602 },
    { make: "Ford", model: "Explorer", year: 2020, height_ft: 5.83, weight_lbs: 4345 },
    { make: "Subaru", model: "Outback", year: 2019, height_ft: 5.54, weight_lbs: 3686 },
  ];
  demo.forEach((car) => addRow(car));
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

// Build info banner (best-effort)
fetch("/static/build.json")
  .then((r) => r.json())
  .then((b) => {
    const el = document.getElementById("buildInfo");
    if (el) el.textContent = `${b.version || ""} ${b.commit ? "(" + b.commit.substring(0, 7) + ")" : ""}`;
  })
  .catch(() => {});

// init
setProfileInputs(DEFAULTS);
addRow({});
addRow({});
addRow({});

// Feedback button
document.getElementById("feedbackBtn").addEventListener("click", () => {
  window.open(FEEDBACK_FORM_URL, "_blank", "noopener");
});
document.getElementById("feedbackFooterLink").addEventListener("click", (e) => {
  e.preventDefault();
  window.open(FEEDBACK_FORM_URL, "_blank", "noopener");
});
