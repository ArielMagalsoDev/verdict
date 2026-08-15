// Illustrative business-impact calculator. Port of the math in
// app/components/ImpactCalculator.tsx — 5 sliders drive 4 derived stat cards.
(function () {
  var ids = ["leadsPerMonth", "minutesPerLead", "pctAutoEligible", "costPerHour", "costPerLeadCents"];
  var inputs = {};
  ids.forEach(function (id) { inputs[id] = document.getElementById(id); });
  if (!inputs.leadsPerMonth) return;

  function fmtUsd(n) {
    return "$" + Math.round(n).toLocaleString("en-US");
  }

  function recalc() {
    var leadsPerMonth = Number(inputs.leadsPerMonth.value);
    var minutesPerLead = Number(inputs.minutesPerLead.value);
    var pctAutoEligible = Number(inputs.pctAutoEligible.value);
    var costPerHour = Number(inputs.costPerHour.value);
    var costPerLeadCents = Number(inputs.costPerLeadCents.value);

    ids.forEach(function (id) {
      var out = document.getElementById(id + "-out");
      if (out) out.textContent = inputs[id].value;
    });

    var eligibleLeads = Math.round((leadsPerMonth * pctAutoEligible) / 100);
    var humanReviewLeads = leadsPerMonth - eligibleLeads;
    var hoursReturned = Math.round(((eligibleLeads * minutesPerLead) / 60) * 10) / 10;
    var handlingCostReduction = Math.round(hoursReturned * costPerHour);
    var automationCost = Math.round(((leadsPerMonth * costPerLeadCents) / 100) * 100) / 100;
    var netSavings = Math.round(handlingCostReduction - automationCost);

    document.getElementById("impact-eligible").textContent = eligibleLeads.toLocaleString();
    document.getElementById("impact-hours").textContent = hoursReturned.toLocaleString();
    document.getElementById("impact-human").textContent = humanReviewLeads.toLocaleString();
    document.getElementById("impact-savings").textContent = fmtUsd(netSavings);
    document.getElementById("impact-breakdown").textContent =
      fmtUsd(handlingCostReduction) + " handling-cost reduction − " + fmtUsd(automationCost) + " automation cost";
  }

  ids.forEach(function (id) {
    inputs[id].addEventListener("input", recalc);
  });
  recalc();
})();
