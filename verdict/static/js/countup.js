// Count-up stat animation. Port of app/components/CountUp.tsx: server-
// rendered value is already correct (no cold-load zeros), then resets to 0
// and animates up the first time the element enters the viewport.
(function () {
  var prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (prefersReduced || !("IntersectionObserver" in window)) return;

  var els = document.querySelectorAll(".countup");
  if (!els.length) return;

  function parseTarget(raw) {
    var prefix = raw.match(/^[^\d.-]+/);
    var suffix = raw.match(/[^\d.]+$/);
    var numeric = parseFloat(raw.replace(/[^\d.-]/g, ""));
    var decimals = (raw.split(".")[1] || "").replace(/[^\d]/g, "").length;
    return {
      value: isNaN(numeric) ? 0 : numeric,
      prefix: prefix ? prefix[0] : "",
      suffix: suffix ? suffix[0] : "",
      decimals: decimals,
    };
  }

  var io = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        io.unobserve(entry.target);
        var el = entry.target;
        var target = parseTarget(el.getAttribute("data-value") || el.textContent);
        var duration = 1400;
        var start = performance.now();
        el.textContent = target.prefix + (0).toFixed(target.decimals) + target.suffix;
        function tick(now) {
          var t = Math.min(1, (now - start) / duration);
          var eased = 1 - Math.pow(1 - t, 3);
          var value = t < 1 ? target.value * eased : target.value;
          el.textContent = target.prefix + value.toFixed(target.decimals) + target.suffix;
          if (t < 1) requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);
      });
    },
    { threshold: 0.4 }
  );
  els.forEach(function (el) { io.observe(el); });
})();
