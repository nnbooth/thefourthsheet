#!/usr/bin/env node
/*
render_templated.js — make every templated report's downloads, every period, the way the site makes them when someone
clicks Export (assets/exports/fill.js filling assets/exports/templates/ with data/reports/<report>.json). For the
publish check (exports_match.py runs this, then checks the files like any other download). Run from the repo root:

    node tools/3_publish_site/tests/render_templated.js <out folder> [report ...]

Writes <out folder>/<period>/<report>.xlsx|pptx|pdf. Needs the libraries the site loads (assets/vendor/), nothing else.
*/
'use strict';
const fs = require('fs');
const path = require('path');

const REPO = path.resolve(__dirname, '..', '..', '..');
const out = process.argv[2];
if (!out) { console.error('usage: render_templated.js <out folder> [report ...]'); process.exit(2); }
const only = process.argv.slice(3);

// the browser builds of the libraries, run as Node modules (both are UMD). pdfmake's reads navigator, which Node only
// has from version 21 (the publish workflow runs 20)
if (typeof globalThis.navigator === 'undefined') globalThis.navigator = { userAgent: 'node' };
function load(file, name) {
  const m = { exports: {} };
  new Function('module', 'exports', 'self', 'window', fs.readFileSync(path.join(REPO, file), 'utf8'))(m, m.exports, globalThis, globalThis);
  return m.exports && Object.keys(m.exports).length ? m.exports : globalThis[name];
}
const JSZip = load('assets/vendor/jszip-3.10.1.min.js', 'JSZip');
const pdfMake = load('assets/vendor/pdfmake-0.2.20.min.js', 'pdfMake');
globalThis.pdfMake = pdfMake;
load('assets/vendor/pdfmake-0.2.20-vfs_fonts.js', 'pdfMake');
const kit = require(path.join(REPO, 'assets/exports/fill.js'));
kit.use({ JSZip, pdfMake, reports: require(path.join(REPO, 'assets/exports/reports.js')) });

const TEMPLATES = path.join(REPO, 'assets/exports/templates');
const fetchTemplate = async (name) => {
  const f = path.join(TEMPLATES, name);
  return name.endsWith('.json') ? JSON.parse(fs.readFileSync(f, 'utf8')) : fs.readFileSync(f);
};

(async () => {
  let n = 0;
  for (const f of fs.readdirSync(path.join(REPO, 'data/reports')).filter((x) => x.endsWith('.json') && x !== 'cards.json')) {
    const d = JSON.parse(fs.readFileSync(path.join(REPO, 'data/reports', f), 'utf8'));
    for (const [period, r] of Object.entries(d.by_period)) {
      if (!r.exports_template || (only.length && !only.includes(r.slug))) continue;
      fs.mkdirSync(path.join(out, period), { recursive: true });
      for (const fmt of ['xlsx', 'pptx', 'pdf']) {
        const file = await kit.build(r, fmt, { fetchTemplate });
        fs.writeFileSync(path.join(out, period, `${r.slug}.${fmt}`), file.bytes);
        n += 1;
      }
    }
  }
  console.log(`made ${n} templated downloads in ${out}`);
})().catch((e) => { console.error(`FAIL ${e.message}`); process.exit(1); });
