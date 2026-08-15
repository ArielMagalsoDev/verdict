// Mobile hamburger menu toggle. Port of the open/close state in
// app/components/SiteHeader.tsx.
(function () {
  var toggle = document.getElementById("nav-hamburger");
  var panel = document.getElementById("mobile-nav-panel");
  if (!toggle || !panel) return;

  function setOpen(open) {
    panel.style.display = open ? "flex" : "none";
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
  }

  toggle.addEventListener("click", function () {
    setOpen(panel.style.display !== "flex");
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") setOpen(false);
  });
  panel.querySelectorAll("a").forEach(function (a) {
    a.addEventListener("click", function () { setOpen(false); });
  });
})();
