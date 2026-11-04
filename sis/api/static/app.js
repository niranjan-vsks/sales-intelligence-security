// Theme toggle (cards/P5_1.md): dark by default, the choice kept in localStorage.
(function () {
  var root = document.documentElement;
  var btn = document.getElementById("theme-toggle");
  if (!btn) return;
  function sync() {
    var light = root.dataset.theme === "light";
    btn.setAttribute("aria-label", light ? "Switch to dark theme" : "Switch to light theme");
  }
  btn.addEventListener("click", function () {
    var light = root.dataset.theme !== "light";
    if (light) root.dataset.theme = "light"; else delete root.dataset.theme;
    try { localStorage.setItem("theme", light ? "light" : "dark"); } catch (e) {}
    sync();
  });
  sync();
})();
