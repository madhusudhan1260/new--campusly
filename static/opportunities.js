(function () {
  "use strict";

  function postJson(url) {
    return fetch(url, { method: "POST", headers: { "X-CSRFToken": window.CSRF_TOKEN } }).then(function (response) {
      return response.json().then(function (data) {
        return { ok: response.ok, data: data };
      });
    });
  }

  document.querySelectorAll(".bookmark-btn").forEach(function (button) {
    button.addEventListener("click", function () {
      button.disabled = true;
      postJson("/opportunities/" + button.getAttribute("data-id") + "/bookmark").then(function (result) {
        button.disabled = false;
        if (result.ok && result.data.ok) {
          button.classList.toggle("saved", result.data.bookmarked);
          button.setAttribute("aria-label", result.data.bookmarked ? "Remove bookmark" : "Save for later");
          button.classList.remove("bump");
          void button.offsetWidth; // restart the animation on repeated clicks
          button.classList.add("bump");
        } else {
          window.alert((result.data && result.data.error) || "Could not update bookmark.");
        }
      });
    });
  });

  document.querySelectorAll(".op-toggle-status").forEach(function (button) {
    button.addEventListener("click", function () {
      button.disabled = true;
      postJson("/opportunities/" + button.getAttribute("data-id") + "/status").then(function (result) {
        if (result.ok && result.data.ok) {
          window.location.reload();
        } else {
          button.disabled = false;
          window.alert((result.data && result.data.error) || "Could not update status.");
        }
      });
    });
  });

  document.querySelectorAll(".op-delete").forEach(function (button) {
    button.addEventListener("click", function () {
      if (!window.confirm("Remove this listing?")) {
        return;
      }
      button.disabled = true;
      postJson("/opportunities/" + button.getAttribute("data-id") + "/delete").then(function (result) {
        if (result.ok && result.data.ok) {
          var card = button.closest(".op-card");
          if (card) {
            card.remove();
          }
        } else {
          button.disabled = false;
          window.alert((result.data && result.data.error) || "Could not remove this listing.");
        }
      });
    });
  });

  // ------------------------------------------------------ Application status

  document.querySelectorAll(".app-status-select").forEach(function (select) {
    select.addEventListener("change", function () {
      var opId = select.getAttribute("data-id");
      var url = select.value
        ? "/opportunities/" + opId + "/application-status"
        : "/opportunities/" + opId + "/application-status/clear";
      var formData = new FormData();
      if (select.value) formData.append("status", select.value);

      fetch(url, { method: "POST", headers: { "X-CSRFToken": window.CSRF_TOKEN }, body: formData })
        .then(function (response) {
          return response.json().then(function (data) {
            return { ok: response.ok, data: data };
          });
        })
        .then(function (result) {
          if (result.ok && result.data.ok) {
            window.location.reload();
          } else {
            window.alert((result.data && result.data.error) || "Could not update status.");
          }
        });
    });
  });

  // -------------------------------------------------------------------- Teams

  document.querySelectorAll(".team-toggle-btn").forEach(function (button) {
    button.addEventListener("click", function () {
      var panel = document.getElementById("teams-" + button.getAttribute("data-id"));
      if (panel) panel.hidden = !panel.hidden;
    });
  });

  document.querySelectorAll(".team-form").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var opId = form.getAttribute("data-id");
      var msg = form.querySelector(".team-msg");
      var submitBtn = form.querySelector('button[type="submit"]');
      submitBtn.disabled = true;

      var formData = new FormData(form);
      fetch("/hackathons/" + opId + "/teams", { method: "POST", headers: { "X-CSRFToken": window.CSRF_TOKEN }, body: formData })
        .then(function (response) {
          return response.json().then(function (data) {
            return { ok: response.ok, data: data };
          });
        })
        .then(function (result) {
          submitBtn.disabled = false;
          if (result.ok && result.data.ok) {
            window.location.reload();
          } else {
            msg.textContent = (result.data && result.data.error) || "Could not create this team.";
            msg.className = "msg err";
          }
        })
        .catch(function () {
          submitBtn.disabled = false;
          msg.textContent = "Network error. Please try again.";
          msg.className = "msg err";
        });
    });
  });

  // ------------------------------------------------------------- Skill gap

  document.querySelectorAll(".skill-gap-toggle-btn").forEach(function (button) {
    button.addEventListener("click", function () {
      var panel = document.getElementById("skill-gap-" + button.getAttribute("data-id"));
      if (panel) panel.hidden = !panel.hidden;
    });
  });

  // -------------------------------------------------------- Interview prep

  function escapeHtml(str) {
    var div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function renderQuestionGroup(title, list) {
    if (!list || !list.length) return "";
    var rows = list
      .map(function (item, i) {
        var qid = "q-" + title.replace(/\s/g, "") + "-" + i;
        return (
          '<div class="interview-q">' +
          "<p><strong>" + escapeHtml(item.q) + "</strong></p>" +
          '<button class="btn ghost small show-answer-btn" type="button" data-target="' + qid + '">Show Answer</button>' +
          '<p class="interview-a" id="' + qid + '" hidden>' + escapeHtml(item.a) + "</p>" +
          "</div>"
        );
      })
      .join("");
    return '<h5>' + title + "</h5>" + rows;
  }

  document.querySelectorAll(".interview-prep-btn").forEach(function (button) {
    button.addEventListener("click", function () {
      var opId = button.getAttribute("data-id");
      var panel = document.getElementById("interview-prep-" + opId);

      if (panel.dataset.loaded === "true") {
        panel.hidden = !panel.hidden;
        return;
      }

      button.disabled = true;
      button.innerHTML = '<span class="spinner"></span> Generating…';

      postJson("/opportunities/" + opId + "/interview-prep").then(function (result) {
        button.disabled = false;
        button.textContent = "📝 Prepare for Interview";
        if (result.ok && result.data.ok) {
          var q = result.data.questions;
          panel.innerHTML =
            renderQuestionGroup("Technical", q.technical) +
            renderQuestionGroup("HR", q.hr) +
            renderQuestionGroup("Company", q.company);
          panel.dataset.loaded = "true";
          panel.hidden = false;
          panel.querySelectorAll(".show-answer-btn").forEach(function (btn) {
            btn.addEventListener("click", function () {
              var answer = document.getElementById(btn.getAttribute("data-target"));
              answer.hidden = !answer.hidden;
              btn.textContent = answer.hidden ? "Show Answer" : "Hide Answer";
            });
          });
        } else {
          panel.innerHTML = '<p class="msg err">' + escapeHtml((result.data && result.data.error) || "Could not generate questions.") + "</p>";
          panel.hidden = false;
        }
      });
    });
  });
})();
