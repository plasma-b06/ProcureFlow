// ProcureFlow: small UI interactions (plain JS, no libraries)
document.addEventListener("DOMContentLoaded", function () {
  var body = document.body;

  // Public navbar: mobile menu
  var nav = document.querySelector(".nav");
  var navToggle = document.querySelector(".nav-toggle");
  if (nav && navToggle) {
    navToggle.addEventListener("click", function () {
      var open = nav.classList.toggle("open");
      navToggle.setAttribute("aria-expanded", open);
    });
    nav.querySelectorAll(".nav-links a").forEach(function (a) {
      a.addEventListener("click", function () {
        nav.classList.remove("open");
        navToggle.setAttribute("aria-expanded", "false");
      });
    });
  }

  // App sidebar (mobile)
  document.querySelectorAll("[data-sidebar-toggle]").forEach(function (b) {
    b.addEventListener("click", function () { body.classList.toggle("sidebar-open"); });
  });
  document.querySelectorAll("[data-sidebar-close]").forEach(function (b) {
    b.addEventListener("click", function () { body.classList.remove("sidebar-open"); });
  });

  // User dropdown
  document.querySelectorAll("[data-dropdown]").forEach(function (dd) {
    var btn = dd.querySelector("button");
    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      var open = dd.classList.toggle("open");
      btn.setAttribute("aria-expanded", open);
    });
  });
  function closeMenus() {
    document.querySelectorAll("[data-dropdown].open").forEach(function (dd) {
      dd.classList.remove("open");
      dd.querySelector("button").setAttribute("aria-expanded", "false");
    });
  }
  document.addEventListener("click", closeMenus);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") { closeMenus(); body.classList.remove("sidebar-open"); }
  });

  // Flash messages: dismiss button, and success messages fade out on their own
  document.addEventListener("click", function (e) {
    var close = e.target.closest(".alert-close");
    if (close) close.closest(".alert").remove();
  });
  document.querySelectorAll(".alert-success").forEach(function (a) {
    setTimeout(function () { if (a.parentNode) a.remove(); }, 6000);
  });

  // FAQ accordion (one open at a time)
  var buttons = document.querySelectorAll(".acc-btn");
  function setOpen(btn, open) {
    var panel = document.getElementById(btn.getAttribute("aria-controls"));
    btn.setAttribute("aria-expanded", open);
    panel.style.maxHeight = open ? panel.scrollHeight + "px" : "0px";
  }
  buttons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var willOpen = btn.getAttribute("aria-expanded") !== "true";
      buttons.forEach(function (b) { setOpen(b, false); });
      if (willOpen) setOpen(btn, true);
    });
  });
  if (buttons.length) setOpen(buttons[0], true);
});

// Show / hide password fields
document.addEventListener("click", function (e) {
  var btn = e.target.closest(".pw-toggle");
  if (!btn) return;
  var input = btn.parentElement.querySelector("input");
  var show = input.type === "password";
  input.type = show ? "text" : "password";
  btn.textContent = show ? "Hide" : "Show";
  btn.setAttribute("aria-pressed", show);
});