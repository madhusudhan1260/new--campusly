(function () {
  "use strict";

  function escapeHtml(str) {
    var div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // ------------------------------------------------------ Animated counters

  document.querySelectorAll(".stat .value[data-count-to]").forEach(function (el) {
    var target = parseInt(el.getAttribute("data-count-to"), 10) || 0;
    if (target === 0) {
      el.textContent = "0";
      return;
    }
    var start = null;
    var duration = 900;
    function step(ts) {
      if (!start) start = ts;
      var progress = Math.min((ts - start) / duration, 1);
      el.textContent = Math.round(progress * target);
      if (progress < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  });

  // -------------------------------------------------------- Mini match rings

  document.querySelectorAll(".mini-ring-progress").forEach(function (ring) {
    var target = ring.getAttribute("data-offset");
    setTimeout(function () {
      ring.style.strokeDashoffset = target;
    }, 200);
  });

  // ---------------------------------------------------------- Ask Campusly

  var fab = document.getElementById("ai-fab");
  var panel = document.getElementById("ai-panel");
  var closeBtn = document.getElementById("ai-panel-close");
  var form = document.getElementById("ai-form");
  var input = document.getElementById("ai-input");
  var log = document.getElementById("ai-log");

  if (fab && panel) {
    fab.addEventListener("click", function () {
      panel.classList.toggle("open");
      if (panel.classList.contains("open") && input && !input.disabled) {
        input.focus();
      }
    });
  }
  if (closeBtn && panel) {
    closeBtn.addEventListener("click", function () {
      panel.classList.remove("open");
    });
  }

  if (form && input && log) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var question = input.value.trim();
      if (!question) return;

      var qBubble = document.createElement("div");
      qBubble.className = "ai-bubble q";
      qBubble.textContent = question;
      log.appendChild(qBubble);
      input.value = "";
      log.scrollTop = log.scrollHeight;

      var submitBtn = form.querySelector('button[type="submit"]');
      submitBtn.disabled = true;

      var formData = new FormData();
      formData.append("question", question);

      fetch("/assistant/ask", { method: "POST", headers: { "X-CSRFToken": window.CSRF_TOKEN }, body: formData })
        .then(function (response) {
          return response.json().then(function (data) {
            return { ok: response.ok, data: data };
          });
        })
        .then(function (result) {
          submitBtn.disabled = false;
          var aBubble = document.createElement("div");
          aBubble.className = "ai-bubble a";
          if (result.ok && result.data.ok) {
            aBubble.innerHTML = escapeHtml(result.data.answer).replace(/\n/g, "<br>");
            if (result.data.action_url) {
              var actionLink = document.createElement("a");
              actionLink.href = result.data.action_url;
              actionLink.className = "ai-action-btn";
              actionLink.textContent = result.data.action_label || "View";
              aBubble.appendChild(document.createElement("br"));
              aBubble.appendChild(actionLink);
            }
          } else {
            aBubble.textContent = (result.data && result.data.error) || "Could not reach the AI assistant.";
          }
          log.appendChild(aBubble);
          log.scrollTop = log.scrollHeight;
        })
        .catch(function () {
          submitBtn.disabled = false;
          var aBubble = document.createElement("div");
          aBubble.className = "ai-bubble a";
          aBubble.textContent = "Network error. Please try again.";
          log.appendChild(aBubble);
        });
    });
  }
})();
