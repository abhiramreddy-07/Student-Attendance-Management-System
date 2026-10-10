// Shared behaviour: password toggle, confirm dialogs, validation, loading buttons, bulk marking.
(function () {
  document.querySelectorAll(".toggle-password").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var input = document.querySelector(btn.dataset.target);
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.querySelector("i").className = show ? "bi bi-eye-slash" : "bi bi-eye";
    });
  });

  // Bootstrap client-side validation
  document.querySelectorAll("form.needs-validation").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (!form.checkValidity()) { e.preventDefault(); e.stopPropagation(); }
      form.classList.add("was-validated");
    }, false);
  });

  // Confirmation dialog for destructive actions: <form data-confirm="Are you sure?">
  var modalEl = document.getElementById("confirmModal");
  if (modalEl) {
    var modal = new bootstrap.Modal(modalEl), pending = null;
    document.querySelectorAll("form[data-confirm]").forEach(function (form) {
      form.addEventListener("submit", function (e) {
        if (form.dataset.confirmed) return;
        e.preventDefault();
        pending = form;
        document.getElementById("confirmText").textContent = form.dataset.confirm;
        modal.show();
      });
    });
    document.getElementById("confirmOk").addEventListener("click", function () {
      if (pending) { pending.dataset.confirmed = "1"; modal.hide(); pending.requestSubmit ? pending.requestSubmit() : pending.submit(); }
    });
  }

  // Loading state on submit buttons
  document.querySelectorAll("form").forEach(function (form) {
    form.addEventListener("submit", function () {
      if (form.classList.contains("was-validated") && !form.checkValidity()) return;
      var btn = form.querySelector("button[type=submit][data-loading]");
      if (btn && !form.dataset.confirm) {
        setTimeout(function () {
          btn.classList.add("btn-loading");
          btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>' + btn.dataset.loading;
        }, 0);
      }
    });
  });

  // Bulk marking on the attendance page
  document.querySelectorAll("[data-bulk]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      document.querySelectorAll("input.status-radio[value='" + btn.dataset.bulk + "']").forEach(function (r) {
        if (!r.disabled) r.checked = true;
      });
    });
  });

  // Auto-dismiss success alerts
  setTimeout(function () {
    document.querySelectorAll(".alert-success.alert-dismissible").forEach(function (a) {
      bootstrap.Alert.getOrCreateInstance(a).close();
    });
  }, 8000);
})();
