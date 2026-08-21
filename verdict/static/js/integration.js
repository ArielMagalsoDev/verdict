(function () {
  var form = document.getElementById("integration-configurator");
  var output = document.getElementById("integration-blueprint");
  if (!form || !output) return;

  var INDUSTRIES = {
    saas: { label: "B2B SaaS", evidence: ["company website and product pages", "team size and operating region", "declared use case and current stack"], rules: ["ICP segment and account tier", "use-case urgency", "region and ownership routing"], pilot: "Start with one inbound form and one sales queue." },
    professional: { label: "Professional services", evidence: ["service pages and sector focus", "office footprint", "engagement type and buying role"], rules: ["service-line fit", "engagement size signals", "territory and partner ownership"], pilot: "Start with one service line and a single intake channel." },
    healthcare: { label: "Healthcare services", evidence: ["public location and service information", "operating footprint", "stated workflow need"], rules: ["service and location fit", "operational scope", "manual review for sensitive context"], pilot: "Start with public business data only; exclude patient information." },
    field: { label: "Field operations", evidence: ["service territory and depot footprint", "operating model", "stated coordination problem"], rules: ["territory fit", "multi-site complexity", "routing by service region"], pilot: "Start with one region and one operations team." }
  };
  var SOURCES = { website: "website form", email: "shared intake inbox", referral: "referral form", event: "event lead export", crm_import: "controlled CRM import" };
  var DESTINATIONS = { hubspot: "HubSpot", salesforce: "Salesforce", crm: "your CRM", webhook: "your webhook or API" };
  var APPROVALS = {
    every: "Every proposed CRM change and outreach draft waits for a named reviewer.",
    uncertain: "Uncertain identity, thin evidence, conflicts, and unsupported drafts route to review.",
    consequential: "Scoring can complete automatically; merges, CRM writes, and first outreach always wait for approval."
  };

  function esc(value) {
    return String(value).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; });
  }
  function list(items) { return "<ul>" + items.map(function (item) { return "<li>" + esc(item) + "</li>"; }).join("") + "</ul>"; }
  function value(id) { return document.getElementById(id).value; }

  function render() {
    var industry = INDUSTRIES[value("integration-industry")];
    var source = SOURCES[value("integration-source")];
    var destination = DESTINATIONS[value("integration-destination")];
    var approval = APPROVALS[value("integration-approval")];
    var stages = ["Capture and validate from " + source, "Resolve identity before enrichment", "Research only approved public sources", "Gate evidence before deterministic scoring", "Propose a reviewable diff to " + destination];
    output.innerHTML =
      '<header class="blueprint-summary"><div><span>ILLUSTRATIVE BLUEPRINT</span><h3>' + esc(industry.label) + " <b>&rarr;</b> " + esc(destination) + '</h3></div><div class="blueprint-tags"><span>' + esc(source) + '</span><span>human-gated</span></div></header>' +
      '<dl class="blueprint-metrics" aria-label="Blueprint summary"><div><dt>Pipeline</dt><dd>05 <span>stages</span></dd></div><div><dt>Evidence gate</dt><dd>Required</dd></div><div><dt>Write authority</dt><dd>Human</dd></div><div><dt>Pilot scope</dt><dd>01 <span>team</span></dd></div></dl>' +
      '<section class="blueprint-workflow"><div class="blueprint-section-head"><span>01</span><div><h3>Proposed workflow</h3><p>From intake to a reviewable business action.</p></div></div><div class="blueprint-flow" aria-label="Proposed workflow">' + stages.map(function (stage, index) { return '<div><span class="blueprint-node">0' + (index + 1) + '</span><p>' + esc(stage) + '</p></div>'; }).join("") + "</div></section>" +
      '<div class="integration-detail-grid"><section class="detail-evidence"><span class="detail-index">02 / EVIDENCE</span><h3>What Verdict can verify</h3>' + list(industry.evidence) + '</section><section class="detail-rules"><span class="detail-index">03 / RULES</span><h3>What plain code decides</h3>' + list(industry.rules) + '</section><section class="detail-control"><span class="detail-index">04 / CONTROL</span><h3>Where a person decides</h3><p>' + esc(approval) + '</p></section><section class="detail-pilot"><span class="detail-index">05 / PILOT</span><h3>How to start safely</h3><p>' + esc(industry.pilot) + '</p><p class="mt-2">Measure agreement, false scores, false refusals, review rate, latency, and cost per lead.</p></section></div>' +
      '<footer class="blueprint-boundary"><p><strong>Illustrative, not a promise.</strong> This preview is not a deployment estimate, compliance claim, or measured customer result.</p><div><a href="/architecture" class="blueprint-link-secondary">Inspect architecture</a><a href="https://github.com/ArielMagalsoDev/verdict" class="blueprint-link-secondary">Read source</a><a href="mailto:hello@arielmagalso.com" class="blueprint-link-primary">Discuss an integration</a></div></footer>';
  }

  form.addEventListener("change", render);
  render();
})();
