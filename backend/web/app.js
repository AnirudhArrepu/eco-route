const state = { start: null, end: null, preview: null, stops: [], proposal: null };
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const dateInput = $("#date");
$("#api-base-url").value = localStorage.getItem("ecoroute.apiBase") || window.ECOROUTE_API_BASE || "";
function apiUrl(path) {
  const base = $("#api-base-url").value.trim().replace(/\/+$/, "") || window.location.origin;
  return `${base}/${path.replace(/^\/+/, "")}`;
}
$("#save-api-base").addEventListener("click", () => {
  const value = $("#api-base-url").value.trim().replace(/\/+$/, "");
  if (value && !/^https?:\/\//i.test(value)) { authMessage("Enter an API URL beginning with http:// or https://.", true); return; }
  if (value) localStorage.setItem("ecoroute.apiBase", value);
  else localStorage.removeItem("ecoroute.apiBase");
  authMessage(value ? "API Gateway endpoint saved for this browser." : "Using the current page origin for API requests.");
});
const tomorrow = new Date();
tomorrow.setDate(tomorrow.getDate() + 1);
dateInput.value = `${tomorrow.getFullYear()}-${String(tomorrow.getMonth() + 1).padStart(2, "0")}-${String(tomorrow.getDate()).padStart(2, "0")}`;

function headers(json = false) {
  const result = {};
  if (json) result["Content-Type"] = "application/json";
  const token = $("#token").value.trim();
  if (token) result.Authorization = `Bearer ${token}`;
  return result;
}

async function api(url, options = {}) {
  const request = () => fetch(apiUrl(url), { ...options, headers: { ...headers(Boolean(options.body)), ...options.headers } });
  let response = await request();
  if (response.status === 401 && url !== "/v1/auth/refresh" && localStorage.getItem("ecoroute.refreshToken")) {
    try {
      const refreshed = await fetch(apiUrl("/v1/auth/refresh"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token: localStorage.getItem("ecoroute.refreshToken") }) });
      if (refreshed.ok) {
        setAuthTokens(await refreshed.json());
        response = await request();
      }
    } catch (_) {}
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body.detail;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail || body));
  }
  return body;
}

function setAuthTokens(tokens) {
  const idToken = tokens.id_token || localStorage.getItem("ecoroute.idToken") || "";
  const accessToken = tokens.access_token || localStorage.getItem("ecoroute.accessToken") || "";
  const refreshToken = tokens.refresh_token || localStorage.getItem("ecoroute.refreshToken") || "";
  if (idToken) localStorage.setItem("ecoroute.idToken", idToken);
  if (accessToken) localStorage.setItem("ecoroute.accessToken", accessToken);
  if (refreshToken) localStorage.setItem("ecoroute.refreshToken", refreshToken);
  $("#token").value = idToken || accessToken;
  $("#sign-out").hidden = false;
}

function authMessage(text, error = false) {
  const box = $("#auth-notice");
  box.textContent = text;
  box.hidden = false;
  box.classList.toggle("error", error);
}

async function loadSignedInUser() {
  $("#token").value = localStorage.getItem("ecoroute.idToken") || localStorage.getItem("ecoroute.accessToken") || "";
  if (!$("#token").value) return;
  try {
    const current = await api("/v1/auth/me");
    $("#user-id").value = current.user_id;
    $("#sign-out").hidden = false;
    authMessage(`Signed in · user ${current.user_id}`);
  } catch (_) {
    $("#token").value = "";
    localStorage.removeItem("ecoroute.idToken");
    localStorage.removeItem("ecoroute.accessToken");
    localStorage.removeItem("ecoroute.refreshToken");
    $("#user-id").value = "local-user";
  }
}

$("#sign-up").addEventListener("click", async () => {
  try {
    const result = await api("/v1/auth/signup", { method: "POST", body: JSON.stringify({ email: $("#auth-email").value.trim(), password: $("#auth-password").value }) });
    authMessage(result.confirmation_required ? "Account created. Check your email for the confirmation code." : "Account created. You can sign in.");
  } catch (error) { authMessage(error.message, true); }
});

$("#confirm-sign-up").addEventListener("click", async () => {
  try {
    await api("/v1/auth/confirm", { method: "POST", body: JSON.stringify({ email: $("#auth-email").value.trim(), code: $("#auth-code").value.trim() }) });
    authMessage("Email confirmed. Sign in to continue.");
  } catch (error) { authMessage(error.message, true); }
});

$("#resend-code").addEventListener("click", async () => {
  try {
    await api("/v1/auth/resend-confirmation", { method: "POST", body: JSON.stringify({ email: $("#auth-email").value.trim() }) });
    authMessage("A new confirmation code was sent to your email.");
  } catch (error) { authMessage(error.message, true); }
});

$("#sign-in").addEventListener("click", async () => {
  try {
    const tokens = await api("/v1/auth/login", { method: "POST", body: JSON.stringify({ email: $("#auth-email").value.trim(), password: $("#auth-password").value }) });
    setAuthTokens(tokens);
    const current = await api("/v1/auth/me");
    $("#user-id").value = current.user_id;
    $("#auth-password").value = "";
    authMessage(`Signed in · user ${current.user_id}`);
  } catch (error) { authMessage(error.message, true); }
});

$("#sign-out").addEventListener("click", () => {
  localStorage.removeItem("ecoroute.idToken");
  localStorage.removeItem("ecoroute.accessToken");
  localStorage.removeItem("ecoroute.refreshToken");
  $("#token").value = "";
  $("#user-id").value = "local-user";
  $("#sign-out").hidden = true;
  authMessage("Signed out on this device.");
});

loadSignedInUser();

function message(text, error = false) {
  const box = $("#notice");
  box.textContent = text;
  box.hidden = false;
  box.classList.toggle("error", error);
}

function asIso(date, time, timezone) {
  const guess = new Date(`${date}T${time}:00Z`);
  const offsetName = new Intl.DateTimeFormat("en", { timeZone: timezone, timeZoneName: "longOffset" })
    .formatToParts(guess).find(part => part.type === "timeZoneName")?.value || "GMT+00:00";
  const match = offsetName.match(/GMT([+-])(\d{2}):(\d{2})/);
  const offset = match ? `${match[1]}${match[2]}:${match[3]}` : "+00:00";
  return `${date}T${time}:00${offset}`;
}

function locationFromFields(latSelector, lonSelector, selected, label) {
  if (selected) return { ...selected, label: selected.label || label };
  const latitude = $(latSelector).value;
  const longitude = $(lonSelector).value;
  if (latitude === "" || longitude === "") throw new Error(`Choose a ${label.toLowerCase()} search result or enter its coordinates.`);
  return { latitude: Number(latitude), longitude: Number(longitude), label };
}

function placeSearch(input, results, onSelect, bias = () => null) {
  let timer;
  input.addEventListener("input", () => {
    clearTimeout(timer);
    results.replaceChildren();
    input.dataset.selected = "";
    onSelect(null);
    const display = input.closest(".location-field")?.querySelector(".selected-location") || input.closest(".stop-content")?.querySelector(".stop-selected");
    if (display) display.textContent = "";
    if (input.value.trim().length < 3) return;
    timer = setTimeout(async () => {
      try {
        const params = new URLSearchParams({ query: input.value.trim() });
        const point = bias();
        if (point) { params.set("latitude", point.latitude); params.set("longitude", point.longitude); }
        const result = await api(`/v1/places/search?${params}`);
        if (!result.places?.length) {
          const empty = document.createElement("div");
          empty.className = "place-option";
          empty.textContent = "No place matches. Try a shorter search or enter coordinates below.";
          results.append(empty);
          return;
        }
        result.places.forEach(place => {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "place-option";
          button.innerHTML = `<strong></strong><span></span>`;
          $("strong", button).textContent = place.label || place.title || input.value;
          $("span", button).textContent = (place.categories || []).map(category => typeof category === "string" ? category : category.Name || category.Type || "").filter(Boolean).join(" · ");
          button.addEventListener("click", () => {
            const selected = { id: place.id, title: place.title || place.label || input.value, label: place.label || place.title, latitude: place.latitude, longitude: place.longitude };
            input.value = selected.title;
            input.dataset.selected = "true";
            onSelect(selected);
            results.replaceChildren();
            const selectedLabel = input.closest(".location-field")?.querySelector(".selected-location") || input.closest(".stop-content")?.querySelector(".stop-selected");
            if (selectedLabel) selectedLabel.textContent = `Selected · ${selected.label}`;
          });
          results.append(button);
        });
      } catch (error) {
        const item = document.createElement("div");
        item.className = "place-option";
        item.textContent = error.message;
        results.append(item);
      }
    }, 280);
  });
}

placeSearch($("#start-query"), $("#start-results"), value => { state.start = value; });
placeSearch($("#end-query"), $("#end-results"), value => { state.end = value; }, () => state.start);

function addStop() {
  const fragment = $("#stop-template").content.cloneNode(true);
  const row = $(".stop-row", fragment);
  const input = $(".stop-query", row);
  const results = $(".stop-results", row);
  const remove = $(".remove-stop", row);
  const fixedToggle = $(".fixed-toggle-input", row);
  const fixedTime = $(".fixed-time-wrap", row);
  const selected = { value: null };
  placeSearch(input, results, value => { selected.value = value; }, () => state.start);
  remove.addEventListener("click", () => { row.remove(); updateStopNumbers(); });
  fixedToggle.addEventListener("change", () => { fixedTime.hidden = !fixedToggle.checked; });
  row._selectedPlace = selected;
  $("#stops").append(fragment);
  updateStopNumbers();
}

function updateStopNumbers() {
  $$(".stop-row").forEach((row, index) => { $(".stop-index", row).textContent = String(index + 1).padStart(2, "0"); });
}

$("#add-stop").addEventListener("click", addStop);
addStop();

function buildPayload() {
  const date = $("#date").value;
  const timezone = $("#timezone").value.trim();
  if (!date || !timezone) throw new Error("Choose a date and timezone.");
  const startLocation = locationFromFields("#start-lat", "#start-lon", state.start, $("#start-query").value.trim());
  let endLocation;
  if (!$("#end-query").value.trim() && !$("#end-lat").value && !state.end) endLocation = startLocation;
  else endLocation = locationFromFields("#end-lat", "#end-lon", state.end, $("#end-query").value.trim());
  const stops = $$(".stop-row").map(row => {
    const title = $(".stop-query", row).value.trim();
    if (!title) throw new Error("Give each stop a name or choose a place.");
    const place = row._selectedPlace.value;
    const manualLat = $(".stop-lat", row).value;
    const manualLon = $(".stop-lon", row).value;
    if (!place && (manualLat === "" || manualLon === "")) throw new Error(`Choose a place for ${title} or enter its coordinates.`);
    const location = place || { latitude: Number(manualLat), longitude: Number(manualLon), label: title };
    const duration = Number($(".duration", row).value);
    const stop = { title: place?.title || title, type: $(".stop-type", row).value, location: { latitude: location.latitude, longitude: location.longitude, label: location.label || title }, duration_minutes: duration, mandatory: true, source: place ? "amazon_location" : "user" };
    const deadline = $(".deadline", row).value;
    if (deadline) stop.latest_end = asIso(date, deadline, timezone);
    if ($(".fixed-toggle-input", row).checked) {
      const fixed = $(".fixed-time", row).value;
      if (!fixed) throw new Error(`Set the fixed appointment time for ${title}.`);
      stop.fixed_start = asIso(date, fixed, timezone);
    }
    return stop;
  });
  return {
    user_id: $("#user-id").value.trim(), date, timezone,
    start_at: asIso(date, $("#start-time").value, timezone),
    end_at: asIso(date, $("#end-time").value, timezone),
    start_location: startLocation, end_location: endLocation,
    stops, constraints: [], include_routines: true, max_candidate_evaluations: 5000,
  };
}

function timeLabel(value) {
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit", timeZone: $("#timezone").value }).format(new Date(value));
}

function drawTimeline(target, items, metrics = {}) {
  target.replaceChildren();
  (items || []).forEach(stop => {
    if (stop.travel_minutes > 0) {
      const travel = document.createElement("li"); travel.className = "timeline-item travel"; travel.innerHTML = '<span class="timeline-time"></span><span class="timeline-dot"></span><div class="timeline-copy"><strong></strong></div>';
      $(".timeline-time", travel).textContent = timeLabel(stop.departed_at || stop.arrival_at);
      $(".timeline-copy strong", travel).textContent = `Travel · ${Math.round(stop.travel_minutes)} min`;
      target.append(travel);
    }
    const item = document.createElement("li"); item.className = "timeline-item"; item.innerHTML = '<span class="timeline-time"></span><span class="timeline-dot"></span><div class="timeline-copy"><strong></strong><span></span></div>';
    $(".timeline-time", item).textContent = timeLabel(stop.start_at);
    $(".timeline-copy strong", item).textContent = stop.title;
    $(".timeline-copy span", item).textContent = `${timeLabel(stop.start_at)}–${timeLabel(stop.end_at)}${stop.waiting_minutes ? ` · ${Math.round(stop.waiting_minutes)} min wait` : ""}`;
    target.append(item);
  });
  if (metrics.return_travel_minutes > 0) {
    const returning = document.createElement("li"); returning.className = "timeline-item travel"; returning.innerHTML = '<span class="timeline-time"></span><span class="timeline-dot"></span><div class="timeline-copy"><strong></strong></div>';
    $(".timeline-time", returning).textContent = timeLabel(metrics.return_departure_at);
    $(".timeline-copy strong", returning).textContent = `Return travel · ${Math.round(metrics.return_travel_minutes)} min`;
    target.append(returning);
  }
  if (metrics.return_arrival_at) {
    const end = document.createElement("li"); end.className = "timeline-item"; end.innerHTML = '<span class="timeline-time"></span><span class="timeline-dot"></span><div class="timeline-copy"><strong>Arrive at end location</strong></div>';
    $(".timeline-time", end).textContent = timeLabel(metrics.return_arrival_at);
    target.append(end);
  }
}

function drawSummary(target, metrics) {
  target.replaceChildren();
  if (!metrics) return;
  [[`${Math.round(metrics.travel_minutes)} min`, "estimated travel"], [`${Number(metrics.distance_km).toFixed(1)} km`, "route distance"], [`${Math.round(metrics.waiting_minutes)} min`, "waiting time"]].forEach(([value, label]) => {
    const item = document.createElement("div"); item.className = "summary-item"; item.innerHTML = "<strong></strong><span></span>"; $("strong", item).textContent = value; $("span", item).textContent = label; target.append(item);
  });
}

function showProposal(proposal) {
  state.proposal = proposal;
  $("#candidate-panel").hidden = true;
  $("#proposal-panel").hidden = false;
  const status = $("#proposal-status");
  status.textContent = String(proposal.status || "pending").toUpperCase();
  status.classList.toggle("bad", !proposal.feasible);
  const metrics = proposal.metrics?.after || proposal.metrics;
  drawSummary($("#proposal-summary"), metrics);
  const conflictBox = $("#proposal-conflicts"); conflictBox.replaceChildren(); conflictBox.hidden = !proposal.conflicts?.length;
  if (proposal.conflicts?.length) {
    conflictBox.append(document.createTextNode("The proposed itinerary has unresolved constraints:"));
    const list = document.createElement("ul"); proposal.conflicts.forEach(conflict => { const item = document.createElement("li"); item.textContent = conflict.reason; list.append(item); }); conflictBox.append(list);
  }
  drawTimeline($("#proposal-timeline"), metrics?.timeline || [] , metrics || {});
  $("#proposal-facts").replaceChildren(...(proposal.explanation_facts || []).map(fact => { const p = document.createElement("p"); p.textContent = fact; return p; }));
  const canApprove = proposal.feasible && proposal.status === "pending" && Boolean(proposal.id);
  $("#approve-proposal").hidden = !canApprove;
  $("#reject-proposal").hidden = !canApprove;
  $("#proposal-note").textContent = canApprove ? `Proposal ${proposal.id} · based on revision ${proposal.base_revision}` : `Proposal ${proposal.id || ""} is not available for approval.`;
  $("#proposal-panel").scrollIntoView({ behavior: "smooth", block: "center" });
}

function renderAgentResult(result) {
  if (result?.status === "destination_candidates" || result?.status === "needs_destination_selection") {
    const panel = $("#candidate-panel"); const list = $("#agent-candidates"); list.replaceChildren(); panel.hidden = false; $("#proposal-panel").hidden = true;
    (result.candidates || []).forEach(candidate => {
      const card = document.createElement("div"); card.className = "candidate-card";
      const details = document.createElement("div"); details.innerHTML = "<strong></strong><span></span>";
      $("strong", details).textContent = candidate.title || candidate.label || "Place";
      $("span", details).textContent = `${candidate.label || ""}${candidate.categories?.length ? ` · ${candidate.categories.map(value => typeof value === "string" ? value : value.Name || value.Type || "").filter(Boolean).join(", ")}` : ""}`;
      const button = document.createElement("button"); button.type = "button"; button.textContent = "Evaluate in my route";
      button.addEventListener("click", () => proposeCandidate(candidate, button));
      card.append(details, button); list.append(card);
    });
    $("#agent-message").textContent = result.candidates?.length ? "Choose a place. EcoRoute will calculate a feasible insertion and wait for your approval." : result.message || "No places were found; try another request.";
    return;
  }
  if (result?.id && result.status) { showProposal(result); return; }
  $("#agent-message").textContent = result?.question || result?.message || `Workflow result: ${result?.status || "No result"}.`;
}

async function proposeCandidate(candidate, button) {
  if (button) button.disabled = true;
  try {
    const userId = $("#user-id").value.trim();
    const scheduleId = $("#manage-schedule-id").value.trim();
    const title = candidate.title || candidate.label || "Suggested stop";
    const proposal = await api(`/v1/schedules/${encodeURIComponent(scheduleId)}/stops`, { method: "POST", body: JSON.stringify({ user_id: userId, destination: { title, type: "errand", location: { latitude: candidate.latitude, longitude: candidate.longitude, label: candidate.label || title, id: candidate.id }, duration_minutes: 30, mandatory: true, source: "amazon_location" } }) });
    showProposal(proposal);
  } catch (error) { agentMessage(error.message, true); if (button) button.disabled = false; }
}

function agentMessage(text, error = false) {
  const box = $("#agent-message"); box.textContent = text; box.hidden = false; box.classList.toggle("error", error);
}

async function waitForWorkflow(executionArn, userId) {
  const params = new URLSearchParams({ execution_arn: executionArn, user_id: userId });
  for (let attempt = 0; attempt < 40; attempt++) {
    await new Promise(resolve => setTimeout(resolve, 1500));
    const status = await api(`/v1/workflows/status?${params}`);
    if (status.status !== "RUNNING") {
      if (status.status !== "SUCCEEDED") throw new Error(status.cause || status.error || `Workflow ${status.status.toLowerCase()}.`);
      return status.result;
    }
  }
  throw new Error("Planning is taking longer than expected. Check workflow status and try again.");
}

$("#ask-agent").addEventListener("click", async () => {
  const button = $("#ask-agent"); button.disabled = true;
  $("#candidate-panel").hidden = true; $("#proposal-panel").hidden = true;
  try {
    const userId = $("#user-id").value.trim(); const scheduleId = $("#manage-schedule-id").value.trim(); const text = $("#agent-request").value.trim();
    if (!userId || !scheduleId || !text) throw new Error("Enter a user ID, schedule ID, and request.");
    agentMessage("Interpreting your request…");
    const started = await api("/v1/agent/requests", { method: "POST", body: JSON.stringify({ user_id: userId, schedule_id: scheduleId, text, timezone: $("#timezone").value || "Asia/Kolkata" }) });
    const result = started.execution_arn ? await waitForWorkflow(started.execution_arn, userId) : started;
    renderAgentResult(result);
  } catch (error) { agentMessage(error.message, true); }
  finally { button.disabled = false; }
});

$("#approve-proposal").addEventListener("click", async () => {
  const button = $("#approve-proposal"); button.disabled = true;
  try {
    const key = crypto.randomUUID ? crypto.randomUUID() : `approve-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const response = await api(`/v1/proposals/${encodeURIComponent(state.proposal.id)}/approve`, { method: "POST", body: JSON.stringify({ user_id: $("#user-id").value.trim(), idempotency_key: key }) });
    $("#proposal-note").textContent = `Approved · schedule revision ${response.revision}.`;
    $("#proposal-status").textContent = "APPROVED";
    $("#approve-proposal").hidden = true; $("#reject-proposal").hidden = true;
  } catch (error) { $("#proposal-note").textContent = error.message; button.disabled = false; }
});

$("#reject-proposal").addEventListener("click", async () => {
  const button = $("#reject-proposal"); button.disabled = true;
  try {
    await api(`/v1/proposals/${encodeURIComponent(state.proposal.id)}/reject`, { method: "POST", body: JSON.stringify({ user_id: $("#user-id").value.trim(), reason: "Rejected in the planner" }) });
    $("#proposal-note").textContent = "Proposal rejected. Your saved schedule is unchanged.";
    $("#proposal-status").textContent = "REJECTED";
    $("#approve-proposal").hidden = true; $("#reject-proposal").hidden = true;
  } catch (error) { $("#proposal-note").textContent = error.message; button.disabled = false; }
});

function renderResult(result) {
  state.preview = result;
  const card = $("#result");
  card.hidden = false;
  const badge = $("#feasibility");
  badge.textContent = result.feasible ? "FEASIBLE ITINERARY" : "NEEDS CHANGES";
  badge.classList.toggle("bad", !result.feasible);
  $("#save-button").hidden = !result.feasible;
  drawSummary($("#summary"), result.metrics);
  const conflictBox = $("#conflicts");
  conflictBox.hidden = !result.conflicts?.length;
  conflictBox.replaceChildren();
  if (result.conflicts?.length) {
    conflictBox.append(document.createTextNode("These constraints could not all be met:"));
    const list = document.createElement("ul");
    result.conflicts.forEach(conflict => { const item = document.createElement("li"); item.textContent = conflict.reason; list.append(item); });
    conflictBox.append(list);
  }
  drawTimeline($("#timeline"), result.timeline || [], result.metrics || {});
  $("#explanation").replaceChildren(...(result.explanation_facts || []).map(fact => { const p = document.createElement("p"); p.textContent = fact; return p; }));
  card.scrollIntoView({ behavior: "smooth", block: "start" });
}

$("#planner-form").addEventListener("submit", async event => {
  event.preventDefault();
  const button = $("#preview-button");
  button.disabled = true;
  $("#save-button").disabled = true;
  $("#result").hidden = true;
  try {
    const payload = buildPayload();
    if (!payload.user_id) throw new Error("Enter a user ID.");
    await api("/v1/preferences", { method: "POST", body: JSON.stringify({ user_id: payload.user_id, key: "travel_mode", value: { mode: $("#travel-mode").value }, confidence: 1, source: "explicit" }) });
    const result = await api("/v1/schedules/preview", { method: "POST", body: JSON.stringify(payload) });
    state.lastPayload = payload;
    renderResult(result);
    message(result.feasible ? "Timeline built. Review the stops and save when it looks right." : "No feasible ordering was found. Check the listed conflicts and update your deadlines.");
  } catch (error) { message(error.message, true); }
  finally { button.disabled = false; $("#save-button").disabled = false; }
});

$("#save-button").addEventListener("click", async () => {
  if (!state.preview?.feasible || !state.lastPayload) return;
  const button = $("#save-button"); button.disabled = true;
  try {
    const payload = { ...state.lastPayload, stops: state.preview.stops };
    const saved = await api("/v1/schedules", { method: "POST", body: JSON.stringify(payload) });
    $("#save-note").textContent = `Saved · Schedule ID ${saved.id} · revision ${saved.current_revision}`;
    message("Your itinerary is saved. You can retrieve it through the API using this schedule ID.");
    button.textContent = "Schedule saved";
    $("#manage-schedule-id").value = saved.id;
    $("#manage-card").hidden = false;
    $("#manage-card").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) { message(error.message, true); button.disabled = false; }
});
