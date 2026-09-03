(function () {
  "use strict";

  function setMsg(el, text, ok) {
    if (!el) return;
    el.textContent = text;
    el.className = "msg " + (ok ? "ok" : "err");
  }

  function escapeHtml(str) {
    var div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function postForm(url, data) {
    var formData = new FormData();
    Object.keys(data || {}).forEach(function (key) {
      formData.append(key, data[key]);
    });
    return fetch(url, { method: "POST", headers: { "X-CSRFToken": window.CSRF_TOKEN }, body: formData }).then(
      function (response) {
        return response.json().then(function (json) {
          return { ok: response.ok, data: json };
        });
      }
    );
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
      if (!question) return;
      var submitBtn = askForm.querySelector('button[type="submit"]');
      submitBtn.disabled = true;
      submitBtn.innerHTML = '<span class="spinner"></span> Asking…';
      setMsg(askMsg, "", true);
      askMsg.classList.remove("visible", "ok", "err");

      var bubbleQ = document.createElement("div");
      bubbleQ.className = "qa-bubble qa-question";
      bubbleQ.textContent = question;
      qaLog.appendChild(bubbleQ);

      postForm("/health/ask", { question: question }).then(function (result) {
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
              '<div class="clinic-card-head"><strong>' +
              escapeHtml(result.data.clinic_name) +
              '</strong><span class="clinic-badge">' +
              (recognised ? "Sounds familiar" : "Not recognised") +
              "</span></div><p>" +
              escapeHtml(result.data.note) +
              '</p><p class="hint">Not a live lookup -- verify with the checklist below before you trust this.</p>';
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

  // ------------------------------------------------------- Wellness ring

  var ring = document.getElementById("wellness-ring");
  if (ring) {
    var targetOffset = ring.getAttribute("data-offset");
    setTimeout(function () {
      ring.style.strokeDashoffset = targetOffset;
    }, 150);
  }

  // ----------------------------------------------------------------- SOS

  var sosOpenBtn = document.getElementById("sos-open-btn");
  var sosFlow = document.getElementById("sos-flow");
  var sosState = { type: null, location: "" };

  function showSosStep(step) {
    document.querySelectorAll(".sos-step").forEach(function (el) {
      el.classList.toggle("active", el.getAttribute("data-step") === step);
    });
  }

  if (sosOpenBtn && sosFlow) {
    sosOpenBtn.addEventListener("click", function () {
      sosFlow.classList.add("open");
      showSosStep("type");
      sosFlow.scrollIntoView({ behavior: "smooth", block: "center" });
    });

    document.querySelectorAll(".sos-type-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        document.querySelectorAll(".sos-type-btn").forEach(function (b) {
          b.classList.remove("selected");
        });
        btn.classList.add("selected");
        sosState.type = btn.getAttribute("data-type");
        showSosStep("location");
      });
    });

    var sosToConfirm = document.getElementById("sos-to-confirm");
    if (sosToConfirm) {
      sosToConfirm.addEventListener("click", function () {
        var loc = document.getElementById("sos-location").value.trim();
        if (!loc) {
          window.alert("Enter your location first.");
          return;
        }
        sosState.location = loc;
        document.getElementById("sos-summary").textContent =
          sosState.type + " at " + sosState.location + ". The campus health team will be notified immediately.";
        showSosStep("confirm");
      });
    }

    var sosCancel = document.getElementById("sos-cancel");
    if (sosCancel) {
      sosCancel.addEventListener("click", function () {
        sosFlow.classList.remove("open");
        showSosStep("type");
        document.querySelectorAll(".sos-type-btn").forEach(function (b) {
          b.classList.remove("selected");
        });
      });
    }

    var sosSend = document.getElementById("sos-send");
    if (sosSend) {
      sosSend.addEventListener("click", function () {
        sosSend.disabled = true;
        sosSend.innerHTML = '<span class="spinner"></span> Sending…';
        postForm("/health/sos", { emergency_type: sosState.type, location: sosState.location }).then(function (
          result
        ) {
          if (result.ok && result.data.ok) {
            showSosStep("sent");
            setTimeout(function () {
              window.location.reload();
            }, 1800);
          } else {
            sosSend.disabled = false;
            sosSend.textContent = "Send SOS";
            window.alert((result.data && result.data.error) || "Could not send SOS. Please try again.");
          }
        });
      });
    }
  }

  document.querySelectorAll(".sos-resolve-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      btn.disabled = true;
      postForm("/health/sos/" + btn.getAttribute("data-id") + "/resolve").then(function (result) {
        if (result.ok && result.data.ok) {
          window.location.reload();
        } else {
          btn.disabled = false;
        }
      });
    });
  });

  // --------------------------------------------------------------- Mood

  var moodMsg = document.getElementById("mood-msg");
  document.querySelectorAll(".mood-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var mood = btn.getAttribute("data-mood");
      postForm("/health/mood", { mood: mood }).then(function (result) {
        if (result.ok && result.data.ok) {
          document.querySelectorAll(".mood-btn").forEach(function (b) {
            b.classList.remove("selected");
          });
          btn.classList.add("selected");
          setMsg(moodMsg, "Thanks for checking in.", true);
        } else {
          setMsg(moodMsg, (result.data && result.data.error) || "Could not save that.", false);
        }
      });
    });
  });

  // ---------------------------------------------------------- Breathing

  var breathingToggle = document.getElementById("breathing-toggle");
  var breathingPanel = document.getElementById("breathing-panel");
  var breathingCircle = document.getElementById("breathing-circle");
  var breathingTimer = null;

  function startBreathing() {
    var inhale = true;
    breathingCircle.textContent = "Breathe in";
    breathingCircle.className = "breathing-circle inhale";
    breathingTimer = setInterval(function () {
      inhale = !inhale;
      breathingCircle.textContent = inhale ? "Breathe in" : "Breathe out";
      breathingCircle.className = "breathing-circle " + (inhale ? "inhale" : "exhale");
    }, 4000);
  }

  function stopBreathing() {
    if (breathingTimer) {
      clearInterval(breathingTimer);
      breathingTimer = null;
    }
  }

  if (breathingToggle) {
    breathingToggle.addEventListener("click", function () {
      var opening = breathingPanel.hidden;
      breathingPanel.hidden = !opening;
      if (opening) {
        startBreathing();
      } else {
        stopBreathing();
      }
    });
  }
  var breathingStop = document.getElementById("breathing-stop");
  if (breathingStop) {
    breathingStop.addEventListener("click", function () {
      stopBreathing();
      breathingPanel.hidden = true;
    });
  }

  // ------------------------------------------------- Counselor / Support toggles

  function wireToggle(toggleId, panelId) {
    var toggle = document.getElementById(toggleId);
    var panel = document.getElementById(panelId);
    if (toggle && panel) {
      toggle.addEventListener("click", function () {
        panel.hidden = !panel.hidden;
      });
    }
  }
  wireToggle("counselor-toggle", "counselor-panel");
  wireToggle("support-toggle", "support-panel");

  var counselorForm = document.getElementById("counselor-form");
  if (counselorForm) {
    counselorForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var note = document.getElementById("counselor-note").value;
      var msg = document.getElementById("counselor-msg");
      postForm("/health/counselor-request", { note: note }).then(function (result) {
        if (result.ok && result.data.ok) {
          setMsg(msg, "Request sent. A counselor will reach out.", true);
          counselorForm.reset();
        } else {
          setMsg(msg, (result.data && result.data.error) || "Could not send that.", false);
        }
      });
    });
  }

  var supportForm = document.getElementById("support-form");
  if (supportForm) {
    supportForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var textarea = supportForm.querySelector("textarea");
      var msg = document.getElementById("support-msg");
      postForm("/health/support", { message: textarea.value }).then(function (result) {
        if (result.ok && result.data.ok) {
          setMsg(msg, "Sent -- anonymously.", true);
          supportForm.reset();
        } else {
          setMsg(msg, (result.data && result.data.error) || "Could not send that.", false);
        }
      });
    });
  }

  // --------------------------------------------------------- Doctors (admin)

  document.querySelectorAll(".doctor-toggle-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      btn.disabled = true;
      postForm("/health/doctors/" + btn.getAttribute("data-id") + "/toggle").then(function (result) {
        if (result.ok && result.data.ok) {
          window.location.reload();
        } else {
          btn.disabled = false;
        }
      });
    });
  });

  // --------------------------------------------------------- Appointments

  var selectedDoctorId = null;
  var selectedSlot = null;

  document.querySelectorAll(".doctor-option").forEach(function (el) {
    el.addEventListener("click", function () {
      document.querySelectorAll(".doctor-option").forEach(function (o) {
        o.classList.remove("selected");
      });
      el.classList.add("selected");
      selectedDoctorId = el.getAttribute("data-doctor-id");
    });
  });

  document.querySelectorAll(".slot-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      document.querySelectorAll(".slot-btn").forEach(function (b) {
        b.classList.remove("selected");
      });
      btn.classList.add("selected");
      selectedSlot = btn.getAttribute("data-slot");
    });
  });

  var apptConfirm = document.getElementById("appt-confirm");
  if (apptConfirm) {
    apptConfirm.addEventListener("click", function () {
      var dateInput = document.getElementById("appt-date");
      var msg = document.getElementById("appt-msg");
      if (!selectedDoctorId) return setMsg(msg, "Choose a doctor.", false);
      if (!dateInput.value) return setMsg(msg, "Choose a date.", false);
      if (!selectedSlot) return setMsg(msg, "Choose a time.", false);

      apptConfirm.disabled = true;
      apptConfirm.innerHTML = '<span class="spinner"></span> Booking…';
      postForm("/health/appointments", { doctor_id: selectedDoctorId, date: dateInput.value, time_slot: selectedSlot }).then(
        function (result) {
          apptConfirm.disabled = false;
          apptConfirm.textContent = "Confirm appointment";
          if (result.ok && result.data.ok) {
            document.getElementById("appt-flow").hidden = true;
            var success = document.getElementById("appt-success");
            success.hidden = false;
            success.innerHTML =
              '<div class="success-panel"><svg class="success-check" viewBox="0 0 52 52"><circle cx="26" cy="26" r="24"></circle><path d="M14 27l7 7 17-17"></path></svg>' +
              '<strong>Appointment Confirmed</strong><p>' +
              escapeHtml(result.data.doctor_name) +
              "<br>" +
              escapeHtml(result.data.date) +
              ", " +
              escapeHtml(result.data.time_slot) +
              "<br>" +
              escapeHtml(result.data.location) +
              "</p></div>";
          } else {
            setMsg(msg, (result.data && result.data.error) || "Could not book that slot.", false);
          }
        }
      );
    });
  }

  // ---------------------------------------------------------- Blood network

  var donorForm = document.getElementById("donor-form");
  if (donorForm) {
    donorForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var msg = document.getElementById("donor-msg");
      var formData = new FormData(donorForm);
      if (!document.getElementById("donor-available").checked) {
        formData.delete("available");
      } else {
        formData.set("available", "on");
      }
      fetch("/health/blood/register", { method: "POST", headers: { "X-CSRFToken": window.CSRF_TOKEN }, body: formData })
        .then(function (response) {
          return response.json();
        })
        .then(function (data) {
          if (data.ok) {
            setMsg(msg, "Saved.", true);
          } else {
            setMsg(msg, data.error || "Could not save that.", false);
          }
        });
    });
  }

  var bloodRequestForm = document.getElementById("blood-request-form");
  if (bloodRequestForm) {
    bloodRequestForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var msg = document.getElementById("blood-request-msg");
      var group = document.getElementById("req-group").value;
      var note = document.getElementById("req-note").value;
      postForm("/health/blood/request", { blood_group: group, note: note }).then(function (result) {
        if (result.ok && result.data.ok) {
          setMsg(msg, result.data.notified + " matching donor(s) notified.", true);
          setTimeout(function () {
            window.location.reload();
          }, 1200);
        } else {
          setMsg(msg, (result.data && result.data.error) || "Could not send that request.", false);
        }
      });
    });
  }

  document.querySelectorAll(".ping-respond-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      btn.disabled = true;
      postForm("/health/blood/ping/" + btn.getAttribute("data-id") + "/respond", {
        decision: btn.getAttribute("data-decision"),
      }).then(function (result) {
        if (result.ok && result.data.ok) {
          var row = btn.closest(".ping-row");
          if (row) row.remove();
        } else {
          btn.disabled = false;
        }
      });
    });
  });

  document.querySelectorAll(".blood-check-responses").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var id = btn.getAttribute("data-id");
      var box = document.getElementById("blood-responses-" + id);
      btn.disabled = true;
      fetch("/health/blood/request/" + id + "/responses")
        .then(function (response) {
          return response.json();
        })
        .then(function (data) {
          btn.disabled = false;
          if (!data.ok) return;
          if (data.donors.length === 0) {
            box.innerHTML = '<p class="hint">No responses yet.</p>';
            return;
          }
          box.innerHTML = data.donors
            .map(function (d) {
              return (
                '<p class="hint">' +
                escapeHtml(d.name) +
                (d.phone ? " &middot; " + escapeHtml(d.phone) : "") +
                (d.location ? " &middot; " + escapeHtml(d.location) : "") +
                "</p>"
              );
            })
            .join("");
        });
    });
  });
})();
