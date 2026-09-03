(function () {
  "use strict";

  function setMsg(el, text, ok) {
    if (!el) return;
    el.textContent = text;
    el.className = "msg " + (ok ? "ok" : "err");
  }

  var feedbackBtn = document.getElementById("feedback-btn");
  var feedbackMsg = document.getElementById("feedback-msg");
  var feedbackResult = document.getElementById("feedback-result");
  var feedbackTarget = document.getElementById("feedback-target");

  if (feedbackBtn) {
    feedbackBtn.addEventListener("click", function () {
      feedbackBtn.disabled = true;
      feedbackBtn.innerHTML = '<span class="spinner"></span> Thinking…';
      setMsg(feedbackMsg, "", true);
      feedbackResult.innerHTML = "";

      var formData = new FormData();
      if (feedbackTarget.value) formData.append("opportunity_id", feedbackTarget.value);

      fetch("/profile/resume-feedback", { method: "POST", headers: { "X-CSRFToken": window.CSRF_TOKEN }, body: formData })
        .then(function (response) {
          return response.json().then(function (data) {
            return { ok: response.ok, data: data };
          });
        })
        .then(function (result) {
          feedbackBtn.disabled = false;
          feedbackBtn.textContent = "Get AI feedback";
          if (result.ok && result.data.ok) {
            var box = document.createElement("div");
            box.className = "clinic-card clinic-known";
            box.innerHTML = "<p>" + result.data.feedback.replace(/\n/g, "<br>") + "</p>";
            feedbackResult.appendChild(box);
          } else {
            setMsg(feedbackMsg, (result.data && result.data.error) || "Could not get feedback.", false);
          }
        })
        .catch(function () {
          feedbackBtn.disabled = false;
          feedbackBtn.textContent = "Get AI feedback";
          setMsg(feedbackMsg, "Network error. Please try again.", false);
        });
    });
  }
})();
