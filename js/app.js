// ===== CONFIG =====
const FUEL_FILES = {
  benzyna: "Benzyna_Eurosuper95_2022-2026.json",
  diesel:  "Olej_Napedowy_Ekodiesel_2022-2026.json",
};

const FUEL_LABELS = {
  benzyna: "Benzyna Eurosuper 95",
  diesel: "Olej Napedowy Ekodiesel"
};

const PERIOD_CONFIG = {
  dd: { label: "D/D", days: 1,  zlCol: "ZMIANA D/D (zl)", pctCol: "ZMIANA D/D (%)", barTitle: "ZMIAN DZIENNYCH" },
  ww: { label: "T/T", days: 7,  zlCol: "ZMIANA T/T (zl)", pctCol: "ZMIANA T/T (%)", barTitle: "ZMIAN TYGODNIOWYCH" },
  mm: { label: "M/M", days: 30, zlCol: "ZMIANA M/M (zl)", pctCol: "ZMIANA M/M (%)", barTitle: "ZMIAN MIESIĘCZNYCH" },
};

// ===== STATE =====
let currentFuel = "benzyna";
let currentPeriod = "dd";
let rows = [];
let rowsDesc = [];
let filtered = [];
let chartReady = false;

// ===== DOM =====
const els = {
  tbody:        document.getElementById("tbody"),
  searchInput:  document.getElementById("searchInput"),
  hiAlert:      document.getElementById("hiAlert"),
  modal:        document.getElementById("modal"),
  btnClose:     document.getElementById("btnClose"),
  btnShowAll:   document.getElementById("btnShowAll"),
  barModal:     document.getElementById("barModal"),
  barBtnClose:  document.getElementById("barBtnClose"),
  barBtnShowAll:document.getElementById("barBtnShowAll"),
  fuelTabs:     document.getElementById("fuelTabs"),
  periodTabs:   document.getElementById("periodTabs"),
  thChangeZl:   document.getElementById("thChangeZl"),
  thChangePct:  document.getElementById("thChangePct"),
};

// ===== HELPERS =====
function parseDateDDMMYYYY(s){
  const t = (s || "").trim();
  const m = t.match(/^(\d{2})-(\d{2})-(\d{4})$/);
  if(!m) return null;
  const [_, dd, mm, yyyy] = m;
  return new Date(Date.UTC(+yyyy, +mm - 1, +dd));
}

function fmtPriceThousands(plnPerM3){
  return (plnPerM3 / 1000).toFixed(3);
}

/**
 * Compute changes for a given lookback period.
 * D/D (days=1): previous entry in the dataset.
 * T/T (days=7): nearest entry to 7 calendar days ago.
 * M/M (days=30): nearest entry to 30 calendar days ago.
 */
function computeChanges(rowsAsc, periodDays){
  const DAY_MS = 24 * 3600 * 1000;
  for (let i = 0; i < rowsAsc.length; i++){
    const cur = rowsAsc[i];

    if(periodDays === 1){
      const prev = rowsAsc[i - 1];
      if(!prev){
        cur.changeAbs = null;
        cur.changePct = null;
        cur.changeRef = null;
        continue;
      }
      const diff = cur.price - prev.price;
      cur.changeAbs = diff;
      cur.changePct = prev.price === 0 ? null : (diff / prev.price) * 100;
      cur.changeRef = prev.dateStr;
    } else {
      const targetTime = cur.date.getTime() - periodDays * DAY_MS;
      let best = null;
      let bestDist = Infinity;

      for (let j = i - 1; j >= 0; j--){
        const dist = Math.abs(rowsAsc[j].date.getTime() - targetTime);
        if(dist < bestDist){
          bestDist = dist;
          best = rowsAsc[j];
        }
        if(rowsAsc[j].date.getTime() < targetTime - 10 * DAY_MS) break;
      }

      const minDays = Math.floor(periodDays * 0.5);
      const actualDays = best ? Math.round((cur.date - best.date) / DAY_MS) : 0;

      if(!best || actualDays < minDays){
        cur.changeAbs = null;
        cur.changePct = null;
        cur.changeRef = null;
        continue;
      }

      const diff = cur.price - best.price;
      cur.changeAbs = diff;
      cur.changePct = best.price === 0 ? null : (diff / best.price) * 100;
      cur.changeRef = best.dateStr;
    }
  }
  return rowsAsc;
}

function bestHighSinceMessage(rowsAsc){
  const last = rowsAsc[rowsAsc.length - 1];
  if(!last) return null;

  let maxSoFar = -Infinity;
  for (const r of rowsAsc) maxSoFar = Math.max(maxSoFar, r.price);

  if (last.price >= maxSoFar){
    return `ALERT: [${FUEL_LABELS[currentFuel]}] CENA ${fmtPriceThousands(last.price)} tys. PLN/m3 — NAJWYŻSZA W HISTORII (od ${rowsAsc[0].dateStr}).`;
  }

  let lastHigherDate = null;
  for (let i = rowsAsc.length - 1; i >= 0; i--){
    if (rowsAsc[i].price > last.price){
      lastHigherDate = rowsAsc[i].dateStr;
      break;
    }
  }
  return `ALERT: [${FUEL_LABELS[currentFuel]}] CENA ${fmtPriceThousands(last.price)} tys. PLN/m3 — NAJWYŻSZA OD ${lastHigherDate}.`;
}

function setAlert(msg){
  if(!msg){ els.hiAlert.style.display = "none"; return; }
  els.hiAlert.textContent = msg;
  els.hiAlert.style.display = "block";
}

function signClass(n){
  if(n == null) return "muted";
  return n >= 0 ? "pos" : "neg";
}

function formatZl(n){
  if(n == null) return "\u2014";
  const abs = Math.abs(n);
  return `${n>=0?"+":"\u2212"}${abs.toFixed(0)} zl`;
}

function formatPct(n){
  if(n == null) return "\u2014";
  const v = Math.abs(n).toFixed(2);
  return `${n>=0?"+":"\u2212"}${v}%`;
}

// ===== UPDATE COLUMN HEADERS =====
function updateHeaders(){
  const cfg = PERIOD_CONFIG[currentPeriod];
  els.thChangeZl.textContent  = cfg.zlCol;
  els.thChangePct.textContent = cfg.pctCol;
}

// ===== RENDER TABLE =====
function renderTable(dataDesc){
  els.tbody.innerHTML = "";
  dataDesc.forEach((r, idx) => {
    const tr = document.createElement("tr");
    const refHint = r.changeRef ? ` title="vs ${r.changeRef}"` : "";

    let flag = "";
    if(idx === 0){
      flag = currentPeriod === "dd"
        ? `<span class="tag">DZISIAJ</span>`
        : `<span class="tag">OSTATNI</span>`;
    }

    tr.innerHTML = `
      <td class="num muted">${idx + 1}</td>
      <td>${r.dateStr}</td>
      <td class="num">${fmtPriceThousands(r.price)}</td>
      <td class="num ${signClass(r.changeAbs)}"${refHint}>${formatZl(r.changeAbs)}</td>
      <td class="num ${signClass(r.changePct)}"${refHint}>${formatPct(r.changePct)}</td>
      <td>${flag}</td>
    `;

    tr.addEventListener("click", () => openChartAtDate(r.dateStr));
    els.tbody.appendChild(tr);
  });
}

function applyFilter(){
  const q = els.searchInput.value.trim().toLowerCase();
  if(!q){
    filtered = rowsDesc.slice();
  } else {
    filtered = rowsDesc.filter(r => {
      const hay = `${r.dateStr} ${fmtPriceThousands(r.price)} ${r.price} ${r.changeAbs ?? ""} ${r.changePct ?? ""}`.toLowerCase();
      return hay.includes(q);
    });
  }
  renderTable(filtered);
}

/**
 * Sample rows for weekly/monthly view.
 * T/T: one row per ISO week (last entry of each week).
 * M/M: one row per calendar month (last entry of each month).
 * D/D: all rows.
 */
function sampleRows(rowsAsc, period){
  if(period === "dd") return rowsAsc.slice();

  const sampled = [];
  const keyFn = period === "ww"
    ? (d) => {
        // ISO week: year + week number
        const tmp = new Date(d.getTime());
        tmp.setUTCDate(tmp.getUTCDate() + 4 - (tmp.getUTCDay() || 7));
        const yearStart = new Date(Date.UTC(tmp.getUTCFullYear(), 0, 1));
        const weekNo = Math.ceil(((tmp - yearStart) / 86400000 + 1) / 7);
        return `${tmp.getUTCFullYear()}-W${String(weekNo).padStart(2,"0")}`;
      }
    : (d) => {
        // Month: year-month
        return `${d.getUTCFullYear()}-${String(d.getUTCMonth()+1).padStart(2,"0")}`;
      };

  let lastKey = null;
  let lastRow = null;

  for(const r of rowsAsc){
    const key = keyFn(r.date);
    if(key !== lastKey){
      if(lastRow) sampled.push(lastRow);
      lastKey = key;
    }
    lastRow = r;
  }
  if(lastRow) sampled.push(lastRow); // push final period's last entry
  return sampled;
}

let displayRows = []; // sampled rows for table & bar chart

function recomputeAndRender(){
  const cfg = PERIOD_CONFIG[currentPeriod];

  // First compute changes on ALL daily rows
  computeChanges(rows, cfg.days);

  // Then sample for display
  displayRows = sampleRows(rows, currentPeriod);
  rowsDesc = displayRows.slice().sort((a,b) => b.date - a.date);

  updateHeaders();
  applyFilter();
}

// ===== LOAD DATA =====
async function loadJSON(path){
  const res = await fetch(path, { cache: "no-store" });
  if(!res.ok) throw new Error(`JSON: ${res.status} ${res.statusText}`);
  const data = await res.json();
  const out = [];
  for (const r of data){
    const dateStr = (r.data_zmiany || r.date || r.DATA || "").trim();
    const price = Number(r.cena_pln_m3 ?? r.price ?? r.CLOSE ?? r.cena);
    const date = parseDateDDMMYYYY(dateStr);
    if(!dateStr || !Number.isFinite(price) || !date) continue;
    out.push({ dateStr, date, price });
  }
  return out;
}

async function loadData(){
  setAlert(null);
  els.tbody.innerHTML = `<tr><td class="muted" colspan="6">Ładowanie danych...</td></tr>`;

  const file = FUEL_FILES[currentFuel];
  const url = `${file}?v=${Date.now()}`;

  let raw = await loadJSON(url);
  raw.sort((a,b) => a.date - b.date);
  rows = raw;

  recomputeAndRender();
  setAlert(bestHighSinceMessage(rows));
  chartReady = false;
}

// ===== VIEW MODE: data / analiza / stopy =====
const dataPanel = document.getElementById("dataPanel");
const analizaPanel = document.getElementById("analizaPanel");
const stopyPanel = document.getElementById("stopyPanel");
const checkPanel = document.getElementById("checkPanel");
let viewMode = "data"; // "data" | "analiza" | "stopy" | "check"

function setViewMode(mode){
  viewMode = mode;
  dataPanel.classList.toggle("hidden", mode !== "data");
  analizaPanel.classList.toggle("visible", mode === "analiza");
  stopyPanel.classList.toggle("visible", mode === "stopy");
  checkPanel.classList.toggle("visible", mode === "check");
  if(mode === "analiza") loadAnalytics();
  if(mode === "stopy") loadStopy();
  if(mode === "check") loadCheck();
}

// ===== FUEL TAB SWITCHING =====
els.fuelTabs.addEventListener("click", (e) => {
  const tab = e.target.closest(".fuel-tab");
  if(!tab) return;
  const fuel = tab.dataset.fuel;

  els.fuelTabs.querySelectorAll(".fuel-tab").forEach(t => t.classList.remove("active"));
  tab.classList.add("active");

  if(fuel === "analiza" || fuel === "stopy" || fuel === "check"){
    setViewMode(fuel);
    return;
  }

  if(viewMode !== "data") setViewMode("data");
  if(fuel !== currentFuel){
    currentFuel = fuel;
    els.searchInput.value = "";
    loadData();
  }
});

// ===== ANALYTICS =====
const CPI_FILE = "CPI_Inflacja_PL_2022-2026.json";
let cpiData = null;
let allFuelData = {};
let currentAnaFuel = "benzyna";

async function loadCPI(){
  if(cpiData) return cpiData;
  const res = await fetch(CPI_FILE + "?v=" + Date.now(), { cache: "no-store" });
  const data = await res.json();
  cpiData = data.map(r => {
    const parts = r.data.split("-");
    return {
      date: new Date(Date.UTC(+parts[2], +parts[1]-1, +parts[0])),
      cpi: r.cpi_rr_pct
    };
  });
  return cpiData;
}

async function loadFuelForAnalysis(fuelKey){
  if(allFuelData[fuelKey]) return allFuelData[fuelKey];
  const file = FUEL_FILES[fuelKey];
  const res = await fetch(file + "?v=" + Date.now(), { cache: "no-store" });
  const data = await res.json();
  const out = [];
  for(const r of data){
    const dateStr = (r.data_zmiany || "").trim();
    const price = Number(r.cena_pln_m3);
    const date = parseDateDDMMYYYY(dateStr);
    if(dateStr && Number.isFinite(price) && date) out.push({ dateStr, date, price });
  }
  out.sort((a,b) => a.date - b.date);
  allFuelData[fuelKey] = out;
  return out;
}

function calcStats(prices){
  const n = prices.length;
  const sorted = [...prices].sort((a,b) => a - b);
  const sum = prices.reduce((a,b) => a+b, 0);
  const mean = sum / n;
  const variance = prices.reduce((a,v) => a + (v - mean)**2, 0) / n;
  const std = Math.sqrt(variance);
  const median = n % 2 === 0
    ? (sorted[n/2-1] + sorted[n/2]) / 2
    : sorted[Math.floor(n/2)];
  const p5 = sorted[Math.floor(n * 0.05)];
  const p25 = sorted[Math.floor(n * 0.25)];
  const p75 = sorted[Math.floor(n * 0.75)];
  const p95 = sorted[Math.floor(n * 0.95)];
  return {
    n, mean, median, std, min: sorted[0], max: sorted[n-1],
    p5, p25, p75, p95,
    current: prices[prices.length - 1]
  };
}

function renderStats(fuelKey, fuelRows){
  const grid = document.getElementById("statsGrid");
  const prices = fuelRows.map(r => r.price);
  const s = calcStats(prices);
  const label = FUEL_LABELS[fuelKey] || fuelKey;
  const pctFromMean = ((s.current - s.mean) / s.mean * 100).toFixed(1);
  const pctSign = pctFromMean >= 0 ? "+" : "";

  grid.innerHTML = `
    <div class="stat-card">
      <div class="label">Aktualna cena</div>
      <div class="value">${(s.current/1000).toFixed(3)}</div>
      <div class="sub">tys. PLN/m3 | ${pctSign}${pctFromMean}% vs srednia</div>
    </div>
    <div class="stat-card">
      <div class="label">Srednia</div>
      <div class="value">${(s.mean/1000).toFixed(3)}</div>
      <div class="sub">z ${s.n} obserwacji</div>
    </div>
    <div class="stat-card">
      <div class="label">Mediana</div>
      <div class="value">${(s.median/1000).toFixed(3)}</div>
      <div class="sub">wartość środkowa</div>
    </div>
    <div class="stat-card">
      <div class="label">Odch. std.</div>
      <div class="value">${(s.std/1000).toFixed(3)}</div>
      <div class="sub">${((s.std/s.mean)*100).toFixed(1)}% współczynnik zmienności</div>
    </div>
    <div class="stat-card">
      <div class="label">Minimum</div>
      <div class="value" style="color:var(--green)">${(s.min/1000).toFixed(3)}</div>
      <div class="sub">najniższa cena w historii</div>
    </div>
    <div class="stat-card">
      <div class="label">Maksimum</div>
      <div class="value" style="color:var(--red)">${(s.max/1000).toFixed(3)}</div>
      <div class="sub">najwyższa cena w historii</div>
    </div>
    <div class="stat-card">
      <div class="label">Percentyl 5%</div>
      <div class="value">${(s.p5/1000).toFixed(3)}</div>
      <div class="sub">tanio — 5% czasu poniżej</div>
    </div>
    <div class="stat-card">
      <div class="label">Percentyl 95%</div>
      <div class="value">${(s.p95/1000).toFixed(3)}</div>
      <div class="sub">drogo — 5% czasu powyżej</div>
    </div>
  `;
}

function drawCpiChart(fuelKey, fuelRows, cpi, offsetMonths){
  offsetMonths = offsetMonths || 0;
  const fLabel = FUEL_LABELS[fuelKey] || fuelKey;
  const fColor = fuelKey === "benzyna" ? "#ff4b4b" : "#ffcc66";

  // Shift CPI dates by offset months
  const shiftedCpi = cpi.map(r => {
    const d = new Date(r.date);
    d.setUTCMonth(d.getUTCMonth() + offsetMonths);
    return { date: d, cpi: r.cpi };
  });

  const offsetLabel = offsetMonths === 0 ? "" :
    (offsetMonths > 0 ? ` [+${offsetMonths} mies.]` : ` [${offsetMonths} mies.]`);

  const traces = [{
    x: fuelRows.map(r => new Date(r.date)),
    y: fuelRows.map(r => r.price / 1000),
    type: "scatter", mode: "lines",
    name: fLabel + " (tys. PLN/m3)",
    line: { width: 2, color: fColor },
    yaxis: "y",
    hovertemplate: "%{x|%m/%Y}<br><b>%{y:.3f} tys.</b><extra>" + fLabel + "</extra>"
  }, {
    x: shiftedCpi.map(r => new Date(r.date)),
    y: shiftedCpi.map(r => r.cpi),
    type: "scatter", mode: "lines+markers",
    name: "CPI r/r (%)" + offsetLabel,
    line: { width: 2.5, color: "#7b61ff", dash: "dot" },
    marker: { size: 5, color: "#7b61ff" },
    yaxis: "y2",
    hovertemplate: "%{x|%m/%Y}<br><b>%{y:.1f}%</b><extra>CPI</extra>"
  }];

  // If 'oba': PB95 (red) first, then Ekodiesel (yellow), then CPI
  if(fuelKey === "oba" && allFuelData.diesel){
    traces[0].name = "Benzyna 95 (tys. PLN/m3)";
    traces[0].line.color = "#ff4b4b";
    traces.splice(1, 0, {
      x: allFuelData.diesel.map(r => new Date(r.date)),
      y: allFuelData.diesel.map(r => r.price / 1000),
      type: "scatter", mode: "lines",
      name: "Ekodiesel (tys. PLN/m3)",
      line: { width: 2, color: "#ffcc66" },
      yaxis: "y",
      hovertemplate: "%{x|%m/%Y}<br><b>%{y:.3f} tys.</b><extra>Ekodiesel</extra>"
    });
  }

  const titleFuel = fuelKey === "oba" ? "Benzyna 95 + Ekodiesel" : fLabel;

  const layout = {
    title: {
      text: titleFuel + " vs Inflacja CPI r/r" + offsetLabel,
      font: { color: "rgba(255,255,255,.85)", size: 14, family: "monospace" },
      x: 0.01, xanchor: "left"
    },
    paper_bgcolor: "#070c12", plot_bgcolor: "#0a0f16",
    margin: { l: 70, r: 70, t: 45, b: 50 },
    xaxis: {
      showgrid: true, gridcolor: "rgba(255,255,255,.06)",
      tickfont: { color: "rgba(255,255,255,.6)" }
    },
    yaxis: {
      title: { text: "Cena (tys. PLN/m3)", font: { color: fuelKey === "oba" ? "#ff4b4b" : fColor } },
      showgrid: true, gridcolor: "rgba(255,255,255,.06)",
      tickfont: { color: "rgba(255,255,255,.6)" },
      side: "left"
    },
    yaxis2: {
      title: { text: "CPI r/r (%)", font: { color: "#7b61ff" } },
      tickfont: { color: "rgba(255,255,255,.6)" },
      overlaying: "y", side: "right",
      showgrid: false
    },
    font: { color: "rgba(255,255,255,.7)" },
    legend: { x: 0.01, y: -0.18, orientation: "h", font: { size: 11 } },
    hovermode: "x unified",
    showlegend: true,
    annotations: [{
      text: "Opracowanie własne | dane: Orlen, GUS",
      showarrow: false, xref: "paper", yref: "paper",
      x: 1, y: -0.22, xanchor: "right", yanchor: "top",
      font: { size: 10, color: "rgba(255,255,255,.3)", family: "monospace" }
    }]
  };

  Plotly.newPlot("cpiChartBox", traces, layout, { responsive: true, displayModeBar: true,
    toImageButtonOptions: { format: "png", width: 1400, height: 600, filename: "paliwa_vs_inflacja" }
  });
}

function drawHistogram(fuelKey, fuelRows){
  const fLabel = FUEL_LABELS[fuelKey] || fuelKey;
  const fColor = fuelKey === "benzyna" ? "#ff4b4b" : fuelKey === "diesel" ? "#ffcc66" : "#ff4b4b";
  const prices = fuelRows.map(r => r.price / 1000);

  const traces = [{
    x: prices,
    type: "histogram",
    nbinsx: 40,
    marker: { color: fColor.replace(")", ",.6)").replace("rgb","rgba").replace("#",""), line: { color: fColor, width: 1 } },
    name: fLabel,
    opacity: 0.75,
    hovertemplate: "Cena: %{x:.3f}<br>Liczba dni: %{y}<extra></extra>"
  }];

  // Fix color for histogram
  traces[0].marker = {
    color: fuelKey === "benzyna" ? "rgba(255,75,75,.55)" : "rgba(255,204,102,.55)",
    line: { color: fColor, width: 1 }
  };

  if(fuelKey === "oba" && allFuelData.diesel){
    const dPrices = allFuelData.diesel.map(r => r.price / 1000);
    traces[0].name = "Benzyna 95";
    traces[0].marker = { color: "rgba(255,75,75,.5)", line: { color: "#ff4b4b", width: 1 } };
    traces.push({
      x: dPrices,
      type: "histogram",
      nbinsx: 40,
      marker: { color: "rgba(255,204,102,.5)", line: { color: "#ffcc66", width: 1 } },
      name: "Ekodiesel",
      opacity: 0.7
    });
  }

  // Add current price vertical line
  const current = prices[prices.length - 1];

  const layout = {
    title: {
      text: "Rozkład cen — " + (fuelKey === "oba" ? "Benzyna 95 + Ekodiesel" : fLabel),
      font: { color: "rgba(255,255,255,.85)", size: 14, family: "monospace" },
      x: 0.01, xanchor: "left"
    },
    paper_bgcolor: "#070c12", plot_bgcolor: "#0a0f16",
    margin: { l: 60, r: 40, t: 45, b: 50 },
    xaxis: {
      title: { text: "Cena (tys. PLN/m3)", font: { color: "rgba(255,255,255,.6)" } },
      showgrid: true, gridcolor: "rgba(255,255,255,.06)",
      tickfont: { color: "rgba(255,255,255,.6)" }
    },
    yaxis: {
      title: { text: "Liczba dni", font: { color: "rgba(255,255,255,.6)" } },
      showgrid: true, gridcolor: "rgba(255,255,255,.06)",
      tickfont: { color: "rgba(255,255,255,.6)" }
    },
    font: { color: "rgba(255,255,255,.7)" },
    barmode: fuelKey === "oba" ? "overlay" : "stack",
    showlegend: fuelKey === "oba",
    legend: { x: 0.01, y: -0.18, orientation: "h", font: { size: 11 } },
    shapes: [{
      type: "line",
      x0: current, x1: current, y0: 0, y1: 1,
      xref: "x", yref: "paper",
      line: { color: "#34ff9a", width: 2, dash: "dash" }
    }],
    annotations: [{
      x: current, y: 1, xref: "x", yref: "paper",
      text: "TERAZ: " + current.toFixed(3),
      showarrow: true, arrowhead: 0, ax: 40, ay: -25,
      font: { color: "#34ff9a", size: 11, family: "monospace" },
      bgcolor: "rgba(0,0,0,.6)", borderpad: 4
    }]
  };

  Plotly.newPlot("histChartBox", traces, layout, { responsive: true, displayModeBar: true,
    toImageButtonOptions: { format: "png", width: 1200, height: 500, filename: "rozklad_cen_paliw" }
  });
}

async function loadAnalytics(){
  const [cpi, pb95, diesel] = await Promise.all([
    loadCPI(),
    loadFuelForAnalysis("benzyna"),
    loadFuelForAnalysis("diesel"),
  ]);

  renderAnalytics();
}

function getCpiOffset(){
  return parseInt(document.getElementById("cpiOffset").value) || 0;
}

function updateOffsetLabel(){
  const v = getCpiOffset();
  const label = v === 0 ? "0 mies." : (v > 0 ? `+${v} mies.` : `${v} mies.`);
  document.getElementById("cpiOffsetLabel").textContent = label;
}

function renderAnalytics(){
  const fuel = currentAnaFuel;
  const offset = getCpiOffset();

  if(fuel === "oba"){
    renderStats("benzyna", allFuelData.benzyna);
    drawCpiChart("oba", allFuelData.benzyna, cpiData, offset);
    drawHistogram("oba", allFuelData.benzyna);
  } else {
    renderStats(fuel, allFuelData[fuel]);
    drawCpiChart(fuel, allFuelData[fuel], cpiData, offset);
    drawHistogram(fuel, allFuelData[fuel]);
  }
  updateCorrDisplay();
}

/**
 * Pearson correlation between fuel prices and CPI at a given month offset.
 * Resamples fuel data to monthly (avg per month) to match CPI granularity.
 */
function calcCorrelation(fuelRows, cpi, offsetMonths){
  // Resample fuel to monthly averages
  const monthMap = {};
  for(const r of fuelRows){
    const key = r.date.getUTCFullYear() + "-" + String(r.date.getUTCMonth()+1).padStart(2,"0");
    if(!monthMap[key]) monthMap[key] = [];
    monthMap[key].push(r.price);
  }
  const fuelMonthly = {};
  for(const [k,v] of Object.entries(monthMap)){
    fuelMonthly[k] = v.reduce((a,b) => a+b, 0) / v.length;
  }

  // Build paired arrays: fuel month <-> CPI month+offset
  const pairs = [];
  for(const c of cpi){
    const shifted = new Date(c.date);
    shifted.setUTCMonth(shifted.getUTCMonth() + offsetMonths);
    const key = shifted.getUTCFullYear() + "-" + String(shifted.getUTCMonth()+1).padStart(2,"0");
    if(fuelMonthly[key] !== undefined){
      pairs.push({ fuel: fuelMonthly[key] / 1000, cpi: c.cpi });
    }
  }

  if(pairs.length < 4) return null;

  const n = pairs.length;
  const sumX = pairs.reduce((a,p) => a + p.fuel, 0);
  const sumY = pairs.reduce((a,p) => a + p.cpi, 0);
  const sumXY = pairs.reduce((a,p) => a + p.fuel * p.cpi, 0);
  const sumX2 = pairs.reduce((a,p) => a + p.fuel * p.fuel, 0);
  const sumY2 = pairs.reduce((a,p) => a + p.cpi * p.cpi, 0);

  const num = n * sumXY - sumX * sumY;
  const den = Math.sqrt((n * sumX2 - sumX*sumX) * (n * sumY2 - sumY*sumY));

  if(den === 0) return null;
  const r = num / den;
  return { r, r2: r*r, n: pairs.length };
}

function updateCorrDisplay(){
  const fuel = currentAnaFuel;
  const offset = getCpiOffset();
  const fuelRows = fuel === "oba" ? allFuelData.benzyna : allFuelData[fuel];
  const corr = calcCorrelation(fuelRows, cpiData, offset);
  const el = document.getElementById("corrDisplay");

  if(!corr){
    el.textContent = "";
    return;
  }

  const rColor = corr.r > 0.6 ? "var(--green)" : corr.r > 0.3 ? "var(--amber)" : corr.r > 0 ? "var(--muted)" : "var(--red)";
  const strength = Math.abs(corr.r) > 0.8 ? "bardzo silna" :
                   Math.abs(corr.r) > 0.6 ? "silna" :
                   Math.abs(corr.r) > 0.4 ? "umiarkowana" :
                   Math.abs(corr.r) > 0.2 ? "słaba" : "brak";

  el.innerHTML = `Pearson r = <span style="color:${rColor}; font-size:15px;">${corr.r.toFixed(3)}</span>`
    + ` &nbsp; R\u00B2 = <span style="color:${rColor};">${corr.r2.toFixed(3)}</span>`
    + ` &nbsp; <span style="color:var(--muted); font-weight:400;">(${strength} korelacja, n=${corr.n} miesiecy)</span>`;
}

function findBestOffset(){
  const fuel = currentAnaFuel;
  const fuelRows = fuel === "oba" ? allFuelData.benzyna : allFuelData[fuel];

  let bestOffset = 0;
  let bestR2 = -1;
  for(let off = -12; off <= 12; off++){
    const corr = calcCorrelation(fuelRows, cpiData, off);
    if(corr && corr.r2 > bestR2){
      bestR2 = corr.r2;
      bestOffset = off;
    }
  }
  return bestOffset;
}

function redrawCpiOnly(){
  const fuel = currentAnaFuel;
  const offset = getCpiOffset();
  const fuelRows = fuel === "oba" ? allFuelData.benzyna : allFuelData[fuel];
  drawCpiChart(fuel, fuelRows, cpiData, offset);
  updateCorrDisplay();
}

// Analiza fuel sub-select
document.getElementById("anaFuelSelect").addEventListener("click", (e) => {
  const btn = e.target.closest(".ana-fuel-btn");
  if(!btn) return;
  currentAnaFuel = btn.dataset.anafuel;
  document.querySelectorAll(".ana-fuel-btn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  renderAnalytics();
});

// CPI offset slider
document.getElementById("cpiOffset").addEventListener("input", () => {
  updateOffsetLabel();
  redrawCpiOnly();
});

// Auto-find best offset
document.getElementById("btnAutoOffset").addEventListener("click", () => {
  const best = findBestOffset();
  document.getElementById("cpiOffset").value = best;
  updateOffsetLabel();
  redrawCpiOnly();
});

// ===== PERIOD TAB SWITCHING =====
els.periodTabs.addEventListener("click", (e) => {
  const tab = e.target.closest(".period-tab");
  if(!tab || tab.dataset.period === currentPeriod) return;
  currentPeriod = tab.dataset.period;
  els.periodTabs.querySelectorAll(".period-tab").forEach(t => t.classList.remove("active"));
  tab.classList.add("active");
  recomputeAndRender();
});

// ===== SHARED: auto-scale Y on X range change =====
function attachYAutoScale(divId, dataSource, valueGetter){
  function yRangeFor(xFrom, xTo){
    const fromT = xFrom.getTime(), toT = xTo.getTime();
    const visible = dataSource.filter(r => {
      const t = r.date.getTime();
      return t >= fromT && t <= toT;
    });
    if(!visible.length) return null;
    const vals = visible.map(r => valueGetter(r)).filter(v => v != null);
    if(!vals.length) return null;
    const mn = Math.min(...vals);
    const mx = Math.max(...vals);
    const span = mx - mn;
    const margin = span * 0.12 || (Math.max(Math.abs(mx), Math.abs(mn)) * 0.15) || 0.5;
    return [mn - margin, mx + margin];
  }

  const div = document.getElementById(divId);
  div.on("plotly_relayout", (ev) => {
    const hasX = ev["xaxis.range[0]"] !== undefined
              || ev["xaxis.range"] !== undefined
              || ev["xaxis.autorange"] !== undefined;
    if(!hasX) return;

    let x0, x1;
    if(ev["xaxis.range[0]"] !== undefined){
      x0 = new Date(ev["xaxis.range[0]"]);
      x1 = new Date(ev["xaxis.range[1]"]);
    } else if(ev["xaxis.range"]){
      x0 = new Date(ev["xaxis.range"][0]);
      x1 = new Date(ev["xaxis.range"][1]);
    }

    if(x0 && x1){
      const r = yRangeFor(x0, x1);
      if(r) Plotly.relayout(divId, { "yaxis.range": r, "yaxis.autorange": false });
    } else {
      Plotly.relayout(divId, { "yaxis.autorange": true });
    }
  });
}

// ===== PRICE LINE CHART =====
function openModal(){ els.modal.style.display = "flex"; }
function closeModal(){ els.modal.style.display = "none"; }

function openChartAtDate(dateStr){
  if(!rows.length) return;
  const picked = rows.find(r => r.dateStr === dateStr) || rows[rows.length-1];
  openModal();
  drawChart(picked);
}

function drawChart(picked){
  const x = rows.map(r => new Date(r.date.getTime()));
  const y = rows.map(r => r.price / 1000);

  const pickedIndex = rows.findIndex(r => r.dateStr === picked.dateStr);
  const pickedX = x[Math.max(0, pickedIndex)];
  const pickedY = y[Math.max(0, pickedIndex)];

  const fuelLabel = FUEL_LABELS[currentFuel];
  const chartTitleText = `${fuelLabel} \u2014 ${picked.dateStr} | ${fmtPriceThousands(picked.price)} tys. PLN/m3`;

  const lineColor = currentFuel === "benzyna" ? "#ff4b4b" : "#ffcc66";
  const markerColor = currentFuel === "benzyna" ? "#ff8888" : "#ffdd88";

  const trace = {
    x, y,
    type: "scatter", mode: "lines",
    line: { width: 2, color: lineColor },
    hovertemplate: "%{x|%d-%m-%Y}<br><b>%{y:.3f} tys. PLN/m3</b><extra></extra>"
  };

  const marker = {
    x: [pickedX], y: [pickedY],
    type: "scatter", mode: "markers",
    marker: { size: 10, color: markerColor },
    hovertemplate: "<b>Wybrana sesja</b><br>%{x|%d-%m-%Y}<br>%{y:.3f} tys. PLN/m3<extra></extra>"
  };

  const layout = {
    title: {
      text: chartTitleText,
      font: { color: "rgba(255,255,255,.90)", size: 14, family: "monospace" },
      x: 0.01, xanchor: "left"
    },
    paper_bgcolor: "#070c12",
    plot_bgcolor: "#0a0f16",
    margin: { l: 70, r: 40, t: 45, b: 50 },
    xaxis: {
      showgrid: true, gridcolor: "rgba(255,255,255,.08)",
      rangeslider: { visible: true, thickness: 0.08 },
      tickfont: { color: "rgba(255,255,255,.70)" },
      title: { text: "Data", font: { color: "rgba(255,255,255,.70)" } },
      showspikes: true, spikemode: "across", spikesnap: "cursor",
      spikecolor: "rgba(255,255,255,.35)", spikethickness: 1
    },
    yaxis: {
      showgrid: true, gridcolor: "rgba(255,255,255,.08)",
      tickfont: { color: "rgba(255,255,255,.70)" },
      title: { text: "Cena (tys. PLN/m3)", font: { color: "rgba(255,255,255,.70)" } },
      showspikes: true, spikemode: "across", spikesnap: "cursor",
      spikecolor: "rgba(255,255,255,.35)", spikethickness: 1,
      autorange: true, rangemode: "normal"
    },
    font: { color: "rgba(255,255,255,.80)" },
    dragmode: "zoom",
    hovermode: "closest",
    showlegend: false,
    annotations: [{
      text: "Opracowanie w\u0142asne na podstawie danych Orlen",
      showarrow: false,
      xref: "paper", yref: "paper",
      x: 1, y: -0.15,
      xanchor: "right", yanchor: "top",
      font: { size: 11, color: "rgba(255,255,255,.40)", family: "monospace" }
    }]
  };

  Plotly.newPlot("chart", [trace, marker], layout, {
    responsive: true, scrollZoom: true, displayModeBar: true,
    toImageButtonOptions: { format: "png", width: 1400, height: 700, filename: chartTitleText.replace(/[^a-zA-Z0-9_\-]/g, "_") }
  }).then(() => {
    chartReady = true;
    attachYAutoScale("chart", rows, r => r.price / 1000);
  });
}

// ===== BAR CHART =====
function openBarModal(){ els.barModal.style.display = "flex"; }
function closeBarModal(){ els.barModal.style.display = "none"; }

function drawBarChart(mode){
  if(!displayRows.length) return;

  const fuelLabel = FUEL_LABELS[currentFuel];
  const periodCfg = PERIOD_CONFIG[currentPeriod];
  const isZl = mode === "zl";
  const valFn = isZl ? (r => r.changeAbs) : (r => r.changePct);
  const label = isZl ? "zl (PLN/m3)" : "%";

  const barTitleText = `${fuelLabel} \u2014 HISTORIA ${periodCfg.barTitle} (${label})`;

  const dataRows = displayRows.filter(r => valFn(r) != null);
  const x = dataRows.map(r => new Date(r.date.getTime()));
  const y = dataRows.map(r => valFn(r));

  const colors = y.map(v => v >= 0 ? "rgba(52,255,154,.75)" : "rgba(255,75,75,.75)");
  const borders = y.map(v => v >= 0 ? "#34ff9a" : "#ff4b4b");

  const trace = {
    x, y,
    type: "bar",
    marker: { color: colors, line: { color: borders, width: 1 } },
    hovertemplate: isZl
      ? "%{x|%d-%m-%Y}<br><b>%{y:+d} zl</b><extra></extra>"
      : "%{x|%d-%m-%Y}<br><b>%{y:+.2f}%</b><extra></extra>"
  };

  const layout = {
    title: {
      text: barTitleText,
      font: { color: "rgba(255,255,255,.90)", size: 14, family: "monospace" },
      x: 0.01, xanchor: "left"
    },
    paper_bgcolor: "#070c12",
    plot_bgcolor: "#0a0f16",
    margin: { l: 70, r: 40, t: 45, b: 50 },
    xaxis: {
      showgrid: true, gridcolor: "rgba(255,255,255,.06)",
      rangeslider: { visible: true, thickness: 0.08 },
      tickfont: { color: "rgba(255,255,255,.70)" },
      title: { text: "Data", font: { color: "rgba(255,255,255,.70)" } },
      showspikes: true, spikemode: "across", spikesnap: "cursor",
      spikecolor: "rgba(255,255,255,.35)", spikethickness: 1
    },
    yaxis: {
      showgrid: true, gridcolor: "rgba(255,255,255,.08)",
      tickfont: { color: "rgba(255,255,255,.70)" },
      title: { text: isZl ? "Zmiana (zl)" : "Zmiana (%)", font: { color: "rgba(255,255,255,.70)" } },
      zeroline: true, zerolinecolor: "rgba(255,255,255,.25)", zerolinewidth: 2,
      autorange: true, rangemode: "normal",
      showspikes: true, spikemode: "across", spikesnap: "cursor",
      spikecolor: "rgba(255,255,255,.35)", spikethickness: 1
    },
    font: { color: "rgba(255,255,255,.80)" },
    dragmode: "zoom",
    hovermode: "closest",
    showlegend: false,
    bargap: 0.15,
    annotations: [{
      text: "Opracowanie w\u0142asne na podstawie danych Orlen",
      showarrow: false,
      xref: "paper", yref: "paper",
      x: 1, y: -0.15,
      xanchor: "right", yanchor: "top",
      font: { size: 11, color: "rgba(255,255,255,.40)", family: "monospace" }
    }]
  };

  openBarModal();
  Plotly.newPlot("barChart", [trace], layout, {
    responsive: true, scrollZoom: true, displayModeBar: true,
    toImageButtonOptions: { format: "png", width: 1400, height: 700, filename: barTitleText.replace(/[^a-zA-Z0-9_\-]/g, "_") }
  }).then(() => {
    attachYAutoScale("barChart", dataRows, valFn);
  });
}

// ===== EVENT LISTENERS =====
els.searchInput.addEventListener("input", applyFilter);

els.btnClose.addEventListener("click", closeModal);
els.modal.addEventListener("click", (e) => { if(e.target === els.modal) closeModal(); });
els.btnShowAll.addEventListener("click", () => {
  if(!chartReady) return;
  Plotly.relayout("chart", { "xaxis.autorange": true, "yaxis.autorange": true });
});

els.barBtnClose.addEventListener("click", closeBarModal);
els.barModal.addEventListener("click", (e) => { if(e.target === els.barModal) closeBarModal(); });
els.barBtnShowAll.addEventListener("click", () => {
  Plotly.relayout("barChart", { "xaxis.autorange": true, "yaxis.autorange": true });
});

els.thChangeZl.addEventListener("click", (e) => {
  e.stopPropagation();
  drawBarChart("zl");
});
els.thChangePct.addEventListener("click", (e) => {
  e.stopPropagation();
  drawBarChart("pct");
});

window.addEventListener("keydown", (e) => {
  if(e.key === "Escape"){ closeModal(); closeBarModal(); closeStopyModal(); }
});

loadData().catch(err => {
  console.error(err);
  els.tbody.innerHTML = `<tr><td class="neg" colspan="6">Błąd: ${err.message}<br><span class="muted">Uruchom serwer HTTP (np. python -m http.server 8000).</span></td></tr>`;
});

// ===== STOPY PANEL =====
let stopyLoaded = false;
let stopyNbp = [], stopyWibor = [], stopyFra = [];
const COMPARE_COLORS = ["#ffcc66","#7b61ff","#ff4b4b","#34ff9a","#ff7a7a"];
let compareEntries = [];

function fmt(v, d=2){ return v != null ? v.toFixed(d)+"%" : "—"; }

function nbpForDate(date){
  let result = null;
  for(const e of stopyNbp){ if(e.date <= date) result = e; }
  return result;
}
function wiborForDate(date){
  let result = null;
  for(const e of stopyWibor){ if(e.date <= date) result = e; }
  return result;
}
function wiborExact(date){
  return stopyWibor.find(e => e.date === date) ?? null;
}

// ===== STOPY MODAL =====
const stopyModal = document.getElementById("stopyModal");
function openStopyModal(){ stopyModal.style.display = "flex"; }
function closeStopyModal(){ stopyModal.style.display = "none"; }

document.getElementById("stopyBtnClose").addEventListener("click", closeStopyModal);
stopyModal.addEventListener("click", (e) => { if(e.target === stopyModal) closeStopyModal(); });
document.getElementById("stopyBtnShowAll").addEventListener("click", () => {
  Plotly.relayout("stopyChart", { "xaxis.autorange": true, "yaxis.autorange": true });
});

// Konfiguracja serii — klucz: {label, color, getPoints(highlightTs), ytitle, decimals}
const STOPY_SERIES = {
  nbp: {
    label: "NBP Stopa ref.",
    color: "#00d4aa",
    decimals: 2,
    ytitle: "Stopa (%)",
    getPoints: () => stopyNbp.map(e => ({ x: new Date(e.date + "T12:00:00Z"), y: e.ref, ts: e.date })),
  },
  wibor: {
    label: "WIBOR 3M",
    color: "#7b61ff",
    decimals: 2,
    ytitle: "Stopa (%)",
    getPoints: () => stopyWibor.map(e => ({ x: new Date(e.date + "T12:00:00Z"), y: e.wibor_3m, ts: e.date })),
  },
  fra1x4: {
    label: "FRA 1\xd74",
    color: "#ffcc66",
    decimals: 3,
    ytitle: "Stopa (%)",
    getPoints: () => stopyFra.filter(e => e.fra_1x4 != null).map(e => ({ x: new Date(e.timestamp), y: e.fra_1x4, ts: e.timestamp })),
  },
  fra3x6: {
    label: "FRA 3\xd76",
    color: "#ff7a7a",
    decimals: 3,
    ytitle: "Stopa (%)",
    getPoints: () => stopyFra.filter(e => e.fra_3x6 != null).map(e => ({ x: new Date(e.timestamp), y: e.fra_3x6, ts: e.timestamp })),
  },
  fra6x9: {
    label: "FRA 6\xd79",
    color: "#34ff9a",
    decimals: 3,
    ytitle: "Stopa (%)",
    getPoints: () => stopyFra.filter(e => e.fra_6x9 != null).map(e => ({ x: new Date(e.timestamp), y: e.fra_6x9, ts: e.timestamp })),
  },
  fra9x12: {
    label: "FRA 9\xd712",
    color: "#4dd0ff",
    decimals: 3,
    ytitle: "Stopa (%)",
    getPoints: () => stopyFra.filter(e => e.fra_9x12 != null).map(e => ({ x: new Date(e.timestamp), y: e.fra_9x12, ts: e.timestamp })),
  },
};

function drawStopyChart(seriesKey, highlightTs){
  const cfg = STOPY_SERIES[seriesKey];
  if(!cfg) return;
  const pts = cfg.getPoints();
  if(!pts.length) return;

  const d = cfg.decimals;
  const hoverFmt = d === 2
    ? "%{x|%d-%m-%Y}<br><b>%{y:.2f}%</b><extra></extra>"
    : "%{x|%d-%m-%Y %H:%M}<br><b>%{y:.3f}%</b><extra></extra>";

  // Tryb: NBP (step) vs reszta (lines)
  const mode = seriesKey === "nbp" ? "lines" : "lines";
  const shape = seriesKey === "nbp" ? "hv" : "linear";

  const trace = {
    x: pts.map(p => p.x),
    y: pts.map(p => p.y),
    type: "scatter",
    mode: mode,
    line: { width: 2.5, color: cfg.color, shape },
    hovertemplate: hoverFmt,
    name: cfg.label,
  };

  const traces = [trace];

  // Marker dla klikniętego punktu
  if(highlightTs){
    const hit = pts.find(p => p.ts === highlightTs);
    if(hit){
      traces.push({
        x: [hit.x], y: [hit.y],
        type: "scatter", mode: "markers",
        marker: { size: 11, color: cfg.color, line: { color: "#fff", width: 2 } },
        hovertemplate: `<b>Wybrana sesja</b><br>${hoverFmt}`,
        showlegend: false,
      });
    }
  }

  const lastVal = pts[pts.length - 1]?.y;
  const titleText = `${cfg.label} \u2014 ${lastVal != null ? lastVal.toFixed(d) + "%" : ""}`;

  const layout = {
    title: {
      text: titleText,
      font: { color: "rgba(255,255,255,.90)", size: 14, family: "monospace" },
      x: 0.01, xanchor: "left",
    },
    paper_bgcolor: "#070c12",
    plot_bgcolor: "#0a0f16",
    margin: { l: 70, r: 40, t: 45, b: 50 },
    xaxis: {
      showgrid: true, gridcolor: "rgba(255,255,255,.08)",
      rangeslider: { visible: true, thickness: 0.08 },
      tickfont: { color: "rgba(255,255,255,.70)" },
      title: { text: "Data", font: { color: "rgba(255,255,255,.70)" } },
      showspikes: true, spikemode: "across", spikesnap: "cursor",
      spikecolor: "rgba(255,255,255,.35)", spikethickness: 1,
    },
    yaxis: {
      showgrid: true, gridcolor: "rgba(255,255,255,.08)",
      tickfont: { color: "rgba(255,255,255,.70)" },
      title: { text: cfg.ytitle, font: { color: "rgba(255,255,255,.70)" } },
      ticksuffix: "%",
      showspikes: true, spikemode: "across", spikesnap: "cursor",
      spikecolor: "rgba(255,255,255,.35)", spikethickness: 1,
      autorange: true, rangemode: "normal",
    },
    font: { color: "rgba(255,255,255,.80)", family: "monospace" },
    dragmode: "zoom",
    hovermode: "closest",
    showlegend: false,
    annotations: [{
      text: "Opracowanie w\u0142asne | dane: NBP, stooq.pl, patria.cz",
      showarrow: false,
      xref: "paper", yref: "paper",
      x: 1, y: -0.15,
      xanchor: "right", yanchor: "top",
      font: { size: 11, color: "rgba(255,255,255,.40)", family: "monospace" },
    }],
  };

  document.getElementById("stopyModalTitle").textContent = cfg.label;
  openStopyModal();

  Plotly.newPlot("stopyChart", traces, layout, {
    responsive: true, scrollZoom: true, displayModeBar: true,
    toImageButtonOptions: { format: "png", width: 1400, height: 700, filename: cfg.label.replace(/[^a-zA-Z0-9_\-]/g, "_") },
  }).then(() => {
    attachYAutoScale("stopyChart", pts, p => p.y);
  });
}

// ===== KRZYWA STOP =====
function buildCurveTrace(nbp, wibor, fra, name, color){
  return {
    x: [0, 3, 4, 6, 9, 12],
    y: [nbp?.ref ?? null, wibor?.wibor_3m ?? null, fra?.fra_1x4 ?? null, fra?.fra_3x6 ?? null, fra?.fra_6x9 ?? null, fra?.fra_9x12 ?? null],
    text: ["NBP ref (0M)","WIBOR 3M (3M)","FRA 1\xd74 (4M)","FRA 3\xd76 (6M)","FRA 6\xd79 (9M)","FRA 9\xd712 (12M)"],
    hovertemplate: "%{text}: <b>%{y:.3f}%</b><extra></extra>",
    mode: "lines+markers",
    name, line: { color, width: 2.5 }, marker: { size: 7, color },
    type: "scatter",
  };
}

function renderCurve(){
  const latestFra = stopyFra.length ? stopyFra[stopyFra.length - 1] : null;
  const latestNbp = latestFra ? nbpForDate(latestFra.date) : (stopyNbp.length ? stopyNbp[stopyNbp.length-1] : null);
  const latestWib = latestFra ? wiborForDate(latestFra.date) : (stopyWibor.length ? stopyWibor[stopyWibor.length-1] : null);

  const traces = [];
  if(latestFra || latestNbp){
    traces.push(buildCurveTrace(latestNbp, latestWib, latestFra, "Aktualna", "#00d4aa"));
  }
  compareEntries.forEach((c, i) => {
    traces.push(buildCurveTrace(c.nbp, c.wibor, c.fra, c.label, COMPARE_COLORS[i % COMPARE_COLORS.length]));
  });

  const latestDate = latestFra?.date ?? latestNbp?.date ?? "";
  const layout = {
    paper_bgcolor: "#070c12", plot_bgcolor: "#0a0f16",
    font: { color: "#cfe6ff", family: "ui-monospace, monospace", size: 12 },
    margin: { l: 55, r: 20, t: 40, b: 50 },
    title: {
      text: "Krzywa stóp procentowych PLN" + (latestDate ? " — " + latestDate : ""),
      font: { size: 13, color: "#cfe6ff" }, x: 0.01, xanchor: "left",
    },
    xaxis: {
      tickvals: [0,3,4,6,9,12],
      ticktext: ["NBP ref\n(0M)","WIBOR 3M\n(3M)","FRA 1\xd74\n(4M)","FRA 3\xd76\n(6M)","FRA 6\xd79\n(9M)","FRA 9\xd712\n(12M)"],
      gridcolor: "#1a2433", color: "#8aa2be", showline: false, fixedrange: true,
      showspikes: true, spikemode: "across", spikesnap: "cursor",
      spikecolor: "rgba(255,255,255,.35)", spikethickness: 1,
    },
    yaxis: {
      gridcolor: "#1a2433", color: "#8aa2be", ticksuffix: "%",
      autorange: true, fixedrange: true,
      showspikes: true, spikemode: "across", spikesnap: "cursor",
      spikecolor: "rgba(255,255,255,.35)", spikethickness: 1,
    },
    legend: { bgcolor: "transparent", font: { size: 11 } },
    hovermode: "closest",
    annotations: [{
      text: "Opracowanie własne | dane: NBP, stooq.pl, patria.cz",
      showarrow: false, xref: "paper", yref: "paper",
      x: 1, y: -0.12, xanchor: "right", yanchor: "top",
      font: { size: 11, color: "rgba(255,255,255,.40)", family: "ui-monospace, monospace" }
    }],
  };

  Plotly.react("stopyCurveChart", traces, layout, { responsive: true, displayModeBar: false });
}

// ===== TABELA HISTORII =====
function renderStopyTable(){
  const tbody = document.getElementById("stopyTbody");
  if(!stopyFra.length){
    tbody.innerHTML = `<tr><td colspan="8" class="muted" style="text-align:center;padding:24px;">Brak danych historycznych</td></tr>`;
    return;
  }

  const rowsHtml = [...stopyFra].reverse().map(fra => {
    const nbp = nbpForDate(fra.date);
    const wib = wiborExact(fra.date);
    const badge = fra.session === "morning"
      ? `<span class="session-badge morning">rano</span>`
      : `<span class="session-badge afternoon">popol.</span>`;
    const ts = fra.timestamp;
    const nbpDate = nbp?.date ?? "";
    const wibDate = wib?.date ?? "";
    return `<tr>
      <td>${fra.date}</td>
      <td>${badge}</td>
      <td class="teal clickable-cell" data-series="nbp" data-ts="${nbpDate}" title="Kliknij — wykres NBP ref.">${fmt(nbp?.ref, 2)}</td>
      <td class="clickable-cell" data-series="wibor" data-ts="${wibDate}" title="Kliknij — wykres WIBOR 3M">${fmt(wib?.wibor_3m, 2)}</td>
      <td class="clickable-cell" data-series="fra1x4" data-ts="${ts}" title="Kliknij — wykres FRA 1x4">${fmt(fra.fra_1x4, 3)}</td>
      <td class="clickable-cell" data-series="fra3x6" data-ts="${ts}" title="Kliknij — wykres FRA 3x6">${fmt(fra.fra_3x6, 3)}</td>
      <td class="clickable-cell" data-series="fra6x9" data-ts="${ts}" title="Kliknij — wykres FRA 6x9">${fmt(fra.fra_6x9, 3)}</td>
      <td class="clickable-cell" data-series="fra9x12" data-ts="${ts}" title="Kliknij — wykres FRA 9x12">${fmt(fra.fra_9x12, 3)}</td>
    </tr>`;
  });
  tbody.innerHTML = rowsHtml.join("");

  // Delegacja kliknięć na komórkach
  tbody.addEventListener("click", (e) => {
    const cell = e.target.closest(".clickable-cell");
    if(!cell) return;
    drawStopyChart(cell.dataset.series, cell.dataset.ts);
  }, { once: false });
}

function populateCompareSelect(){
  const sel = document.getElementById("stopyCompareSel");
  sel.innerHTML = `<option value="">-- wybierz datę --</option>` +
    stopyFra.slice().reverse().map(e =>
      `<option value="${e.timestamp}">${e.date} \xb7 ${e.session === "morning" ? "rano" : "popol."}</option>`
    ).join("");
}

async function loadStopy(){
  if(stopyLoaded) return;
  try {
    const v = Date.now();
    [stopyNbp, stopyWibor, stopyFra] = await Promise.all([
      fetch(`data/nbp_history.json?v=${v}`, { cache: "no-store" }).then(r => r.json()),
      fetch(`data/wibor_history.json?v=${v}`, { cache: "no-store" }).then(r => r.json()),
      fetch(`data/fra_history.json?v=${v}`, { cache: "no-store" }).then(r => r.json()),
    ]);
    stopyNbp.sort((a, b) => a.date < b.date ? -1 : 1);
    stopyWibor.sort((a, b) => a.date < b.date ? -1 : 1);
    stopyFra.sort((a, b) => a.timestamp < b.timestamp ? -1 : 1);
    stopyLoaded = true;
    renderCurve();
    renderStopyTable();
    populateCompareSelect();
  } catch(e){
    console.error("Błąd ładowania stopy:", e);
    document.getElementById("stopyTbody").innerHTML =
      `<tr><td colspan="8" style="color:var(--red);padding:24px;text-align:center;">Błąd: ${e.message}</td></tr>`;
  }
}

// Resize wrappera krzywej → przerysuj Plotly
new ResizeObserver(() => {
  const chartDiv = document.getElementById("stopyCurveChart");
  if(chartDiv && chartDiv.data) Plotly.Plots.resize(chartDiv);
}).observe(document.getElementById("stopyCurveWrap"));

// Klikalne nagłówki kolumn — otwierają pełne wykresy historii
document.getElementById("thStopyNbp").addEventListener("click",    () => drawStopyChart("nbp"));
document.getElementById("thStopyWibor").addEventListener("click",  () => drawStopyChart("wibor"));
document.getElementById("thStopyFra1x4").addEventListener("click", () => drawStopyChart("fra1x4"));
document.getElementById("thStopyFra3x6").addEventListener("click", () => drawStopyChart("fra3x6"));
document.getElementById("thStopyFra6x9").addEventListener("click", () => drawStopyChart("fra6x9"));
document.getElementById("thStopyFra9x12").addEventListener("click",() => drawStopyChart("fra9x12"));

// Porownanie krzywych
document.getElementById("stopyCompareAdd").addEventListener("click", () => {
  const sel = document.getElementById("stopyCompareSel");
  const ts  = sel.value;
  if(!ts) return;
  if(compareEntries.find(c => c.ts === ts)) return;
  const fra = stopyFra.find(e => e.timestamp === ts);
  if(!fra) return;
  const label = `${fra.date} \xb7 ${fra.session === "morning" ? "rano" : "popol."}`;
  compareEntries.push({ ts, label, nbp: nbpForDate(fra.date), wibor: wiborForDate(fra.date), fra });
  renderCurve();
});

document.getElementById("stopyCompareClear").addEventListener("click", () => {
  compareEntries = [];
  renderCurve();
});

// ===== CHECK PANEL =====
let checkLoaded = false;
let checkIce = [];
let checkDiesel = [];
let currentCheckOffset = 0;
let checkDualAxis = false;
const DAY_MS = 24 * 3600 * 1000;

async function loadCheck(){
  if(checkLoaded) return;
  try {
    const v = Date.now();
    const [iceData, dieselData] = await Promise.all([
      fetch(`data/ice_history.json?v=${v}`, { cache: "no-store" }).then(r => r.json()),
      loadFuelForAnalysis("diesel"),
    ]);
    checkIce = iceData.sort((a, b) => a.date < b.date ? -1 : 1);
    checkDiesel = dieselData;
    checkLoaded = true;
    drawCheckCharts(currentCheckOffset);
  } catch(e){
    console.error("Błąd ładowania Check:", e);
    document.getElementById("checkPriceChart").innerHTML =
      `<div style="color:var(--red);padding:32px;text-align:center;font-family:monospace;">Błąd: ${e.message}</div>`;
  }
}

function drawCheckCharts(offset){
  if(!checkIce.length || !checkDiesel.length) return;

  // Przytnij Orlen do zakresu dat ICE
  const iceStart = checkIce[0].date;
  const diesel = checkDiesel.filter(r => r.date.toISOString().slice(0, 10) >= iceStart);

  const offsetLabel = offset > 0 ? ` (Orlen −${offset}d)` : "";

  const orlenX = diesel.map(r => new Date(r.date.getTime() - offset * DAY_MS));
  const orlenY = diesel.map(r => r.price); // PLN/m3 = PLN/1000l

  const orlenTrace = {
    x: orlenX,
    y: orlenY,
    type: "scatter", mode: "lines",
    name: `Orlen Ekodiesel${offsetLabel} (PLN/1000l)`,
    line: { color: "#ffcc66", width: 2 },
    yaxis: checkDualAxis ? "y2" : "y",
    hovertemplate: "%{x|%d-%m-%Y}<br><b>%{y:.2f} PLN/1000l</b><extra>Orlen Ekodiesel</extra>",
  };

  const priceTraces = [
    {
      x: checkIce.map(e => new Date(e.date + "T12:00:00Z")),
      y: checkIce.map(e => e.ice_pln_1000l),
      type: "scatter", mode: "lines",
      name: "ICE Low Sulphur (PLN/1000l)",
      line: { color: "#4dd0ff", width: 2 },
      hovertemplate: "%{x|%d-%m-%Y}<br><b>%{y:.2f} PLN/1000l</b><extra>ICE Low Sulphur</extra>",
    },
    orlenTrace,
  ];

  const commonLayout = {
    paper_bgcolor: "#070c12", plot_bgcolor: "#0a0f16",
    font: { color: "rgba(255,255,255,.80)", family: "monospace" },
    dragmode: "zoom", hovermode: "x unified",
  };

  const yaxisBase = {
    showgrid: true, gridcolor: "rgba(255,255,255,.08)",
    tickfont: { color: "rgba(255,255,255,.70)" },
    autorange: true,
    showspikes: true, spikemode: "across", spikesnap: "cursor",
    spikecolor: "rgba(255,255,255,.35)", spikethickness: 1,
  };

  const priceLayout = {
    ...commonLayout,
    title: {
      text: "ICE Low Sulphur Gasoil vs Orlen Ekodiesel" + offsetLabel,
      font: { color: "rgba(255,255,255,.90)", size: 14, family: "monospace" },
      x: 0.01, xanchor: "left",
    },
    margin: { l: 70, r: checkDualAxis ? 80 : 40, t: 45, b: 80 },
    xaxis: {
      showgrid: true, gridcolor: "rgba(255,255,255,.08)",
      rangeslider: { visible: true, thickness: 0.08 },
      tickfont: { color: "rgba(255,255,255,.70)" },
      showspikes: true, spikemode: "across", spikesnap: "cursor",
      spikecolor: "rgba(255,255,255,.35)", spikethickness: 1,
    },
    yaxis: {
      ...yaxisBase,
      title: { text: "ICE (PLN/1000l)", font: { color: "#4dd0ff" } },
      tickfont: { color: checkDualAxis ? "#4dd0ff" : "rgba(255,255,255,.70)" },
    },
    legend: { x: 0.01, y: -0.18, orientation: "h", font: { size: 11 }, bgcolor: "transparent" },
    showlegend: true,
    annotations: [{
      text: "Opracowanie własne | źródło: stooq.pl (ICE LF.F, USD/PLN), Orlen",
      showarrow: false, xref: "paper", yref: "paper",
      x: 1, y: -0.15, xanchor: "right", yanchor: "top",
      font: { size: 11, color: "rgba(255,255,255,.40)", family: "monospace" },
    }],
  };

  if(checkDualAxis){
    priceLayout.yaxis2 = {
      ...yaxisBase,
      title: { text: "Orlen (PLN/1000l)", font: { color: "#ffcc66" } },
      tickfont: { color: "#ffcc66" },
      overlaying: "y", side: "right",
      showgrid: false,
    };
  } else {
    priceLayout.yaxis.title = { text: "PLN / 1000l", font: { color: "rgba(255,255,255,.70)" } };
    priceLayout.yaxis.tickfont = { color: "rgba(255,255,255,.70)" };
  }

  Plotly.newPlot("checkPriceChart", priceTraces, priceLayout,
    { responsive: true, scrollZoom: true, displayModeBar: true,
      toImageButtonOptions: { format: "png", width: 1400, height: 600, filename: "ice_vs_orlen" } });

  // === SPREAD ===
  const orlenByDate = {};
  diesel.forEach(r => {
    orlenByDate[r.date.toISOString().slice(0, 10)] = r.price;
  });

  const spreadX = [], spreadY = [];
  checkIce.forEach(e => {
    const orlenDate = new Date(e.date + "T12:00:00Z");
    orlenDate.setUTCDate(orlenDate.getUTCDate() + offset);
    const key = orlenDate.toISOString().slice(0, 10);
    if(orlenByDate[key] != null){
      spreadX.push(new Date(e.date + "T12:00:00Z"));
      spreadY.push(+(orlenByDate[key] - e.ice_pln_1000l).toFixed(2));
    }
  });

  const sMin = spreadY.length ? Math.min(...spreadY) : 0;
  const sMax = spreadY.length ? Math.max(...spreadY) : 0;
  const sPad = Math.max((sMax - sMin) * 0.08, 20);

  Plotly.newPlot("checkSpreadChart", [{
    x: spreadX, y: spreadY,
    type: "scatter", mode: "lines",
    line: { color: "#4dd0ff", width: 1.5 },
    fill: "tozeroy",
    fillcolor: "rgba(77,208,255,.10)",
    hovertemplate: "%{x|%d-%m-%Y}<br><b>%{y:+.2f} PLN/1000l</b><extra>Spread Orlen−ICE</extra>",
  }], {
    ...commonLayout,
    margin: { l: 70, r: 40, t: 45, b: 50 },
    xaxis: {
      showgrid: true, gridcolor: "rgba(255,255,255,.06)",
      tickfont: { color: "rgba(255,255,255,.70)" },
      showspikes: true, spikemode: "across", spikesnap: "cursor",
      spikecolor: "rgba(255,255,255,.35)", spikethickness: 1,
    },
    yaxis: {
      showgrid: true, gridcolor: "rgba(255,255,255,.08)",
      tickfont: { color: "rgba(255,255,255,.70)" },
      title: { text: "Spread (PLN/1000l)", font: { color: "rgba(255,255,255,.70)" } },
      zeroline: true, zerolinecolor: "rgba(255,255,255,.25)", zerolinewidth: 2,
      range: [sMin - sPad, sMax + sPad],
    },
    showlegend: false,
    title: {
      text: "Spread: Orlen − ICE (PLN/1000l)",
      font: { color: "rgba(255,255,255,.90)", size: 14, family: "monospace" },
      x: 0.01, xanchor: "left",
    },
  }, { responsive: true, displayModeBar: false });

  // === SPREAD STATS ===
  if(spreadY.length > 0){
    const sAvg = spreadY.reduce((a, b) => a + b, 0) / spreadY.length;
    const fmtSpread = v => (v >= 0 ? "+" : "") + v.toFixed(2);
    const col = v => v >= 0 ? "var(--green)" : "var(--red)";
    document.getElementById("checkSpreadStats").innerHTML =
      `MIN&nbsp;<b style="color:${col(sMin)}">${fmtSpread(sMin)}</b>&nbsp;&nbsp;` +
      `ŚR&nbsp;<b style="color:${col(sAvg)}">${fmtSpread(sAvg)}</b>&nbsp;&nbsp;` +
      `MAX&nbsp;<b style="color:${col(sMax)}">${fmtSpread(sMax)}</b>&nbsp;&nbsp;PLN/1000l` +
      `&nbsp;&nbsp;<span style="color:var(--muted)">(n=${spreadY.length})</span>`;
  }

  // === SYNC OSI X ===
  const priceEl = document.getElementById("checkPriceChart");
  const spreadEl = document.getElementById("checkSpreadChart");
  priceEl.removeAllListeners("plotly_relayout");
  spreadEl.removeAllListeners("plotly_relayout");
  let _syncBusy = false;
  priceEl.on("plotly_relayout", ev => {
    if(_syncBusy) return;
    const upd = {};
    if(ev["xaxis.range[0]"] !== undefined) upd["xaxis.range[0]"] = ev["xaxis.range[0]"];
    if(ev["xaxis.range[1]"] !== undefined) upd["xaxis.range[1]"] = ev["xaxis.range[1]"];
    if(ev["xaxis.autorange"])              upd["xaxis.autorange"] = true;
    if(Object.keys(upd).length){ _syncBusy = true; Plotly.relayout(spreadEl, upd); _syncBusy = false; }
  });
  spreadEl.on("plotly_relayout", ev => {
    if(_syncBusy) return;
    const upd = {};
    if(ev["xaxis.range[0]"] !== undefined) upd["xaxis.range[0]"] = ev["xaxis.range[0]"];
    if(ev["xaxis.range[1]"] !== undefined) upd["xaxis.range[1]"] = ev["xaxis.range[1]"];
    if(ev["xaxis.autorange"])              upd["xaxis.autorange"] = true;
    if(Object.keys(upd).length){ _syncBusy = true; Plotly.relayout(priceEl, upd); _syncBusy = false; }
  });
}

document.getElementById("checkOffsetBtns").addEventListener("click", (e) => {
  const btn = e.target.closest(".ana-fuel-btn");
  if(!btn) return;
  currentCheckOffset = parseInt(btn.dataset.offset) || 0;
  document.querySelectorAll("#checkOffsetBtns .ana-fuel-btn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  drawCheckCharts(currentCheckOffset);
});

document.getElementById("checkDualAxisBtn").addEventListener("click", () => {
  checkDualAxis = !checkDualAxis;
  const btn = document.getElementById("checkDualAxisBtn");
  btn.classList.toggle("active", checkDualAxis);
  drawCheckCharts(currentCheckOffset);
});

// ===== SHARE / EXPORT (1080x1080) =====
function renderChartToCanvas(el) {
  return Plotly.toImage(el, { format: "png", width: 1080, height: 1080 }).then(dataUrl => {
    return new Promise(resolve => {
      const canvas = document.createElement("canvas");
      canvas.width = 1080; canvas.height = 1080;
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#070c12";
      ctx.fillRect(0, 0, 1080, 1080);
      const img = new Image();
      img.onload = () => { ctx.drawImage(img, 0, 0); resolve(canvas); };
      img.src = dataUrl;
    });
  });
}

document.addEventListener("click", async (e) => {
  const btn = e.target.closest(".btn-share");
  if(!btn) return;
  const chartId = btn.dataset.chart;
  const el = document.getElementById(chartId);
  if(!el || !el.data) return;

  const titleRaw = el.layout?.title?.text || chartId;
  const filename = titleRaw.replace(/<[^>]*>/g, "").replace(/[^a-zA-Z0-9_\-]/g, "_").slice(0, 60) + "_1x1";

  const canvas = await renderChartToCanvas(el);

  // Try Web Share API (native share sheet on mobile)
  if (navigator.canShare) {
    const blob = await new Promise(r => canvas.toBlob(r, "image/png"));
    const file = new File([blob], filename + ".png", { type: "image/png" });
    if (navigator.canShare({ files: [file] })) {
      try {
        await navigator.share({ files: [file], title: filename });
        return;
      } catch(err) {
        if (err.name === "AbortError") return;
      }
    }
  }

  // Fallback: download
  const a = document.createElement("a");
  a.href = canvas.toDataURL("image/png");
  a.download = filename + ".png";
  a.click();
});
