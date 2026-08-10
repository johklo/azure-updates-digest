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
    var stageFacet = {};
    var catFacet = {};

    items.forEach(function (el) {
      var stage = el.getAttribute("data-stage");
      var cat = el.getAttribute("data-category");
      var date = el.getAttribute("data-date") || "";
      var hay = el.getAttribute("data-search") || "";

      var okDate = !((from && date && date < from) || (to && date && date > to));
      var okSearch = !q || hay.indexOf(q) !== -1;
      var okStage = !stageOn || stageOn.indexOf(stage) !== -1;
      var okCat = !catOn || catOn.indexOf(cat) !== -1;

      // Facet counts ignore the facet's own selection, so each chip shows how
      // many updates it would add under the other active filters.
      if (okDate && okSearch && okCat) stageFacet[stage] = (stageFacet[stage] || 0) + 1;
      if (okDate && okSearch && okStage) catFacet[cat] = (catFacet[cat] || 0) + 1;

      var ok = okDate && okSearch && okStage && okCat;
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
    updateFacet(".chip[data-stage]", "data-stage", stageFacet, stages);
    updateFacet(".chip[data-cat]", "data-cat", catFacet, cats);
    refreshDeck();
    layoutGrid();
  }

  function updateFacet(selector, attribute, counts, selection) {
    chips(selector).forEach(function (chip) {
      var key = chip.getAttribute(attribute);
      var n = counts[key] || 0;
      var badge = chip.querySelector(".n");
      if (badge) badge.textContent = n;
      chip.classList.toggle("zero", n === 0 && !selection[key]);
    });
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

  function slideData(el) {
    var link = el.querySelector("a.title");
    var pill = el.querySelector(".meta .pill");
    var meta = (el.querySelector(".meta") || { textContent: "" }).textContent.trim();
    var doc = el.querySelector(".doclink a");
    return {
      category: el.getAttribute("data-category") || "",
      stage: pill ? pill.textContent.trim() : "",
      stageClass: pill ? pill.className.replace("pill", "").trim() : "muted",
      date: el.getAttribute("data-date") || "",
      products: meta.split("\u00b7").slice(1).join("\u00b7").trim(),
      title: link ? link.textContent.trim() : "",
      url: link ? link.getAttribute("href") : "",
      summary: textOf(el, ".summary-line"),
      points: Array.prototype.map.call(el.querySelectorAll("ul.points li"), function (li) {
        return li.textContent.trim();
      }),
      docUrl: doc ? doc.getAttribute("href") : "",
      docTitle: doc ? doc.textContent.trim() : ""
    };
  }

  var EXPORT_CSS =
    "*{box-sizing:border-box}" +
    "body{margin:0;background:#eef1f4;color:#1b1f23;font:16px/1.55 'Segoe UI',Helvetica,Arial,sans-serif}" +
    ".cover,.slide-page{background:#fff;width:100%;max-width:1280px;margin:0 auto 18px;padding:56px 64px;" +
    "min-height:calc(100vh - 96px);display:flex;flex-direction:column;box-shadow:0 1px 4px rgba(0,0,0,.12)}" +
    ".cover h1{font-size:38px;margin:0 0 12px;color:#004578}" +
    ".cover p{font-size:16px;color:#57606a;margin:4px 0}" +
    ".cover .meta{margin-top:auto;font-size:13px;color:#57606a}" +
    ".cover ul{columns:2;font-size:14px;color:#333a42;margin:22px 0}" +
    ".eyebrow{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:14px;font-size:13px;color:#57606a}" +
    ".eyebrow .cat{font-weight:700;color:#0078d4;text-transform:uppercase;letter-spacing:.06em;font-size:12px}" +
    ".pill{display:inline-block;border-radius:10px;padding:2px 10px;font-size:11px;font-weight:600;background:#eef0f2;color:#57606a}" +
    ".pill.ga{background:#e8f5ec;color:#0f7b34}.pill.pv{background:#fdf3e0;color:#8a5a00}" +
    ".pill.pp{background:#f2ecfa;color:#6b3fa0}.pill.rt{background:#fdeaec;color:#b02a37}" +
    ".pill.dv{background:#e9f1f8;color:#2b5f8a}" +
    ".body{flex:1;display:flex;flex-direction:column;justify-content:center}" +
    "h2{font-size:31px;line-height:1.24;margin:0 0 18px;font-weight:700;letter-spacing:-.01em}" +
    "h2 a{color:#1b1f23;text-decoration:none}" +
    ".lead{font-size:19px;line-height:1.55;color:#2b3138;margin:0 0 18px;padding-left:14px;border-left:4px solid #0078d4}" +
    "ul.points{margin:0;padding:0;list-style:none}" +
    "ul.points li{position:relative;padding-left:26px;margin:0 0 12px;font-size:16px;line-height:1.5;color:#333a42}" +
    "ul.points li::before{content:'';position:absolute;left:6px;top:.55em;width:8px;height:8px;border-radius:50%;background:#0078d4}" +
    ".foot{margin-top:20px;padding-top:14px;border-top:1px solid #e1e4e8;display:flex;gap:20px;flex-wrap:wrap;font-size:12.5px}" +
    ".foot a{color:#0078d4;text-decoration:none;font-weight:600}" +
    ".num{position:absolute;top:18px;right:26px;font-size:12px;color:#8b949e}" +
    ".slide-page{position:relative}" +
    ".navbar{position:fixed;bottom:0;left:0;right:0;background:#fff;border-top:1px solid #e1e4e8;" +
    "padding:10px 18px;display:flex;gap:12px;align-items:center;justify-content:center;z-index:9}" +
    ".navbar button{cursor:pointer;background:#fff;border:1px solid #e1e4e8;border-radius:6px;padding:7px 16px;" +
    "font:14px 'Segoe UI',Helvetica,Arial,sans-serif;color:#0078d4;font-weight:600}" +
    ".navbar button:disabled{opacity:.4;cursor:not-allowed}" +
    ".navbar .c{font-weight:600;min-width:90px;text-align:center}" +
    "@media screen{body{padding-bottom:70px}.paged .cover,.paged .slide-page{display:none}" +
    ".paged .cover.on,.paged .slide-page.on{display:flex}}" +
    "@media print{@page{size:A4 landscape;margin:11mm}body{background:#fff;padding:0}" +
    ".navbar{display:none}.cover,.slide-page{display:flex !important;max-width:none;margin:0;padding:9mm 11mm;" +
    "min-height:0;height:auto;box-shadow:none;page-break-after:always;break-after:page;" +
    "page-break-inside:avoid;break-inside:avoid}" +
    ".slide-page:last-child{page-break-after:auto;break-after:auto}" +
    "h2{font-size:21pt;margin-bottom:4mm}.lead{font-size:12pt;margin-bottom:4mm;padding-left:3mm}" +
    "ul.points li{font-size:10.5pt;margin-bottom:2.6mm;padding-left:6mm}" +
    "ul.points li::before{width:2mm;height:2mm;left:1.4mm}" +
    ".eyebrow{margin-bottom:3mm;font-size:9pt}.foot{margin-top:4mm;padding-top:2.5mm;font-size:8.5pt}" +
    ".num{top:5mm;right:8mm;font-size:8pt}" +
    ".cover h1{font-size:26pt}.cover p{font-size:11pt}.cover ul{font-size:10pt;margin:6mm 0}}";

  var EXPORT_JS =
    "(function(){var s=[].slice.call(document.querySelectorAll('.cover,.slide-page'));var i=0;" +
    "var c=document.getElementById('c'),p=document.getElementById('p'),n=document.getElementById('n');" +
    "document.body.className='paged';" +
    "function r(){s.forEach(function(e,k){e.classList.toggle('on',k===i)});" +
    "c.textContent=i+' / '+(s.length-1);p.disabled=i===0;n.disabled=i===s.length-1;window.scrollTo(0,0)}" +
    "p.onclick=function(){if(i>0){i--;r()}};n.onclick=function(){if(i<s.length-1){i++;r()}};" +
    "document.addEventListener('keydown',function(e){" +
    "if(e.key==='ArrowRight'||e.key==='PageDown'||e.key===' '){e.preventDefault();n.onclick()}" +
    "else if(e.key==='ArrowLeft'||e.key==='PageUp'){e.preventDefault();p.onclick()}" +
    "else if(e.key==='Home'){i=0;r()}else if(e.key==='End'){i=s.length-1;r()}});r()})();";

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function buildDeckDocument() {
    var data = deckItems.map(slideData);
    var today = new Date().toISOString().slice(0, 10);
    var scope = [];
    var activeStages = activeSet(stages);
    var activeCats = activeSet(cats);
    if (activeStages) scope.push("Release stage: " + activeStages.map(stageName).join(", "));
    if (activeCats) scope.push("Categories: " + activeCats.join(", "));
    if (fromInput.value || toInput.value) scope.push("Dates: " + (fromInput.value || "start") + " to " + (toInput.value || today));
    if (search.value.trim()) scope.push('Search: "' + search.value.trim() + '"');
    if (!scope.length) scope.push("All tracked updates");

    var counts = {};
    data.forEach(function (d) { counts[d.category] = (counts[d.category] || 0) + 1; });

    var html = "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">" +
      '<meta name="viewport" content="width=device-width,initial-scale=1">' +
      "<title>Azure product updates - " + esc(today) + "</title><style>" + EXPORT_CSS + "</style></head><body>";

    html += '<section class="cover"><h1>Azure Product Updates</h1>' +
      "<p>" + data.length + " update(s) &middot; generated " + esc(today) + "</p>" +
      "<p>" + esc(scope.join(" \u00b7 ")) + "</p><ul>";
    Object.keys(counts).forEach(function (k) { html += "<li>" + esc(k) + " &mdash; " + counts[k] + "</li>"; });
    html += '</ul><div class="meta">Source: Microsoft Azure Updates &middot; summaries generated from each announcement and its linked documentation.</div></section>';

    data.forEach(function (d, index) {
      html += '<section class="slide-page"><span class="num">' + (index + 1) + " / " + data.length + "</span>";
      html += '<div class="body"><div class="eyebrow"><span class="cat">' + esc(d.category) + "</span>";
      if (d.stage) html += '<span class="pill ' + esc(d.stageClass) + '">' + esc(d.stage) + "</span>";
      html += "<span>" + esc(d.date) + "</span>";
      if (d.products) html += "<span>" + esc(d.products) + "</span>";
      html += "</div>";
      html += '<h2><a href="' + esc(d.url) + '">' + esc(d.title) + "</a></h2>";
      if (d.summary) html += '<p class="lead">' + esc(d.summary) + "</p>";
      if (d.points.length) {
        html += '<ul class="points">';
        d.points.forEach(function (p) { html += "<li>" + esc(p) + "</li>"; });
        html += "</ul>";
      }
      html += "</div>";
      html += '<div class="foot"><a href="' + esc(d.url) + '">Azure Updates announcement</a>';
      if (d.docUrl) html += '<a href="' + esc(d.docUrl) + '">' + esc(d.docTitle || "Microsoft documentation") + "</a>";
      html += "</div></section>";
    });

    html += '<div class="navbar"><button id="p">&larr; Previous</button>' +
      '<span class="c" id="c"></span><button id="n">Next &rarr;</button>' +
      '<button onclick="window.print()">Save as PDF</button></div>';
    html += "<script>" + EXPORT_JS + "<\/script></body></html>";
    return html;
  }

  function stageName(key) {
    var chip = document.querySelector('.chip[data-stage="' + key + '"]');
    if (!chip) return key;
    return chip.textContent.replace(/\d+$/, "").trim();
  }

  function downloadDeck() {
    if (!deckItems.length) return;
    var blob = new Blob([buildDeckDocument()], { type: "text/html;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = "azure-updates-deck-" + new Date().toISOString().slice(0, 10) + ".html";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
  }

  function printDeck() {
    if (!deckItems.length) return;
    var win = window.open("", "_blank");
    if (!win) { downloadDeck(); return; }
    win.document.open();
    win.document.write(buildDeckDocument());
    win.document.close();
    win.focus();
    setTimeout(function () { win.print(); }, 600);
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

  var dlBtn = document.getElementById("dl");
  if (dlBtn) dlBtn.addEventListener("click", downloadDeck);
  var pdfBtn = document.getElementById("pdf");
  if (pdfBtn) pdfBtn.addEventListener("click", printDeck);

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
