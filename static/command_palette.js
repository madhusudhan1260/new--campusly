(function () {
  "use strict";

  var dataEl = document.getElementById("cmdk-data");
  if (!dataEl) return;
  var data = JSON.parse(dataEl.textContent);

  var overlay = document.getElementById("cmdk-overlay");
  var input = document.getElementById("cmdk-input");
  var list = document.getElementById("cmdk-list");
  var activeIndex = 0;
  var visible = [];

  function render(query) {
    var q = (query || "").trim().toLowerCase();
    visible = q ? data.commands.filter(function (c) { return c.label.toLowerCase().indexOf(q) !== -1; }) : data.commands.slice();
    activeIndex = 0;

    if (visible.length === 0) {
      list.innerHTML = '<div class="cmdk-empty">No matching pages -- press Enter to search "' + escapeHtml(q) + '"</div>';
      return;
    }
    list.innerHTML = visible
      .map(function (c, i) {
        return (
          '<button class="cmdk-item' + (i === 0 ? " active" : "") + '" data-index="' + i + '" data-url="' + c.url + '">' +
          '<span class="cmdk-icon">' + c.icon + "</span>" + escapeHtml(c.label) +
          "</button>"
        );
      })
      .join("");
  }

  function escapeHtml(str) {
    var div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function open() {
    overlay.hidden = false;
    input.value = "";
    render("");
    setTimeout(function () { input.focus(); }, 10);
  }

  function close() {
    overlay.hidden = true;
  }

  function setActive(index) {
    var items = list.querySelectorAll(".cmdk-item");
    items.forEach(function (el) { el.classList.remove("active"); });
    if (items[index]) {
      items[index].classList.add("active");
      items[index].scrollIntoView({ block: "nearest" });
    }
    activeIndex = index;
  }

  function goTo(url) {
    window.location.href = url;
  }

  document.addEventListener("keydown", function (event) {
    var isCmdK = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k";
    if (isCmdK) {
      event.preventDefault();
      overlay.hidden ? open() : close();
      return;
    }
    if (overlay.hidden) return;

    if (event.key === "Escape") {
      close();
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive(Math.min(activeIndex + 1, visible.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive(Math.max(activeIndex - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (visible.length > 0) {
        goTo(visible[activeIndex].url);
      } else if (input.value.trim()) {
        goTo(data.searchUrl + "?q=" + encodeURIComponent(input.value.trim()));
      }
    }
  });

  if (input) {
    input.addEventListener("input", function () { render(input.value); });
  }
  if (overlay) {
    overlay.addEventListener("click", function (event) {
      if (event.target === overlay) close();
    });
  }
  if (list) {
    list.addEventListener("click", function (event) {
      var item = event.target.closest(".cmdk-item");
      if (item) goTo(item.getAttribute("data-url"));
    });
    list.addEventListener("mouseover", function (event) {
      var item = event.target.closest(".cmdk-item");
      if (item) setActive(parseInt(item.getAttribute("data-index"), 10));
    });
  }
})();
