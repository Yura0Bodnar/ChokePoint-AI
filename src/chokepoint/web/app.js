/* ChokePoint AI — demo UI logic.
 *
 * Note on scope: GET /api/v1/graph (the full dependency-graph endpoint)
 * does not exist yet — that's separate backend work. So instead of loading
 * a static background graph on page load, this page builds the graph
 * entirely from each POST /api/v1/simulate response (epicentre_node_ids +
 * impacted[].path). That is arguably a better demo anyway: every run draws
 * exactly the causal story for that event, with no unrelated clutter.
 */

(() => {
  "use strict";

  const els = {
    textInput: document.getElementById("text-input"),
    runBtn: document.getElementById("run-btn"),
    runSpinner: document.getElementById("run-spinner"),
    runLabel: document.getElementById("run-label"),
    status: document.getElementById("status"),
    errorBanner: document.getElementById("error-banner"),
    eventJson: document.getElementById("event-json"),
    unresolvedNote: document.getElementById("unresolved-note"),
    degradedBadge: document.getElementById("degraded-badge"),
    summaryCard: document.getElementById("summary-card"),
    summaryText: document.getElementById("summary-text"),
    graphHint: document.getElementById("graph-hint"),
    severitySlider: document.getElementById("severity-slider"),
    severityValue: document.getElementById("severity-value"),
    forecastRows: document.getElementById("forecast-rows"),
    fallbackDialog: document.getElementById("fallback-dialog"),
    fallbackReason: document.getElementById("fallback-reason"),
    pipelineSteps: Array.from(document.querySelectorAll(".pipeline-step")),
  };

  /** The most recently extracted DisruptionEvent, reused by the severity
   * slider so dragging it never triggers a fresh (costly) LLM call. */
  let lastEvent = null;

  /** Monotonic id so an older response can never overwrite a newer one
   * (e.g. two quick slider changes finishing out of order). */
  let latestRequestId = 0;

  // ── Cytoscape setup ──────────────────────────────────────────────────
  const cy = cytoscape({
    container: document.getElementById("cy"),
    elements: [],
    userZoomingEnabled: true,
    userPanningEnabled: true,
    style: [
      {
        selector: "node",
        style: {
          label: "data(label)",
          "font-size": "12px",
          "font-weight": "600",
          color: "#111827", // gray-900: high-contrast label text on white
          "text-valign": "bottom",
          "text-margin-y": 7,
          "text-wrap": "wrap",
          "text-max-width": "100px",
          // white plate behind labels so edges never strike through the text
          "text-background-color": "#ffffff",
          "text-background-opacity": 0.92,
          "text-background-padding": "3px",
          "text-background-shape": "roundrectangle",
          "background-color": "#6b7280",
          width: 28,
          height: 28,
          "border-width": 2,
          "border-color": "#374151",
        },
      },
      {
        selector: "node[kind='epicentre']",
        style: {
          "background-color": "#dc2626", // red-600
          "border-color": "#fca5a5", // red-300 — becomes the pulsing halo
          "border-width": 4,
          width: 42,
          height: 42,
          "font-size": "13px",
          "font-weight": "bold",
        },
      },
      {
        selector: "node[kind='impacted']",
        style: {
          "background-color": "data(color)",
          "border-color": "data(borderColor)",
          "border-width": 2.5,
          width: "data(size)",
          height: "data(size)",
        },
      },
      {
        selector: "node.selected-row",
        style: { "border-color": "#1d4ed8", "border-width": 5 },
      },
      {
        selector: "edge",
        style: {
          width: 2.5,
          "line-color": "#6b7280", // gray-500
          "target-arrow-color": "#6b7280",
          "target-arrow-shape": "triangle",
          "curve-style": "bezier",
          opacity: 1,
        },
      },
    ],
    layout: { name: "grid" },
  });

  let pulseHandle = null;

  function pulseEpicentres() {
    if (pulseHandle) clearInterval(pulseHandle);
    const epicentres = cy.nodes("[kind='epicentre']");
    if (epicentres.length === 0) return;
    let grown = false;
    pulseHandle = setInterval(() => {
      grown = !grown;
      epicentres.animate(
        { style: { "border-width": grown ? 11 : 4 } },
        { duration: 500, easing: "ease-in-out" }
      );
    }, 500);
  }

  // ── Impact color scale, tuned to stay vibrant on white ────────────────
  // amber-500 (low) -> orange-600 (mid) -> red-700 (high). Light yellows
  // vanish on white, so the scale starts at a saturated amber.
  const HEAT_STOPS = [
    [245, 158, 11],
    [234, 88, 12],
    [185, 28, 28],
  ];

  function impactRgb(score) {
    const t = Math.max(0, Math.min(1, score)) * (HEAT_STOPS.length - 1);
    const i = Math.min(Math.floor(t), HEAT_STOPS.length - 2);
    const f = t - i;
    return HEAT_STOPS[i].map((c, k) => Math.round(c + (HEAT_STOPS[i + 1][k] - c) * f));
  }

  function impactColor(score) {
    const [r, g, b] = impactRgb(score);
    return `rgb(${r}, ${g}, ${b})`;
  }

  /** Darker outline of the same hue so every node keeps a clear edge on white. */
  function impactBorder(score) {
    const [r, g, b] = impactRgb(score).map((c) => Math.round(c * 0.68));
    return `rgb(${r}, ${g}, ${b})`;
  }

  // ── Pipeline step highlighting (purely cosmetic feedback) ────────────
  function setActiveStep(index) {
    els.pipelineSteps.forEach((el, i) => el.classList.toggle("is-active", i === index));
  }

  // ── Rendering ─────────────────────────────────────────────────────────
  /** The "Intelligence brief" card. Only ever revealed from here, i.e. after a successful
   * run; a missing or blank summary keeps it hidden rather than showing an empty card. */
  function renderSummary(summary) {
    const text = typeof summary === "string" ? summary.trim() : "";
    const changed = text !== els.summaryText.textContent;
    els.summaryText.textContent = text; // textContent: the model's text is never parsed as HTML
    els.summaryCard.hidden = text === "";
    if (text !== "" && changed) {
      // Re-trigger the fade only for a new summary, not on every what-if slider re-run.
      els.summaryCard.classList.remove("fade-in");
      void els.summaryCard.offsetWidth;
      els.summaryCard.classList.add("fade-in");
    }
  }

  function renderEvent(event, degraded) {
    els.eventJson.textContent = JSON.stringify(event, null, 2);
    els.eventJson.classList.add("fade-in");
    els.degradedBadge.hidden = !degraded;
    renderSummary(event.summary);

    const unresolved = event.locations.filter((loc) => !loc.node_id);
    if (unresolved.length > 0) {
      els.unresolvedNote.hidden = false;
      els.unresolvedNote.textContent =
        `⚠ ${unresolved.length} location(s) not found in the graph: ` +
        unresolved.map((loc) => loc.raw).join(", ");
    } else {
      els.unresolvedNote.hidden = true;
    }
  }

  function renderGraph(result) {
    const event = result.event;
    const rawByNodeId = new Map(
      event.locations.filter((loc) => loc.node_id).map((loc) => [loc.node_id, loc.raw])
    );

    const nodes = [];
    const edgeKeys = new Set();
    const edges = [];

    for (const nodeId of result.epicentre_node_ids) {
      nodes.push({
        data: { id: nodeId, label: rawByNodeId.get(nodeId) || nodeId, kind: "epicentre" },
      });
    }

    for (const impacted of result.impacted) {
      nodes.push({
        data: {
          id: impacted.node_id,
          label: impacted.label,
          kind: "impacted",
          color: impactColor(impacted.impact_score),
          borderColor: impactBorder(impacted.impact_score),
          size: 24 + impacted.impact_score * 20,
        },
      });
      const path = impacted.path;
      for (let i = 0; i < path.length - 1; i++) {
        const key = `${path[i]}__${path[i + 1]}`;
        if (!edgeKeys.has(key)) {
          edgeKeys.add(key);
          edges.push({ data: { id: key, source: path[i], target: path[i + 1] } });
        }
      }
    }

    cy.elements().remove();
    cy.add([...nodes, ...edges]);
    cy.layout({ name: "breadthfirst", roots: result.epicentre_node_ids, directed: true, spacingFactor: 1.5 }).run();
    cy.fit(undefined, 40);
    pulseEpicentres();

    els.graphHint.hidden = nodes.length > 0;
  }

  function renderForecast(impacted) {
    if (impacted.length === 0) {
      els.forecastRows.innerHTML =
        '<tr><td colspan="4" class="py-3 text-center text-gray-600">No downstream impact for this event.</td></tr>';
      return;
    }
    els.forecastRows.innerHTML = "";
    for (const node of impacted) {
      const tr = document.createElement("tr");
      tr.className =
        "forecast-row cursor-pointer border-t border-gray-200 transition-colors hover:bg-blue-50";
      tr.dataset.nodeId = node.node_id;
      const pct = Math.max(0, Math.min(100, node.impact_score * 100));
      // Impact bar: a thin orange fill whose width is the impact out of 100%, on a gray track,
      // directly under the percentage. Plain Tailwind utilities (no custom CSS to go stale);
      // the 3px floor keeps a non-zero impact visible in the narrow column.
      tr.innerHTML = `
        <td class="truncate px-2.5 py-2.5 font-semibold text-gray-900">${escapeHtml(node.label)}</td>
        <td class="px-2.5 py-2.5">
          <div class="flex flex-col items-end gap-1">
            <span class="font-bold tabular-nums text-gray-900">${pct.toFixed(0)}%</span>
            <div class="h-1.5 w-full overflow-hidden rounded-full bg-gray-200" aria-hidden="true">
              <div class="h-full rounded-full bg-orange-500" style="width:${pct}%;min-width:${pct > 0 ? 3 : 0}px"></div>
            </div>
          </div>
        </td>
        <td class="px-2.5 py-2.5 text-right tabular-nums text-gray-700">${node.eta_days.toFixed(1)}d</td>
        <td class="px-2.5 py-2.5 text-right tabular-nums text-gray-700">${node.hops}</td>
      `;
      // The Node cell is truncated with an ellipsis, so put the full name in a native tooltip.
      // Set as a DOM property (not inside the template) so any label text is escaped for free.
      tr.firstElementChild.title = node.label;
      tr.addEventListener("click", () => {
        cy.nodes().removeClass("selected-row");
        const target = cy.getElementById(node.node_id);
        target.addClass("selected-row");
        cy.animate({ center: { eles: target }, zoom: Math.max(cy.zoom(), 1.2) }, { duration: 300 });
      });
      els.forecastRows.appendChild(tr);
    }
  }

  function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  }

  function showError(message) {
    els.errorBanner.hidden = false;
    els.errorBanner.textContent = message;
  }

  function clearError() {
    els.errorBanner.hidden = true;
    els.errorBanner.textContent = "";
  }

  /** FastAPI's validation errors come back as `detail: [...]`; our own
   * ValueError-driven 422s and the RFC 9457 handler both use `detail: str`.
   * Handle both shapes rather than dumping raw JSON at the user. */
  function extractErrorMessage(body) {
    if (!body || typeof body !== "object") return "Something went wrong.";
    const detail = body.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
    }
    return body.title ? `${body.title}: ${body.detail || ""}` : "Something went wrong.";
  }

  // ── Networking ────────────────────────────────────────────────────────
  /** Loading state for the full text -> LLM -> graph run. The what-if slider
   * is deliberately NOT disabled during its own (fast) re-runs: disabling a
   * focused input drops keyboard focus after every change. */
  function setLoading(isLoading, label = "Simulating…") {
    els.runBtn.disabled = isLoading;
    els.severitySlider.disabled = isLoading || lastEvent === null;
    els.runSpinner.hidden = !isLoading;
    els.runLabel.textContent = isLoading ? label : "Simulate";
  }

  /** The API answers HTTP 424 `{detail: {code: "hf_unavailable", ...}}` when Hugging Face
   * failed and the slow local model needs the user's consent (`force_local: true`). */
  class HfUnavailableError extends Error {
    constructor(message, reason) {
      super(message);
      this.reason = reason;
    }
  }

  /** Native <dialog>, not window.confirm(): styled, focus-trapped, Esc = Cancel.
   * Resolves true only for "Run Local". */
  function askRunLocally(reason) {
    const dialog = els.fallbackDialog;
    els.fallbackReason.hidden = !reason;
    els.fallbackReason.textContent = reason ? `Reason: ${reason}` : "";
    return new Promise((resolve) => {
      dialog.returnValue = "";
      dialog.addEventListener("close", () => resolve(dialog.returnValue === "run-local"), {
        once: true,
      });
      dialog.showModal();
    });
  }

  async function postSimulate(payload) {
    let resp;
    try {
      resp = await fetch("/api/v1/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } catch (_networkError) {
      throw new Error("Can't reach the server. Is the API running?");
    }
    const body = await resp.json().catch(() => null);
    if (!resp.ok) {
      const detail = body && body.detail;
      if (resp.status === 424 && detail && detail.code === "hf_unavailable") {
        throw new HfUnavailableError(detail.message, detail.reason);
      }
      throw new Error(extractErrorMessage(body));
    }
    return body;
  }

  /** Text -> event -> graph. If Hugging Face is down, pause and let the user decide whether
   * to run the ~40 s local model; resolves null when they decline. */
  async function extractAndSimulate(text) {
    let hfError;
    try {
      return await postSimulate({ text });
    } catch (err) {
      if (!(err instanceof HfUnavailableError)) throw err;
      hfError = err;
    }

    setLoading(false);
    els.status.textContent = "Hugging Face API is unavailable.";
    if (!(await askRunLocally(hfError.reason))) {
      els.status.textContent = "Cancelled: Hugging Face API is unavailable.";
      return null;
    }

    setLoading(true, "Running locally…");
    els.status.textContent = "Running the model locally on CPU. This may take ~40 seconds…";
    return postSimulate({ text, force_local: true });
  }

  async function runFromText() {
    const text = els.textInput.value.trim();
    if (!text) {
      showError("Type or paste a headline first.");
      return;
    }
    clearError();
    const requestId = ++latestRequestId;
    setLoading(true);
    setActiveStep(1); // "LLM Agent Extracts JSON" — request in flight
    els.status.textContent = "Extracting event and simulating…";

    try {
      const result = await extractAndSimulate(text);
      if (result === null || requestId !== latestRequestId) return;
      lastEvent = result.event;
      els.severitySlider.value = String(result.event.severity);
      els.severityValue.textContent = String(result.event.severity);
      applyResult(result);
      els.status.textContent = `Done in ${result.runtime_ms.toFixed(1)} ms`;
    } catch (err) {
      if (requestId !== latestRequestId) return;
      showError(err.message);
      els.status.textContent = "";
    } finally {
      // Only text runs set the loading state, and the button is disabled while
      // one is in flight, so this always belongs to the current text run.
      setLoading(false);
    }
  }

  async function runWhatIf(severity) {
    if (!lastEvent) return;
    clearError();
    const requestId = ++latestRequestId;
    els.status.textContent = "Re-running graph simulation (no LLM call)…";

    try {
      // The extracted event is sent back as-is; severity_override lets the
      // graph layer re-run without touching the LLM (scarce free-tier credits).
      const result = await postSimulate({ event: lastEvent, severity_override: severity });
      if (requestId !== latestRequestId) return;
      applyResult(result);
      els.status.textContent = `Done in ${result.runtime_ms.toFixed(1)} ms`;
    } catch (err) {
      if (requestId !== latestRequestId) return;
      showError(err.message);
      els.status.textContent = "";
    }
  }

  function applyResult(result) {
    setActiveStep(2); // "Graph Simulates Impact" — response rendered
    renderEvent(result.event, result.degraded);
    renderGraph(result);
    renderForecast(result.impacted);
    els.severitySlider.disabled = false;
  }

  // ── Tooltips ──────────────────────────────────────────────────────────
  // One shared, fixed-position element, clamped to the viewport so tooltips
  // never overflow the page on narrow screens. Works on hover and keyboard focus.
  const tooltip = document.createElement("div");
  tooltip.id = "tooltip";
  tooltip.setAttribute("role", "tooltip");
  document.body.appendChild(tooltip);

  function showTooltip(target) {
    const text = target.getAttribute("data-tip");
    if (!text) return;
    tooltip.textContent = text;
    tooltip.classList.add("is-visible");

    const margin = 8;
    const rect = target.getBoundingClientRect();
    const tipRect = tooltip.getBoundingClientRect();
    let left = rect.left + rect.width / 2 - tipRect.width / 2;
    left = Math.max(margin, Math.min(left, window.innerWidth - tipRect.width - margin));
    // prefer above the trigger; flip below when there isn't room
    let top = rect.top - tipRect.height - margin;
    if (top < margin) top = rect.bottom + margin;
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
  }

  function hideTooltip() {
    tooltip.classList.remove("is-visible");
  }

  document.addEventListener("mouseover", (e) => {
    const target = e.target.closest("[data-tip]");
    if (target) showTooltip(target);
  });
  document.addEventListener("mouseout", (e) => {
    if (e.target.closest("[data-tip]")) hideTooltip();
  });
  document.addEventListener("focusin", (e) => {
    const target = e.target.closest("[data-tip]");
    if (target) showTooltip(target);
  });
  document.addEventListener("focusout", hideTooltip);
  window.addEventListener("scroll", hideTooltip, { passive: true });

  // ── Wire up events ────────────────────────────────────────────────────
  els.runBtn.addEventListener("click", runFromText);

  // A click on the dimmed backdrop lands on the <dialog> itself (its form fills the box).
  els.fallbackDialog.addEventListener("click", (e) => {
    if (e.target === els.fallbackDialog) els.fallbackDialog.close("cancel");
  });

  els.textInput.addEventListener("focus", () => setActiveStep(0), { once: true });

  els.severitySlider.addEventListener("input", () => {
    els.severityValue.textContent = els.severitySlider.value;
  });

  els.severitySlider.addEventListener("change", () => {
    runWhatIf(Number(els.severitySlider.value));
  });

  setActiveStep(0);
})();
