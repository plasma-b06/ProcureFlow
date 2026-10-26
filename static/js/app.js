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

// ---------- Page components ----------
(function () {
  // Open / close modals (<dialog>). Extra data attributes prefill the form:
  //   data-form-action="/vendors/3/edit"   sets the form's action
  //   data-field-company_name="Acme"       sets the input named company_name
  document.addEventListener("click", function (e) {
    var opener = e.target.closest("[data-modal-open]");
    if (opener) {
      var dlg = document.getElementById(opener.getAttribute("data-modal-open"));
      if (!dlg) return;
      var form = dlg.querySelector("form");
      if (form) {
        if (opener.hasAttribute("data-form-action")) form.setAttribute("action", opener.getAttribute("data-form-action"));
        Array.prototype.forEach.call(opener.attributes, function (attr) {
          if (attr.name.indexOf("data-field-") !== 0) return;
          var field = form.elements[attr.name.slice(11)];
          if (field) field.value = attr.value;
        });
      }
      dlg.showModal();
      return;
    }
    var closer = e.target.closest("[data-modal-close]");
    if (closer) { closer.closest("dialog").close(); return; }
    if (e.target.tagName === "DIALOG") e.target.close(); // click on the backdrop

    var print = e.target.closest("[data-print]");
    if (print) window.print();

    // Repeating rows (RFQ items)
    var add = e.target.closest("[data-add-row]");
    if (add) {
      var tpl = document.getElementById(add.getAttribute("data-add-row"));
      var box = document.getElementById(add.getAttribute("data-target"));
      box.appendChild(tpl.content.cloneNode(true));
      var first = box.lastElementChild.querySelector("input");
      if (first) first.focus();
      return;
    }
    var rm = e.target.closest("[data-remove-row]");
    if (rm) {
      var container = rm.closest("[data-rows]");
      if (container.children.length > 1) rm.closest(".item-row").remove();
    }
  });

  // Confirm dialogs, and stop double submits
  document.addEventListener("submit", function (e) {
    var form = e.target;
    var msg = form.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) { e.preventDefault(); return; }
    if ((form.method || "").toLowerCase() === "post") {
      setTimeout(function () {
        form.querySelectorAll("button[type=submit]").forEach(function (b) { b.disabled = true; });
      }, 0);
    }
  });

  // Filters that submit when changed
  document.addEventListener("change", function (e) {
    var el = e.target.closest("[data-autosubmit]");
    if (el) el.form.submit();
  });

  // Live line totals while a vendor types prices (display only; the server recalculates)
  function rupees(n) {
    return "₹" + n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  function recalc(form) {
    var grand = 0;
    form.querySelectorAll("[data-qty]").forEach(function (input) {
      var line = (parseFloat(input.value) || 0) * parseFloat(input.getAttribute("data-qty"));
      grand += line;
      var out = form.querySelector('[data-line-total="' + input.getAttribute("data-item") + '"]');
      if (out) out.textContent = rupees(line);
    });
    var g = form.querySelector("[data-grand-total]");
    if (g) g.textContent = rupees(grand);
  }
  document.addEventListener("input", function (e) {
    if (e.target.matches("[data-qty]")) recalc(e.target.form);
  });
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("form").forEach(function (f) { if (f.querySelector("[data-qty]")) recalc(f); });
    // Open a modal straight away when the URL asks for it, e.g. /rfqs?new=1
    if (new URLSearchParams(location.search).get("new") === "1") {
      var d = document.querySelector("dialog[data-open-on-new]");
      if (d) d.showModal();
    }
  });
})();

// Re-enable submit buttons if the page is restored from the back/forward cache
window.addEventListener("pageshow", function (e) {
  if (e.persisted) document.querySelectorAll("button[type=submit]").forEach(function (b) { b.disabled = false; });
});