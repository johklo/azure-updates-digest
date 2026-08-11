/* Minimal dependency-free PowerPoint (.pptx) writer for the Azure updates deck.
   Builds an OOXML package as an uncompressed (stored) ZIP, which PowerPoint accepts. */
(function (global) {
  "use strict";

  var CRC_TABLE = (function () {
    var table = new Int32Array(256);
    for (var n = 0; n < 256; n++) {
      var c = n;
      for (var k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      table[n] = c;
    }
    return table;
  })();

  function crc32(bytes) {
    var c = -1;
    for (var i = 0; i < bytes.length; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
    return (c ^ -1) >>> 0;
  }

  function utf8(text) {
    if (global.TextEncoder) return new TextEncoder().encode(text);
    var out = [];
    for (var i = 0; i < text.length; i++) {
      var c = text.charCodeAt(i);
      if (c < 128) out.push(c);
      else if (c < 2048) out.push(192 | (c >> 6), 128 | (c & 63));
      else out.push(224 | (c >> 12), 128 | ((c >> 6) & 63), 128 | (c & 63));
    }
    return new Uint8Array(out);
  }

  function zip(files) {
    var chunks = [];
    var central = [];
    var offset = 0;

    files.forEach(function (file) {
      var name = utf8(file.name);
      var data = utf8(file.data);
      var crc = crc32(data);

      var local = new Uint8Array(30 + name.length);
      var view = new DataView(local.buffer);
      view.setUint32(0, 0x04034b50, true);
      view.setUint16(4, 20, true);
      view.setUint16(6, 0x0800, true);
      view.setUint16(8, 0, true);
      view.setUint16(10, 0, true);
      view.setUint16(12, 0x21, true);
      view.setUint32(14, crc, true);
      view.setUint32(18, data.length, true);
      view.setUint32(22, data.length, true);
      view.setUint16(26, name.length, true);
      view.setUint16(28, 0, true);
      local.set(name, 30);

      var entry = new Uint8Array(46 + name.length);
      var cview = new DataView(entry.buffer);
      cview.setUint32(0, 0x02014b50, true);
      cview.setUint16(4, 20, true);
      cview.setUint16(6, 20, true);
      cview.setUint16(8, 0x0800, true);
      cview.setUint16(10, 0, true);
      cview.setUint16(12, 0, true);
      cview.setUint16(14, 0x21, true);
      cview.setUint32(16, crc, true);
      cview.setUint32(20, data.length, true);
      cview.setUint32(24, data.length, true);
      cview.setUint16(28, name.length, true);
      cview.setUint32(42, offset, true);
      entry.set(name, 46);

      chunks.push(local, data);
      central.push(entry);
      offset += local.length + data.length;
    });

    var centralSize = central.reduce(function (a, e) { return a + e.length; }, 0);
    var end = new Uint8Array(22);
    var eview = new DataView(end.buffer);
    eview.setUint32(0, 0x06054b50, true);
    eview.setUint16(8, files.length, true);
    eview.setUint16(10, files.length, true);
    eview.setUint32(12, centralSize, true);
    eview.setUint32(16, offset, true);

    return new Blob(chunks.concat(central, [end]), {
      type: "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    });
  }

  function xmlEscape(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&apos;")
      .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, "");
  }

  var HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n';
  var NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main";
  var NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
  var NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main";
  var NS_REL = "http://schemas.openxmlformats.org/package/2006/relationships";

  var W = 12192000;   // 16:9 slide width in EMU
  var H = 6858000;
  var MARGIN = 685800;
  var BODY_W = W - MARGIN * 2;
  var GUTTER = 457200;
  var COL_L = Math.round((BODY_W - GUTTER) * 0.53);
  var COL_R = BODY_W - GUTTER - COL_L;
  var X_R = MARGIN + COL_L + GUTTER;
  var EMU_PT = 12700;

  /* Hallmark · genre: editorial · macrostructure: Split Studio · scope: pptx export
     theme: custom "broadsheet, azure ink, hairline rules"
     paper oklch(97.5% 0.006 252) -> F4F7FB · accent oklch(50% 0.152 252) -> 0064B6 */
  var PAPER = "F4F7FB";
  var PAPER_2 = "E9EEF3";
  var RULE = "CED5DD";
  var RULE_STRONG = "9BA6B2";
  var MUTED = "5F6A77";
  var INK_2 = "384350";
  var INK = "131E2A";
  var ACCENT = "0064B6";
  var COVER = "0E253E";
  var COVER_INK = "E9EFF7";
  var COVER_MUTED = "9EADBE";
  var COVER_RULE = "3A5169";     /* oklch(45% 0.05 252) */
  var COVER_RULE_2 = "27405A";   /* oklch(35% 0.05 252) */

  var DISPLAY = "Cambria";
  var BODY = "Segoe UI";
  var OUTLIER = "Consolas";
  // PowerPoint resolves Hangul through the East Asian slot, so Korean keeps its own face
  // while Latin stays on the display/body face inside the very same run properties.
  var EA_DISPLAY = "Batang";
  var EA_BODY = "Malgun Gothic";

  var STAGE_COLOR = { ga: "09672E", pv: "8A5600", pp: "643B9A", rt: "A5292B", dv: "135F83", muted: MUTED };
  var STAGE = STAGE_COLOR;

  function shape(id, name, x, y, cx, cy, bodyXml, extra) {
    return '<p:sp><p:nvSpPr><p:cNvPr id="' + id + '" name="' + name + '"/>' +
      '<p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>' +
      '<p:spPr><a:xfrm><a:off x="' + x + '" y="' + y + '"/><a:ext cx="' + cx + '" cy="' + cy + '"/></a:xfrm>' +
      '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>' + (extra || "<a:noFill/>") + "</p:spPr>" +
      '<p:txBody><a:bodyPr wrap="square" lIns="0" tIns="0" rIns="0" bIns="0" anchor="t"><a:normAutofit/></a:bodyPr>' +
      "<a:lstStyle/>" + bodyXml + "</p:txBody></p:sp>";
  }

  function rect(id, x, y, cx, cy, color) {
    return '<p:sp><p:nvSpPr><p:cNvPr id="' + id + '" name="Rule ' + id + '"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>' +
      '<p:spPr><a:xfrm><a:off x="' + x + '" y="' + y + '"/><a:ext cx="' + cx + '" cy="' + cy + '"/></a:xfrm>' +
      '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val="' + color + '"/></a:solidFill>' +
      '<a:ln><a:noFill/></a:ln></p:spPr><p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody></p:sp>';
  }

  function run(text, opts) {
    opts = opts || {};
    var face = opts.face || BODY;
    var ea = opts.ea || (face === DISPLAY ? EA_DISPLAY : face === OUTLIER ? EA_BODY : EA_BODY);
    // OOXML requires rPr children in schema order: fill, latin/ea/cs, then hlinkClick.
    var props = '<a:rPr lang="en-US"' + (opts.lang ? ' altLang="' + opts.lang + '"' : "") +
      ' sz="' + (opts.size || 1400) + '"' +
      (opts.bold ? ' b="1"' : "") +
      (opts.caps ? ' cap="all"' : "") +
      (opts.spc ? ' spc="' + opts.spc + '"' : "") + ' dirty="0">' +
      '<a:solidFill><a:srgbClr val="' + (opts.color || INK) + '"/></a:solidFill>' +
      '<a:latin typeface="' + face + '"/><a:ea typeface="' + ea + '"/><a:cs typeface="' + face + '"/>' +
      (opts.link ? '<a:hlinkClick xmlns:r="' + NS_R + '" r:id="' + opts.link + '"/>' : "") +
      "</a:rPr>";
    return "<a:r>" + props + "<a:t>" + xmlEscape(text) + "</a:t></a:r>";
  }

  function para(runs, opts) {
    opts = opts || {};
    // OOXML requires pPr children in schema order: lnSpc, spcBef, buClr, buFont, buChar.
    var pr = '<a:pPr algn="' + (opts.align || "l") + '">';
    pr += '<a:lnSpc><a:spcPct val="' + (opts.lineSpacing || 105000) + '"/></a:lnSpc>';
    if (opts.spaceBefore) pr += '<a:spcBef><a:spcPts val="' + opts.spaceBefore + '"/></a:spcBef>';
    pr += "<a:buNone/></a:pPr>";
    return "<a:p>" + pr + runs + "</a:p>";
  }

  // Rough line-count estimate: PowerPoint cannot reflow for us, so lay out by measurement.
  // Hangul is full-width, so it needs a much larger per-character factor than Latin.
  function estLines(text, sizeHundredths, widthEmu, factor) {
    if (!text) return 0;
    var charEmu = (sizeHundredths / 100) * EMU_PT * (factor || 0.5);
    var perLine = Math.max(6, Math.floor(widthEmu / charEmu));
    return Math.max(1, Math.ceil(String(text).length / perLine));
  }

  function blockH(text, sizeHundredths, widthEmu, factor, leading) {
    return estLines(text, sizeHundredths, widthEmu, factor) *
      Math.round((sizeHundredths / 100) * EMU_PT * (leading || 1.2));
  }

  var KO_FACTOR = 1.02;

  function koBlockH(text, sizeHundredths, widthEmu, leading) {
    return blockH(text, sizeHundredths, widthEmu, KO_FACTOR, leading || 1.45);
  }

  function scaleFor(slide) {
    var weight = (slide.title || "").length * 1.7 + (slide.summary || "").length;
    (slide.points || []).forEach(function (p) { weight += p.length + 24; });
    // Korean is denser per character, so it costs more vertical space than its length suggests.
    weight += (slide.titleKo || "").length * 2.6 + (slide.summaryKo || "").length * 1.5;
    (slide.pointsKo || []).forEach(function (p) { weight += (p || "").length * 1.5; });
    if (weight > 1150) return 0.8;
    if (weight > 900) return 0.88;
    if (weight > 700) return 0.94;
    return 1;
  }

  // Running head — N6 masthead voice: mono small caps, double rule beneath.
  function runningHead(shapes, idRef, leftText, folioText, inkColor, mutedColor, ruleColor, ruleLight) {
    shapes.push(shape(idRef.id++, "Mast", MARGIN, 393700, BODY_W - 1600000, 220000,
      para(run(leftText, { size: 900, face: OUTLIER, color: mutedColor, caps: true, spc: 300 }))));
    shapes.push(shape(idRef.id++, "Folio", W - MARGIN - 1600000, 393700, 1600000, 220000,
      para(folioText, { align: "r" })));
    shapes.push(rect(idRef.id++, MARGIN, 685800, BODY_W, 12700, ruleColor));
    shapes.push(rect(idRef.id++, MARGIN, 723900, BODY_W, 9525, ruleLight));
  }

  function slideXml(slide, index, total, links) {
    var s = scaleFor(slide);
    var sz = function (base) { return Math.round(base * s); };
    var shapes = [];
    var idRef = { id: 2 };

    var folio = run(pad2(index), { size: 900, face: OUTLIER, color: INK, bold: true, spc: 200 }) +
      run("  /  " + pad2(total), { size: 900, face: OUTLIER, color: MUTED, spc: 200 });
    runningHead(shapes, idRef, "Azure Product Updates", folio,
      INK, MUTED, RULE_STRONG, RULE);

    var TOP = 1143000;
    var BOTTOM = 5715000;
    var REGION = BOTTOM - TOP;

    /* ---- Left half: kicker, headline (+ Korean), standfirst (+ Korean), byline ---- */
    var titleSize = sz(slide.title && slide.title.length > 62 ? 2400 : 3000);
    if (slide.title && slide.title.length > 110) titleSize = sz(2000);
    var titleH = blockH(slide.title, titleSize, COL_L, 0.5, 1.12);
    var titleKoSize = Math.round(titleSize * 0.66);
    var titleKoH = slide.titleKo ? koBlockH(slide.titleKo, titleKoSize, COL_L, 1.4) + 76200 : 0;

    var leadSize = sz(1450);
    var leadH = slide.summary ? blockH(slide.summary, leadSize, COL_L, 0.48, 1.5) : 0;
    var leadKoSize = Math.round(leadSize * 0.88);
    var leadKoH = slide.summaryKo ? koBlockH(slide.summaryKo, leadKoSize, COL_L, 1.55) + 63500 : 0;

    var kickerH = 260350;
    var leadGap = slide.summary || slide.summaryKo ? 190500 : 0;
    var bylineGap = 285750;
    var bylineH = 260350;
    var leftH = kickerH + titleH + titleKoH + leadGap + leadH + leadKoH + bylineGap + bylineH;
    var yL = TOP + Math.max(0, Math.round((REGION - leftH) / 2));

    shapes.push(shape(idRef.id++, "Kicker", MARGIN, yL, COL_L, 220000,
      para(run(slide.category || "Update", { size: 1000, face: OUTLIER, color: ACCENT, caps: true, spc: 340 }))));
    yL += kickerH;

    var headline = para(run(slide.title, { size: titleSize, face: DISPLAY, color: INK, link: links.title }),
      { lineSpacing: 100000 });
    if (slide.titleKo) {
      headline += para(run(slide.titleKo, { size: titleKoSize, face: DISPLAY, color: INK_2, lang: "ko-KR" }),
        { lineSpacing: 124000, spaceBefore: 500 });
    }
    shapes.push(shape(idRef.id++, "Headline", MARGIN, yL, COL_L, titleH + titleKoH + 120000, headline));
    yL += titleH + titleKoH + leadGap;

    if (slide.summary || slide.summaryKo) {
      var standfirst = "";
      if (slide.summary) {
        standfirst += para(run(slide.summary, { size: leadSize, face: DISPLAY, color: INK_2 }),
          { lineSpacing: 128000 });
      }
      if (slide.summaryKo) {
        standfirst += para(run(slide.summaryKo, { size: leadKoSize, face: DISPLAY, color: MUTED, lang: "ko-KR" }),
          { lineSpacing: 138000, spaceBefore: slide.summary ? 400 : 0 });
      }
      shapes.push(shape(idRef.id++, "Standfirst", MARGIN, yL, COL_L, leadH + leadKoH + 120000, standfirst));
      yL += leadH + leadKoH;
    }

    yL += bylineGap;
    shapes.push(rect(idRef.id++, MARGIN, yL - 152400, COL_L, 9525, RULE));
    var byline = [];
    if (slide.stage) {
      var stageColor = STAGE_COLOR[slide.stageClass] || MUTED;
      byline.push(run("\u25a0 ", { size: 900, color: stageColor }));
      byline.push(run(slide.stage + "     ", { size: 900, face: OUTLIER, color: stageColor, caps: true, spc: 200 }));
    }
    var tail = [slide.date, slide.products].filter(Boolean).join("     \u00b7     ");
    if (tail) byline.push(run(tail, { size: 900, face: OUTLIER, color: MUTED, spc: 100 }));
    shapes.push(shape(idRef.id++, "Byline", MARGIN, yL, COL_L, 240000, para(byline.join(""))));

    /* ---- Right half: numbered notes, hairline separated ---- */
    var points = (slide.points || []).slice(0, 6);
    var pointsKo = (slide.pointsKo || []).slice(0, 6);
    if (points.length) {
      var numW = 400050;
      var textW = COL_R - numW;
      var ptSize = sz(1250);
      var ptKoSize = Math.round(ptSize * 0.86);
      var heights = points.map(function (text, i) {
        var h = Math.max(285750, blockH(text, ptSize, textW, 0.48, 1.45));
        if (pointsKo[i]) h += koBlockH(pointsKo[i], ptKoSize, textW, 1.5) + 50800;
        return h;
      });
      var pad = 133350;
      var notesH = 190500 + heights.reduce(function (a, b) { return a + b + pad * 2 + 9525; }, 0);
      var yR = TOP + Math.max(0, Math.round((REGION - notesH) / 2));

      shapes.push(rect(idRef.id++, X_R, yR, COL_R, 25400, INK));
      yR += 190500;

      points.forEach(function (text, i) {
        shapes.push(shape(idRef.id++, "PointNo" + i, X_R, yR + pad + 25400, numW - 76200, 220000,
          para(run(pad2(i + 1), { size: 950, face: OUTLIER, color: ACCENT, spc: 200 }))));
        var body = para(run(text, { size: ptSize, color: INK_2 }), { lineSpacing: 122000 });
        if (pointsKo[i]) {
          body += para(run(pointsKo[i], { size: ptKoSize, color: MUTED, lang: "ko-KR" }),
            { lineSpacing: 140000, spaceBefore: 300 });
        }
        shapes.push(shape(idRef.id++, "Point" + i, X_R + numW, yR + pad, textW, heights[i] + 60000, body));
        yR += heights[i] + pad * 2;
        if (i < points.length - 1) {
          shapes.push(rect(idRef.id++, X_R, yR, COL_R, 9525, RULE));
          yR += 9525;
        }
      });
    }

    /* ---- Ft2 footer: hairline + single inline line ---- */
    shapes.push(rect(idRef.id++, MARGIN, 5943600, BODY_W, 9525, RULE_STRONG));
    var foot = [run("Announcement", { size: 900, face: OUTLIER, color: ACCENT, caps: true, spc: 200, link: links.url })];
    if (links.doc) {
      foot.push(run("          ", { size: 900, face: OUTLIER, color: MUTED }));
      foot.push(run(slide.docTitle || "Microsoft documentation",
        { size: 900, face: OUTLIER, color: ACCENT, caps: true, spc: 200, link: links.doc }));
    }
    shapes.push(shape(idRef.id++, "Footer", MARGIN, 6096000, BODY_W, 260000, para(foot.join(""))));

    return wrapSlide(shapes.join(""));
  }

  function pad2(n) {
    return (n < 10 ? "0" : "") + n;
  }

  function coverXml(meta, total) {
    var shapes = [];
    var idRef = { id: 2 };
    shapes.push(rect(idRef.id++, 0, 0, W, H, COVER));

    runningHead(shapes, idRef, "Azure Product Updates",
      run("Cover", { size: 900, face: OUTLIER, color: COVER_MUTED, caps: true, spc: 300 }),
      COVER_INK, COVER_MUTED, COVER_MUTED, COVER_RULE);

    shapes.push(shape(idRef.id++, "Masthead", MARGIN, 1143000, BODY_W - 2000000, 1600000,
      para(run("Azure Product Updates", { size: 5400, face: DISPLAY, color: COVER_INK }),
        { lineSpacing: 96000 })));

    shapes.push(rect(idRef.id++, MARGIN, 2679700, BODY_W, 9525, COVER_MUTED));
    shapes.push(shape(idRef.id++, "Issue", MARGIN, 2819400, BODY_W, 240000,
      para(run("No. " + meta.date + "     \u00b7     " + total + " update" + (total === 1 ? "" : "s"),
        { size: 1000, face: OUTLIER, color: COVER_MUTED, caps: true, spc: 300 }))));

    shapes.push(shape(idRef.id++, "Scope", MARGIN, 3200400, Math.round(BODY_W * 0.62), 700000,
      para(run(meta.scope, { size: 1400, face: DISPLAY, color: COVER_INK }), { lineSpacing: 128000 })));

    // Index — dot-leader category list, two columns.
    var half = Math.ceil(meta.categories.length / 2);
    var colW = Math.round((BODY_W - GUTTER) / 2);
    [0, 1].forEach(function (col) {
      var slice = meta.categories.slice(col * half, col * half + half);
      var x = MARGIN + col * (colW + GUTTER);
      var y = 4114800;
      slice.forEach(function (entry) {
        shapes.push(shape(idRef.id++, "Idx" + col + entry[0], x, y, colW - 500000, 220000,
          para(run(entry[0], { size: 1000, face: OUTLIER, color: COVER_INK, spc: 80 }))));
        shapes.push(shape(idRef.id++, "IdxN" + col + entry[0], x + colW - 500000, y, 500000, 220000,
          para(run(pad2(entry[1]), { size: 1000, face: OUTLIER, color: COVER_MUTED, spc: 80 }), { align: "r" })));
        y += 260350;
        shapes.push(rect(idRef.id++, x, y - 63500, colW, 9525, COVER_RULE_2));
      });
    });

    shapes.push(rect(idRef.id++, MARGIN, 5943600, BODY_W, 9525, COVER_MUTED));
    shapes.push(shape(idRef.id++, "Colophon", MARGIN, 6096000, BODY_W, 260000,
      para(run("Source: Microsoft Azure Updates \u00b7 summaries generated from each announcement and its linked documentation.",
        { size: 850, face: OUTLIER, color: COVER_MUTED, spc: 80 }))));

    return wrapSlide(shapes.join(""));
  }

  function wrapSlide(shapeXml) {
    return HEAD + '<p:sld xmlns:a="' + NS_A + '" xmlns:r="' + NS_R + '" xmlns:p="' + NS_P + '">' +
      "<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>" +
      '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>' +
      '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>' +
      shapeXml + "</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>";
  }

  function themeXml() {
    var colors = [ACCENT, STAGE.pv, RULE_STRONG, STAGE.ga, STAGE.dv, STAGE.pp];
    var scheme = colors.map(function (c, i) {
      return '<a:accent' + (i + 1) + '><a:srgbClr val="' + c + '"/></a:accent' + (i + 1) + ">";
    }).join("");
    var fill =
      '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>' +
      '<a:gradFill rotWithShape="1"><a:gsLst>' +
      '<a:gs pos="0"><a:schemeClr val="phClr"><a:tint val="60000"/><a:satMod val="105000"/></a:schemeClr></a:gs>' +
      '<a:gs pos="100000"><a:schemeClr val="phClr"><a:shade val="80000"/></a:schemeClr></a:gs>' +
      '</a:gsLst><a:lin ang="5400000" scaled="0"/></a:gradFill>' +
      '<a:gradFill rotWithShape="1"><a:gsLst>' +
      '<a:gs pos="0"><a:schemeClr val="phClr"><a:tint val="80000"/></a:schemeClr></a:gs>' +
      '<a:gs pos="100000"><a:schemeClr val="phClr"><a:shade val="60000"/></a:schemeClr></a:gs>' +
      '</a:gsLst><a:lin ang="5400000" scaled="0"/></a:gradFill>';
    var lines = [6350, 12700, 19050].map(function (w) {
      return '<a:ln w="' + w + '" cap="flat" cmpd="sng" algn="ctr">' +
        '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/></a:ln>';
    }).join("");
    var effects = "<a:effectStyle><a:effectLst/></a:effectStyle>";

    return HEAD + '<a:theme xmlns:a="' + NS_A + '" name="Azure Updates Broadsheet">' +
      "<a:themeElements><a:clrScheme name=\"Broadsheet\">" +
      '<a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>' +
      '<a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>' +
      '<a:dk2><a:srgbClr val="' + INK + '"/></a:dk2><a:lt2><a:srgbClr val="' + PAPER + '"/></a:lt2>' + scheme +
      '<a:hlink><a:srgbClr val="' + ACCENT + '"/></a:hlink><a:folHlink><a:srgbClr val="' + STAGE.pp + '"/></a:folHlink>' +
      "</a:clrScheme>" +
      '<a:fontScheme name="Broadsheet"><a:majorFont><a:latin typeface="' + DISPLAY + '"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>' +
      '<a:minorFont><a:latin typeface="' + BODY + '"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont></a:fontScheme>' +
      '<a:fmtScheme name="Broadsheet">' +
      "<a:fillStyleLst>" + fill + "</a:fillStyleLst>" +
      "<a:lnStyleLst>" + lines + "</a:lnStyleLst>" +
      "<a:effectStyleLst>" + effects + effects + effects + "</a:effectStyleLst>" +
      "<a:bgFillStyleLst>" + fill + "</a:bgFillStyleLst>" +
      "</a:fmtScheme></a:themeElements></a:theme>";
  }

  function masterXml() {
    return HEAD + '<p:sldMaster xmlns:a="' + NS_A + '" xmlns:r="' + NS_R + '" xmlns:p="' + NS_P + '">' +
      '<p:cSld><p:bg><p:bgPr><a:solidFill><a:srgbClr val="' + PAPER + '"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>' +
      "<p:spTree><p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>" +
      '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>' +
      '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld>' +
      '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" ' +
      'accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>' +
      '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>' +
      "</p:sldMaster>";
  }

  function layoutXml() {
    return HEAD + '<p:sldLayout xmlns:a="' + NS_A + '" xmlns:r="' + NS_R + '" xmlns:p="' + NS_P +
      '" type="blank" preserve="1"><p:cSld name="Blank"><p:spTree>' +
      "<p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>" +
      '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>' +
      '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld>' +
      "<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>";
  }

  function relationships(items) {
    return HEAD + '<Relationships xmlns="' + NS_REL + '">' + items.map(function (item) {
      return '<Relationship Id="' + item.id + '" Type="' + item.type + '" Target="' + xmlEscape(item.target) + '"' +
        (item.external ? ' TargetMode="External"' : "") + "/>";
    }).join("") + "</Relationships>";
  }

  var REL = {
    officeDocument: NS_R + "/officeDocument",
    slide: NS_R + "/slide",
    slideMaster: NS_R + "/slideMaster",
    slideLayout: NS_R + "/slideLayout",
    theme: NS_R + "/theme",
    hyperlink: NS_R + "/hyperlink"
  };

  function build(slides, meta) {
    var files = [];
    var total = slides.length;
    var count = total + 1;

    var overrides = ['<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>',
      '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>',
      '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>',
      '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'];
    for (var i = 1; i <= count; i++) {
      overrides.push('<Override PartName="/ppt/slides/slide' + i + '.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>');
    }

    files.push({
      name: "[Content_Types].xml",
      data: HEAD + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
        '<Default Extension="xml" ContentType="application/xml"/>' + overrides.join("") + "</Types>"
    });

    files.push({
      name: "_rels/.rels",
      data: relationships([{ id: "rId1", type: REL.officeDocument, target: "ppt/presentation.xml" }])
    });

    var sldIds = "";
    var presRels = [{ id: "rId1", type: REL.slideMaster, target: "slideMasters/slideMaster1.xml" }];
    for (var n = 1; n <= count; n++) {
      var rid = "rId" + (n + 1);
      sldIds += '<p:sldId id="' + (255 + n) + '" r:id="' + rid + '"/>';
      presRels.push({ id: rid, type: REL.slide, target: "slides/slide" + n + ".xml" });
    }
    presRels.push({ id: "rId" + (count + 2), type: REL.theme, target: "theme/theme1.xml" });

    files.push({
      name: "ppt/presentation.xml",
      data: HEAD + '<p:presentation xmlns:a="' + NS_A + '" xmlns:r="' + NS_R + '" xmlns:p="' + NS_P + '" saveSubsetFonts="1">' +
        '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>' +
        "<p:sldIdLst>" + sldIds + "</p:sldIdLst>" +
        '<p:sldSz cx="' + W + '" cy="' + H + '"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>'
    });
    files.push({ name: "ppt/_rels/presentation.xml.rels", data: relationships(presRels) });

    files.push({ name: "ppt/slideMasters/slideMaster1.xml", data: masterXml() });
    files.push({
      name: "ppt/slideMasters/_rels/slideMaster1.xml.rels",
      data: relationships([
        { id: "rId1", type: REL.slideLayout, target: "../slideLayouts/slideLayout1.xml" },
        { id: "rId2", type: REL.theme, target: "../theme/theme1.xml" }
      ])
    });
    files.push({ name: "ppt/slideLayouts/slideLayout1.xml", data: layoutXml() });
    files.push({
      name: "ppt/slideLayouts/_rels/slideLayout1.xml.rels",
      data: relationships([{ id: "rId1", type: REL.slideMaster, target: "../slideMasters/slideMaster1.xml" }])
    });
    files.push({ name: "ppt/theme/theme1.xml", data: themeXml() });

    files.push({ name: "ppt/slides/slide1.xml", data: coverXml(meta, total) });
    files.push({
      name: "ppt/slides/_rels/slide1.xml.rels",
      data: relationships([{ id: "rId1", type: REL.slideLayout, target: "../slideLayouts/slideLayout1.xml" }])
    });

    slides.forEach(function (slide, index) {
      var rels = [{ id: "rId1", type: REL.slideLayout, target: "../slideLayouts/slideLayout1.xml" }];
      var links = {};
      if (slide.url) {
        rels.push({ id: "rId2", type: REL.hyperlink, target: slide.url, external: true });
        links.url = "rId2";
        links.title = "rId2";
      }
      if (slide.docUrl) {
        rels.push({ id: "rId3", type: REL.hyperlink, target: slide.docUrl, external: true });
        links.doc = "rId3";
      }
      var number = index + 2;
      files.push({ name: "ppt/slides/slide" + number + ".xml", data: slideXml(slide, index + 1, total, links) });
      files.push({ name: "ppt/slides/_rels/slide" + number + ".xml.rels", data: relationships(rels) });
    });

    return zip(files);
  }

  global.buildPptx = build;
})(window);
