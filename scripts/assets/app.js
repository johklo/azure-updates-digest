(function () {
  var root = document.getElementById("explorer");
  if (!root) return;

  var items = Array.prototype.slice.call(root.querySelectorAll(".item"));
  var groups = Array.prototype.slice.call(root.querySelectorAll(".columns > details"));
  var rows = Array.prototype.slice.call(document.querySelectorAll("table.summary tbody tr"));
  var search = document.getElementById("q");
  var fromInput = document.getElementById("from");
  var toInput = document.getElementById("to");
  var result = document.getElementById("result");
  var empty = document.getElementById("empty");

  var deck = document.getElementById("deck");
  var slide = document.getElementById("slide");
  var counter = document.getElementById("counter");
  var progressBar = document.getElementById("progressbar");
  var prevBtn = document.getElementById("prev");
  var nextBtn = document.getElementById("next");
  var browseOnly = Array.prototype.slice.call(document.querySelectorAll(".browse-only"));
  var view = "browse";
  var deckItems = [];
  var deckIndex = 0;

  var stages = {};
  var cats = {};
  var defaultDays = root.getAttribute("data-default-days") || "30";
  var defaultStage = root.getAttribute("data-default-stage") || "";

  function chips(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }

  function activeSet(map) {
    var on = Object.keys(map).filter(function (k) { return map[k]; });
    return on.length ? on : null;
  }

  function apply() {
    var stageOn = activeSet(stages);
    var catOn = activeSet(cats);
    var q = (search.value || "").trim().toLowerCase();
    var from = fromInput.value || "";
    var to = toInput.value || "";
    var visible = 0;
    var perCat = {};

    items.forEach(function (el) {
      var stage = el.getAttribute("data-stage");
      var cat = el.getAttribute("data-category");
      var date = el.getAttribute("data-date") || "";
      var hay = el.getAttribute("data-search") || "";
      var ok = true;
      if (stageOn && stageOn.indexOf(stage) === -1) ok = false;
      if (ok && catOn && catOn.indexOf(cat) === -1) ok = false;
      if (ok && from && date && date < from) ok = false;
      if (ok && to && date && date > to) ok = false;
      if (ok && q && hay.indexOf(q) === -1) ok = false;
      el.classList.toggle("hidden", !ok);
      if (!ok) return;
      visible++;
      if (!perCat[cat]) perCat[cat] = { n: 0, ga: 0, pv: 0, pp: 0, rt: 0 };
      perCat[cat].n++;
      if (stage === "ga") perCat[cat].ga++;
      else if (stage === "public-preview") perCat[cat].pv++;
      else if (stage === "private-preview") perCat[cat].pp++;
      else if (stage === "retirement") perCat[cat].rt++;
    });

    var maxN = 1;
    Object.keys(perCat).forEach(function (k) { if (perCat[k].n > maxN) maxN = perCat[k].n; });

    groups.forEach(function (node) {
      var cat = node.getAttribute("data-category");
      var stat = perCat[cat];
      node.classList.toggle("hidden", !stat);
      var counter = node.querySelector(".count");
      if (stat && counter) counter.textContent = stat.n + " update(s)";
    });

    var shown = groups.filter(function (n) { return !n.classList.contains("hidden"); });
    if (shown.length && shown.length <= 6) {
      shown.forEach(function (n) { n.open = true; });
    }

    rows.forEach(function (row) {
      var cat = row.getAttribute("data-category");
      var stat = perCat[cat];
      row.classList.toggle("hidden", !stat);
      if (!stat) return;
      row.querySelector(".c-n").innerHTML = "<b>" + stat.n + "</b>";
      row.querySelector(".c-ga").innerHTML = stat.ga ? '<span class="pill ga">' + stat.ga + "</span>" : "";
      row.querySelector(".c-pv").innerHTML = stat.pv ? '<span class="pill pv">' + stat.pv + "</span>" : "";
      row.querySelector(".c-pp").innerHTML = stat.pp ? '<span class="pill pp">' + stat.pp + "</span>" : "";
      row.querySelector(".c-rt").innerHTML = stat.rt ? '<span class="pill rt">' + stat.rt + "</span>" : "";
      var bar = row.querySelector(".bar");
      if (bar) bar.style.width = Math.max(3, Math.round((stat.n / maxN) * 100)) + "%";
    });

    var totals = { n: visible, ga: 0, pv: 0, pp: 0, rt: 0 };
    Object.keys(perCat).forEach(function (k) {
      totals.ga += perCat[k].ga; totals.pv += perCat[k].pv;
      totals.pp += perCat[k].pp; totals.rt += perCat[k].rt;
    });
    var foot = document.getElementById("tfoot");
    if (foot) {
      foot.querySelector(".c-n").textContent = totals.n;
      foot.querySelector(".c-ga").textContent = totals.ga || "";
      foot.querySelector(".c-pv").textContent = totals.pv || "";
      foot.querySelector(".c-pp").textContent = totals.pp || "";
      foot.querySelector(".c-rt").textContent = totals.rt || "";
    }

    result.innerHTML = "Showing <b>" + visible + "</b> of " + items.length + " updates";
    empty.classList.toggle("hidden", visible > 0);
    refreshDeck();
    layoutGrid();
  }

  function refreshDeck() {
    deckItems = items.filter(function (el) { return !el.classList.contains("hidden"); });
    if (deckIndex >= deckItems.length) deckIndex = Math.max(0, deckItems.length - 1);
    if (view === "slides") renderSlide();
  }

  var grid = document.querySelector(".columns");

  function layoutGrid() {
    if (!grid || view === "slides") return;
    var styles = window.getComputedStyle(grid);
    var row = parseFloat(styles.getPropertyValue("grid-auto-rows")) || 8;
    var gap = parseFloat(styles.getPropertyValue("row-gap")) || 16;
    groups.forEach(function (node) {
      if (node.classList.contains("hidden")) return;
      node.style.gridRowEnd = "span " + Math.max(1, Math.ceil((node.getBoundingClientRect().height + gap) / (row + gap)));
    });
  }

  function textOf(el, selector) {
    var node = el.querySelector(selector);
    return node ? node.textContent.trim() : "";
  }

  function renderSlide() {
    if (!deckItems.length) {
      slide.innerHTML = '<div class="empty">No updates match the selected filters.</div>';
      counter.textContent = "0 / 0";
      progressBar.style.width = "0";
      prevBtn.disabled = true;
      nextBtn.disabled = true;
      return;
    }
    var el = deckItems[deckIndex];
    var link = el.querySelector("a.title");
    var pill = el.querySelector(".meta .pill");
    var meta = textOf(el, ".meta");
    var products = meta.split("\u00b7").slice(1).join("\u00b7").trim();
    var lead = textOf(el, ".summary-line");
    var points = Array.prototype.map.call(el.querySelectorAll("ul.points li"), function (li) {
      return li.textContent.trim();
    });
    var doc = el.querySelector(".doclink a");

    var html = '<div class="slide-main"><div class="eyebrow"><span class="cat">' + esc(el.getAttribute("data-category")) + "</span>";
    if (pill) html += '<span class="pill ' + pill.className.replace("pill", "").trim() + '">' + esc(pill.textContent) + "</span>";
    html += "<span>" + esc(el.getAttribute("data-date")) + "</span>";
    if (products) html += "<span>" + esc(products) + "</span>";
    html += "</div>";
    html += '<h3><a href="' + esc(link.getAttribute("href")) + '" target="_blank" rel="noopener">' + esc(link.textContent) + "</a></h3>";
    if (lead) html += '<p class="lead">' + esc(lead) + "</p>";
    if (points.length) {
      html += '<ul class="deck-points">';
      points.forEach(function (p) { html += "<li>" + esc(p) + "</li>"; });
      html += "</ul>";
    }
    html += '</div><div class="slide-foot"><a href="' + esc(link.getAttribute("href")) + '" target="_blank" rel="noopener">Azure Updates announcement</a>';
    if (doc) html += '<a href="' + esc(doc.getAttribute("href")) + '" target="_blank" rel="noopener">&#128196; ' + esc(doc.textContent) + "</a>";
    html += "</div>";

    slide.innerHTML = html;
    slide.scrollTop = 0;
    counter.textContent = deckIndex + 1 + " / " + deckItems.length;
    progressBar.style.width = Math.round(((deckIndex + 1) / deckItems.length) * 1000) / 10 + "%";
    prevBtn.disabled = deckIndex === 0;
    nextBtn.disabled = deckIndex === deckItems.length - 1;
    fitSlide();
  }

  function sizeDeck() {
    if (view !== "slides") return;
    if (document.fullscreenElement === deck) {
      deck.style.removeProperty("--deck-h");
      return;
    }
    var top = deck.getBoundingClientRect().top + (window.pageYOffset || 0);
    var available = (window.innerHeight || 800) - 28;
    deck.style.setProperty("--deck-h", Math.max(340, Math.round(available)) + "px");
    if (top > 0 && window.scrollTo) window.scrollTo({ top: top - 8, behavior: "auto" });
  }

  function fitSlide() {
    if (!deckItems.length || typeof slide.scrollHeight !== "number") return;
    var scale = 1;
    slide.style.setProperty("--fit", scale);
    for (var i = 0; i < 12 && scale > 0.62 && slideOverflows(); i++) {
      scale = Math.round((scale - 0.045) * 1000) / 1000;
      slide.style.setProperty("--fit", scale);
    }
  }

  function slideOverflows() {
    var main = slide.querySelector(".slide-main");
    if (main && main.scrollHeight > main.clientHeight + 2) return true;
    return slide.scrollHeight > slide.clientHeight + 2;
  }

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function move(step) {
    if (!deckItems.length) return;
    var next = deckIndex + step;
    if (next < 0 || next >= deckItems.length) return;
    deckIndex = next;
    renderSlide();
  }

  function setView(next) {
    view = next;
    chips("[data-view]").forEach(function (b) {
      b.setAttribute("aria-pressed", b.getAttribute("data-view") === next ? "true" : "false");
    });
    deck.classList.toggle("hidden", next !== "slides");
    browseOnly.forEach(function (node) { node.classList.toggle("hidden", next === "slides"); });
    if (next === "slides") { deckIndex = 0; sizeDeck(); renderSlide(); }
    else { deck.style.removeProperty("--deck-h"); layoutGrid(); }
  }

  groups.forEach(function (node) {
    node.addEventListener("toggle", layoutGrid);
  });

  var resizeTimer = null;
  window.addEventListener("resize", function () {
    if (resizeTimer) clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      if (view === "slides") { sizeDeck(); fitSlide(); }
      else layoutGrid();
    }, 120);
  });

  document.addEventListener("fullscreenchange", function () {
    sizeDeck();
    fitSlide();
  });

  chips(".chip[data-stage]").forEach(function (chip) {
    chip.addEventListener("click", function () {
      var key = chip.getAttribute("data-stage");
      stages[key] = !stages[key];
      chip.setAttribute("aria-pressed", stages[key] ? "true" : "false");
      apply();
    });
  });

  chips(".chip[data-cat]").forEach(function (chip) {
    chip.addEventListener("click", function () {
      var key = chip.getAttribute("data-cat");
      cats[key] = !cats[key];
      chip.setAttribute("aria-pressed", cats[key] ? "true" : "false");
      apply();
    });
  });

  chips("[data-days]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var days = parseInt(btn.getAttribute("data-days"), 10);
      chips("[data-days]").forEach(function (b) { b.setAttribute("aria-pressed", "false"); });
      btn.setAttribute("aria-pressed", "true");
      if (!days) { fromInput.value = ""; toInput.value = ""; }
      else {
        var d = new Date();
        toInput.value = "";
        d.setDate(d.getDate() - days);
        fromInput.value = d.toISOString().slice(0, 10);
      }
      apply();
    });
  });

  [search, fromInput, toInput].forEach(function (el) {
    el.addEventListener("input", function () {
      if (el !== search) {
        chips("[data-days]").forEach(function (b) { b.setAttribute("aria-pressed", "false"); });
      }
      apply();
    });
  });

  chips("[data-view]").forEach(function (btn) {
    btn.addEventListener("click", function () { setView(btn.getAttribute("data-view")); });
  });

  prevBtn.addEventListener("click", function () { move(-1); });
  nextBtn.addEventListener("click", function () { move(1); });

  var fsBtn = document.getElementById("fs");
  if (fsBtn) {
    fsBtn.addEventListener("click", function () {
      if (document.fullscreenElement) {
        if (document.exitFullscreen) document.exitFullscreen();
      } else if (deck.requestFullscreen) {
        deck.requestFullscreen();
      }
    });
  }

  document.addEventListener("keydown", function (event) {
    if (view !== "slides") return;
    var tag = (event.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea") return;
    if (event.key === "ArrowRight" || event.key === "PageDown" || event.key === " ") { event.preventDefault(); move(1); }
    else if (event.key === "ArrowLeft" || event.key === "PageUp") { event.preventDefault(); move(-1); }
    else if (event.key === "Home") { deckIndex = 0; renderSlide(); }
    else if (event.key === "End") { deckIndex = Math.max(0, deckItems.length - 1); renderSlide(); }
    else if (event.key === "Escape" && !document.fullscreenElement) setView("browse");
  });

  function applyDefaults() {
    Object.keys(stages).forEach(function (k) { stages[k] = false; });
    Object.keys(cats).forEach(function (k) { cats[k] = false; });
    chips(".chip[data-stage],.chip[data-cat]").forEach(function (c) { c.setAttribute("aria-pressed", "false"); });
    search.value = ""; fromInput.value = ""; toInput.value = "";
    if (defaultStage) {
      stages[defaultStage] = true;
      var chip = document.querySelector('.chip[data-stage="' + defaultStage + '"]');
      if (chip) chip.setAttribute("aria-pressed", "true");
    }
    var preset = document.querySelector('[data-days="' + defaultDays + '"]');
    if (preset) preset.click(); else apply();
  }

  document.addEventListener("click", function (event) {
    var action = event.target.getAttribute("data-toggle");
    if (!action) return;
    if (action === "reset") {
      applyDefaults();
      return;
    }
    groups.forEach(function (node) { node.open = action === "open"; });
  });

  applyDefaults();
  if (window.requestAnimationFrame) window.requestAnimationFrame(layoutGrid);
})();
