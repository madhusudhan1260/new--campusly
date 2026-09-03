(function () {
  "use strict";

  function setMsg(el, text, ok) {
    el.textContent = text;
    el.className = "msg " + (ok ? "ok" : "err");
  }

  function escapeHtml(str) {
    var div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // ---------------------------------------------------------------- Q&A

  var askForm = document.getElementById("ask-form");
  var qaLog = document.getElementById("qa-log");
  var askMsg = document.getElementById("ask-msg");

  if (askForm) {
    askForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var textarea = document.getElementById("q-question");
      var question = textarea.value.trim();
      if (!question) {
        return;
      }
      var submitBtn = askForm.querySelector('button[type="submit"]');
      submitBtn.disabled = true;
      submitBtn.innerHTML = '<span class="spinner"></span> Asking…';
      setMsg(askMsg, "", true);

      var bubbleQ = document.createElement("div");
      bubbleQ.className = "qa-bubble qa-question";
      bubbleQ.textContent = question;
      qaLog.appendChild(bubbleQ);

      var formData = new FormData();
      formData.append("question", question);

      fetch("/health/ask", { method: "POST", headers: { "X-CSRFToken": window.CSRF_TOKEN }, body: formData })
        .then(function (response) {
          return response.json().then(function (data) {
            return { ok: response.ok, data: data };
          });
        })
        .then(function (result) {
          submitBtn.disabled = false;
          submitBtn.textContent = "Ask";
          if (result.ok && result.data.ok) {
            var bubbleA = document.createElement("div");
            bubbleA.className = "qa-bubble qa-answer";
            bubbleA.innerHTML = escapeHtml(result.data.answer).replace(/\n/g, "<br>");
            qaLog.appendChild(bubbleA);
            qaLog.scrollTop = qaLog.scrollHeight;
            textarea.value = "";
          } else {
            bubbleQ.remove();
            setMsg(askMsg, (result.data && result.data.error) || "Could not get an answer.", false);
          }
        })
        .catch(function () {
          submitBtn.disabled = false;
          submitBtn.textContent = "Ask";
          bubbleQ.remove();
          setMsg(askMsg, "Network error. Please try again.", false);
        });
    });
  }

  // ---------------------------------------------------------- Clinic check

  var clinicForm = document.getElementById("clinic-form");
  var clinicMsg = document.getElementById("clinic-msg");
  var clinicResult = document.getElementById("clinic-result");

  if (clinicForm) {
    clinicForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var formData = new FormData(clinicForm);
      var submitBtn = clinicForm.querySelector('button[type="submit"]');
      submitBtn.disabled = true;
      submitBtn.innerHTML = '<span class="spinner"></span> Checking…';
      setMsg(clinicMsg, "", true);
      clinicResult.innerHTML = "";

      fetch("/health/verify-clinic", { method: "POST", headers: { "X-CSRFToken": window.CSRF_TOKEN }, body: formData })
        .then(function (response) {
          return response.json().then(function (data) {
            return { ok: response.ok, data: data };
          });
        })
        .then(function (result) {
          submitBtn.disabled = false;
          submitBtn.textContent = "Get AI opinion";
          if (result.ok && result.data.ok) {
            var recognised = result.data.recognised;
            var card = document.createElement("div");
            card.className = "clinic-card " + (recognised ? "clinic-known" : "clinic-unknown");
            card.innerHTML =
              '<div class="clinic-card-head">' +
              '<strong>' + escapeHtml(result.data.clinic_name) + '</strong>' +
              '<span class="clinic-badge">' + (recognised ? "Sounds familiar" : "Not recognised") + '</span>' +
              '</div>' +
              '<p>' + escapeHtml(result.data.note) + '</p>' +
              '<p class="hint">Not a live lookup -- verify with the checklist below before you trust this.</p>';
            clinicResult.appendChild(card);
          } else {
            setMsg(clinicMsg, (result.data && result.data.error) || "Could not check this clinic.", false);
          }
        })
        .catch(function () {
          submitBtn.disabled = false;
          submitBtn.textContent = "Get AI opinion";
          setMsg(clinicMsg, "Network error. Please try again.", false);
        });
    });
  }
})();
