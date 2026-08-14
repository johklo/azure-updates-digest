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
  var langBar = document.getElementById("langs");
  var view = "browse";
  var deckItems = [];
  var deckIndex = 0;
  var lang = "both";
  var LANG_KEY = "azupdates.deck.lang";

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
      if (bar) bar.style.transform = "scaleX(" + Math.max(0.03, stat.n / maxN) + ")";
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
    syncLangBar();
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
      progressBar.style.transform = "scaleX(0)";
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
    var doc = el.querySelector(".doclink a");
    var title = link.textContent.trim();
    var titleKo = textOf(el, ".title-ko");
    var leadKo = textOf(el, ".summary-line-ko");
    var points = pointsOf(el);

    // 병기 leads with Korean and sets English underneath; an update with no translation
    // falls back to English as the primary line and drops the secondary one entirely.
    var pair = languagePair(!!titleKo);
    var headline = pair.primary === "ko" && titleKo ? titleKo : title;
    var headlineAlt = pair.secondary && titleKo ? title : "";

    var html = '<div class="slide-head"><span class="mast">Azure Product Updates</span>' +
      '<span class="folio"><b>' + pad2(deckIndex + 1) + "</b> / " + pad2(deckItems.length) + "</span></div>";

    html += '<div class="slide-main' + (points.length ? "" : " single") + '"><div class="lede">';
    html += '<p class="kicker">' + esc(el.getAttribute("data-category")) + "</p>";
    html += '<h3' + (headline === titleKo ? ' lang="ko"' : "") + '><a href="' +
      esc(link.getAttribute("href")) + '" target="_blank" rel="noopener">' + esc(headline) + "</a>";
    if (headlineAlt) html += '<span class="alt">' + esc(headlineAlt) + "</span>";
    html += "</h3>";

    var leadPrimary = pair.primary === "ko" && leadKo ? leadKo : lead;
    var leadAlt = pair.secondary && leadKo && lead ? lead : "";
    if (leadPrimary) {
      html += '<p class="lead"' + (leadPrimary === leadKo ? ' lang="ko"' : "") + ">" +
        esc(leadPrimary) + "</p>";
    }
    if (leadAlt) html += '<p class="lead alt">' + esc(leadAlt) + "</p>";

    html += '<p class="byline">';
    if (pill) html += '<span class="stage ' + esc(pill.className.replace("pill", "").trim()) + '">' + esc(pill.textContent) + "</span>";
    html += "<span>" + esc(el.getAttribute("data-date")) + "</span>";
    if (products) html += "<span>" + esc(products) + "</span>";
    html += "</p></div>";

    if (points.length) {
      html += '<div class="notes"><ol class="deck-points">';
      points.forEach(function (p) {
        var main = pair.primary === "ko" && p.ko ? p.ko : p.en;
        var alt = pair.secondary && p.ko ? p.en : "";
        html += "<li><span" + (main === p.ko ? ' lang="ko"' : "") + ">" + esc(main) + "</span>";
        if (alt) html += '<span class="alt">' + esc(alt) + "</span>";
        html += "</li>";
      });
      html += "</ol></div>";
    }
    html += "</div>";

    html += '<div class="slide-foot"><a href="' + esc(link.getAttribute("href")) + '" target="_blank" rel="noopener">Announcement</a>';
    if (doc) html += '<a href="' + esc(doc.getAttribute("href")) + '" target="_blank" rel="noopener">' + esc(doc.textContent) + "</a>";
    html += "</div>";

    // Korean says the same thing in far fewer characters, so it needs its own step-down point.
    var longAt = headline === titleKo ? 34 : 62;
    slide.classList.toggle("long", headline.length > longAt);
    slide.classList.toggle("bilingual", !!(headlineAlt || leadAlt));
    slide.innerHTML = html;
    slide.scrollTop = 0;
    counter.textContent = pad2(deckIndex + 1) + " / " + pad2(deckItems.length);
    progressBar.style.transform = "scaleX(" + (deckIndex + 1) / deckItems.length + ")";
    prevBtn.disabled = deckIndex === 0;
    nextBtn.disabled = deckIndex === deckItems.length - 1;
    fitSlide();
  }

  function pointsOf(el) {
    return Array.prototype.map.call(el.querySelectorAll("ul.points li"), function (li) {
      var en = li.querySelector(".en");
      var ko = li.querySelector(".ko");
      return {
        en: en ? en.textContent.trim() : li.textContent.trim(),
        ko: ko ? ko.textContent.trim() : ""
      };
    });
  }
  function hasKorean() {
    return deckItems.some(function (el) { return !!el.querySelector(".title-ko, .summary-line-ko, ul.points .ko"); });
  }

  // `lang` is the user's preference and survives filter changes; the effective mode falls back
  // to English whenever the current result set carries no Korean at all.
  function effectiveLang() {
    return hasKorean() ? lang : "en";
  }

  // Which language leads, and whether a second one follows. 병기 leads with Korean because a
  // Korean reader should not have to read past English to reach their own language; an update
  // with no translation quietly falls back to English alone.
  function languagePair(hasKo) {
    var mode = effectiveLang();
    if (mode === "en" || !hasKo) return { primary: "en", secondary: false };
    if (mode === "ko") return { primary: "ko", secondary: false };
    return { primary: "ko", secondary: true };
  }

  function syncLangBar() {
    if (!langBar) return;
    langBar.classList.toggle("hidden", !hasKorean());
    chips("#langs .lang").forEach(function (btn) {
      btn.setAttribute("aria-pressed", btn.getAttribute("data-lang") === lang ? "true" : "false");
    });
  }

  function setLang(next) {
    if (next === lang) return;
    lang = next;
    try { window.localStorage.setItem(LANG_KEY, lang); } catch (e) { /* private mode */ }
    syncLangBar();
    renderSlide();
  }

  function pad2(n) {
    return (n < 10 ? "0" : "") + n;
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
    // Bilingual slides carry about twice the copy, so they are allowed to shrink further
    // before the deck gives up and lets the slide scroll.
    var floor = slide.classList.contains("bilingual") ? 0.44 : 0.62;
    var scale = 1;
    slide.style.setProperty("--fit", scale);
    for (var i = 0; i < 20 && scale > floor && slideOverflows(); i++) {
      scale = Math.round((scale - 0.04) * 1000) / 1000;
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
    var points = pointsOf(el);
    var titleKo = textOf(el, ".title-ko");
    var leadKo = textOf(el, ".summary-line-ko");
    var title = link ? link.textContent.trim() : "";
    var summary = textOf(el, ".summary-line");
    var pair = languagePair(!!titleKo);
    var koLeads = pair.primary === "ko";

    return {
      category: el.getAttribute("data-category") || "",
      stage: pill ? pill.textContent.trim() : "",
      stageClass: pill ? pill.className.replace("pill", "").trim() : "muted",
      date: el.getAttribute("data-date") || "",
      products: meta.split("\u00b7").slice(1).join("\u00b7").trim(),
      // `title` / `summary` / `points` are always the leading language; the *Alt fields carry
      // the second one, so every export renders the pair in the same order the deck does.
      title: koLeads && titleKo ? titleKo : title,
      titleAlt: pair.secondary && titleKo ? title : "",
      titleLeadsKo: koLeads && !!titleKo,
      url: link ? link.getAttribute("href") : "",
      summary: koLeads && leadKo ? leadKo : summary,
      summaryAlt: pair.secondary && leadKo && summary ? summary : "",
      points: points.map(function (p) { return koLeads && p.ko ? p.ko : p.en; }),
      pointsAlt: points.map(function (p) { return pair.secondary && p.ko ? p.en : ""; }),
      docUrl: doc ? doc.getAttribute("href") : "",
      docTitle: doc ? doc.textContent.trim() : ""
    };
  }

  var EXPORT_CSS =
    "@import url('https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600" +
    "&family=IBM+Plex+Sans:wght@400;600&family=JetBrains+Mono:wght@400;500" +
    "&family=Noto+Serif+KR:wght@400;500&family=Noto+Sans+KR:wght@400;500&display=swap');" +
    ":root{--paper:oklch(97.5% 0.006 252);--paper-2:oklch(94.6% 0.009 252);" +
    "--rule:oklch(87% 0.014 252);--rule-strong:oklch(72% 0.022 252);--muted:oklch(52% 0.024 252);" +
    "--ink-2:oklch(38% 0.026 252);--ink:oklch(23% 0.028 252);--accent:oklch(50% 0.152 252);" +
    "--cover:oklch(26% 0.055 252);--cover-ink:oklch(95% 0.012 252);--cover-muted:oklch(74% 0.03 252);" +
    "--cover-rule:oklch(45% 0.05 252);--cover-rule-2:oklch(35% 0.05 252);" +
    "--ga:oklch(45% 0.12 150);--pv:oklch(50% 0.11 70);--pp:oklch(45% 0.15 300);" +
    "--rt:oklch(48% 0.16 25);--dv:oklch(46% 0.09 235);" +
    "--display:'Newsreader',ui-serif,'Noto Serif KR',Cambria,Georgia,serif;" +
    "--body:'IBM Plex Sans',ui-sans-serif,'Noto Sans KR','Segoe UI',Helvetica,sans-serif;" +
    "--outlier:'JetBrains Mono',ui-monospace,Consolas,monospace;" +
    "--ease-out:cubic-bezier(.16,1,.3,1)}" +
    "*{box-sizing:border-box}html,body{overflow-x:clip}" +
    "body{margin:0;background:var(--paper-2);color:var(--ink);font:16px/1.55 var(--body)}" +
    ".cover,.slide-page{background:var(--paper);width:100%;max-width:1280px;margin:0 auto 20px;" +
    "padding:52px 68px 34px;min-height:calc(100vh - 96px);display:flex;flex-direction:column}" +
    /* running head */
    ".head{flex:none;display:flex;align-items:baseline;justify-content:space-between;gap:16px;" +
    "padding-bottom:8px;border-bottom:1px solid var(--rule-strong);box-shadow:0 3px 0 -2px var(--rule);" +
    "font-family:var(--outlier);font-size:10.5px;letter-spacing:.18em;text-transform:uppercase;color:var(--muted)}" +
    ".head .mast{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}" +
    ".head .folio{font-variant-numeric:tabular-nums;white-space:nowrap}" +
    ".head .folio b{color:var(--ink);font-weight:500}" +
    /* cover */
    ".cover{background:var(--cover);color:var(--cover-ink)}" +
    ".cover .head{color:var(--cover-muted);border-bottom-color:var(--cover-muted);" +
    "box-shadow:0 3px 0 -2px var(--cover-rule)}" +
    ".cover .head .folio b{color:var(--cover-ink)}" +
    ".cover .masthead{flex:1;display:flex;flex-direction:column;justify-content:center;padding:34px 0}" +
    ".cover h1{font-family:var(--display);font-size:58px;font-weight:500;line-height:1.02;" +
    "letter-spacing:-.025em;margin:0;max-width:16ch}" +
    ".cover .issue{margin:22px 0 0;padding-top:14px;border-top:1px solid var(--cover-rule);" +
    "font-family:var(--outlier);font-size:11.5px;letter-spacing:.16em;text-transform:uppercase;" +
    "color:var(--cover-muted)}" +
    ".cover .scope{margin:14px 0 0;max-width:62ch;font-family:var(--display);font-size:17px;" +
    "line-height:1.5;color:var(--cover-ink)}" +
    ".cover .index{margin:30px 0 0;padding:0;list-style:none;columns:2;column-gap:56px;" +
    "font-family:var(--outlier);font-size:12px;letter-spacing:.04em}" +
    ".cover .index li{display:flex;align-items:baseline;gap:6px;padding:7px 0;break-inside:avoid;" +
    "border-bottom:1px solid var(--cover-rule-2);color:var(--cover-ink)}" +
    ".cover .index .dots{flex:1;border-bottom:1px dotted var(--cover-muted);transform:translateY(-3px)}" +
    ".cover .index .n{font-variant-numeric:tabular-nums;color:var(--cover-muted)}" +
    ".cover .colophon{flex:none;padding-top:12px;border-top:1px solid var(--cover-rule);" +
    "font-family:var(--outlier);font-size:10px;letter-spacing:.08em;color:var(--cover-muted)}" +
    /* slide body — split studio */
    ".body{flex:1;min-height:0;display:grid;align-content:center;align-content:safe center;" +
    "grid-template-columns:1.06fr .94fr;column-gap:56px;row-gap:24px;padding:34px 0 26px}" +
    ".body.single{grid-template-columns:minmax(0,1fr) minmax(0,.3fr)}" +
    ".lede,.notes{min-width:0}" +
    ".kicker{margin:0 0 14px;font-family:var(--outlier);font-size:11px;font-weight:500;" +
    "letter-spacing:.2em;text-transform:uppercase;color:var(--accent)}" +
    "h2{margin:0;font-family:var(--display);font-size:40px;font-weight:500;line-height:1.08;" +
    "letter-spacing:-.02em;overflow-wrap:anywhere}" +
    ".long h2{font-size:32px}" +
    "h2 a{color:var(--ink);text-decoration:none}" +
    /* Korean leads at display size, so it needs looser leading and near-zero tracking; the
       English line follows one step down. */
    "h2:lang(ko){letter-spacing:-.005em;line-height:1.24;word-break:keep-all}" +
    "h2 .alt{display:block;margin-top:.3em;font-size:.62em;font-weight:400;line-height:1.24;" +
    "letter-spacing:-.015em;color:var(--ink-2)}" +
    ".lead{margin:16px 0 0;max-width:46ch;font-family:var(--display);font-size:18.5px;" +
    "line-height:1.5;color:var(--ink-2)}" +
    ".lead:lang(ko){line-height:1.6;word-break:keep-all}" +
    ".lead.alt{margin-top:7px;font-size:15.5px;line-height:1.5;color:var(--muted)}" +
    ".byline{display:flex;align-items:center;flex-wrap:wrap;gap:9px 20px;margin:26px 0 0;padding-top:13px;" +
    "border-top:1px solid var(--rule);font-family:var(--outlier);font-size:11px;letter-spacing:.06em;color:var(--muted)}" +
    ".byline .stage{display:inline-flex;align-items:center;gap:7px;font-weight:500;letter-spacing:.12em;" +
    "text-transform:uppercase}" +
    ".byline .stage::before{content:'';width:8px;height:8px;background:currentColor}" +
    ".byline .stage.ga{color:var(--ga)}.byline .stage.pv{color:var(--pv)}.byline .stage.pp{color:var(--pp)}" +
    ".byline .stage.rt{color:var(--rt)}.byline .stage.dv{color:var(--dv)}.byline .stage.muted{color:var(--muted)}" +
    "ol.points{margin:0;padding:14px 0 0;list-style:none;counter-reset:pt;border-top:2px solid var(--ink)}" +
    "ol.points li{counter-increment:pt;display:grid;grid-template-columns:36px minmax(0,1fr);" +
    "align-items:baseline;gap:0 6px;padding:11px 0;border-bottom:1px solid var(--rule);" +
    "font-size:15px;line-height:1.5;color:var(--ink-2)}" +
    "ol.points li:last-child{border-bottom:none}" +
    "ol.points li:lang(ko){word-break:keep-all}" +
    "ol.points li .alt{display:block;grid-column:2;margin-top:4px;font-size:13.5px;" +
    "line-height:1.5;color:var(--muted)}" +
    "ol.points li::before{content:counter(pt,decimal-leading-zero);font-family:var(--outlier);" +
    "font-size:11px;font-weight:500;letter-spacing:.08em;font-variant-numeric:tabular-nums;color:var(--accent)}" +
    ".foot{flex:none;display:flex;gap:26px;flex-wrap:wrap;align-items:baseline;padding-top:13px;" +
    "border-top:1px solid var(--rule-strong);font-family:var(--outlier);font-size:10.5px;" +
    "letter-spacing:.08em;color:var(--muted)}" +
    ".foot a{color:var(--accent);text-decoration:none;box-shadow:inset 0 -1px 0 var(--rule-strong)}" +
    /* pager */
    ".navbar{position:fixed;bottom:0;left:0;right:0;background:var(--paper-2);" +
    "border-top:1px solid var(--rule);padding:11px 18px;display:flex;gap:18px;align-items:center;" +
    "justify-content:center;z-index:200;font-family:var(--outlier);font-size:11.5px;letter-spacing:.1em;" +
    "text-transform:uppercase}" +
    ".navbar button{cursor:pointer;background:none;border:1px solid var(--rule-strong);border-radius:0;" +
    "padding:7px 14px;font:inherit;color:var(--ink);transition:border-color .22s var(--ease-out),color .22s var(--ease-out)}" +
    ".navbar button:hover{border-color:var(--accent);color:var(--accent)}" +
    ".navbar button:focus-visible{outline:2px solid var(--accent);outline-offset:3px}" +
    ".navbar button:disabled{border-color:var(--rule);color:var(--rule-strong);cursor:not-allowed}" +
    ".navbar .c{font-variant-numeric:tabular-nums;letter-spacing:.14em;min-width:92px;text-align:center}" +
    "@media screen{body{padding-bottom:74px}.paged .cover,.paged .slide-page{display:none}" +
    ".paged .cover.on,.paged .slide-page.on{display:flex}}" +
    "@media screen and (max-width:820px){.body,.body.single{grid-template-columns:minmax(0,1fr);align-content:start}" +
    ".cover h1{font-size:38px}.cover .index{columns:1}h2{font-size:29px}.long h2{font-size:25px}" +
    ".cover,.slide-page{padding:30px 24px 24px}}" +
    "@media (prefers-reduced-motion:reduce){*{transition-duration:1ms !important}}" +
    "@media print{@page{size:A4 landscape;margin:9mm}body{background:var(--paper);padding:0}" +
    ".navbar{display:none}.cover,.slide-page{display:flex !important;max-width:none;margin:0;" +
    "padding:8mm 11mm 6mm;min-height:185mm;height:185mm;page-break-after:always;break-after:page;" +
    "page-break-inside:avoid;break-inside:avoid}" +
    ".slide-page:last-child{page-break-after:auto;break-after:auto}" +
    ".body{grid-template-columns:1.06fr .94fr}" +
    ".body.single{grid-template-columns:minmax(0,1fr) minmax(0,.3fr)}" +
    ".head{font-size:7.5pt;padding-bottom:1.5mm}" +
    ".body{padding:6mm 0 5mm;column-gap:9mm}" +
    ".kicker{font-size:7.5pt;margin-bottom:2.5mm}" +
    "h2{font-size:20pt}.long h2{font-size:16pt}" +
    "h2 .alt{font-size:12pt;margin-top:1.8mm}" +
    ".lead{font-size:11pt;margin-top:3mm}" +
    ".lead.alt{font-size:9.5pt;margin-top:1.6mm}" +
    ".byline{font-size:7.5pt;margin-top:4mm;padding-top:2.2mm}" +
    "ol.points li{font-size:9.5pt;padding:2mm 0;grid-template-columns:8mm minmax(0,1fr)}" +
    "ol.points li::before{font-size:7.5pt}" +
    "ol.points li .alt{font-size:8.5pt;margin-top:1mm}" +
    ".foot{font-size:7pt;padding-top:2.2mm}" +
    ".cover h1{font-size:34pt}.cover .issue{font-size:8.5pt}.cover .scope{font-size:11pt}" +
    ".cover .index{font-size:8.5pt;margin-top:6mm}}";

  var EXPORT_JS =
    "(function(){var s=[].slice.call(document.querySelectorAll('.cover,.slide-page'));var i=0;" +
    "var c=document.getElementById('c'),p=document.getElementById('p'),n=document.getElementById('n');" +
    "document.body.className='paged';var q=function(n){return(n<10?'0':'')+n};" +
    "function r(){s.forEach(function(e,k){e.classList.toggle('on',k===i)});" +
    "c.textContent=(i===0?'Cover':q(i)+' / '+q(s.length-1));p.disabled=i===0;n.disabled=i===s.length-1;window.scrollTo(0,0)}" +
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
    var meta = deckMeta();
    var total = data.length;

    var html = "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">" +
      '<meta name="viewport" content="width=device-width,initial-scale=1">' +
      "<title>Azure product updates \u2014 " + esc(meta.date) + "</title><style>" + EXPORT_CSS + "</style></head><body>";

    html += '<section class="cover">' +
      '<div class="head"><span class="mast">Azure Product Updates</span>' +
      '<span class="folio">Cover</span></div>' +
      '<div class="masthead"><h1>Azure Product Updates</h1>' +
      '<p class="issue">No. ' + esc(meta.date) + " &middot; " + total + " update" + (total === 1 ? "" : "s") + "</p>" +
      '<p class="scope">' + esc(meta.scope) + "</p><ul class=\"index\">";
    meta.categories.forEach(function (entry) {
      html += "<li><span>" + esc(entry[0]) + '</span><span class="dots"></span><span class="n">' +
        (entry[1] < 10 ? "0" : "") + entry[1] + "</span></li>";
    });
    html += "</ul></div>" +
      '<div class="colophon">Source: Microsoft Azure Updates &middot; summaries generated from each announcement and its linked documentation.</div>' +
      "</section>";

    data.forEach(function (d, index) {
      var long = d.title.length > 62;
      html += '<section class="slide-page' + (long ? " long" : "") + '">' +
        '<div class="head"><span class="mast">Azure Product Updates</span>' +
        '<span class="folio"><b>' + pad2(index + 1) + "</b> / " + pad2(total) + "</span></div>";
      html += '<div class="body' + (d.points.length ? "" : " single") + '"><div class="lede">';
      html += '<p class="kicker">' + esc(d.category) + "</p>";
      html += '<h2' + (d.titleLeadsKo ? ' lang="ko"' : "") + '><a href="' + esc(d.url) + '">' +
        esc(d.title) + "</a>";
      if (d.titleAlt) html += '<span class="alt">' + esc(d.titleAlt) + "</span>";
      html += "</h2>";
      if (d.summary) html += '<p class="lead">' + esc(d.summary) + "</p>";
      if (d.summaryAlt) html += '<p class="lead alt">' + esc(d.summaryAlt) + "</p>";
      html += '<p class="byline">';
      if (d.stage) html += '<span class="stage ' + esc(d.stageClass) + '">' + esc(d.stage) + "</span>";
      html += "<span>" + esc(d.date) + "</span>";
      if (d.products) html += "<span>" + esc(d.products) + "</span>";
      html += "</p></div>";
      if (d.points.length) {
        html += '<div class="notes"><ol class="points">';
        d.points.forEach(function (p, i) {
          html += "<li><span>" + esc(p) + "</span>";
          if (d.pointsAlt[i]) html += '<span class="alt">' + esc(d.pointsAlt[i]) + "</span>";
          html += "</li>";
        });
        html += "</ol></div>";
      }
      html += "</div>";
      html += '<div class="foot"><a href="' + esc(d.url) + '">Announcement</a>';
      if (d.docUrl) html += '<a href="' + esc(d.docUrl) + '">' + esc(d.docTitle || "Microsoft documentation") + "</a>";
      html += "</div></section>";
    });

    html += '<div class="navbar"><button id="p">&larr; Prev</button>' +
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

  function downloadBlob(blob, filename) {
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
  }

  function deckMeta() {
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
    deckItems.forEach(function (el) {
      var cat = el.getAttribute("data-category");
      counts[cat] = (counts[cat] || 0) + 1;
    });
    return {
      date: today,
      scope: scope.join("   \u00b7   "),
      categories: Object.keys(counts).map(function (k) { return [k, counts[k]]; })
        .sort(function (a, b) { return b[1] - a[1]; })
    };
  }

  function fileStem() {
    return "azure-updates-deck-" + new Date().toISOString().slice(0, 10);
  }

  function downloadPptx() {
    if (!deckItems.length) return;
    if (typeof window.buildPptx !== "function") { downloadDeck(); return; }
    downloadBlob(window.buildPptx(deckItems.map(slideData), deckMeta()), fileStem() + ".pptx");
  }

  function downloadDeck() {
    if (!deckItems.length) return;
    downloadBlob(new Blob([buildDeckDocument()], { type: "text/html;charset=utf-8" }), fileStem() + ".html");
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
    if (next === "slides") { deckIndex = 0; syncLangBar(); sizeDeck(); renderSlide(); }
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

  try {
    var savedLang = window.localStorage.getItem(LANG_KEY);
    if (savedLang === "en" || savedLang === "ko" || savedLang === "both") lang = savedLang;
  } catch (e) { /* storage unavailable */ }

  chips("#langs .lang").forEach(function (btn) {
    btn.addEventListener("click", function () { setLang(btn.getAttribute("data-lang")); });
  });
  syncLangBar();

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
  var pptBtn = document.getElementById("ppt");
  if (pptBtn) pptBtn.addEventListener("click", downloadPptx);
  var pdfBtn = document.getElementById("pdf");
  if (pdfBtn) pdfBtn.addEventListener("click", printDeck);

  // Newsletter signup. A hosted endpoint posts in place; without one we hand over the address
  // with a copy button, so subscribing never launches a mail client.
  var signup = document.querySelector(".signup[data-mode]");
  if (signup) {
    var strings = {};
    try { strings = JSON.parse(signup.getAttribute("data-strings") || "{}"); } catch (e) { /* keep markup text */ }
    var help = signup.querySelector(".signup-help");
    var defaultNote = help ? help.textContent : "";

    var setState = function (state, message) {
      signup.setAttribute("data-state", state || "");
      if (help) help.textContent = message || defaultNote;
    };

    if (signup.getAttribute("data-mode") === "copy") {
      var copyBtn = signup.querySelector("#nl-copy");
      var addressNode = signup.querySelector("#nl-address");
      var address = signup.getAttribute("data-contact") || "";

      var selectAddress = function () {
        try {
          var range = document.createRange();
          range.selectNodeContents(addressNode);
          var sel = window.getSelection();
          sel.removeAllRanges();
          sel.addRange(range);
        } catch (e) { /* selection is a convenience, not a requirement */ }
      };

      copyBtn.addEventListener("click", function () {
        var settled = false;
        // The clipboard promise can hang when the document lacks focus, which would leave the
        // button with no feedback at all. Guarantee an answer either way.
        var finish = function (ok) {
          if (settled) return;
          settled = true;
          clearTimeout(guard);
          if (ok) {
            setState("success", strings.copied);
          } else {
            selectAddress();
            setState("error", strings.copy_failed);
          }
        };
        var guard = setTimeout(function () { finish(false); }, 1200);

        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(address).then(
            function () { finish(true); },
            function () { finish(false); }
          );
          return;
        }
        selectAddress();
        var ok = false;
        try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
        finish(ok);
      });
    } else {
      var emailField = signup.querySelector("input[type=email]");
      var submitBtn = signup.querySelector("button[type=submit]");

      signup.addEventListener("input", function () {
        if (signup.getAttribute("data-state") === "error") setState("", defaultNote);
      });

      signup.addEventListener("submit", function (event) {
        event.preventDefault();
        var value = (emailField.value || "").trim();
        if (!value || !emailField.checkValidity()) {
          setState("error", strings.invalid);
          emailField.focus();
          return;
        }
        setState("loading", strings.sending);
        emailField.disabled = true;
        submitBtn.disabled = true;

        var body = new FormData();
        body.append("email", value);
        fetch(signup.getAttribute("action"), {
          method: "POST", body: body, headers: { Accept: "application/json" }
        }).then(function (res) {
          // Prefer the server's own wording: it explains rate limits and rejected
          // addresses far better than a generic failure line.
          return res.json().catch(function () { return {}; }).then(function (data) {
            if (!res.ok || data.ok === false) {
              var error = new Error(res.status);
              error.serverMessage = data.message;
              throw error;
            }
            setState("success", data.message || strings.sent);
          });
        }).catch(function (error) {
          setState("error", (error && error.serverMessage) || strings.failed);
          emailField.disabled = false;
          submitBtn.disabled = false;
        });
      });
    }
  }

  document.addEventListener("keydown", function (event) {    if (view !== "slides") return;
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
