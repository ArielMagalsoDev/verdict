// Guided demo controller. Unlike the original's single blocking POST, this
// port's API returns 202 immediately (a durable worker processes the lead)
// and this file polls GET /api/v1/leads/{id} every 750ms, rendering audit
// events as they land — a progressive reveal of the pipeline the original's
// architecture can't offer.
(function () {
  var OUTCOME_LABEL = {
    qualified: "Qualified",
    insufficient_evidence: "Insufficient evidence",
    disqualified: "Disqualified",
    duplicate_or_merge_review: "Duplicate / merge review",
  };
  var OUTCOME_EXPLAINER = {
    qualified: "Sufficient evidence, meets the ICP — assigned, drafted, ready for a rep.",
    insufficient_evidence: "Too little evidence to score responsibly — returning clarifying questions instead of a guess.",
    disqualified: "Scored (or classified) and doesn't meet the ICP — reason recorded, no outreach sent.",
    duplicate_or_merge_review: "Resolves to a record already in the CRM — no duplicate created.",
  };
  var POLL_MS = 750;
  var MAX_POLLS = 120;

  var turnstileToken = "";
  window.__onTurnstileToken = function (token) { turnstileToken = token; };

  var scenarioButtons = document.querySelectorAll(".scenario-btn");
  var autofillButtons = document.querySelectorAll(".autofill-btn");
  var form = document.getElementById("custom-lead-form");
  var messageField = form ? form.querySelector('textarea[name="message"]') : null;
  var messageCount = document.getElementById("message-count");
  var submitBtn = document.getElementById("custom-submit-btn");
  var submitLabel = document.getElementById("custom-submit-label");
  var errorBox = document.getElementById("error-box");
  var resultBox = document.getElementById("result-box");
  var resultAnchor = document.getElementById("result-anchor");

  var busy = false;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function setBusy(isBusy) {
    busy = isBusy;
    scenarioButtons.forEach(function (b) { b.disabled = isBusy; });
    if (submitBtn) submitBtn.disabled = isBusy || !messageField || !messageField.value.trim();
  }

  function showError(message, details) {
    errorBox.style.display = "block";
    resultBox.style.display = "none";
    var html =
      '<div class="card p-4 mt-6" style="border-color: var(--outcome-disqualified-fg);">' +
      '<p class="text-sm" style="color: var(--outcome-disqualified-fg);">' + esc(message) + "</p>";
    if (details && details.length) {
      html += '<ul class="text-xs mt-2" style="color: var(--outcome-disqualified-fg); padding-left:1.1rem;">';
      details.forEach(function (d) { html += "<li>" + esc(d) + "</li>"; });
      html += "</ul>";
    }
    html += "</div>";
    errorBox.innerHTML = html;
    resultAnchor.scrollIntoView({ behavior: "auto", block: "start" });
  }

  function clearError() {
    errorBox.style.display = "none";
    errorBox.innerHTML = "";
  }

  // -------- rendering --------
  function renderAuditTrail(events) {
    var rows = events.map(function (e) {
      var pillCls =
        e.status === "failed" ? "badge-outcome-disqualified" :
        e.status === "skipped" ? "badge-outcome-insufficient_evidence" :
        e.status === "started" ? "" : "badge-outcome-qualified";
      var time = new Date(e.timestamp).toLocaleTimeString();
      return (
        '<li class="flex items-center justify-between gap-3 font-display text-xs" style="padding:0.2rem 0;">' +
        '<span class="text-muted shrink-0">' + time + "</span>" +
        '<span style="flex:1; min-width:0;" class="truncate">' + esc(e.event_type) + "</span>" +
        '<span class="text-muted">' + (e.duration_ms != null ? e.duration_ms + "ms" : "") + "</span>" +
        (pillCls ? '<span class="pill ' + pillCls + '">' + esc(e.status) + "</span>" : '<span class="pill">' + esc(e.status) + "</span>") +
        "</li>"
      );
    });
    return (
      '<div class="card p-5"><h3 class="label mb-3">Audit trail</h3>' +
      '<ul class="list-none" style="display:flex; flex-direction:column; gap:0.3rem;">' + rows.join("") + "</ul></div>"
    );
  }

  function renderInboundPanel(lead) {
    return (
      '<div class="card p-5"><h3 class="label mb-3">Inbound lead</h3>' +
      '<p class="font-semibold text-sm">' + esc(lead.first_name) + " " + esc(lead.last_name) +
      '<span class="text-muted" style="font-weight:400;"> &middot; ' + esc(lead.job_title || "unknown title") + "</span></p>" +
      '<p class="text-sm text-muted">' + esc(lead.company_name) + "</p>" +
      '<p class="text-xs text-muted mt-1 font-display">' + esc(lead.work_email) + "</p>" +
      '<p class="text-sm mt-3 italic leading-relaxed">&ldquo;' + esc(lead.message) + "&rdquo;</p></div>"
    );
  }

  function renderEvidencePanel(state) {
    var html = '<div class="card p-5"><h3 class="label mb-3">Research evidence</h3>';
    if (state.identity && state.identity.match_type === "possible") {
      html +=
        '<div class="mb-3 text-xs"><p class="font-semibold mb-1">Ambiguous identity — ' +
        state.identity.candidates.length + " candidate(s), none auto-selected:</p><ul class=\"text-muted\" style=\"padding-left:1.1rem;\">";
      state.identity.candidates.forEach(function (c) {
        html += "<li>" + esc(c.company_name) + ' <span class="text-muted">— ' + esc(c.reason) + "</span></li>";
      });
      html += "</ul></div>";
    }
    if (!state.facts.length) {
      html += '<p class="text-sm text-muted">No verified facts — see qualification panel for why.</p>';
    } else {
      html += '<ul style="display:flex; flex-direction:column; gap:0.5rem;">';
      state.facts.forEach(function (f) {
        html +=
          '<li class="text-sm"><span class="font-semibold">' + esc(f.field.replace(/_/g, " ")) + ":</span> " + esc(f.value);
        if (f.source_url) {
          html +=
            ' <a href="' + esc(f.source_url) + '" class="text-xs" style="margin-left:0.5rem; text-decoration:underline; font-weight:600; color: var(--signal);">source</a>';
        }
        html += "</li>";
      });
      html += "</ul>";
    }
    return html + "</div>";
  }

  function fmtCriterion(r) {
    if (r === "met") return { label: "Met", cls: "badge-outcome-qualified" };
    if (r === "not_met") return { label: "Not met", cls: "badge-outcome-disqualified" };
    return { label: "Unknown", cls: "badge-outcome-insufficient_evidence" };
  }

  function renderQualificationPanel(state) {
    var d = state.decision;
    if (!d) return '<div class="card p-5"><h3 class="label mb-3">Qualification</h3><p class="text-sm text-muted">Not evaluated yet.</p></div>';
    var html =
      '<div class="card p-5"><h3 class="label mb-3">Qualification</h3>' +
      '<p class="font-display text-2xl font-bold">' + (d.score === null ? "—" : d.score) +
      '<span class="text-sm text-muted" style="font-family: var(--font-sans); font-weight:400;">' + (d.score !== null ? " / 100" : "") + "</span></p>" +
      '<p class="text-xs text-muted mb-3">' + esc(d.reason) + "</p>";
    if (d.criteria && d.criteria.length) {
      html += '<ul style="display:flex; flex-direction:column; gap:0.4rem;">';
      d.criteria.forEach(function (c) {
        var r = fmtCriterion(c.result);
        html +=
          '<li class="flex items-center justify-between text-xs gap-2"><span>' + esc(c.label) +
          '</span><span class="pill ' + r.cls + '">' + r.label + "</span></li>";
      });
      html += "</ul>";
    }
    if (d.missing_information && d.missing_information.length) {
      html += '<div class="mt-3 pt-3 border-t"><p class="text-xs font-semibold mb-1">Questions that would unblock scoring:</p><ul class="text-xs text-muted" style="padding-left:1.1rem;">';
      d.missing_information.forEach(function (q) { html += "<li>" + esc(q) + "</li>"; });
      html += "</ul></div>";
    }
    return html + "</div>";
  }

  function renderCrmActionPanel(state) {
    var cs = state.change_set;
    if (!cs) return '<div class="card p-5"><h3 class="label mb-3">CRM action</h3><p class="text-sm text-muted">No change set proposed.</p></div>';
    var html =
      '<div class="card p-5"><h3 class="label mb-3">CRM action (proposed diff — nothing applied yet)</h3>' +
      '<p class="text-xs mb-2"><span class="font-semibold">Contact:</span> ' + esc(cs.contact_action) +
      ' &middot; <span class="font-semibold">Company:</span> ' + esc(cs.company_action) + "</p>";
    if (!cs.field_changes.length) {
      html += '<p class="text-sm text-muted">No fields proposed — matches an ambiguous or existing record.</p>';
    } else {
      html += '<ul style="display:flex; flex-direction:column; gap:0.25rem;">';
      cs.field_changes.forEach(function (fc) {
        html +=
          '<li class="text-xs font-display"><span class="text-muted">' + esc(fc.object) + "." + esc(fc.field) +
          "</span> &rarr; " + esc(fc.proposed_value) + ' <span class="text-muted">(' + esc(fc.source) + ")</span></li>";
      });
      html += "</ul>";
    }
    return html + "</div>";
  }

  var STATUS_PILL = {
    pending_review: { label: "Pending review", cls: "badge-outcome-insufficient_evidence" },
    approved: { label: "Approved (simulated — nothing sent)", cls: "badge-outcome-qualified" },
    rejected: { label: "Rejected", cls: "badge-outcome-disqualified" },
  };

  function renderDraftPanel(leadId, draft) {
    var canApprove = draft.unsupported_claims.length === 0 && draft.status === "pending_review";
    var pill = STATUS_PILL[draft.status] || { label: draft.status, cls: "" };
    var html =
      '<div class="card p-5" id="draft-panel"><h3 class="label mb-3">Outreach draft (human approval required — nothing is ever actually sent)</h3>' +
      '<p class="text-sm" style="white-space:pre-line; line-height:1.6;">' + esc(draft.approved_body || draft.generated_body) + "</p>" +
      '<div class="mt-3 pt-3 border-t flex flex-wrap items-center gap-2">' +
      '<span class="pill ' + pill.cls + '">' + pill.label + "</span>";
    if (draft.unsupported_claims.length) {
      html += '<span class="pill badge-outcome-disqualified">' + draft.unsupported_claims.length + " unsupported claim(s) — approval blocked</span>";
    }
    html += "</div>";
    if (draft.status === "pending_review") {
      html +=
        '<div class="mt-4 flex flex-wrap items-center gap-2">' +
        '<button type="button" class="btn-signal px-4 py-2 text-xs" id="draft-approve-btn" ' + (canApprove ? "" : "disabled") + ">Approve</button>" +
        '<button type="button" class="btn-outline px-4 py-2 text-xs" id="draft-reject-btn">Reject</button>' +
        "</div>";
    }
    html += '<p class="text-xs mt-2" id="draft-action-error" style="color: var(--outcome-disqualified-fg); display:none;"></p>';
    return html + "</div>";
  }

  function wireDraftButtons(leadId, state) {
    var approveBtn = document.getElementById("draft-approve-btn");
    var rejectBtn = document.getElementById("draft-reject-btn");
    var errEl = document.getElementById("draft-action-error");
    function decide(action) {
      if (approveBtn) approveBtn.disabled = true;
      if (rejectBtn) rejectBtn.disabled = true;
      fetch("/api/v1/leads/" + leadId + "/draft", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: action }),
      })
        .then(function (res) { return res.json().then(function (json) { return { ok: res.ok, json: json }; }); })
        .then(function (r) {
          if (!r.ok) {
            if (errEl) { errEl.style.display = "block"; errEl.textContent = r.json.error || "Something went wrong."; }
            if (approveBtn) approveBtn.disabled = false;
            if (rejectBtn) rejectBtn.disabled = false;
            return;
          }
          state.draft = r.json.draft;
          var panel = document.getElementById("draft-panel");
          if (panel) {
            panel.outerHTML = renderDraftPanel(leadId, state.draft);
            wireDraftButtons(leadId, state);
          }
        })
        .catch(function () {
          if (errEl) { errEl.style.display = "block"; errEl.textContent = "Network error."; }
        });
    }
    if (approveBtn) approveBtn.addEventListener("click", function () { decide("approve"); });
    if (rejectBtn) rejectBtn.addEventListener("click", function () { decide("reject"); });
  }

  function renderResult(state, outcome, replayed) {
    var html =
      '<div class="card p-6 flex flex-wrap items-center gap-4 justify-between">' +
      '<div><span class="pill badge-outcome-' + outcome + '">' + (OUTCOME_LABEL[outcome] || outcome) + "</span>" +
      '<p class="text-sm text-muted mt-2" style="max-width:36rem;">' + (OUTCOME_EXPLAINER[outcome] || "") + "</p></div>";
    if (replayed) html += '<span class="text-xs text-muted font-display">served from cache</span>';
    html += "</div>";

    html += '<div class="grid-responsive mt-6" style="grid-template-columns: 1fr 1fr;">';
    html += renderInboundPanel(state.lead);
    html += renderEvidencePanel(state);
    html += renderQualificationPanel(state);
    html += renderCrmActionPanel(state);
    html += "</div>";

    if (state.draft) {
      html += '<div class="mt-6">' + renderDraftPanel(state.lead.id, state.draft) + "</div>";
    }

    html += '<div class="mt-6">' + renderAuditTrail(state.audit_events) + "</div>";

    resultBox.style.display = "block";
    resultBox.innerHTML = html;
    if (state.draft) wireDraftButtons(state.lead.id, state);
  }

  function renderPending(state) {
    // Progressive reveal while the worker is still processing: show what's
    // landed in the audit trail so far, nothing else yet.
    resultBox.style.display = "block";
    resultBox.innerHTML =
      '<div class="card p-6"><p class="text-sm font-semibold" style="color: var(--signal);">Running pipeline&hellip;</p>' +
      '<p class="text-xs text-muted mt-1">Status: ' + esc(state.status) + "</p></div>" +
      '<div class="mt-6">' + renderAuditTrail(state.audit_events) + "</div>";
  }

  // -------- polling --------
  function poll(statusUrl, replayed, attempt) {
    attempt = attempt || 0;
    fetch(statusUrl)
      .then(function (res) { return res.json(); })
      .then(function (state) {
        if (state.status === "processing" && attempt < MAX_POLLS) {
          renderPending(state);
          setTimeout(function () { poll(statusUrl, replayed, attempt + 1); }, POLL_MS);
          return;
        }
        setBusy(false);
        scenarioButtons.forEach(function (b) { b.querySelector(".scenario-status").style.display = "none"; });
        if (submitLabel) submitLabel.textContent = "Run my lead through Verdict";

        if (state.status === "failed_permanent") {
          showError("The pipeline failed to process this lead after multiple attempts. Check /operations for details.");
          return;
        }
        clearError();
        renderResult(state, state.outcome, replayed);
        resultAnchor.scrollIntoView({ behavior: "auto", block: "start" });
      })
      .catch(function () {
        setBusy(false);
        showError("Network error while checking pipeline status.");
      });
  }

  function submit(url, body, loadingEl) {
    if (busy) return;
    setBusy(true);
    clearError();
    resultBox.style.display = "none";
    if (loadingEl) loadingEl.style.display = "block";

    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.assign({}, body, { turnstile_token: turnstileToken })),
    })
      .then(function (res) { return res.json().then(function (json) { return { ok: res.ok, status: res.status, json: json }; }); })
      .then(function (r) {
        if (!r.ok) {
          setBusy(false);
          if (loadingEl) loadingEl.style.display = "none";
          showError(r.json.message || r.json.error || "Something went wrong.", r.json.details);
          return;
        }
        poll(r.json.status_url, !!r.json.replayed, 0);
      })
      .catch(function () {
        setBusy(false);
        if (loadingEl) loadingEl.style.display = "none";
        showError("Network error — is the server running?");
      });
  }

  // -------- wiring --------
  scenarioButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var statusEl = btn.querySelector(".scenario-status");
      if (statusEl) statusEl.style.display = "block";
      submit("/api/v1/scenarios/" + btn.getAttribute("data-key"), {}, null);
    });
  });

  autofillButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      if (!form) return;
      form.querySelector('[name="company_name"]').value = btn.getAttribute("data-company") || "";
      form.querySelector('[name="website"]').value = btn.getAttribute("data-website") || "";
      form.querySelector('[name="country"]').value = btn.getAttribute("data-country") || "";
    });
  });

  if (messageField && messageCount) {
    messageField.addEventListener("input", function () {
      messageCount.textContent = String(messageField.value.length);
      if (submitBtn) submitBtn.disabled = busy || !messageField.value.trim();
    });
  }

  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var fd = new FormData(form);
      var body = {
        submission_id: (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now()) + Math.random(),
        source: "website",
        first_name: fd.get("first_name"),
        last_name: fd.get("last_name"),
        work_email: fd.get("work_email"),
        company_name: fd.get("company_name"),
        website: fd.get("website") || null,
        country: fd.get("country") || null,
        message: fd.get("message"),
        consent_to_contact: fd.get("consent") === "on",
      };
      if (submitLabel) submitLabel.textContent = "Running pipeline…";
      submit("/api/v1/leads", body, null);
    });
  }

  // Turnstile callback bridge (rendered widget calls window.turnstile.render
  // with this as the callback — see the inline snippet in demo.html when a
  // site key is configured).
  var widget = document.getElementById("turnstile-widget");
  if (widget && widget.getAttribute("data-sitekey")) {
    var tryRender = function () {
      if (!window.turnstile) return;
      window.turnstile.render(widget, {
        sitekey: widget.getAttribute("data-sitekey"),
        callback: window.__onTurnstileToken,
        "error-callback": function () { window.__onTurnstileToken(""); },
      });
    };
    var iv = setInterval(function () {
      if (window.turnstile) { clearInterval(iv); tryRender(); }
    }, 200);
  }
})();
