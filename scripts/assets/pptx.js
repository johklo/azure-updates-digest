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

  var INK = "1B1F23";
  var MUTED = "57606A";
  var BRAND = "0078D4";
  var DARK = "004578";

  var STAGE_COLOR = { ga: "0F7B34", pv: "8A5A00", pp: "6B3FA0", rt: "B02A37", dv: "2B5F8A", muted: MUTED };

  function shape(id, name, x, y, cx, cy, bodyXml, extra) {
    return '<p:sp><p:nvSpPr><p:cNvPr id="' + id + '" name="' + name + '"/>' +
      '<p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>' +
      '<p:spPr><a:xfrm><a:off x="' + x + '" y="' + y + '"/><a:ext cx="' + cx + '" cy="' + cy + '"/></a:xfrm>' +
      '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>' + (extra || "<a:noFill/>") + "</p:spPr>" +
      '<p:txBody><a:bodyPr wrap="square" lIns="0" tIns="0" rIns="0" bIns="0" anchor="t"><a:normAutofit/></a:bodyPr>' +
      "<a:lstStyle/>" + bodyXml + "</p:txBody></p:sp>";
  }

  function rect(id, x, y, cx, cy, color) {
    return '<p:sp><p:nvSpPr><p:cNvPr id="' + id + '" name="Bar ' + id + '"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>' +
      '<p:spPr><a:xfrm><a:off x="' + x + '" y="' + y + '"/><a:ext cx="' + cx + '" cy="' + cy + '"/></a:xfrm>' +
      '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val="' + color + '"/></a:solidFill>' +
      '<a:ln><a:noFill/></a:ln></p:spPr><p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody></p:sp>';
  }

  function run(text, opts) {
    opts = opts || {};
    // OOXML requires rPr children in schema order: fill, latin/ea/cs, then hlinkClick.
    var props = '<a:rPr lang="en-US" sz="' + (opts.size || 1400) + '"' +
      (opts.bold ? ' b="1"' : "") + ' dirty="0">' +
      '<a:solidFill><a:srgbClr val="' + (opts.color || INK) + '"/></a:solidFill>' +
      '<a:latin typeface="Segoe UI"/><a:ea typeface="Segoe UI"/><a:cs typeface="Segoe UI"/>' +
      (opts.link ? '<a:hlinkClick xmlns:r="' + NS_R + '" r:id="' + opts.link + '"/>' : "") +
      "</a:rPr>";
    return "<a:r>" + props + "<a:t>" + xmlEscape(text) + "</a:t></a:r>";
  }

  function para(runs, opts) {
    opts = opts || {};
    // OOXML requires pPr children in schema order: lnSpc, spcBef, buClr, buFont, buChar.
    var pr = "<a:pPr";
    if (opts.bullet) pr += ' marL="285750" indent="-285750"';
    pr += ' algn="' + (opts.align || "l") + '">';
    pr += '<a:lnSpc><a:spcPct val="' + (opts.lineSpacing || 105000) + '"/></a:lnSpc>';
    if (opts.spaceBefore) pr += '<a:spcBef><a:spcPts val="' + opts.spaceBefore + '"/></a:spcBef>';
    pr += opts.bullet
      ? '<a:buClr><a:srgbClr val="' + BRAND + '"/></a:buClr><a:buFont typeface="Arial"/><a:buChar char="\u2022"/>'
      : "<a:buNone/>";
    pr += "</a:pPr>";
    return "<a:p>" + pr + runs + "</a:p>";
  }

  function scaleFor(slide) {
    var weight = (slide.title || "").length * 1.7 + (slide.summary || "").length;
    (slide.points || []).forEach(function (p) { weight += p.length + 24; });
    if (weight > 1150) return 0.78;
    if (weight > 900) return 0.86;
    if (weight > 700) return 0.93;
    return 1;
  }

  function slideXml(slide, index, total, links) {
    var s = scaleFor(slide);
    var sz = function (base) { return Math.round(base * s); };
    var shapes = [];
    var id = 2;

    var eyebrow = [];
    if (slide.category) eyebrow.push(run(slide.category.toUpperCase() + "   ", { size: 1100, bold: true, color: BRAND }));
    if (slide.stage) eyebrow.push(run(slide.stage + "   ", { size: 1100, bold: true, color: STAGE_COLOR[slide.stageClass] || MUTED }));
    var tail = [slide.date, slide.products].filter(Boolean).join("   \u00b7   ");
    if (tail) eyebrow.push(run(tail, { size: 1100, color: MUTED }));
    shapes.push(shape(id++, "Eyebrow", MARGIN, 548640, BODY_W, 320000, para(eyebrow.join(""))));

    shapes.push(shape(id++, "Title", MARGIN, 1005840, BODY_W, 1280160,
      para(run(slide.title, { size: sz(2800), bold: true, color: INK, link: links.title }), { lineSpacing: 100000 })));

    var y = 2377440;
    if (slide.summary) {
      shapes.push(rect(id++, MARGIN, y, 45720, 640080, BRAND));
      shapes.push(shape(id++, "Summary", MARGIN + 182880, y, BODY_W - 182880, 640080,
        para(run(slide.summary, { size: sz(1600), color: "2B3138" }), { lineSpacing: 110000 })));
      y += 868680;
    }

    var points = (slide.points || []).slice(0, 6);
    if (points.length) {
      var body = points.map(function (text, i) {
        return para(run(text, { size: sz(1400), color: "333A42" }), { bullet: true, spaceBefore: i ? 500 : 0 });
      }).join("");
      shapes.push(shape(id++, "Points", MARGIN, y, BODY_W, 5486400 - y, body));
    }

    var foot = [run("Azure Updates announcement", { size: 1000, bold: true, color: BRAND, link: links.url })];
    if (links.doc) foot.push(run("      " + (slide.docTitle || "Microsoft documentation"), { size: 1000, bold: true, color: BRAND, link: links.doc }));
    shapes.push(rect(id++, MARGIN, 5943600, BODY_W, 9525, "E1E4E8"));
    shapes.push(shape(id++, "Footer", MARGIN, 6080760, BODY_W - 800000, 320000, para(foot.join(""))));
    shapes.push(shape(id++, "Number", W - MARGIN - 800000, 6080760, 800000, 320000,
      para(run(index + " / " + total, { size: 1000, color: "8B949E" }), { align: "r" })));

    return HEAD + '<p:sld xmlns:a="' + NS_A + '" xmlns:r="' + NS_R + '" xmlns:p="' + NS_P + '">' +
      "<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>" +
      '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>' +
      '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>' +
      shapes.join("") + "</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>";
  }

  function coverXml(meta, total) {
    var shapes = [];
    var id = 2;
    shapes.push(rect(id++, 0, 0, W, 1737360, DARK));
    shapes.push(shape(id++, "CoverTitle", MARGIN, 548640, BODY_W, 700000,
      para(run("Azure Product Updates", { size: 4000, bold: true, color: "FFFFFF" }))));
    shapes.push(shape(id++, "CoverSub", MARGIN, 1280160, BODY_W, 320000,
      para(run(total + " update(s)   \u00b7   generated " + meta.date, { size: 1400, color: "D6E7F7" }))));
    shapes.push(shape(id++, "Scope", MARGIN, 2194560, BODY_W, 640080,
      para(run(meta.scope, { size: 1400, color: MUTED }))));

    var rows = meta.categories.map(function (entry, i) {
      return para(run(entry[0] + "  \u2014  " + entry[1], { size: 1300, color: "333A42" }), { bullet: true, spaceBefore: i ? 400 : 0 });
    }).join("");
    shapes.push(shape(id++, "Categories", MARGIN, 2926080, BODY_W, 2560320, rows));
    shapes.push(shape(id++, "CoverFoot", MARGIN, 6080760, BODY_W, 320000,
      para(run("Source: Microsoft Azure Updates \u00b7 summaries generated from each announcement and its linked documentation.",
        { size: 1000, color: "8B949E" }))));

    return HEAD + '<p:sld xmlns:a="' + NS_A + '" xmlns:r="' + NS_R + '" xmlns:p="' + NS_P + '">' +
      "<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>" +
      '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>' +
      '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>' +
      shapes.join("") + "</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>";
  }

  function themeXml() {
    var colors = ["4472C4", "ED7D31", "A5A5A5", "FFC000", "5B9BD5", "70AD47"];
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

    return HEAD + '<a:theme xmlns:a="' + NS_A + '" name="Azure Updates">' +
      "<a:themeElements><a:clrScheme name=\"Azure\">" +
      '<a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>' +
      '<a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>' +
      '<a:dk2><a:srgbClr val="1B1F23"/></a:dk2><a:lt2><a:srgbClr val="F4F6F8"/></a:lt2>' + scheme +
      '<a:hlink><a:srgbClr val="0078D4"/></a:hlink><a:folHlink><a:srgbClr val="6B3FA0"/></a:folHlink>' +
      "</a:clrScheme>" +
      '<a:fontScheme name="Azure"><a:majorFont><a:latin typeface="Segoe UI"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>' +
      '<a:minorFont><a:latin typeface="Segoe UI"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont></a:fontScheme>' +
      '<a:fmtScheme name="Azure">' +
      "<a:fillStyleLst>" + fill + "</a:fillStyleLst>" +
      "<a:lnStyleLst>" + lines + "</a:lnStyleLst>" +
      "<a:effectStyleLst>" + effects + effects + effects + "</a:effectStyleLst>" +
      "<a:bgFillStyleLst>" + fill + "</a:bgFillStyleLst>" +
      "</a:fmtScheme></a:themeElements></a:theme>";
  }

  function masterXml() {
    return HEAD + '<p:sldMaster xmlns:a="' + NS_A + '" xmlns:r="' + NS_R + '" xmlns:p="' + NS_P + '">' +
      '<p:cSld><p:bg><p:bgPr><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>' +
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
