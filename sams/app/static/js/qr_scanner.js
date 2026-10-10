// Student QR scanner. Sends the scanned token to the Flask backend, which does ALL validation.
function initScanner(markUrl, dashboardUrl) {
  var csrf = document.querySelector('meta[name="csrf-token"]').content;
  var resultBox = document.getElementById("result");
  var camError = document.getElementById("camError");
  var scanner = null, busy = false;

  function show(ok, text) {
    resultBox.innerHTML = '<div class="alert alert-' + (ok ? "success" : "danger") + '"></div>';
    resultBox.firstChild.innerHTML = '<i class="bi bi-' + (ok ? "check-circle" : "x-circle") + ' me-2"></i>';
    resultBox.firstChild.appendChild(document.createTextNode(text));
  }

  async function submit(token) {
    if (busy) return; busy = true;
    try {
      var res = await fetch(markUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf, "Accept": "application/json" },
        body: JSON.stringify({ token: token })
      });
      var data = await res.json();
      show(data.ok, data.message);
      if (data.ok) { await stop(); setTimeout(function () { location.href = dashboardUrl; }, 2000); }
    } catch (e) { show(false, "Network error. Please try again."); }
    finally { setTimeout(function () { busy = false; }, 2500); }
  }

  async function stop() {
    if (scanner) { try { await scanner.stop(); } catch (e) {} scanner = null; }
    document.getElementById("stopBtn").classList.add("d-none");
    document.getElementById("startBtn").classList.remove("d-none");
  }

  document.getElementById("startBtn").addEventListener("click", async function () {
    camError.classList.add("d-none");
    if (typeof Html5Qrcode === "undefined") {
      camError.textContent = "The scanner library could not be loaded (check your internet connection). Use the manual code box.";
      camError.classList.remove("d-none"); return;
    }
    if (!window.isSecureContext) {
      camError.textContent = "Camera access requires HTTPS or http://localhost. Use the manual code box, or open the site over HTTPS.";
      camError.classList.remove("d-none"); return;
    }
    scanner = new Html5Qrcode("reader");
    try {
      await scanner.start({ facingMode: "environment" }, { fps: 10, qrbox: 240 }, function (text) { submit(text); });
      document.getElementById("startBtn").classList.add("d-none");
      document.getElementById("stopBtn").classList.remove("d-none");
    } catch (err) {
      scanner = null;
      camError.textContent = "Could not start the camera: allow camera permission in your browser, or use the manual code box.";
      camError.classList.remove("d-none");
    }
  });
  document.getElementById("stopBtn").addEventListener("click", stop);
  document.getElementById("manualBtn").addEventListener("click", function () {
    var v = document.getElementById("manualToken").value.trim();
    if (!v) { show(false, "Enter the session code first."); return; }
    submit(v);
  });
}
