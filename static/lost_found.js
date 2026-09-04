(function () {
  "use strict";

  function setMsg(el, text, ok) {
    el.textContent = text;
    el.className = "msg " + (ok ? "ok" : "err");
  }

  document.querySelectorAll(".stats-band .value[data-count-to]").forEach(function (el) {
    var target = parseInt(el.getAttribute("data-count-to"), 10) || 0;
    if (target === 0) {
      el.textContent = "0";
      return;
    }
    var start = null;
    function step(ts) {
      if (!start) start = ts;
      var progress = Math.min((ts - start) / 900, 1);
      el.textContent = Math.round(progress * target);
      if (progress < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  });

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
      var form = document.querySelector('.claim-form[data-id="' + button.getAttribute("data-id") + '"]');
      button.hidden = true;
      form.hidden = false;
      form.querySelector("textarea").focus();
    });
  });

  document.querySelectorAll(".claim-cancel").forEach(function (button) {
    button.addEventListener("click", function () {
      var form = button.closest(".claim-form");
      form.hidden = true;
      var openBtn = document.querySelector('.btn.claim[data-id="' + form.getAttribute("data-id") + '"]');
      if (openBtn) openBtn.hidden = false;
    });
  });

  document.querySelectorAll(".claim-form").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var itemId = form.getAttribute("data-id");
      var msg = form.querySelector(".claim-msg");
      var submitBtn = form.querySelector('button[type="submit"]');
      var details = form.querySelector("textarea").value.trim();
      if (!details) return;

      submitBtn.disabled = true;
      var formData = new FormData();
      formData.append("details", details);

      fetch("/lost-found/claim/" + itemId, {
        method: "POST",
        headers: { "X-CSRFToken": window.CSRF_TOKEN },
        body: formData,
      })
        .then(function (response) {
          return response.json().then(function (data) {
            return { ok: response.ok, data: data };
          });
        })
        .then(function (result) {
          submitBtn.disabled = false;
          if (result.ok && result.data.ok) {
            form.outerHTML = '<p class="hint claim-sent">' + result.data.message + "</p>";
          } else {
            setMsg(msg, (result.data && result.data.error) || "Could not submit this claim.", false);
          }
        })
        .catch(function () {
          submitBtn.disabled = false;
          setMsg(msg, "Network error. Please try again.", false);
        });
    });
  });

  document.querySelectorAll(".view-claims-btn").forEach(function (button) {
    button.addEventListener("click", function () {
      var itemId = button.getAttribute("data-id");
      var box = document.getElementById("claims-" + itemId);
      if (!box.hidden) {
        box.hidden = true;
        return;
      }
      button.disabled = true;
      fetch("/lost-found/" + itemId + "/claims")
        .then(function (response) {
          return response.json();
        })
        .then(function (data) {
          button.disabled = false;
          if (!data.ok) return;
          if (data.claims.length === 0) {
            box.innerHTML = '<p class="hint">No claims yet.</p>';
          } else {
            box.innerHTML = data.claims
              .map(function (c) {
                var checklist = (c.confidence || [])
                  .map(function (chk) {
                    return (
                      '<li class="' + (chk.ok ? "conf-ok" : "conf-miss") + '">' +
                      (chk.ok ? "✓" : "✕") + " " + escapeHtml(chk.label) +
                      "</li>"
                    );
                  })
                  .join("");
                return (
                  '<div class="claim-entry"><p class="hint"><strong>' +
                  escapeHtml(c.name) +
                  "</strong> (" +
                  escapeHtml(c.email) +
                  ") &middot; " +
                  escapeHtml(c.submitted) +
                  "<br>" +
                  escapeHtml(c.details) +
                  '</p><ul class="confidence-checklist">' + checklist + "</ul></div>"
                );
              })
              .join("");
          }
          box.hidden = false;
        });
    });
  });

  document.querySelectorAll(".return-btn").forEach(function (button) {
    button.addEventListener("click", function () {
      if (!window.confirm("Mark this item as returned to its owner?")) return;
      button.disabled = true;
      fetch("/lost-found/" + button.getAttribute("data-id") + "/return", {
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
            window.alert((result.data && result.data.error) || "Could not update this item.");
          }
        });
    });
  });

  function escapeHtml(str) {
    var div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }
})();
