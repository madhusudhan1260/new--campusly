(function () {
  "use strict";

  function setMsg(el, text, ok) {
    el.textContent = text;
    el.className = "msg " + (ok ? "ok" : "err");
  }

  var photoInput = document.getElementById("f-photo");
  var aiBtn = document.getElementById("ai-btn");
  var aiStatus = document.getElementById("ai-status");

  if (photoInput && aiBtn) {
    photoInput.addEventListener("change", function () {
      aiBtn.disabled = !photoInput.files || !photoInput.files.length;
      aiStatus.textContent = "";
    });

    aiBtn.addEventListener("click", function () {
      var file = photoInput.files[0];
      if (!file) {
        return;
      }
      var formData = new FormData();
      formData.append("image", file);

      aiBtn.disabled = true;
      aiBtn.textContent = "Analyzing…";
      aiStatus.textContent = "";

      fetch("/ai/analyze", { method: "POST", headers: { "X-CSRFToken": window.CSRF_TOKEN }, body: formData })
        .then(function (response) {
          return response.json().then(function (data) {
            return { ok: response.ok, data: data };
          });
        })
        .then(function (result) {
          aiBtn.disabled = false;
          aiBtn.textContent = "Analyze with AI";
          if (result.ok && result.data.ok) {
            document.getElementById("f-name").value = result.data.name || "";
            document.getElementById("f-desc").value = result.data.description || "";
            var categorySelect = document.getElementById("f-category");
            if (result.data.category) {
              categorySelect.value = result.data.category;
            }
            aiStatus.textContent = "Filled in by Gemini -- double-check before posting.";
          } else {
            aiStatus.textContent = (result.data && result.data.error) || "AI analysis failed.";
          }
        })
        .catch(function () {
          aiBtn.disabled = false;
          aiBtn.textContent = "Analyze with AI";
          aiStatus.textContent = "Network error reaching the AI service.";
        });
    });
  }

  var reportForm = document.getElementById("report-form");
  var reportMsg = document.getElementById("report-msg");

  reportForm.addEventListener("submit", function (event) {
    event.preventDefault();
    var formData = new FormData(reportForm);
    var submitBtn = reportForm.querySelector('button[type="submit"]');
    submitBtn.disabled = true;

    fetch("/lost-found/report", { method: "POST", headers: { "X-CSRFToken": window.CSRF_TOKEN }, body: formData })
      .then(function (response) {
        return response.json().then(function (data) {
          return { ok: response.ok, data: data };
        });
      })
      .then(function (result) {
        submitBtn.disabled = false;
        if (result.ok && result.data.ok) {
          setMsg(reportMsg, "Posted! Refreshing the board…", true);
          setTimeout(function () {
            window.location.reload();
          }, 500);
        } else {
          setMsg(reportMsg, (result.data && result.data.error) || "Could not post this item.", false);
        }
      })
      .catch(function () {
        submitBtn.disabled = false;
        setMsg(reportMsg, "Network error. Please try again.", false);
      });
  });

  document.querySelectorAll(".btn.claim").forEach(function (button) {
    button.addEventListener("click", function () {
      button.disabled = true;
      button.textContent = "Claiming…";
      fetch("/lost-found/claim/" + button.getAttribute("data-id"), {
        method: "POST",
        headers: { "X-CSRFToken": window.CSRF_TOKEN },
      })
        .then(function (response) {
          return response.json().then(function (data) {
            return { ok: response.ok, data: data };
          });
        })
        .then(function (result) {
          if (result.ok && result.data.ok) {
            window.location.reload();
          } else {
            button.disabled = false;
            button.textContent = "This is mine";
            window.alert((result.data && result.data.error) || "Could not claim this item.");
          }
        });
    });
  });
})();
