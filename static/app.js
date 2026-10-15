const state = {
  payload: null,
  rows: [],
  sortKey: "rank",
  sortDir: 1,
  selected: null,
};

const $ = (sel) => document.querySelector(sel);

function selectedClasses() {
  return [...document.querySelectorAll('input[name="classes"]:checked')].map((el) => el.value);
}

function setStatus(text, isError = false) {
  const node = $("#status");
  node.textContent = text;
  node.classList.toggle("error", isError);
}

function fillSelect(id, values) {
  const el = $(id);
  const current = el.value;
  el.innerHTML = `<option value="">All</option>` + values.map((v) => `<option>${v}</option>`).join("");
  if (values.includes(current)) el.value = current;
}

function applyFilters(rows) {
  const cls = $("#filter-class").value;
  const coach = $("#filter-coach").value;
  const berth = $("#filter-berth").value;
  const coverage = $("#filter-coverage").value;
  const quality = $("#filter-quality").value;
  return rows.filter((row) => {
    if (cls && row.class_code !== cls) return false;
    if (coach && row.coach_name !== coach) return false;
    if (berth && row.berth_code !== berth) return false;
    if (coverage === "full" && !row.covers_full_journey) return false;
    if (coverage === "partial" && (row.covers_full_journey || !row.consecutive_segments)) return false;
    if (quality === "high" && row.confidence !== "high") return false;
    if (quality === "uncertain" && !["unknown", "uncertain", "low", "none"].includes(row.confidence) && !["unknown", "uncertain"].includes(row.vacancy_class)) return false;
    return true;
  });
}

function sortRows(rows) {
  const key = state.sortKey;
  const dir = state.sortDir;
  return [...rows].sort((a, b) => {
    const av = a[key];
    const bv = b[key];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    if (av < bv) return -1 * dir;
    if (av > bv) return 1 * dir;
    return a.coach_name.localeCompare(b.coach_name) || a.berth_no - b.berth_no;
  });
}

function renderTable() {
  const tbody = $("#results tbody");
  const filtered = sortRows(applyFilters(state.rows));
  tbody.innerHTML = filtered.map((row) => {
    const run = row.run_from ? `${row.run_from}→${row.run_to}` : "—";
    const km = row.distance_km == null ? "n/a" : row.distance_km;
    const cover = row.coverage_percent == null ? "n/a" : `${row.coverage_percent}%`;
    const selected = state.selected && state.selected.coach_name === row.coach_name && state.selected.berth_no === row.berth_no;
    return `<tr data-coach="${row.coach_name}" data-berth="${row.berth_no}" class="${selected ? "selected" : ""}">
      <td>${row.rank}</td>
      <td>${row.class_code}</td>
      <td>${row.coach_name}</td>
      <td>${row.berth_no}</td>
      <td>${row.berth_code || ""}</td>
      <td>${run}</td>
      <td>${km}</td>
      <td>${row.consecutive_segments}</td>
      <td>${cover}${row.covers_full_journey ? " full" : ""}</td>
      <td class="tag ${row.vacancy_class}">${row.vacancy_class}</td>
      <td>${row.confidence}</td>
    </tr>`;
  }).join("");
  const empty = $("#empty");
  if (filtered.length) {
    empty.hidden = true;
  } else if (state.payload && !state.payload.ok && (state.payload.errors || []).length) {
    empty.hidden = false;
    empty.textContent = state.payload.errors.join(" ");
  } else if (state.rows.length) {
    empty.hidden = false;
    empty.textContent = "No berths matched the filters.";
  } else if (state.payload) {
    empty.hidden = false;
    empty.textContent = "No berth rows were returned for this enquiry.";
  } else {
    empty.hidden = true;
  }
  tbody.querySelectorAll("tr").forEach((tr) => {
    tr.addEventListener("click", () => {
      const coach = tr.dataset.coach;
      const berth = Number(tr.dataset.berth);
      state.selected = state.rows.find((r) => r.coach_name === coach && r.berth_no === berth);
      renderDetail();
      renderTable();
      renderCoaches();
    });
  });
}

function renderCoaches() {
  const filtered = applyFilters(state.rows);
  const allowed = new Set(filtered.map((r) => `${r.coach_name}:${r.berth_no}`));
  const root = $("#coaches");
  const coaches = state.payload?.coaches || [];
  root.innerHTML = coaches.map((coach) => {
    const cells = (coach.berths || []).filter((b) => allowed.has(`${coach.coach_name}:${b.berth_no}`));
    const shown = coach.fetch_ok ? cells : [];
    const err = coach.fetch_ok ? "" : `<p class="empty">${coach.error || "Coach data missing"}</p>`;
    return `<article class="coach-card">
      <h3>${coach.coach_name} · ${coach.class_code}${coach.position_from_engine ? ` · pos ${coach.position_from_engine}` : ""}</h3>
      ${err}
      <div class="berth-grid">
        ${shown.map((b) => `<button type="button" class="berth ${b.vacancy_class}" data-coach="${coach.coach_name}" data-berth="${b.berth_no}">${b.berth_no}<br>${b.berth_code || ""}</button>`).join("")}
      </div>
    </article>`;
  }).join("") || "<p>No coach layouts.</p>";
  root.querySelectorAll(".berth").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.selected = state.rows.find((r) => r.coach_name === btn.dataset.coach && r.berth_no === Number(btn.dataset.berth));
      renderDetail();
      renderTable();
    });
  });
}

function renderDetail() {
  const box = $("#detail");
  const body = $("#detail-body");
  if (!state.selected) {
    box.hidden = true;
    return;
  }
  const row = state.selected;
  const segs = (row.segments || []).map((s) =>
    `${s.split_no ?? "-"} ${s.from_station}→${s.to_station} occupancy=${JSON.stringify(s.occupancy_raw)} status=${s.status} clip=${s.clipped_from || ""}→${s.clipped_to || ""} quota=${s.quota || ""}`
  ).join("\n");
  body.textContent = [
    row.ranking_rationale,
    `Distance source: ${row.distance_source}`,
    `Retrieved: ${row.retrieved_at}`,
    row.warnings.length ? `Warnings: ${row.warnings.join("; ")}` : "",
    row.missing_data_reasons.length ? `Missing: ${row.missing_data_reasons.join("; ")}` : "",
    "",
    segs || "No segment records.",
  ].filter(Boolean).join("\n");
  box.hidden = false;
}

function ingest(payload) {
  state.payload = payload;
  state.rows = payload.results || [];
  fillSelect("#filter-class", [...new Set(state.rows.map((r) => r.class_code))].sort());
  fillSelect("#filter-coach", [...new Set(state.rows.map((r) => r.coach_name))].sort());
  fillSelect("#filter-berth", [...new Set(state.rows.map((r) => r.berth_code).filter(Boolean))].sort());
  document.querySelector(".filters").hidden = false;
  const bits = [
    payload.freshness_label,
    payload.train_name ? `${payload.train_no} ${payload.train_name}` : "",
    payload.ranking_mode === "kilometres" ? "ranked by verified km" : "ranked by consecutive segments",
    payload.retrieved_at ? `retrieved ${payload.retrieved_at}` : "",
  ].filter(Boolean);
  setStatus(bits.join(" · "), !payload.ok);
  if (payload.errors?.length) setStatus(payload.errors.join(" "), true);
  renderTable();
  renderCoaches();
}

document.querySelectorAll("th[data-sort]").forEach((th) => {
  th.addEventListener("click", () => {
    const key = th.dataset.sort;
    if (state.sortKey === key) state.sortDir *= -1;
    else {
      state.sortKey = key;
      state.sortDir = key === "rank" ? 1 : -1;
    }
    renderTable();
  });
});

["filter-class", "filter-coach", "filter-berth", "filter-coverage", "filter-quality"].forEach((id) => {
  document.getElementById(id).addEventListener("change", () => {
    renderTable();
    renderCoaches();
  });
});

function formatStation(station) {
  return `${station.name} (${station.code})`;
}

function bindStationCombo(searchId, hiddenId, menuId) {
  const input = document.getElementById(searchId);
  const hidden = document.getElementById(hiddenId);
  const menu = document.getElementById(menuId);
  let items = [];
  let active = -1;
  let timer = null;

  function close() {
    menu.hidden = true;
    input.setAttribute("aria-expanded", "false");
    active = -1;
  }

  function render(results, query) {
    items = results;
    if (!query.trim()) {
      close();
      return;
    }
    if (!results.length) {
      menu.innerHTML = `<li class="empty-hint">No stations match “${query}”</li>`;
      menu.hidden = false;
      input.setAttribute("aria-expanded", "true");
      return;
    }
    menu.innerHTML = results.map((station, index) =>
      `<li role="option" data-index="${index}" aria-selected="${index === 0}">`
      + `<span>${station.name}</span><span class="code">${station.code}</span></li>`
    ).join("");
    menu.hidden = false;
    input.setAttribute("aria-expanded", "true");
    active = 0;
  }

  function choose(index) {
    const station = items[index];
    if (!station) return;
    hidden.value = station.code;
    input.value = formatStation(station);
    close();
  }

  async function lookup(query) {
    const response = await fetch(`/api/stations?q=${encodeURIComponent(query)}`);
    const payload = await response.json();
    render(payload.results || [], query);
  }

  input.addEventListener("input", () => {
    hidden.value = "";
    const query = input.value;
    clearTimeout(timer);
    timer = setTimeout(() => lookup(query), 80);
  });
  input.addEventListener("focus", () => {
    if (input.value.trim()) lookup(input.value);
  });
  input.addEventListener("keydown", (event) => {
    if (menu.hidden && event.key !== "ArrowDown") return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (menu.hidden) lookup(input.value);
      active = Math.min(items.length - 1, active + 1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      active = Math.max(0, active - 1);
    } else if (event.key === "Enter" && !menu.hidden && items[active]) {
      event.preventDefault();
      choose(active);
      return;
    } else if (event.key === "Escape") {
      close();
      return;
    } else {
      return;
    }
    [...menu.querySelectorAll('[role="option"]')].forEach((li, index) => {
      li.setAttribute("aria-selected", String(index === active));
      if (index === active) li.scrollIntoView({ block: "nearest" });
    });
  });
  menu.addEventListener("mousedown", (event) => {
    const li = event.target.closest("[data-index]");
    if (li) choose(Number(li.dataset.index));
  });
  input.addEventListener("blur", () => setTimeout(close, 120));
}

bindStationCombo("boarding_search", "boarding_station", "boarding_menu");
bindStationCombo("destination_search", "destination_station", "destination_menu");

$("#enquiry").addEventListener("submit", async (event) => {
  event.preventDefault();
  const classes = selectedClasses();
  if (!classes.length) {
    setStatus("Select at least one class.", true);
    return;
  }
  function stationCode(hidden, typed) {
    if (hidden) return hidden;
    const match = typed.match(/\(([A-Z]{2,5})\)\s*$/);
    if (match) return match[1];
    return typed.trim().toUpperCase();
  }
  const form = event.currentTarget;
  const boarding = stationCode(form.boarding_station.value, form.boarding_search.value);
  const destination = stationCode(form.destination_station.value, form.destination_search.value);
  const body = {
    train_no: form.train_no.value,
    boarding_station: boarding,
    destination_station: destination,
    journey_date: form.journey_date.value,
    classes,
  };
  setStatus("Reading composition…");
  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    const text = await response.text();
    let payload;
    try {
      payload = JSON.parse(text);
    } catch (parseErr) {
      setStatus(
        `Analyse failed (${response.status}). The chart desk returned a non-JSON error.`,
        true
      );
      return;
    }
    if (!payload || typeof payload !== "object") {
      setStatus("Analyse failed: empty response.", true);
      return;
    }
    ingest(payload);
  } catch (err) {
    setStatus(`Request failed: ${err}`, true);
  }
});
