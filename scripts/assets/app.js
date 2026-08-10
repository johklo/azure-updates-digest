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

  var stages = {};
  var cats = {};
  var defaultDays = root.getAttribute("data-default-days") || "30";

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
  }

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

  document.addEventListener("click", function (event) {
    var action = event.target.getAttribute("data-toggle");
    if (!action) return;
    if (action === "reset") {
      Object.keys(stages).forEach(function (k) { stages[k] = false; });
      Object.keys(cats).forEach(function (k) { cats[k] = false; });
      chips(".chip[data-stage],.chip[data-cat]").forEach(function (c) { c.setAttribute("aria-pressed", "false"); });
      search.value = ""; fromInput.value = ""; toInput.value = "";
      var back = document.querySelector('[data-days="' + defaultDays + '"]');
      if (back) back.click(); else apply();
      return;
    }
    groups.forEach(function (node) { node.open = action === "open"; });
  });

  var preset = document.querySelector('[data-days="' + defaultDays + '"]');
  if (preset) preset.click(); else apply();
})();
