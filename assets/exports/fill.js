/* ---------------------------------------------------------------------------
   EXPORTS FROM TEMPLATES — the Excel, PowerPoint and PDF downloads, made when someone clicks Export: the report's
   template (assets/exports/templates/) filled with the report's data for the period on screen (data/reports/<report>.json,
   the same numbers the page shows). Nothing is made in advance and no download is stored anywhere.

     const file = await FourthSheetExports.build(periodData, 'xlsx');     // { bytes, name, type }

   Slots in a template:
     {{answer}}           text: anywhere in a cell, a text box, a header or footer, or the PDF layout
     {{n:w.calls}}        a number (an Excel cell holding only this slot becomes a number, so formulas can use it)
     {{months.label}}     a row repeated for every month (Excel): every slot in the row names the same list; the row must
                          be the last on its sheet; formulas in it are renumbered for each row, and any chart or formula
                          range on that row (e.g. Data!$C$6:$C$6) is stretched to every row
     chart:hours          a PowerPoint chart's alt text: its data is replaced with the "hours" chart (categories, series)
   The PDF layout (templates/<report>.pdf.json) is a pdfmake document with the same text slots, plus
     {"$each": "status", "$do": [...]}   repeated for every item in a list (inside a table body or a stack)
     {"$if": "part_note", ...}           left out when that value is empty
     {"$chart": "hours", "kind": "hbar" | "columns" | "line", "width": 250, "height": 160}   a chart, drawn as vector graphics
   A slot the data doesn't have stops the build with an error naming it, so a template can never print a blank by mistake.

   Each report's data (the values, lists and charts its slots name) is worked out by assets/exports/reports.js.
   Runs in the browser (libraries loaded on first use from assets/vendor/) and in Node for the publish check
   (tools/3_publish_site/tests/render_templated.js passes the libraries in).
--------------------------------------------------------------------------- */
(function (root) {
  'use strict';

  const TYPES = {
    xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    pdf: 'application/pdf',
  };
  const libs = {};          // JSZip, pdfMake, reports (Node: set by use(); browser: loaded on first use)

  // ------------------------------------------------------------------ slots
  const SLOT = /\{\{\s*(n:)?([\w.]+)\s*\}\}/g;
  const ONLY_NUMBER = /^\s*\{\{\s*n:([\w.]+)\s*\}\}\s*$/;

  function lookup(ctx, key, scope) {
    const parts = key.split('.');
    let v = scope && parts[0] === scope.name ? scope.item : ctx;
    for (const p of scope && parts[0] === scope.name ? parts.slice(1) : parts) {
      v = v == null ? undefined : v[p];
    }
    if (v === undefined) throw new Error(`The template asks for {{${key}}}, which the data for this report doesn't have.`);
    return v;
  }
  const fillText = (s, ctx, scope) => s.replace(SLOT, (m, n, k) => {
    const v = lookup(ctx, k, scope);
    return v == null ? '' : String(v);
  });
  const listIn = (s, ctx) => {        // the list a piece of text repeats over, if any of its slots name one
    for (const m of s.matchAll(SLOT)) {
      const first = m[2].split('.')[0];
      if (Array.isArray(ctx[first])) return first;
    }
    return null;
  };

  // ------------------------------------------------------------------ XML
  const ENT = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'" };
  const decode = (s) => s.replace(/&(#x[0-9a-f]+|#\d+|amp|lt|gt|quot|apos);/gi, (m, e) => (e[0] === '#'
    ? String.fromCodePoint(e[1] === 'x' || e[1] === 'X' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10)) : ENT[e.toLowerCase()]));
  const encode = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const texts = (frag, tag) => [...frag.matchAll(new RegExp(`<${tag}(?:\\s[^>]*)?>([\\s\\S]*?)</${tag}>`, 'g'))].map((m) => decode(m[1])).join('');
  const attrs = (tag) => Object.fromEntries([...tag.matchAll(/([\w:]+)="([^"]*)"/g)].map((m) => [m[1], m[2]]));
  const fillXml = (xml, ctx) => xml.replace(SLOT, (m, n, k) => {
    const v = lookup(ctx, k);
    return encode(v == null ? '' : v);
  });
  const relTargets = (rels, base) => Object.fromEntries([...(rels || '').matchAll(/<Relationship\b[^>]*>/g)].map((m) => {
    const a = attrs(m[0]);
    return [a.Id, resolvePath(base, a.Target)];
  }));
  function resolvePath(base, target) {      // a relationship's Target, relative to its part's folder (or absolute)
    if (target.startsWith('/')) return target.slice(1);
    const out = base.split('/').filter(Boolean);
    for (const p of target.split('/')) {
      if (p === '..') out.pop(); else if (p !== '.') out.push(p);
    }
    return out.join('/');
  }

  // a filled package, zipped. No folder entries: JSZip adds one for each folder it writes into, and Office packages
  // don't have them (PowerPoint offers to "repair" a file that does).
  function save(zip) {
    for (const k of Object.keys(zip.files)) if (zip.files[k].dir) delete zip.files[k];
    return zip.generateAsync({ type: 'uint8array', compression: 'DEFLATE' });
  }

  // ------------------------------------------------------------------ Excel
  const ROW = /<row\b[^>]*?(?:\/>|>[\s\S]*?<\/row>)/g;
  const CELL = /<c\b[^>]*?(?:\/>|>[\s\S]*?<\/c>)/g;

  function cellText(cell, sst) {
    const a = attrs(cell.slice(0, cell.indexOf('>') + 1));
    if (a.t === 's') {
      const v = /<v>(\d+)<\/v>/.exec(cell);
      return v ? sst[Number(v[1])] : null;
    }
    if (a.t === 'inlineStr') return texts(cell, 't');
    return null;
  }

  function fillCell(cell, ctx, scope, sst) {
    const text = cellText(cell, sst);
    if (text == null || !text.includes('{{')) return cell;
    const a = attrs(cell.slice(0, cell.indexOf('>') + 1));
    const head = `<c r="${a.r}"${a.s ? ` s="${a.s}"` : ''}`;
    const num = ONLY_NUMBER.exec(text);
    if (num) {
      const v = lookup(ctx, num[1], scope);
      if (v == null || v === '') return `${head}/>`;
      if (typeof v !== 'number' || !Number.isFinite(v)) throw new Error(`{{n:${num[1]}}} should be a number but is "${v}".`);
      return `${head}><v>${v}</v></c>`;
    }
    return `${head} t="inlineStr"><is><t xml:space="preserve">${encode(fillText(text, ctx, scope))}</t></is></c>`;
  }

  // a cell reference on the template row, moved down `by` rows (absolute rows, $6, stay put)
  const moveRefs = (formula, row, by) => formula.replace(/(\$?[A-Z]{1,3})(\d+)(?![\d(!])/g, (m, col, r) => (Number(r) === row && !col.endsWith('$') ? `${col}${row + by}` : m));

  // a cell with something in it: a value, a formula or text (an empty cell can still carry formatting)
  const hasContent = (c) => /<v>|<f[\s>]|<is>/.test(c);

  function fillSheet(xml, ctx, sst) {
    // a formula's saved result is the template's (Excel saves one, sometimes showing a slot's text): drop it, the
    // workbook recalculates on opening
    xml = xml.replace(/(<f\b[^>]*\/>|<f\b[^>]*>[\s\S]*?<\/f>)<v>[\s\S]*?<\/v>/g, '$1');
    const rows = xml.match(ROW) || [];
    let repeat = null;
    const out = [];
    for (const rowXml of rows) {
      const cells = rowXml.match(CELL) || [];
      const list = cells.map((c) => cellText(c, sst)).filter((t) => t && t.includes('{{')).map((t) => listIn(t, ctx)).find(Boolean);
      const r = Number(attrs(rowXml.slice(0, rowXml.indexOf('>') + 1)).r);
      if (repeat) {
        // rows below the repeating row: formatting only (e.g. a table formatted further down) is dropped, since the
        // repeated rows carry the template row's own formatting; anything with content can't stay below it
        if (cells.some(hasContent)) throw new Error(`Row ${r} comes after the repeating row ${repeat.row}: a repeating row must be the last on its sheet (empty, formatted rows below it are fine).`);
        out.push([rowXml, '']);
        continue;
      }
      if (!list) {
        out.push([rowXml, rowXml.replace(CELL, (c) => fillCell(c, ctx, null, sst))]);
        continue;
      }
      const items = ctx[list];
      repeat = { row: r, n: items.length, list };
      const copies = items.map((item, i) => rowXml
        .replace(/(<row\b[^>]*\br=")\d+"/, `$1${r + i}"`)
        .replace(CELL, (c) => {
          const filled = fillCell(c, ctx, { name: list, item }, sst)
            .replace(/(<c\b[^>]*\br="[A-Z]+)\d+"/, `$1${r + i}"`);
          return filled.replace(/<f\b([^>]*)>([\s\S]*?)<\/f>/, (m, fa, f) => `<f${fa.replace(/\s(t|ref|si)="[^"]*"/g, '')}>${moveRefs(f, r, i)}</f>`)
            .replace(/(<\/f>)<v>[\s\S]*?<\/v>/, '$1');
        }));
      out.push([rowXml, copies.join('')]);
    }
    let i = 0;
    let filled = xml.replace(ROW, () => out[i++][1]);
    if (repeat) {
      const last = repeat.row + Math.max(repeat.n, 1) - 1;
      filled = filled.replace(/(<dimension ref="[A-Z]+\d+:[A-Z]+)(\d+)"/, (m, a, b) => `${a}${Math.max(Number(b), last)}"`);
    }
    return { xml: fillXml(filled, ctx), repeat };
  }

  // a range on a repeating row, stretched to every row: 'Data'!$C$6:$C$6 (or 'Data'!$C$6 in a chart) -> 'Data'!$C$6:$C$29
  function stretch(text, sheet, row, n, singles) {
    const name = sheet.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const re = new RegExp(`((?:'${name}'|${name})!)(\\$?[A-Z]{1,3}\\$?)${row}(?::(\\$?[A-Z]{1,3}\\$?)${row})?(?![\\d:])`, 'g');
    return text.replace(re, (m, sh, c1, c2) => (c2 || singles ? `${sh}${c1}${row}:${c2 || c1}${row + Math.max(n, 1) - 1}` : m));
  }

  async function fillXlsx(bytes, ctx) {
    const zip = await libs.JSZip.loadAsync(bytes);
    const read = (p) => (zip.file(p) ? zip.file(p).async('string') : Promise.resolve(null));
    const sstXml = await read('xl/sharedStrings.xml');
    const sst = sstXml ? (sstXml.match(/<si>[\s\S]*?<\/si>/g) || []).map((si) => texts(si, 't')) : [];
    let wb = await read('xl/workbook.xml');
    const targets = relTargets(await read('xl/_rels/workbook.xml.rels'), 'xl');
    const sheets = [...wb.matchAll(/<sheet\b[^>]*>/g)].map((m) => {
      const a = attrs(m[0]);
      return { name: decode(a.name), path: targets[a['r:id']] };
    });
    const repeats = [];
    for (const s of sheets) {
      const res = fillSheet(await read(s.path), ctx, sst);
      zip.file(s.path, res.xml);
      if (res.repeat) repeats.push({ sheet: s.name, ...res.repeat });
    }
    // ranges on the repeating rows, wherever they're used: formulas, defined names, charts
    const parts = Object.keys(zip.files).filter((p) => /^xl\/(worksheets|charts)\/[^/]+\.xml$/.test(p) || p === 'xl/workbook.xml');
    for (const p of parts) {
      let xml = p === 'xl/workbook.xml' ? wb : await read(p);
      const chart = p.startsWith('xl/charts/');
      if (chart) xml = fillXml(xml.replace(/<((?:c:)?)(numCache|strCache)>[\s\S]*?<\/\1\2>/g, ''), ctx);  // Excel redraws from the cells
      for (const r of repeats) {
        xml = xml.replace(/(<(?:c:)?f>|<definedName\b[^>]*>|<f\b[^>]*>)([\s\S]*?)(<\/(?:c:)?f>|<\/definedName>)/g, (m, a, f, b) => a + stretch(f, r.sheet, r.row, r.n, chart) + b);
      }
      if (p === 'xl/workbook.xml') wb = xml; else zip.file(p, xml);
    }
    // recalculate every formula on opening (the template's saved results are for no data)
    wb = /<calcPr\b/.test(wb)
      ? wb.replace(/<calcPr\b([^>]*?)\s*\/>/, (m, a) => `<calcPr${a.replace(/\sfullCalcOnLoad="[^"]*"/, '')} fullCalcOnLoad="1"/>`)
      : wb.replace(/(<\/sheets>(?:\s*<definedNames>[\s\S]*?<\/definedNames>)?)/, '$1<calcPr fullCalcOnLoad="1"/>');
    zip.file('xl/workbook.xml', wb);
    if (zip.file('xl/calcChain.xml')) {
      zip.remove('xl/calcChain.xml');
      zip.file('xl/_rels/workbook.xml.rels', (await read('xl/_rels/workbook.xml.rels')).replace(/<Relationship\b[^>]*calcChain[^>]*\/>/, ''));
      zip.file('[Content_Types].xml', (await read('[Content_Types].xml')).replace(/<Override\b[^>]*calcChain[^>]*\/>/, ''));
    }
    for (const p of ['docProps/core.xml', 'docProps/app.xml']) if (zip.file(p)) zip.file(p, fillXml(await read(p), ctx));
    return save(zip);
  }

  // ------------------------------------------------------------------ PowerPoint
  const PARA = /<a:p(?:\s[^>]*)?>[\s\S]*?<\/a:p>/g;
  const first = (re, s) => (re.exec(s) || [''])[0];

  // a paragraph with slots: its text (however PowerPoint split it into runs) filled in, in its first run's style;
  // a value with line breaks becomes one paragraph per line
  function fillParagraphs(xml, ctx) {
    return xml.replace(PARA, (p) => {
      const text = texts(p, 'a:t');
      if (!text.includes('{{')) return p;
      const open = first(/^<a:p(?:\s[^>]*)?>/, p);
      const pPr = first(/<a:pPr\b[^>]*\/>|<a:pPr\b[^>]*>[\s\S]*?<\/a:pPr>/, p);
      const rPr = first(/<a:rPr\b[^>]*\/>|<a:rPr\b[^>]*>[\s\S]*?<\/a:rPr>/, p);
      const end = first(/<a:endParaRPr\b[^>]*\/>|<a:endParaRPr\b[^>]*>[\s\S]*?<\/a:endParaRPr>/, p);
      return fillText(text, ctx).split('\n').map((line) => `${open}${pPr}<a:r>${rPr}<a:t>${encode(line)}</a:t></a:r>${end}</a:p>`).join('');
    });
  }

  const colName = (i) => String.fromCharCode(65 + i);
  const pts = (vals, tag) => vals.map((v, i) => (v == null ? '' : `<c:pt idx="${i}"><c:v>${tag === 'num' ? v : encode(v)}</c:v></c:pt>`)).join('');

  function fillChart(xml, data, name) {
    const n = data.categories.length;
    let i = 0;
    const out = xml.replace(/<c:ser>[\s\S]*?<\/c:ser>/g, (ser) => {
      const s = data.series[i];
      const col = colName(1 + i);
      i += 1;
      if (!s) return '';
      const fc = first(/<c:formatCode>[\s\S]*?<\/c:formatCode>/, ser) || '<c:formatCode>General</c:formatCode>';
      return ser
        .replace(/<c:tx>[\s\S]*?<\/c:tx>/, `<c:tx><c:strRef><c:f>Sheet1!$${col}$1</c:f><c:strCache><c:ptCount val="1"/>${pts([s.name], 'str')}</c:strCache></c:strRef></c:tx>`)
        .replace(/<c:cat>[\s\S]*?<\/c:cat>/, `<c:cat><c:strRef><c:f>Sheet1!$A$2:$A$${n + 1}</c:f><c:strCache><c:ptCount val="${n}"/>${pts(data.categories, 'str')}</c:strCache></c:strRef></c:cat>`)
        .replace(/<c:val>[\s\S]*?<\/c:val>/, `<c:val><c:numRef><c:f>Sheet1!$${col}$2:$${col}$${n + 1}</c:f><c:numCache>${fc}<c:ptCount val="${n}"/>${pts(s.values, 'num')}</c:numCache></c:numRef></c:val>`)
        .replace(/<c:dPt>[\s\S]*?<\/c:dPt>/g, '');
    });
    if (i < data.series.length) throw new Error(`The template's chart:${name} has ${i} series; the data has ${data.series.length}.`);
    // a label every few categories, so months never crowd (about 9 labels across, like the site)
    return out.replace(/<c:tickLblSkip val="\d+"\/>/, `<c:tickLblSkip val="${Math.max(1, Math.ceil(n / 9))}"/>`);
  }

  // the workbook behind a PowerPoint chart ("Edit Data"), rewritten with the chart's new data
  async function fillChartWorkbook(bytes, data) {
    const zip = await libs.JSZip.loadAsync(bytes);
    const targets = relTargets(await zip.file('xl/_rels/workbook.xml.rels').async('string'), 'xl');
    const wbXml = await zip.file('xl/workbook.xml').async('string');
    const path = targets[attrs(first(/<sheet\b[^>]*>/, wbXml))['r:id']];
    const cell = (c, r, v) => (v == null ? '' : typeof v === 'number' ? `<c r="${c}${r}"><v>${v}</v></c>`
      : `<c r="${c}${r}" t="inlineStr"><is><t xml:space="preserve">${encode(v)}</t></is></c>`);
    const rows = [[null, ...data.series.map((s) => s.name)], ...data.categories.map((cat, k) => [cat, ...data.series.map((s) => s.values[k])])];
    const sheetData = `<sheetData>${rows.map((row, r) => `<row r="${r + 1}">${row.map((v, c) => cell(colName(c), r + 1, v)).join('')}</row>`).join('')}</sheetData>`;
    const xml = (await zip.file(path).async('string'))
      .replace(/<sheetData\/>|<sheetData>[\s\S]*?<\/sheetData>/, sheetData)
      .replace(/<dimension ref="[^"]*"\/>/, `<dimension ref="A1:${colName(data.series.length)}${rows.length}"/>`);
    zip.file(path, xml);
    return save(zip);
  }

  async function fillPptx(bytes, ctx) {
    const zip = await libs.JSZip.loadAsync(bytes);
    const read = (p) => zip.file(p).async('string');
    for (const p of Object.keys(zip.files).filter((x) => /^ppt\/(slides|notesSlides)\/[^/]+\.xml$/.test(x))) {
      let xml = fillParagraphs(await read(p), ctx);
      if (p.startsWith('ppt/slides/')) {
        const rels = relTargets(await read(p.replace('slides/', 'slides/_rels/') + '.rels'), 'ppt/slides');
        for (const frame of xml.match(/<p:graphicFrame>[\s\S]*?<\/p:graphicFrame>/g) || []) {
          const tag = /descr="chart:([\w-]+)"/.exec(frame);
          const rid = /<c:chart\b[^>]*r:id="([^"]+)"/.exec(frame);
          if (!tag || !rid) continue;
          const data = (ctx.charts || {})[tag[1]];
          if (!data) throw new Error(`The template has chart:${tag[1]}, which the data for this report doesn't have.`);
          const chartPath = rels[rid[1]];
          zip.file(chartPath, fillChart(await read(chartPath), data, tag[1]));
          const crels = relTargets(zip.file(chartPath.replace('charts/', 'charts/_rels/') + '.rels')
            ? await read(chartPath.replace('charts/', 'charts/_rels/') + '.rels') : '', 'ppt/charts');
          for (const t of Object.values(crels).filter((x) => x.endsWith('.xlsx'))) {
            zip.file(t, await fillChartWorkbook(await zip.file(t).async('uint8array'), data));
          }
        }
      }
      zip.file(p, fillXml(xml, ctx));
    }
    for (const p of ['docProps/core.xml', 'docProps/app.xml']) if (zip.file(p)) zip.file(p, fillXml(await read(p), ctx));
    return save(zip);
  }

  // ------------------------------------------------------------------ PDF
  const SKIP = Symbol('skip');

  function expand(node, ctx, scope) {
    if (typeof node === 'string') return fillText(node, ctx, scope);
    if (Array.isArray(node)) {
      return node.flatMap((x) => {
        if (x && typeof x === 'object' && !Array.isArray(x) && x.$each) {
          return lookup(ctx, x.$each).map((item) => expand(x.$do, ctx, { name: x.$each, item }));
        }
        const v = expand(x, ctx, scope);
        return v === SKIP ? [] : [v];
      });
    }
    if (node && typeof node === 'object') {
      if (node.$if) {
        const v = lookup(ctx, node.$if, scope);
        if (v == null || v === '' || (Array.isArray(v) && !v.length)) return SKIP;
      }
      if (node.$chart) {
        const data = (ctx.charts || {})[node.$chart];
        if (!data) throw new Error(`The PDF layout has $chart ${node.$chart}, which the data for this report doesn't have.`);
        return { svg: chartSvg(data, node), width: node.width, margin: node.margin || [0, 0, 0, 0] };
      }
      const out = {};
      for (const [k, v] of Object.entries(node)) {
        if (k === '$if') continue;
        const x = expand(v, ctx, scope);
        if (x !== SKIP) out[k] = x;
      }
      return out;
    }
    return node;
  }

  const GREEN = '#0E9F6E', FADED = '#B7E4CF', INK = '#25342A', MUTED = '#5F6F63', LINE = '#DCE8DC';
  const fmt = (v, f) => (v == null ? '' : f && f.startsWith('pct') ? `${v.toFixed(1)}%`
    : Math.round(v).toLocaleString('en-AU'));
  const svgText = (x, y, s, size, colour, anchor, weight) => `<text x="${x.toFixed(1)}" y="${y.toFixed(1)}" font-family="Roboto" font-size="${size}" fill="${colour}"${anchor ? ` text-anchor="${anchor}"` : ''}${weight ? ` font-weight="${weight}"` : ''}>${encode(s)}</text>`;

  // charts for the PDF: horizontal bars for categories, columns or a line for months. Small data labels; a target is
  // a dashed line drawn on top. Months still in progress are drawn paler.
  function chartSvg(data, o) {
    const W = o.width, H = o.height, s = data.series[0], f = s.format || data.format, vals = s.values;
    const parts = [];
    const max = Math.max(...vals.filter((v) => v != null), data.target || 0) || 1;
    if (o.kind === 'hbar') {
      const labW = o.labelWidth || 78, valW = 34, rowH = H / vals.length, bh = Math.min(14, rowH * 0.62);
      vals.forEach((v, i) => {
        const y = i * rowH + (rowH - bh) / 2, w = v == null ? 0 : (W - labW - valW) * (v / max);
        parts.push(svgText(labW - 6, y + bh * 0.75, data.categories[i], 7.5, INK, 'end'));
        parts.push(`<rect x="${labW}" y="${y.toFixed(1)}" width="${Math.max(w, 0.5).toFixed(1)}" height="${bh.toFixed(1)}" fill="${GREEN}"/>`);
        parts.push(svgText(labW + w + 3, y + bh * 0.75, fmt(v, f), 7, MUTED));
      });
    } else {
      const top = 12, bottom = 16, plotH = H - top - bottom, n = vals.length, x0 = o.kind === 'line' ? 26 : 0, step = (W - x0) / n;
      const every = Math.max(1, Math.ceil(n / 9));
      // columns start at zero; a line (a rate) is scaled to its own range, in round steps, with light gridlines
      let lo = 0, hi = max;
      if (o.kind === 'line') {
        const all = vals.filter((v) => v != null).concat(data.target != null ? [data.target] : []);
        const stepV = (Math.max(...all) - Math.min(...all)) > 20 ? 10 : 5;
        lo = Math.max(0, Math.floor((Math.min(...all) - 1) / stepV) * stepV);
        hi = Math.ceil((Math.max(...all) + 1) / stepV) * stepV;
        for (let g = lo; g <= hi; g += stepV) {
          const gy = top + plotH * (1 - (g - lo) / (hi - lo));
          parts.push(`<line x1="${x0 - 2}" y1="${gy.toFixed(1)}" x2="${W}" y2="${gy.toFixed(1)}" stroke="${LINE}" stroke-width="0.5"/>`);
          parts.push(svgText(x0 - 5, gy + 2.5, fmt(g, f).replace('.0%', '%'), 6.5, MUTED, 'end'));
        }
      }
      const y = (v) => top + plotH * (1 - (v - lo) / (hi - lo));
      parts.push(`<line x1="${x0}" y1="${top + plotH}" x2="${W}" y2="${top + plotH}" stroke="${LINE}" stroke-width="0.8"/>`);
      if (o.kind === 'columns') {
        vals.forEach((v, i) => {
          if (v == null) return;
          const x = x0 + i * step + step * 0.15, w = step * 0.7, done = !data.status || data.status[i] !== 'Incomplete';
          parts.push(`<rect x="${x.toFixed(1)}" y="${y(v).toFixed(1)}" width="${w.toFixed(1)}" height="${(top + plotH - y(v)).toFixed(1)}" fill="${done ? GREEN : FADED}"/>`);
          parts.push(svgText(x + w / 2, y(v) - 2.5, fmt(v, f), n > 18 ? 5.5 : 6.5, MUTED, 'middle'));
        });
      } else {
        const ptsXY = vals.map((v, i) => (v == null ? null : [x0 + i * step + step / 2, y(v)])).filter(Boolean);
        parts.push(`<polyline points="${ptsXY.map((p) => p.map((c) => c.toFixed(1)).join(',')).join(' ')}" fill="none" stroke="${GREEN}" stroke-width="1.6"/>`);
        // every point labelled when there's room; otherwise the ones with a month label under them, the highest, the lowest
        const known = vals.filter((v) => v != null);
        const hiV = Math.max(...known), loV = Math.min(...known);
        vals.forEach((v, i) => {
          if (v == null) return;
          const x = x0 + i * step + step / 2;
          parts.push(`<circle cx="${x.toFixed(1)}" cy="${y(v).toFixed(1)}" r="1.8" fill="${!data.status || data.status[i] !== 'Incomplete' ? GREEN : FADED}"/>`);
          if (n <= 12 || i % every === 0 || i === n - 1 || v === hiV || v === loV) {
            parts.push(svgText(x, v === loV && i !== n - 1 ? y(v) + 9 : y(v) - 4, fmt(v, f), 6.5, MUTED, 'middle'));
          }
        });
      }
      data.categories.forEach((c, i) => {
        if (i % every === 0 || i === n - 1) parts.push(svgText(x0 + i * step + step / 2, H - 4, c, 7, MUTED, 'middle'));
      });
      if (data.target != null) {            // the target, on top of the data
        const ty = y(data.target);
        parts.push(`<line x1="${x0}" y1="${ty.toFixed(1)}" x2="${W}" y2="${ty.toFixed(1)}" stroke="${INK}" stroke-width="1" stroke-dasharray="4,3"/>`);
        parts.push(svgText(W, ty - 3, `Target ${fmt(data.target, f)}`, 7, INK, 'end', 'bold'));
      }
    }
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${parts.join('')}</svg>`;
  }

  // table borders a layout can name ("layout": "cards"), since a JSON file can't hold pdfmake's border functions
  const TABLE_LAYOUTS = {
    cards: { hLineWidth: () => 0.8, vLineWidth: () => 0.8, hLineColor: () => LINE, vLineColor: () => LINE },
    rows: {                 // a table: a firm line under the heading, light lines between rows, compact
      hLineWidth: (i, node) => (i === 0 || i === node.table.body.length ? 0 : i === 1 ? 0.8 : 0.4),
      vLineWidth: () => 0,
      hLineColor: (i) => (i === 1 ? INK : LINE),
      paddingLeft: (i) => (i ? 4 : 0), paddingRight: (i, node) => (i === node.table.widths.length - 1 ? 0 : 4),
      paddingTop: () => 1.6, paddingBottom: () => 1.6,
    },
  };

  function buildPdf(layout, ctx) {
    const { footer, header, ...doc } = layout;
    const dd = expand(doc, ctx);
    if (footer) dd.footer = (page, pages) => expand(footer, { ...ctx, page, pages });
    if (header) dd.header = (page, pages) => expand(header, { ...ctx, page, pages });
    dd.defaultStyle = { font: 'Roboto', ...(dd.defaultStyle || {}) };
    return new Promise((resolve, reject) => {
      try {
        libs.pdfMake.createPdf(dd, TABLE_LAYOUTS).getBuffer((buf) => resolve(new Uint8Array(buf)));
      } catch (e) { reject(e); }
    });
  }

  // ------------------------------------------------------------------ loading (browser)
  const loaded = {};
  function script(src) {
    if (!loaded[src]) {
      loaded[src] = new Promise((resolve, reject) => {
        const s = document.createElement('script');
        s.src = src;
        s.onload = resolve;
        s.onerror = () => reject(new Error(`Couldn't load ${src}`));
        document.head.appendChild(s);
      });
    }
    return loaded[src];
  }

  async function ready(fmt, opts) {
    if (libs.reports && (fmt === 'pdf' ? libs.pdfMake : libs.JSZip)) return;
    const v = opts.ver ? `?v=${opts.ver}` : '';
    await script(`assets/exports/reports.js${v}`);
    libs.reports = root.FourthSheetReports;
    if (fmt === 'pdf') {
      await script(`assets/vendor/pdfmake-0.2.20.min.js${v}`);
      await script(`assets/vendor/pdfmake-0.2.20-vfs_fonts.js${v}`);
      libs.pdfMake = root.pdfMake;
    } else {
      await script(`assets/vendor/jszip-3.10.1.min.js${v}`);
      libs.JSZip = root.JSZip;
    }
  }

  // ------------------------------------------------------------------ the one call
  async function build(period, fmt, opts = {}) {
    const slug = period.exports_template;
    if (!TYPES[fmt]) throw new Error(`No ${fmt} export.`);
    if (typeof document !== 'undefined') await ready(fmt, opts);
    const report = libs.reports && libs.reports[slug];
    if (!report) throw new Error(`No template data for ${slug}.`);
    const ctx = report(period, opts.now || new Date());
    const fetchTemplate = opts.fetchTemplate || ((name) => fetch(`assets/exports/templates/${name}${opts.ver ? `?v=${opts.ver}` : ''}`).then((r) => {
      if (!r.ok) throw new Error(`Couldn't load the template ${name}`);
      return name.endsWith('.json') ? r.json() : r.arrayBuffer();
    }));
    let bytes;
    if (fmt === 'xlsx') bytes = await fillXlsx(await fetchTemplate(`${slug}.xlsx`), ctx);
    else if (fmt === 'pptx') bytes = await fillPptx(await fetchTemplate(`${slug}.pptx`), ctx);
    else bytes = await buildPdf(await fetchTemplate(`${slug}.pdf.json`), ctx);
    return { bytes, name: `${ctx.file_name}.${fmt}`, type: TYPES[fmt] };
  }

  const api = { build, use: (x) => Object.assign(libs, x), _chartSvg: chartSvg };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.FourthSheetExports = api;
}(typeof self !== 'undefined' ? self : this));
