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
})();
