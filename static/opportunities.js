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
})();
