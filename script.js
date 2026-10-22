/*
  script.js — The Fourth Sheet

  KEY LOCATIONS:
  - Report cards (edit this to add reports) .. REPORTS list, just below
  - Report card builder ...................... renderReports() / buildReportCard()
  - Loading message + 8-second fallback ...... watchEmbedLoad()
  - Game (load on Play) ...................... setupGameSlot()
  - Prices ($110 an hour, $800 a day) ........ SHOW_PRICES / PRICES
  - Analytics (off until a token is set) ..... ANALYTICS / track()
  - Home-page sample dashboard ............... setupHeroDash() (data: data/dashboard.json)
  - Generated data files (data/*.json) ....... loadData()
  - Home-page opening animation ............. setupIntro() / INTRO_HOLD_MS
  - Mobile menu + footer year ................ bottom of file (DOMContentLoaded)

  No frameworks. Publishing (.github/workflows/pages.yml) stamps every ?v= with the commit; locally it's ?v=dev.
*/

/* ---------------------------------------------------------------------------
   REPORTS — one entry per report card in the "Reports" section.

   To add a report, copy one { ... } block and change the values:
     title     Card heading, e.g. 'Sales'.
     question  The one-line question the report answers.
     embedUrl  Power BI "Publish to web" link (starts with
               https://app.powerbi.com/view?r=...). Leave as '' while the
               report is still being built: the card then shows a mock
               dashboard outline and "In build — preview coming soon".
               Never paste the address you see while signed in to your
               own Power BI workspace: visitors can't sign in to it.
     status    Short label for the chip on the card, e.g. 'Live demo'.
               Ignored while embedUrl is empty (the chip says "In build").
     preview   Picture shown while embedUrl is empty, e.g. a screenshot of
               the report in progress. The current ones are mock-ups made by
               tools/archive/render_mockups.py. Leave as '' for a plain grey outline.
--------------------------------------------------------------------------- */
const REPORTS = [
  {
    title: 'Sales',
    preview: 'media/mockups/report-sales.png',
    question: "What's selling, what's cancelling and what's in the pipeline",
    embedUrl: '',
    status: 'In build',
  },
  {
    title: 'Purchasing',
    preview: 'media/mockups/report-purchasing.png',
    question: 'Which suppliers are late, and where costs are moving',
    embedUrl: '',
    status: 'In build',
  },
  {
    title: 'Payroll & overtime',
    preview: 'media/mockups/report-payroll.png',
    question: 'Where overtime is growing, and why',
    embedUrl: '',
    status: 'In build',
  },
];

// How long an embedded sheet/report may take before we show the
// "taking longer than usual" message (milliseconds).
const EMBED_SLOW_AFTER_MS = 8000;

/* ---------------------------------------------------------------------------
   Report cards
--------------------------------------------------------------------------- */

// Small helper: create an element with a class and optional text.
// Uses textContent (not innerHTML) so report text can never inject HTML.
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

// The "In build" placeholder: a grey outline of a dashboard (KPI tiles,
// a bar chart and a table) drawn with plain divs styled in styles.css
// (search "REPORT MOCK"). `variant` just varies the bar heights per card.
function buildReportMock(variant) {
  const barSets = [
    [45, 60, 52, 70, 64, 82, 76],
    [70, 58, 66, 50, 62, 48, 55],
    [30, 38, 35, 48, 55, 61, 72],
  ];
  const bars = barSets[variant % barSets.length];

  const mock = el('div', 'report-mock');
  mock.setAttribute('aria-hidden', 'true'); // decorative only

  const kpis = el('div', 'mock-kpis');
  for (let i = 0; i < 3; i += 1) kpis.appendChild(el('span', 'mock-kpi'));

  const chart = el('div', 'mock-chart');
  bars.forEach((height) => {
    const bar = el('span', 'mock-bar');
    bar.style.height = `${height}%`;
    chart.appendChild(bar);
  });

  const rows = el('div', 'mock-rows');
  for (let i = 0; i < 3; i += 1) rows.appendChild(el('span', 'mock-row'));

  mock.append(kpis, chart, rows);
  return mock;
}

function buildReportCard(report, index) {
  const isLive = Boolean(report.embedUrl);

  const card = el('article', isLive ? 'report-card report-card--live' : 'report-card');

  const header = el('div', 'report-card-header');
  header.appendChild(el('h3', '', report.title));
  header.appendChild(el('span', 'status-chip', isLive ? report.status || 'Live demo' : 'In build'));
  card.appendChild(header);

  card.appendChild(el('p', 'report-question', report.question));

  const frame = el('div', 'report-frame');

  if (isLive) {
    // Real Power BI "Publish to web" report, loaded only when scrolled near.
    frame.setAttribute('data-embed', '');
    frame.dataset.slowMessage = 'This report is taking longer than usual to load. Try refreshing the page in a moment.';

    const status = el('div', 'embed-status');
    status.setAttribute('role', 'status');
    status.appendChild(el('span', 'spinner'));
    status.appendChild(el('span', 'embed-status-msg', 'Loading report…'));

    const iframe = document.createElement('iframe');
    iframe.src = report.embedUrl;
    iframe.title = `${report.title} report: interactive Power BI preview`;
    iframe.loading = 'lazy';
    iframe.allowFullscreen = true;

    frame.append(status, iframe);
  } else {
    // Nothing to embed yet: show the mock outline, never an empty iframe.
    frame.classList.add('report-frame--pending');
    if (report.preview) {
      // Preview image (a mock-up for now), opens full size in a new tab
      const link = document.createElement('a');
      link.href = report.preview;
      link.target = '_blank';
      link.rel = 'noopener';
      link.className = 'report-preview';
      const img = document.createElement('img');
      img.src = report.preview;
      img.alt = `${report.title} report preview with sample data.`;
      img.loading = 'lazy';
      img.width = 1600;
      img.height = 900;
      link.appendChild(img);
      frame.appendChild(link);
    } else {
      frame.appendChild(buildReportMock(index));
    }
    frame.appendChild(el('p', 'report-pending-msg', report.preview ? 'Sample data · live report coming soon' : 'Live report coming soon'));
  }

  card.appendChild(frame);
  return card;
}

// What made the hand-built charts (Nathan: every hand-built chart or report says what tools made it; embeds say it themselves)

function setupTitleBar() {
  // A page title kept in view: once the big h1[data-title-bar] scrolls under the site header, a slim bar with the title
  // (and a "jump to" menu) shows just below the header. Fixed, so nothing on the page moves when it appears.
  const h1 = document.querySelector('h1[data-title-bar]');
  const bar = document.getElementById('title-bar');
  const header = document.querySelector('.site-header');
  if (!h1 || !bar || !header) return;
  const place = () => { bar.style.top = `${Math.max(0, header.getBoundingClientRect().bottom)}px`; };
  const update = () => { place(); bar.classList.toggle('is-shown', h1.getBoundingClientRect().bottom < header.getBoundingClientRect().bottom); };
  window.addEventListener('scroll', update, { passive: true });
  window.addEventListener('resize', update);
  update();
  const sel = bar.querySelector('select');
  if (sel) sel.addEventListener('change', () => {
    const t = sel.value && document.getElementById(sel.value);
    if (t) { const y = t.getBoundingClientRect().top + window.scrollY - header.offsetHeight - bar.offsetHeight - 8; window.scrollTo({ top: y }); }
    sel.value = '';
  });
}

function setupChartTips() {
  // Every chart point, bar or row with data-tip shows its label and value: on hover, on keyboard focus, and on tap.
  const tip = document.createElement('div');
  tip.className = 'chart-tip';
  tip.setAttribute('role', 'status');
  tip.hidden = true;
  document.body.appendChild(tip);
  let cur = null;
  const show = (el) => {
    if (!el || el === cur) return;
    cur = el;
    tip.textContent = el.dataset.tip;
    tip.hidden = false;
    const a = el.querySelector('.dash-dot, .dash-bar, .mb-t i') || el;
    const r = a.getBoundingClientRect();
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    let x = r.left + r.width / 2 - tw / 2;
    x = Math.max(8, Math.min(x, window.innerWidth - tw - 8));
    let y = r.top - th - 8;
    if (y < 8) y = r.bottom + 8;
    tip.style.left = `${Math.round(x + window.scrollX)}px`;
    tip.style.top = `${Math.round(y + window.scrollY)}px`;
  };
  const hide = () => { cur = null; tip.hidden = true; };
  const find = (t) => (t && t.closest ? t.closest('[data-tip]') : null);
  document.addEventListener('pointerover', (e) => { const el = find(e.target); if (el) show(el); else if (e.pointerType === 'mouse') hide(); });
  document.addEventListener('pointerdown', (e) => { const el = find(e.target); if (el) { cur = null; show(el); } else hide(); });
  document.addEventListener('focusin', (e) => { const el = find(e.target); if (el) show(el); else hide(); });
  document.addEventListener('scroll', () => { if (cur) { const el = cur; cur = null; show(el); } }, { passive: true });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') hide(); });
}

function setupLightbox() {
  // Mock-up images open in a <dialog> on the page (Esc or the close button shuts it); the link still works without JS.
  const links = document.querySelectorAll('a.display-link');
  if (!links.length) return;
  const dlg = document.createElement('dialog');
  dlg.className = 'lightbox';
  dlg.innerHTML = '<button type="button" class="lightbox-close" aria-label="Close">&times;</button><img alt="" /><p class="lightbox-cap"></p>';
  document.body.appendChild(dlg);
  const img = dlg.querySelector('img'), cap = dlg.querySelector('.lightbox-cap');
  links.forEach((a) => a.addEventListener('click', (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey) return;            // let a new-tab click through
    e.preventDefault();
    const src = a.querySelector('img');
    img.src = a.getAttribute('href');
    img.alt = src ? src.alt : '';
    const fc = a.closest('figure') && a.closest('figure').querySelector('figcaption');
    cap.textContent = fc ? fc.textContent : '';
    dlg.showModal();
  }));
  dlg.querySelector('.lightbox-close').addEventListener('click', () => dlg.close());
  dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });
}

function renderReports() {
  const grid = document.getElementById('report-grid');
  if (!grid) return;
  REPORTS.forEach((report, index) => grid.appendChild(buildReportCard(report, index)));
}

/* ---------------------------------------------------------------------------
   Loading state for embedded iframes (Power BI reports).

   Any element with a `data-embed` attribute that contains an <iframe> and an
   .embed-status box gets:
     - "is-loading" while waiting (spinner shown over the frame),
     - "is-loaded" once the iframe finishes loading (spinner hidden),
     - "is-slow" if it hasn't loaded EMBED_SLOW_AFTER_MS after scrolling
       into view (message swapped for the element's data-slow-message).
   The timer starts on scroll-into-view because the iframes are lazy-loaded
   and don't start downloading until then.
--------------------------------------------------------------------------- */
function watchEmbedLoad(container) {
  const iframe = container.querySelector('iframe');
  const message = container.querySelector('.embed-status-msg');
  if (!iframe) return;

  container.classList.add('is-loading');
  let slowTimer = null;

  iframe.addEventListener('load', () => {
    clearTimeout(slowTimer);
    container.classList.remove('is-loading', 'is-slow');
    container.classList.add('is-loaded');
  });

  const startTimer = () => {
    slowTimer = setTimeout(() => {
      if (container.classList.contains('is-loaded')) return;
      container.classList.add('is-slow');
      if (message && container.dataset.slowMessage) {
        message.textContent = container.dataset.slowMessage;
      }
    }, EMBED_SLOW_AFTER_MS);
  };

  if (!('IntersectionObserver' in window)) {
    startTimer();
    return;
  }

  const observer = new IntersectionObserver((entries) => {
    if (entries.some((entry) => entry.isIntersecting)) {
      observer.disconnect();
      startTimer();
    }
  });
  observer.observe(container);
}

/* ---------------------------------------------------------------------------
   EXPORT MENU — one Export button and menu wherever there are downloads (report pages, the home hero, the
   deliveries map, and any future embedded report: Power BI or other iframe).

     const menu = mountExportMenu(container, { period, filterLabel, exports: {xlsx, pdf, pptx}, meta: {pdf_pages, pptx_slides} });
     menu.update({ period, filterLabel, exports, meta });     // when the period or the filter changes
     mountExportMenu(container, { period, build: (fmt) => promiseOf({ bytes, name, type }) });   // made on click, nothing stored

   With build (a report filled from its templates: assets/exports/fill.js), each format is made when it's chosen and
   handed straight to the browser as a download.

   Static pages can declare one instead: <div data-export data-export-period="September 2026" data-export-filter="All"
   data-export-xlsx="…" data-export-pdf="…" data-export-pptx="…" data-export-pdf-pages="5" data-export-pptx-slides="9"></div>
   No exports for a period (exports null) shows the rows disabled: "Not available for a part month".
--------------------------------------------------------------------------- */
const EXPORT_FORMATS = [
  { fmt: 'xlsx', badge: 'XLSX', name: 'Spreadsheet', what: 'Every figure as a live formula, the data behind it, and charts. Opens in Excel, Google Sheets or Numbers.' },
  { fmt: 'pdf', badge: 'PDF', name: 'PDF report', what: 'Print-ready A4, the same pages as this screen. For the board pack or your accountant.' },
  { fmt: 'pptx', badge: 'PPTX', name: 'Slides', what: 'Editable charts, one slide per finding. For the monthly meeting. Opens in PowerPoint, Google Slides or Keynote.' },
];
const ICON_DOWNLOAD = '<svg class="xm-ico" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 4v11m0 0-4.5-4.5M12 15l4.5-4.5M5 19h14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const ICON_CHEVRON = '<svg class="xm-chev" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="m7 10 5 5 5-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
let exportMenuCount = 0;
const fileSize = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

function mountExportMenu(container, opts) {
  const id = `xm-${exportMenuCount += 1}`;
  let state = { ...opts };
  container.classList.add('xm');
  container.innerHTML = `<button type="button" class="xm-btn" aria-haspopup="true" aria-expanded="false" aria-controls="${id}">${ICON_DOWNLOAD}<span>Export</span>${ICON_CHEVRON}</button>`
    + `<div class="xm-menu" id="${id}" role="menu" aria-label="Export" hidden>`
    + `<p class="xm-head"></p>`
    + EXPORT_FORMATS.map((f) => `<a class="xm-item" role="menuitem" data-fmt="${f.fmt}" data-track="export" data-track-detail="${f.fmt}" download><span class="xm-badge xm-badge--${f.fmt}">${f.badge}</span><span class="xm-text"><b>${f.name}</b><span>${f.what}</span><small class="xm-size"></small></span></a>`).join('')
    // (An "Include the workings" option would go here. Every export includes the workings for now.)
    + `<div class="xm-foot"><a class="xm-sub" role="menuitem" href="contact.html?topic=monthly">Get this report on your schedule &rarr;</a></div>`
    + `</div>`;
  const btn = container.querySelector('.xm-btn');
  const menu = container.querySelector('.xm-menu');
  const items = () => [...menu.querySelectorAll('[role="menuitem"]')].filter((x) => !x.hasAttribute('aria-disabled'));

  function paint() {
    const q = new URLSearchParams({ topic: 'monthly', report: state.report || document.title.split(' | ')[0], period: state.period || '', view: state.filterLabel || '' });
    menu.querySelector('.xm-sub').href = `contact.html?${q}`;
    const bits = [state.filterLabel, 'sample data'].filter(Boolean).map(esc).join(' · ');
    menu.querySelector('.xm-head').innerHTML = `Export <strong>${esc(state.period || '')}</strong>${bits ? ` · ${bits}` : ''}`;
    menu.querySelectorAll('.xm-item').forEach((a) => {
      const href = state.exports && state.exports[a.dataset.fmt];
      const size = a.querySelector('.xm-size');
      if (state.build) {               // made when chosen: no file to link to yet
        a.href = '#';
        a.removeAttribute('download');
        a.removeAttribute('aria-disabled');
        a.removeAttribute('tabindex');
        if (!a.hasAttribute('aria-busy')) size.textContent = 'Made when you choose it';
      } else if (href) {
        a.href = href;
        a.removeAttribute('aria-disabled');
        a.removeAttribute('tabindex');
        const m = state.meta || {};
        // saved as e.g. "Sample Electrical & Air Pty Ltd - Job margins - September 2026 - generated 2026-10-08 1435.xlsx"
        if (m.names && m.names[a.dataset.fmt]) a.setAttribute('download', m.names[a.dataset.fmt]); else a.setAttribute('download', '');
        size.textContent = a.dataset.fmt === 'pdf' && m.pdf_pages ? `${m.pdf_pages} page${m.pdf_pages === 1 ? '' : 's'}`
          : a.dataset.fmt === 'pptx' && m.pptx_slides ? `${m.pptx_slides} slide${m.pptx_slides === 1 ? '' : 's'}` : '';
      } else {
        a.removeAttribute('href');
        a.setAttribute('aria-disabled', 'true');
        a.tabIndex = -1;
        size.textContent = (state.meta && state.meta.unavailable) || 'Not available for a part month';
      }
    });
  }
  function sizeExcel() {                         // the workbook's size, read when the menu opens (blank if that fails)
    const a = menu.querySelector('.xm-item[data-fmt="xlsx"]');
    if (state.build || !a.getAttribute('href')) return;
    fetch(a.getAttribute('href'), { method: 'HEAD' }).then((r) => {
      const n = Number(r.headers.get('content-length'));
      if (r.ok && n) a.querySelector('.xm-size').textContent = fileSize(n);
    }).catch(() => {});
  }
  function open() {
    paint();
    menu.hidden = false;
    btn.setAttribute('aria-expanded', 'true');
    container.classList.add('is-open');
    sizeExcel();
    (items()[0] || btn).focus();
  }
  function close(refocus = true) {
    if (menu.hidden) return;
    menu.hidden = true;
    btn.setAttribute('aria-expanded', 'false');
    container.classList.remove('is-open');
    if (refocus) btn.focus();
  }
  btn.addEventListener('click', () => (menu.hidden ? open() : close()));
  menu.addEventListener('keydown', (e) => {
    const list = items(), i = list.indexOf(document.activeElement);
    if (e.key === 'Escape') { e.preventDefault(); close(); }
    else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); list[(i + (e.key === 'ArrowDown' ? 1 : -1) + list.length) % list.length].focus(); }
    else if (e.key === 'Home' || e.key === 'End') { e.preventDefault(); list[e.key === 'Home' ? 0 : list.length - 1].focus(); }
    else if (e.key === 'Tab') close(false);
  });
  menu.addEventListener('click', (e) => {
    const item = e.target.closest('.xm-item[aria-disabled]');
    if (item) { e.preventDefault(); return; }
    const made = state.build && e.target.closest('.xm-item');
    if (made) {
      e.preventDefault();
      if (made.hasAttribute('aria-busy')) return;
      const size = made.querySelector('.xm-size');
      made.setAttribute('aria-busy', 'true');
      size.textContent = 'Making your file…';
      state.build(made.dataset.fmt).then((file) => {
        const url = URL.createObjectURL(new Blob([file.bytes], { type: file.type }));
        const a = document.createElement('a');
        a.href = url;
        a.download = file.name;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 10000);
        made.removeAttribute('aria-busy');
        paint();
        close();
      }).catch((err) => {
        console.error(err);
        made.removeAttribute('aria-busy');
        size.textContent = "Couldn't make the file. Try again in a moment.";
      });
      return;
    }
    if (e.target.closest('.xm-item, .xm-sub')) setTimeout(() => close(), 0);   // a choice closes the menu
  });
  document.addEventListener('click', (e) => { if (!container.contains(e.target)) close(false); });
  paint();
  return { update(next) { state = { ...state, ...next }; paint(); }, close };
}

// assets/exports/fill.js, loaded the first time someone chooses a download it makes (it loads its own libraries)
let exportKit = null;
function loadExportKit(ver) {
  if (!exportKit) {
    exportKit = new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = `assets/exports/fill.js${ver ? `?v=${ver}` : ''}`;
      s.onload = () => resolve(window.FourthSheetExports);
      s.onerror = () => { exportKit = null; reject(new Error('Could not load assets/exports/fill.js')); };
      document.head.appendChild(s);
    });
  }
  return exportKit;
}

function mountStaticExportMenus() {
  document.querySelectorAll('[data-export]').forEach((el) => {
    const d = el.dataset;
    mountExportMenu(el, {
      period: d.exportPeriod, filterLabel: d.exportFilter,
      exports: d.exportXlsx || d.exportPdf || d.exportPptx ? { xlsx: d.exportXlsx, pdf: d.exportPdf, pptx: d.exportPptx } : null,
      meta: { pdf_pages: Number(d.exportPdfPages) || 0, pptx_slides: Number(d.exportPptxSlides) || 0 },
    });
  });
}

/* ---------------------------------------------------------------------------
   CONTACT PAGE (contact.html) — the form posts to a form service that emails Nathan (the form's action: FormSubmit
   now, but anything that takes a POST and answers in JSON works). If the action isn't a web address the form says so
   rather than pretending to send. A link from a report's Export menu (?topic=monthly&report=…&period=…&view=…) fills
   in what's being asked for.
--------------------------------------------------------------------------- */
function setupContactForm() {
  const form = document.getElementById('contact-form');
  if (!form) return;
  const q = new URLSearchParams(location.search);
  const status = document.getElementById('form-status');
  if (q.get('topic')) {
    const radio = form.querySelector(`input[name="topic"][value="${CSS.escape(q.get('topic'))}"]`);
    if (radio) radio.checked = true;
  }
  ['report', 'period', 'view'].forEach((k) => { form.elements[k].value = q.get(k) || ''; });
  if (q.get('question') && form.elements.message) {   // from a question's "Ask me →": the question, ready to send
    form.elements.message.value = q.get('question');
    const req = document.getElementById('contact-request');
    req.innerHTML = `You're asking: <strong>${esc(q.get('question'))}</strong> Add anything that helps, and I'll come back to you on how your data could answer it.`;
    req.hidden = false;
  }
  if (q.get('topic') === 'monthly' && q.get('report')) {
    const req = document.getElementById('contact-request');
    req.innerHTML = `You're asking for <strong>${esc(q.get('report'))}</strong>${q.get('view') ? ` (${esc(q.get('view'))})` : ''} as monthly reporting, done for you${q.get('period') ? `, starting from ${esc(q.get('period'))}` : ''}.`;
    req.hidden = false;
  }
  // the button says what you're asking for: its words follow the option picked
  const button = form.querySelector('button[type="submit"]');
  const BUTTON_WORDS = { 'numbers-check': 'Request my free numbers check', monthly: 'Ask about monthly reporting', other: 'Send my message' };
  const label = () => { button.textContent = BUTTON_WORDS[(form.querySelector('input[name="topic"]:checked') || {}).value] || 'Send my message'; };
  form.addEventListener('change', (e) => { if (e.target.name === 'topic') label(); });
  label();
  // phone: an Australian number, spaces, dashes and brackets allowed (mobile, landline, 13/1300/1800, or +61)
  const phone = form.elements.phone;
  const checkPhone = () => {
    const d = phone.value.replace(/[\s\-().]/g, '');
    const ok = !d || /^(?:\+?61|0)[2-478]\d{8}$/.test(d) || /^1[38]00\d{6}$/.test(d) || /^13\d{4}$/.test(d);
    phone.setCustomValidity(ok ? '' : 'Please enter an Australian mobile or landline number.');
  };
  if (phone) { phone.addEventListener('input', checkPhone); phone.addEventListener('blur', checkPhone); }
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    if (phone) checkPhone();
    if (!form.reportValidity()) return;
    track('contact-submit', (form.querySelector('input[name="topic"]:checked') || {}).value || '');
    const thanks = 'Thanks. I reply within one business day.';
    if (form.elements._gotcha && form.elements._gotcha.value) { form.reset(); label(); status.textContent = thanks; return; }  // a bot filled the trap
    const action = form.getAttribute('action') || '';
    if (!/^https?:\/\//.test(action)) {                    // no form service set
      status.textContent = "Thanks. This form isn't connected yet, so nothing has been sent. Please email me instead.";
      return;
    }
    const data = new FormData(form);
    data.delete('_gotcha');
    const topic = form.querySelector('input[name="topic"]:checked');
    const topicLabel = topic ? topic.parentElement.textContent.trim() : 'Enquiry';
    data.set('_subject', `Website enquiry: ${topicLabel}${data.get('organisation') ? `, ${data.get('organisation')}` : ''}`);
    data.set('_replyto', data.get('email') || '');
    button.disabled = true;
    status.textContent = 'Sending…';
    fetch(action, { method: 'POST', body: data, headers: { Accept: 'application/json' } })
      .then((r) => r.json().catch(() => ({})).then((j) => {
        // Formspree says no with an error status; FormSubmit can answer 200 with success: "false"
        if (!r.ok || j.success === false || j.success === 'false') throw new Error(j.message || '');
        form.reset();
        label();
        status.textContent = thanks;
      }))
      .catch(() => { status.textContent = "That didn't send. Please try again in a moment, or email me instead."; })
      .finally(() => { button.disabled = false; });
  });
}

/* ---------------------------------------------------------------------------
   GAME SLOT — "The Month-End Run".

   The page only loads the poster image. Pressing Play (on the poster or the
   button beside it) swaps the poster for the game in an iframe, so visitors
   who don't play never download it. The game tells us its height
   ('s3-game-height' message) so the iframe fits without scrollbars, and we
   ask it to pause ('s3:pause') when it's scrolled out of view.
--------------------------------------------------------------------------- */
function setupGameSlot() {
  const stage = document.querySelector('.game-stage');
  if (!stage) return;
  const grid = stage.closest('.game-grid');
  let frame = null;

  const play = () => {
    if (frame) return;
    frame = document.createElement('iframe');
    frame.className = 'game-frame';
    frame.src = stage.dataset.gameSrc;
    frame.title = 'The Month-End Run (game)';
    frame.allow = 'fullscreen';
    grid.classList.add('is-playing');
    // A first guess at the height until the game reports its real one
    frame.style.height = `${Math.round((grid.clientWidth * 9) / 16) + 120}px`;
    stage.replaceChildren(frame);
    frame.addEventListener('load', () => {
      // Same site, so we can put keyboard focus straight into the game
      try { frame.contentDocument.getElementById('game-canvas').focus({ preventScroll: true }); } catch { /* ignore */ }
    });
  };

  document.querySelectorAll('.game-play, [data-game-play]').forEach((btn) => btn.addEventListener('click', play));

  window.addEventListener('message', (event) => {
    if (!frame || event.origin !== location.origin || event.source !== frame.contentWindow) return;
    if (event.data && event.data.type === 's3-game-height') frame.style.height = `${event.data.height}px`;
  });

  if ('IntersectionObserver' in window) {
    new IntersectionObserver((entries) => {
      if (frame && !entries[0].isIntersecting) frame.contentWindow.postMessage('s3:pause', location.origin);
    }, { threshold: 0.2 }).observe(stage);
  }
}

/* ---------------------------------------------------------------------------
   PRICES — base rate $110 an hour; day rate $800 (7 hours × $110 = $770, rounded up).

   Each price on the page shows "Talk to me about pricing" in the HTML (what visitors see
   without JavaScript); with SHOW_PRICES on, the PRICES text replaces it.
   A price still written like [[TOKEN]] is never shown.
--------------------------------------------------------------------------- */
const SHOW_PRICES = true;
const PRICES = {
  setup: 'From $110 an hour · $800 a day',
  bedding: '$110 an hour · $800 a day',
  monthly: '$110 an hour · $800 a day',
};

/* ---------------------------------------------------------------------------
   ANALYTICS — switched OFF. One setting: while ANALYTICS.token is a [[TOKEN]], nothing loads and nothing is sent.
   Cookieless analytics only (no cookies, so no consent banner). To switch on once a provider is chosen: set token,
   set src to the provider's script, and fill in send(name, detail) with the provider's event call.
   Events come from data-track attributes, so new buttons only need the attribute:
     numbers-check (every "Ask for a free 20-minute numbers check", which opens the contact page), email (mailto links), export (each download, detail = the
     format), contact-submit (the contact form, sent once it passes its checks, detail = the topic).
--------------------------------------------------------------------------- */
const ANALYTICS = {
  token: '[[ANALYTICS_TOKEN]]',
  src: '',                          // the provider's script, e.g. https://<provider>/script.js
  send: null,                       // (name, detail) => { /* the provider's event call */ }
};
const analyticsOn = () => Boolean(ANALYTICS.token) && !/\[\[.*\]\]/.test(ANALYTICS.token);
function track(name, detail) {
  if (!analyticsOn() || typeof ANALYTICS.send !== 'function') return;
  try { ANALYTICS.send(name, detail || ''); } catch (e) { /* analytics never breaks the page */ }
}
function setupAnalytics() {
  if (analyticsOn() && ANALYTICS.src) {
    const el = document.createElement('script');
    el.defer = true; el.src = ANALYTICS.src; el.dataset.token = ANALYTICS.token;
    document.head.appendChild(el);
  }
  document.addEventListener('click', (e) => {
    const el = e.target.closest && e.target.closest('[data-track]');
    if (el && el.dataset.track !== 'contact-submit') track(el.dataset.track, el.dataset.trackDetail || el.getAttribute('href') || '');
  });
}

function applyPrices() {
  if (!SHOW_PRICES) return;
  document.querySelectorAll('[data-price-note]').forEach((n) => { n.hidden = true; });   // "Talk to me about pricing" goes once prices show
  document.querySelectorAll('[data-price]').forEach((node) => {
    const value = PRICES[node.dataset.price];
    if (value && !/\[\[.*\]\]/.test(value)) node.textContent = value;
  });
}

/* ---------------------------------------------------------------------------
   HERO DASHBOARD — three invented sample organisations on the home page.

   The numbers come from data/dashboard.json, which is GENERATED by
   tools/1_build_data/financial_model.py (a driver-based model with built-in checks).
   Don't type numbers in here: change the assumptions in that file and run
   python3 tools/1_build_data/sample_data.py.

   Month-end: September 2026 against the prior month (August 2026), whole
   dollars, built up from individual jobs, engagements and grants.
   Tabs: The fourth sheet (always first, and shown by default), P&L,
   Balance sheet, Cash flow.
   Toggle: SME · trades, SME · services, Not-for-profit.
   Phones show headline lines; larger screens show every line (CSS hides
   .detail rows under 720px). The page re-checks that everything adds up
   before showing the "Balances" tick.
--------------------------------------------------------------------------- */
const dash = { org: 'trades', tab: 'fourth', view: 'pct' };

// one rounding rule everywhere (site, PDF, spreadsheet, slides): halves round away from zero, so 112.5 shows as 113 and 12.25 as 12.3
const hu = (v, dp = 0) => { const p = 10 ** dp; return Math.sign(v) * Math.round(Math.abs(v) * p + 1e-9) / p; };
// Accounting format in whole dollars: 1,234 / (1,234) for negatives / - for zero
const acct = (n) => (n < 0 ? `(${Math.abs(n).toLocaleString('en-AU')})` : n === 0 ? '-' : n.toLocaleString('en-AU'));
const esc = (v) => String(v).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const CHART_FORMATS = {
  // over (+) / under (-) budget, said in words so an underspend isn't shown as a red negative
  pct_var: (v) => (hu(v, 1) === 0 ? 'on budget' : `${hu(Math.abs(Number(v)), 1).toFixed(1)}% ${v > 0 ? 'over' : 'under'}`),
  money_var: (v) => (hu(v) === 0 ? 'on budget' : `$${hu(Math.abs(v)).toLocaleString('en-AU')} ${v > 0 ? 'over' : 'under'}`),
  money0: (v) => (v < 0 ? `($${hu(-v).toLocaleString('en-AU')})` : `$${hu(v).toLocaleString('en-AU')}`),
  pct0: (v) => `${hu(v)}%`,
  pct1: (v) => (v < 0 ? `(${hu(Math.abs(Number(v)), 1).toFixed(1)}%)` : `${hu(Number(v), 1).toFixed(1)}%`),
  cents_int: (v) => `${v}¢`,
  int: (v) => hu(v).toLocaleString('en-AU'),
  money_k: (v) => (Math.abs(v) >= 1000 ? `$${hu(v / 1000).toLocaleString('en-AU')}k` : `$${v}`),
};

// EXPLANATIONS: the "gross margin, not profit" boxes on the report pages. Hide them for an audience that
// doesn't need them: set SHOW_EXPLANATIONS = false (whole site), or add ?explain=off to any link you send.
const SHOW_EXPLANATIONS = true;
if (!SHOW_EXPLANATIONS || new URLSearchParams(location.search).get('explain') === 'off') document.documentElement.classList.add('no-explain');

// Charts are drawn at their real pixel width (1 SVG unit = 1px), so chart text stays at a fixed, readable size
// (11px labels, 12px values) on every screen. chartWidth() measures the box a chart will sit in.
const chartWidth = (node, pad = 0) => Math.max(160, Math.round((node && node.clientWidth ? node.clientWidth : 320) - pad));
const textW = (t, px = 11) => String(t).length * px * 0.56;              // close enough for Roboto at chart sizes
const clip = (t, maxW, px = 11) => { const s = String(t); const n = Math.floor(maxW / (px * 0.56)); return s.length <= n ? s : `${s.slice(0, Math.max(1, n - 1))}…`; };

// Colour by meaning, not by sign: is this value good, close (warn) or bad? goodWhen 'higher' or 'lower';
// target is the line it's judged against; warnWithin (same units) counts as close. Returns a CSS class.
function tone(value, { goodWhen = 'higher', target = null, warnWithin = 0 } = {}) {
  if (value == null || target == null || Number.isNaN(Number(value))) return '';
  const gap = goodWhen === 'lower' ? target - value : value - target;     // positive = on the good side
  if (gap >= 0) return 'is-good';
  return -gap <= warnWithin ? 'is-warn' : 'is-bad';
}

// Negative numbers are always red (and in brackets)
const isNeg = (t) => /^\(?-?\$?\(|^-\d|^-\$|^\(\$?\d/.test(String(t).trim());
const negCls = (t) => (isNeg(t) ? ' neg' : '');

// Re-check a statement: every subtotal equals the detail lines above it
function statementAddsUp(rows) {
  let pending = [];
  for (const r of rows) {
    if (r.level === 'heading') pending = [];
    else if (r.level === 'detail') pending.push(r);
    else if (r.level === 'subtotal' && pending.length) {
      for (let i = 0; i < 2; i++) if (pending.reduce((t, p) => t + p.values[i], 0) !== r.values[i]) return false;
      pending = [];
    }
  }
  return true;
}

// The headline ties: balance sheet balances, cash flow ends at the bank balance
function orgBalances(o) {
  const val = (rows, label) => (rows.find((r) => r.label === label) || {}).values;
  if (o.statements.bs.unavailable) return statementAddsUp(o.statements.pnl.rows);    // a month with the profit and loss only
  const bs = o.statements.bs.rows, cf = o.statements.cf.rows;
  const equity = val(bs, 'Total equity') || val(bs, 'Accumulated funds');
  const ok = ['pnl', 'bs', 'cf'].every((k) => statementAddsUp(o.statements[k].rows));
  return ok && [0, 1].every((i) => val(bs, 'Net assets')[i] === equity[i] && val(cf, 'Cash at end of month')[i] === val(bs, 'Cash at bank')[i]);
}

function renderStatement(o, st) {
  if (st.unavailable) return `<p class="dash-unavailable">${esc(st.unavailable)}</p>`;
  const rows = st.rows.map((r) => {
    if (r.level === 'heading') return `<tr class="st-heading"><th colspan="4" scope="rowgroup">${esc(r.label)}</th></tr>`;
    const change = r.values[0] - r.values[1];
    return `<tr class="st-${r.level}${r.level === 'detail' ? ' detail' : ''}"><td>${esc(r.label)}</td>${r.values.map((v) => `<td class="n${v < 0 ? ' neg' : ''}">${acct(v)}</td>`).join('')}<td class="n st-change${change < 0 ? ' neg' : ''}">${acct(change)}</td></tr>`;
  }).join('');
  const sts = window.FOURTH_SHEET_DASHBOARD.status.slice(0, 2).map((m) => `${m.label}: ${m.status.toLowerCase()}`).join(' · ');
  return `<p class="dash-chart-title">${esc(st.title)} · ${esc(o.name)}</p><p class="dash-status-line">${esc(sts)}</p>
    <div class="st-scroll" tabindex="0" role="region" aria-label="${esc(`${st.title}, ${o.name} (scrolls)`)}"><table class="st-table"><thead><tr><th scope="col">$</th>${o.columns.map((c) => `<th scope="col" class="n">${c}</th>`).join('')}<th scope="col" class="n st-change">Change</th></tr></thead><tbody>${rows}</tbody></table></div>
    <p class="dash-phone-note">Headline lines shown. Every line is on a larger screen, and in the spreadsheet and PDF downloads.</p>`;
}

function renderChart(ch, width = 320) {
  // Categorical data -> horizontal bars (labels down the left), the default. Drawn at its real pixel width.
  // Every bar carries a value label and opens its workings when clicked. Grey = below target (unless the chart is
  // "plain"); red = losing money (below zero). "marks" = a small tick per bar (e.g. budget to date).
  const fmt = CHART_FORMATS[ch.format] || String;
  const W = Math.round(width), top = 8, row = 26, bh = 15;
  const valW = Math.max(...ch.values.map((v) => textW(fmt(v), 12))) + 10;
  const right = W - valW;
  const left = Math.min(Math.round(W * 0.42), 12 + Math.max(...ch.labels.map((l) => textW(l))));
  const n = ch.values.length, plotH = n * row;
  const below = (v, i) => !ch.plain && ((ch.target != null && v < ch.target) || (ch.below_marks && ch.marks && v < ch.marks[i]));
  const anyBelow = ch.values.some((v, i) => below(v, i));
  const be = ch.breakeven != null ? 14 : 0;               // a second label row for the break-even line
  const H = top + plotH + be + (anyBelow || ch.marks || ch.variance ? 40 : ch.target != null ? 24 : 6);
  const lo = Math.min(0, ...ch.values);
  const max = Math.max(...ch.values, ch.target || 0, ch.breakeven || 0, ...(ch.marks || [0])) * 1.05;
  const x = (v) => left + ((v - lo) / (max - lo || 1)) * (right - left);
  const x0 = x(0);
  let g = `<line class="dash-grid" x1="${x0.toFixed(1)}" x2="${x0.toFixed(1)}" y1="${top - 2}" y2="${top + plotH}"/>`;
  // bars sorted by value, largest first; the order is set once (by the first view) and doesn't move when the view changes
  const by = ch.orderBy || ch.values;
  const order = ch.keep_order ? ch.values.map((v, i) => i) : ch.values.map((v, i) => i).sort((p, q) => by[q] - by[p]);   // times of day keep clock order
  order.forEach((i, pos) => {
    const v = ch.values[i];
    const y = top + pos * row + (row - bh) / 2;
    const dim = ch.highlight && ch.labels[i] !== ch.highlight ? ' dash-row--dim' : '';
    // variance charts: off budget either way is red; within 1% amber; on budget neutral (judged on the % of budget)
    // variance charts (judged on % of budget): over budget red, under budget green, within 1% amber, on budget neutral
    const vs = ch.variance ? (ch.variancePct || ch.values)[i] : 0, vp = Math.abs(vs);
    const cls = ch.variance ? (vp < 0.05 ? '' : vp < 1 ? ' dash-bar--warn' : vs > 0 ? ' dash-bar--bad' : ' dash-bar--good') : v < 0 ? ' dash-bar--bad' : below(v, i) ? ' dash-bar--below' : '';
    const bx = Math.min(x(v), x0), bw = Math.abs(x(v) - x0);
    g += `<g class="dash-row${dim}" data-detail="${i}" data-tip="${esc(ch.labels[i])}: ${fmt(v)}${ch.marks ? ` · ${esc(ch.mark_label || 'mark')} ${fmt(ch.marks[i])}` : ''}" tabindex="0" role="button" aria-label="${esc(ch.labels[i])}: ${fmt(v)}. Show the workings.">`
      + `<rect class="dash-hit" x="0" y="${(top + pos * row).toFixed(1)}" width="${W}" height="${row}"/>`
      + `<text class="dash-axis" x="${left - 8}" y="${(y + bh - 3).toFixed(1)}" text-anchor="end"><title>${esc(ch.labels[i])}</title>${esc(clip(ch.labels[i], left - 12))}</text>`
      + `<rect class="dash-bar dash-bar--h${cls}" x="${bx.toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${bh}" rx="2"/>`;
    if (ch.marks) g += `<line class="dash-mark" x1="${x(ch.marks[i]).toFixed(1)}" x2="${x(ch.marks[i]).toFixed(1)}" y1="${(y - 3).toFixed(1)}" y2="${(y + bh + 3).toFixed(1)}"/>`;
    // value label at the bar's end; it steps past a marker or the target line rather than sitting on it
    const txt = fmt(v), tw = textW(txt, 12);
    let lx = Math.max(x(v), x0) + 5;
    if (ch.marks) { const mx = x(ch.marks[i]); if (mx >= x(v) - 1 && mx < lx + tw + 3) lx = mx + 5; }
    if (ch.breakeven != null && lx - 3 < x(ch.breakeven) && x(ch.breakeven) < lx + tw + 3) lx = x(ch.breakeven) + 5;
    if (ch.target != null && lx - 3 < x(ch.target) && x(ch.target) < lx + tw + 3) lx = x(ch.target) + 5;
    const bad = ch.variance ? vp >= 1 && vs > 0 : v < 0;
    const good = ch.variance && vp >= 1 && vs < 0;
    g += `<text class="dash-value${bad ? ' neg' : good ? ' dash-value--good' : ''}" x="${lx.toFixed(1)}" y="${(y + bh - 3).toFixed(1)}">${txt}</text></g>`;
  });
  if (ch.target != null) {   // drawn after the bars, so the target sits on top
    const tx = x(ch.target).toFixed(1);
    g += `<line class="dash-target" x1="${tx}" x2="${tx}" y1="${top - 4}" y2="${top + plotH + 2}"/>`;
    g += `<text class="dash-target-label" x="${tx}" y="${top + plotH + 16}" text-anchor="middle">Target ${fmt(ch.target)}</text>`;
  }
  if (ch.breakeven != null) {   // what just covers overheads: below the target, labelled on the row under it
    const bx = x(ch.breakeven).toFixed(1);
    g += `<line class="dash-breakeven" x1="${bx}" x2="${bx}" y1="${top - 4}" y2="${top + plotH + 18}"/>`;
    g += `<text class="dash-breakeven-label" x="${bx}" y="${top + plotH + 30}" text-anchor="middle">Break-even ${fmt(ch.breakeven)}</text>`;
  }
  if (ch.variance) g += `<rect class="dash-bar--bad" x="${left}" y="${H - 13}" width="11" height="11" rx="2"/><text class="dash-key" x="${left + 16}" y="${H - 3}">Over budget</text>`
    + `<rect class="dash-bar--good" x="${left + 106}" y="${H - 13}" width="11" height="11" rx="2"/><text class="dash-key" x="${left + 122}" y="${H - 3}">Under budget</text>`
    + `<rect class="dash-bar--warn" x="${left + 218}" y="${H - 13}" width="11" height="11" rx="2"/><text class="dash-key" x="${left + 234}" y="${H - 3}">Within 1%</text>`;
  else if (anyBelow && !ch.marks) g += `<rect class="dash-bar--below" x="${left}" y="${H - 13}" width="11" height="11" rx="2"/><text class="dash-key" x="${left + 16}" y="${H - 3}">Below target</text>`;
  if (ch.marks) g += `<line class="dash-mark" x1="${left + 4}" x2="${left + 4}" y1="${H - 14}" y2="${H - 1}"/><text class="dash-key" x="${left + 12}" y="${H - 3}">${esc(ch.mark_label || '')}</text>`;
  const label = `${ch.title}: ${ch.labels.map((l, i) => `${l} ${fmt(ch.values[i])}`).join(', ')}${ch.target != null ? `; target ${fmt(ch.target)}` : ''}${ch.breakeven != null ? `; break-even ${fmt(ch.breakeven)}` : ''}.`;
  // a labelled group, not an image: every bar inside is a button that opens its workings (an image can't hold buttons)
  return `<svg class="dash-svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="group" aria-label="${esc(label)}">${g}</svg>`;
}

// A time series (spend by month): columns, with the budget as a dotted step line
function renderSeries(se, width = 560) {
  const fmt = CHART_FORMATS[se.format] || String;
  const W = Math.round(width), H = 190, top = 10, base = 150, left = 4, right = W - 4, n = se.values.length;
  const max = Math.max(...se.values, ...(se.budget || [0])) * 1.12;
  const slot = (right - left) / n, bw = slot * 0.62, y = (v) => base - (v / max) * (base - top);
  const every = Math.max(1, Math.ceil((n * 46) / (right - left)));          // month labels never overlap
  let g = `<line class="dash-grid" x1="${left}" x2="${right}" y1="${base}" y2="${base}"/>`;
  se.values.forEach((v, i) => {
    const bx = left + i * slot + (slot - bw) / 2;
    g += `<rect class="dash-bar" data-tip="${esc(se.labels[i])}: ${fmt(v)}${se.budget ? ` · budget ${fmt(se.budget[i])}` : ''}" x="${bx.toFixed(1)}" y="${y(v).toFixed(1)}" width="${bw.toFixed(1)}" height="${(base - y(v)).toFixed(1)}" rx="2"></rect>`;
    if (i % every === 0 || i === n - 1) g += `<text class="dash-axis" x="${(bx + bw / 2).toFixed(1)}" y="${base + 16}" text-anchor="middle">${esc(se.labels[i])}</text>`;
    if (se.budget) g += `<line class="dash-target" x1="${(left + i * slot).toFixed(1)}" x2="${(left + (i + 1) * slot).toFixed(1)}" y1="${y(se.budget[i]).toFixed(1)}" y2="${y(se.budget[i]).toFixed(1)}"/>`;
  });
  if (se.budget) g += `<line class="dash-target" x1="${left}" x2="${left + 18}" y1="${H - 8}" y2="${H - 8}"/><text class="dash-key" x="${left + 24}" y="${H - 4}">Monthly budget</text>`;
  return `<p class="support-chart-title">${esc(se.title)}</p><svg class="dash-svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(se.title)}: ${se.labels.map((l, i) => `${l} ${fmt(se.values[i])}`).join(', ')}">${g}</svg>`;
}

function openSupport(sp) {
  if (!sp) return;
  document.getElementById('support-title').textContent = sp.title;
  const rows = sp.rows.map((r) => `<tr><th scope="row">${esc(r[0])}</th>${r.slice(1).map((c) => `<td class="n${negCls(c)}">${esc(c)}</td>`).join('')}</tr>`).join('');
  const twoCol = sp.rows.every((r) => !r[2]);
  const head = twoCol ? '' : `<thead><tr>${sp.head.map((h, i) => `<th scope="col"${i ? ' class="n"' : ''}>${esc(h)}</th>`).join('')}</tr></thead>`;
  document.getElementById('support-body').innerHTML =
    `<p class="support-formula">${esc(sp.formula)}</p>`
    + `<table class="support-table${twoCol ? ' support-table--two' : ''}">${head}<tbody>${twoCol ? rows.replace(/<td class="n"><\/td>/g, '') : rows}</tbody></table>`
    + (sp.note ? `<p class="assumptions-intro">${esc(sp.note)}</p>` : '')
    + (sp.series ? renderSeries(sp.series, chartWidth(document.getElementById('support-body'), 40)) : '')
    + `<p class="support-foot">Sample data. Every figure is in the spreadsheet download.${document.getElementById('assumptions-dialog') ? ' <button type="button" class="link-btn" data-open-assumptions>See all assumptions</button>' : ''}</p>`;
  const dlg = document.getElementById('support-dialog');
  if (dlg.showModal) dlg.showModal(); else dlg.setAttribute('open', '');
}

function renderFourth(o) {
  // Kept deliberately simple: three headline numbers and one chart. Every
  // number opens its workings; the full lists are in the Excel and PDF.
  const f = o.fourth;
  const kpis = f.kpis.slice(0, 3).map((k, i) => `<button type="button" class="dash-kpi" data-kpi="${i}"><span>${esc(k.label)}</span><strong class="${(negCls(k.value) + (k.tone ? ` is-${k.tone}` : '')).trim()}">${esc(k.value)}</strong><em class="${k.cls}">${esc(k.sub)}</em><small class="dash-how">How it's worked out</small></button>`).join('');
  let ch = f.chart;
  let toggle = '';
  if (ch.views) {
    const v = ch.views.find((x) => x.id === dash.view) || ch.views[0];
    ch = { ...ch, values: v.values, format: v.format, target: v.target, breakeven: v.breakeven, marks: v.marks, mark_label: v.mark_label, below_marks: v.below_marks, variancePct: ch.views[0].values };
    toggle = `<div class="seg" role="group" aria-label="Show as">${ch.views.map((x) => `<button type="button" data-view="${x.id}" aria-pressed="${x.id === v.id}">${esc(x.label)}</button>`).join('')}</div>`;
  }
  const w = chartWidth(document.getElementById('dash-panel'), 32);
  return `<div class="dash-kpis">${kpis}</div>
    <div class="dash-chart"><div class="dash-chart-head"><p class="dash-chart-title">${esc(ch.title)}</p>${toggle}</div>${ch.subtitle ? `<p class="dash-chart-sub">${esc(ch.subtitle)}</p>` : ''}${renderChart(ch, w)}<p class="dash-hint">Click or tap any number for its workings.</p></div>`;
}

function renderAssumptions(o) {
  document.getElementById('assumptions-title').textContent = `Assumptions: ${o.name}`;
  document.getElementById('assumptions-body').innerHTML =
    `<p class="assumptions-intro">Sample data. Every figure on the dashboard is calculated from these assumptions by a driver-based model, then checked.</p>` +
    o.assumptions.map(([group, items]) => `<h3>${esc(group)}</h3><dl>${items.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>`).join('') +
    `<h3>How final is this data?</h3><dl>${window.FOURTH_SHEET_DASHBOARD.status.map((m) => `<div><dt>${esc(m.label)} · ${esc(m.status)}</dt><dd>${esc(m.note)}</dd></div>`).join('')}</dl>` +
    `<h3>Checks</h3><ul class="assumptions-checks">${o.checks.map((c) => `<li>${esc(c)}</li>`).join('')}</ul>`;
}

function renderDash() {
  const data = window.FOURTH_SHEET_DASHBOARD;
  const o = data.orgs.find((x) => x.id === dash.org);
  const panel = document.getElementById('dash-panel');
  panel.innerHTML = dash.tab === 'fourth' ? renderFourth(o) : renderStatement(o, o.statements[dash.tab]);
  document.querySelectorAll('#hero-dash [role="tab"]').forEach((t) => {
    t.setAttribute('aria-selected', String(t.dataset.tab === dash.tab));
    t.tabIndex = t.dataset.tab === dash.tab ? 0 : -1;
    if (t.dataset.tab === 'pnl') t.textContent = o.id === 'nfp' ? 'Income & exp.' : 'P&L';
  });
  document.querySelectorAll('#dash-orgs button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.org === dash.org)));
  const check = document.getElementById('dash-check');
  const ok = orgBalances(o);
  if (!ok) console.warn('Sample statements do not balance: re-run tools/1_build_data/sample_data.py');
  if (check) {
  check.hidden = false;
  check.className = `dash-check ${ok ? 'is-ok' : 'is-bad'}`;
  check.textContent = ok ? '✓ Balances' : '✗ Does not balance';
  check.title = ok ? o.checks.join(' · ') : 'A check failed: re-run tools/1_build_data/sample_data.py';
  }
  const rep = data.status[0];
  const chip = document.getElementById('dash-status');
  if (chip) {
    chip.hidden = false;
    chip.className = `dash-status is-${rep.status.toLowerCase()}`;
    chip.textContent = `${rep.label.split(' ')[0]} ${rep.status.toLowerCase()}`;
    chip.title = data.status.map((m) => m.note).join(' ');
  }
  if (dash.menu) dash.menu.update({ period: rep.label, filterLabel: o.toggle, exports: o.exports, meta: o.exports_meta });
  const u = new URL(window.location.href);
  if (dash.org === data.orgs[0].id) u.searchParams.delete('business'); else u.searchParams.set('business', dash.org);
  if (u.href !== window.location.href) history.replaceState(null, '', u);
  renderAssumptions(o);
}

/* ---------------------------------------------------------------------------
   DELIVERIES MAP (examples.html) — deliveries in and out of an invented Brisbane
   distribution centre. Data: data/deliveries.json, GENERATED by
   tools/1_build_data/deliveries.py (don't type numbers in here). Map: Leaflet with
   OpenStreetMap tiles. Dot colour = share on time; red if anything overdue.
--------------------------------------------------------------------------- */
const DELIV_COL = { good: '#0E9F6E', some: '#8a6d3b', bad: '#8f4a3e', open: '#8e9cab' };
function delivBand(p) {
  const done = p.on_time + p.late + p.very_late;
  if (p.overdue) return 'bad';
  if (!done) return 'open';
  const r = p.on_time / (done + p.overdue);      // overdue counts as late: on time ÷ (delivered + overdue)
  return r >= 0.95 ? 'good' : r >= 0.8 ? 'some' : 'bad';
}
function setupDeliveries() {
  const box = document.getElementById('deliv');
  if (!box) return;
  loadData('data/deliveries.json').then((D) => startDeliveries(box, D)).catch(() => dataFailed(document.getElementById('deliv-map')));
}
function startDeliveries(box, D) {
  const st = { side: 'out', period: '30d' };
  let map = null, layer = null;
  if (window.L) {
    map = L.map('deliv-map', { scrollWheelZoom: false });
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 18, attribution: '&copy; OpenStreetMap contributors' }).addTo(map);
    L.marker([D.dc.lat, D.dc.lon], { icon: L.divIcon({ className: '', html: '<span class="deliv-dc">DC</span>', iconSize: null }) }).bindPopup(esc(D.dc.name)).addTo(map);
    layer = L.layerGroup().addTo(map);
  } else {
    document.getElementById('deliv-map').innerHTML = '<p style="padding:1rem">The map could not load. The spreadsheet and PDF downloads have every delivery.</p>';
  }
  const exportBox = document.getElementById('deliv-export');
  const menu = exportBox ? mountExportMenu(exportBox, { period: D.periods[0].long, exports: D.exports, meta: D.exports_meta }) : null;
  document.getElementById('deliv-periods').innerHTML = D.periods.map((p) => `<button type="button" data-period="${p.id}" aria-pressed="false">${esc(p.label)}</button>`).join('');
  const pct = (v) => (v == null ? '–' : `${Number(v).toFixed(1)}%`);
  function render() {
    const v = D[st.side][st.period], k = v.kpis, out = st.side === 'out';
    box.querySelectorAll('[data-side]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.side === st.side)));
    box.querySelectorAll('[data-period]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.period === st.period)));
    document.getElementById('deliv-status').innerHTML = `<span class="dash-status is-${v.status.toLowerCase()}">${esc(v.status)}</span>${esc(v.status_note)}`;
    document.getElementById('deliv-period-label').textContent = `${out ? 'Deliveries out to customers' : 'Deliveries in from suppliers'} · ${D.periods.find((p) => p.id === st.period).long}`;
    if (menu) menu.update({ period: D.periods.find((p) => p.id === st.period).long, filterLabel: 'In and out: every delivery' });
    document.getElementById('deliv-kpis').innerHTML = [
      [out ? 'Deliveries' : 'Deliveries due', k.total.toLocaleString('en-AU'), ''],
      ['On time', pct(k.on_time_pct), k.on_time_pct != null && k.on_time_pct < 95 ? 'bad' : ''],
      ['Delivered late', k.late, ''],
      ['Overdue now', k.overdue, k.overdue ? 'bad' : ''],
      [out ? 'On the truck' : 'Due, not here yet', k.open, ''],
    ].map(([l, val, c]) => `<div class="${c}"><span>${l}</span><strong>${val}</strong></div>`).join('');
    document.getElementById('deliv-hot').innerHTML = v.hotspots.length
      ? v.hotspots.map((h) => `<li>${esc(h.label)}: <b>${Number(h.pct).toFixed(1)}% late</b> (${h.late} of ${h.of})</li>`).join('')
      : '<li>Nothing stands out for this period.</li>';
    if (!map) return;
    layer.clearLayers();
    const pts = [[D.dc.lat, D.dc.lon]];
    v.points.forEach((p) => {
      pts.push([p.lat, p.lon]);
      const done = p.on_time + p.late + p.very_late;
      const lines = [`<strong>${esc(p.name)}</strong>`, esc(p.sub), `${p.n} ${p.n === 1 ? 'delivery' : 'deliveries'}${done ? `, ${p.on_time} on time` : ''}`];
      if (p.late + p.very_late) lines.push(`${p.late + p.very_late} late${p.very_late ? ` (${p.very_late} by 2+ days)` : ''}`);
      if (p.overdue) lines.push(`<b style="color:#8f4a3e">${p.overdue} overdue now</b>`);
      if (p.open) lines.push(`${p.open} on the way`);
      L.circleMarker([p.lat, p.lon], { radius: 4 + Math.sqrt(p.n) * 1.4, color: '#ffffff', weight: 1.5, fillColor: DELIV_COL[delivBand(p)], fillOpacity: 0.9 })
        .bindPopup(lines.join('<br>')).addTo(layer);
    });
    map.fitBounds(pts, { padding: [20, 20], maxZoom: 11 });
  }
  box.addEventListener('click', (e) => {
    const b = e.target.closest('[data-side],[data-period]');
    if (!b) return;
    if (b.dataset.side) st.side = b.dataset.side; else st.period = b.dataset.period;
    render();
  });
  render();
}

/* ---------------------------------------------------------------------------
   REPORT PAGES (report-*.html) — one report per question on the SME and
   not-for-profit pages. Data: data/reports/<report>.json (every period of one report) and
   data/reports/cards.json (what the cards draw), GENERATED by tools/3_publish_site/fourthsheet (don't type numbers in here).
   Sections: headline numbers, bar charts (categories, horizontal), column
   charts (months: incomplete months lighter, marked "to date"), tables,
   "what it shows / what you'd do". Every number opens its workings.
--------------------------------------------------------------------------- */
function niceTicks(min, max, n) {
  const span = max - min || Math.abs(max) || 1, step0 = span / n, mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((x) => x >= step0);
  const lo = Math.floor(min / step) * step, hi = Math.ceil(max / step) * step, out = [];
  for (let v = lo; v <= hi + step / 2; v += step) out.push(+v.toFixed(10));
  return out;
}

function renderArea(labels, values, status, format, mini, width, target) {
  // Time series as an area, drawn at its real pixel width: labelled y-axis with light gridlines, a dot per month
  // (tap for the workings), the highest and lowest values labelled (the latest on minis), incomplete or provisional
  // months dashed and lighter. Month labels thin out so they never overlap.
  const fmt = CHART_FORMATS[format] || String;
  const n = values.length, W = Math.round(width || (mini ? 280 : 720));
  const H = mini ? 96 : Math.round(Math.max(210, Math.min(320, W * 0.3)));
  const vals = values.filter((v) => v != null);
  const tv = target && !mini ? target.value : null;      // e.g. the reserves target: a dashed line across
  const ticks = niceTicks(Math.min(0, ...vals), Math.max(0, ...vals, tv || 0), mini ? 2 : 4);
  const yMin = ticks[0], yMax = ticks[ticks.length - 1];
  const tickW = mini ? 0 : Math.max(...ticks.map((t) => textW(fmt(t)))) + 10;
  const left = mini ? 4 : tickW, right = W - (mini ? 6 : 12), top = mini ? 20 : 22, base = H - (mini ? 6 : 34);
  const x = (i) => left + (n === 1 ? (right - left) / 2 : (i * (right - left)) / (n - 1));
  const y = (v) => base - ((v - yMin) / (yMax - yMin || 1)) * (base - top);
  const done = (i) => !status || (status[i] !== 'Incomplete' && status[i] !== 'Provisional' && status[i] !== 'Forecast');   // forecast days are drawn lighter
  const gid = `ag${renderArea.n = (renderArea.n || 0) + 1}`;          // Google Sheets style: colour under the line fading to nothing
  let g = `<defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0E9F6E" stop-opacity="0.30"/><stop offset="1" stop-color="#0E9F6E" stop-opacity="0.03"/></linearGradient>`
    + `<linearGradient id="${gid}l" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0E9F6E" stop-opacity="0.16"/><stop offset="1" stop-color="#0E9F6E" stop-opacity="0.03"/></linearGradient></defs>`;
  if (!mini) ticks.forEach((t) => { g += `<line class="dash-gridline" x1="${left}" x2="${right}" y1="${y(t).toFixed(1)}" y2="${y(t).toFixed(1)}"/><text class="dash-ytick" x="${left - 8}" y="${(y(t) + 4).toFixed(1)}" text-anchor="end">${fmt(t)}</text>`; });
  const pts = values.map((v, i) => (v == null ? null : [x(i), y(v)]));
  const zeroY = y(Math.max(yMin, Math.min(0, yMax)));
  const firm = pts.map((p, i) => (p && done(i) ? p : null));
  const lastFirm = firm.reduce((a, p, i) => (p ? i : a), -1);
  const path = (arr) => arr.filter(Boolean).map((p, k) => `${k ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join('');   // straight segments, no rounding
  const firmPts = firm.filter(Boolean);
  if (firmPts.length) {
    g += `<path class="dash-area" fill="url(#${gid})" d="${path(firmPts)}L${firmPts[firmPts.length - 1][0].toFixed(1)},${zeroY.toFixed(1)}L${firmPts[0][0].toFixed(1)},${zeroY.toFixed(1)}Z"/>`;
    g += `<path class="dash-line" d="${path(firmPts)}"/>`;
  }
  const tail = pts.map((p, i) => (p && i >= lastFirm && lastFirm >= 0 ? p : null)).filter(Boolean);
  if (tail.length > 1) {
    g += `<path class="dash-area dash-area--light" fill="url(#${gid}l)" d="${path(tail)}L${tail[tail.length - 1][0].toFixed(1)},${zeroY.toFixed(1)}L${tail[0][0].toFixed(1)},${zeroY.toFixed(1)}Z"/>`;
    g += `<path class="dash-line dash-line--light" d="${path(tail)}"/>`;
  }
  if (tv != null) g += `<line class="dash-target" x1="${left}" x2="${right}" y1="${y(tv).toFixed(1)}" y2="${y(tv).toFixed(1)}"/>`
    + `<text class="dash-target-label" x="${right}" y="${(y(tv) - 5).toFixed(1)}" text-anchor="end">${esc(target.label || `Target ${fmt(tv)}`)}</text>`;
  if (yMin < 0) g += `<line class="dash-grid" x1="${left}" x2="${right}" y1="${zeroY.toFixed(1)}" y2="${zeroY.toFixed(1)}"/>`;
  const idx = values.map((v, i) => (v == null ? null : i)).filter((i) => i != null);
  const hi = idx.reduce((a, i) => (values[i] > values[a] ? i : a), idx[0]);
  const lo = idx.reduce((a, i) => (values[i] < values[a] ? i : a), idx[0]);
  const labelled = mini ? new Set([idx[idx.length - 1]]) : new Set([hi, lo]);   // the y-axis carries the rest: mark only the highest and lowest
  const slot = (right - left) / Math.max(1, n - 1);
  const lw = mini ? 0 : Math.max(...labels.map((l) => textW(l)));           // widest label
  const every = Math.max(1, Math.ceil((n * Math.max(64, lw + 18)) / Math.max(1, right - left)));   // a label every ~64px, never crowded
  const clear = 1.5 * lw + 12;    // the first and last labels hang off their point (start / end), so the next one in keeps this far away
  values.forEach((v, i) => {
    const cx = x(i);
    const tip = `${esc(labels[i])}: ${v == null ? 'no figure' : fmt(v)}${done(i) ? '' : ` (${status[i].toLowerCase()})`}`;
    g += `<g class="dash-row" data-point="${i}" data-tip="${tip}" tabindex="0" role="button" aria-label="${tip}. Show the workings.">`
      + `<rect class="dash-hit" x="${(cx - slot / 2).toFixed(1)}" y="0" width="${slot.toFixed(1)}" height="${H}"/>`
      + `<line class="dash-guide" x1="${cx.toFixed(1)}" x2="${cx.toFixed(1)}" y1="${top}" y2="${base}"/>`;
    if (v != null) {
      g += `<circle class="dash-dot${done(i) ? '' : ' dash-dot--light'}" cx="${cx.toFixed(1)}" cy="${y(v).toFixed(1)}" r="${mini ? 2 : 3}"><title>${esc(labels[i])}: ${fmt(v)}</title></circle>`;
      if (labelled.has(i)) {
        const anchor = i === n - 1 ? 'end' : i === 0 ? 'start' : 'middle';
        const below = !mini && i === lo && i !== hi;               // the lowest point's value sits under its marker
        g += `<circle class="dash-marker" cx="${cx.toFixed(1)}" cy="${y(v).toFixed(1)}" r="${mini ? 3 : 4.5}"/>`
          + `<text class="dash-value dash-value--top${v < 0 ? ' neg' : ''}" x="${cx.toFixed(1)}" y="${(below ? y(v) + 19 : y(v) - 10).toFixed(1)}" text-anchor="${anchor}">${fmt(v)}</text>`;
      }
    }
    // month labels: first and last always; others every few so they never collide (minis show none: the value says it)
    const crowd = i !== 0 && i !== n - 1 && (cx - x(0) < clear || x(n - 1) - cx < clear);
    if (!mini && ((i % every === 0 && !crowd) || i === n - 1)) g += `<text class="dash-axis" x="${cx.toFixed(1)}" y="${(base + 17).toFixed(1)}" text-anchor="${i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'}">${esc(labels[i])}</text>`;
    if (!mini && status && status[i] === 'Incomplete') g += `<text class="dash-key dash-key--warn" x="${cx.toFixed(1)}" y="${base + 31}" text-anchor="end">to date</text>`;
    g += '</g>';
  });
  // a text alternative for screen readers: every point when there are few, otherwise the range, the latest, the highest and the lowest
  const said = labels.map((l, i) => [l, values[i]]).filter(([, v]) => v != null);
  const top_ = said.reduce((a, b) => (b[1] > a[1] ? b : a), said[0] || ['', 0]), bot_ = said.reduce((a, b) => (b[1] < a[1] ? b : a), said[0] || ['', 0]);
  const summary = !said.length ? 'No data' : said.length <= 24 ? said.map(([l, v]) => `${l} ${fmt(v)}`).join(', ')
    : `${said.length} points, ${said[0][0]} to ${said[said.length - 1][0]}; latest ${fmt(said[said.length - 1][1])}; highest ${fmt(top_[1])} (${top_[0]}); lowest ${fmt(bot_[1])} (${bot_[0]})`;
  return `<svg class="dash-svg report-area${mini ? ' report-area--mini' : ''}" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="group" aria-label="${esc(`Chart: ${summary}${tv != null ? `; target ${fmt(tv)}` : ''}.`)}">${g}</svg>`;
}

function renderColumns(labels, values, status, format, width) { return renderArea(labels, values, status, format, true, width); }

function mountReport(root, r, only, simple, opts = {}) {
  // Draws a report into root. One filter per block drives every section ("vary" sections have a version
  // for each filter value; bars and tables highlight it; series follow it). Only sections whose content
  // changed are redrawn, so charts don't re-animate when nothing about them changed.
  const state = { block: 0, filter: {}, views: {} };
  if (opts.initial) {                                   // e.g. from ?business=services&filter=Installations
    const bi = r.blocks.findIndex((x) => x.label && x.label.toLowerCase() === String(opts.initial.business || '').toLowerCase());
    if (bi >= 0) state.block = bi;
    const fb = r.blocks[state.block].filter;
    if (fb && opts.initial.filter != null && fb.options.some(([v]) => v === opts.initial.filter)) state.filter[state.block] = opts.initial.filter;
  }
  const supports = [];
  const cw = () => chartWidth(root, 38);                    // a card's inner width (cards have ~18px padding a side)
  const sup = (sp) => { supports.push(sp); return supports.length - 1; };
  const fval = () => { const b = r.blocks[state.block]; return b.filter ? (state.filter[state.block] ?? b.filter.options[0][0]) : 'All'; };

  function kpiHtml(sec) {
    return `<div class="dash-kpis report-kpis${sec.big ? ' report-kpis--big' : ''}${sec.items.length === 1 ? ' report-kpis--one' : ''}">${sec.items.map((k) => `<button type="button" class="dash-kpi" data-sup="${sup(k.support)}"><span>${esc(k.label)}</span><strong class="${(negCls(k.value) + (k.tone ? ` is-${k.tone}` : '')).trim()}">${esc(k.value)}</strong><em class="${k.cls || ''}">${esc(k.sub || '')}</em><small class="dash-how">How it's worked out</small></button>`).join('')}</div>`;
  }
  function barsHtml(sec, key) {
    let ch = sec.chart, toggle = '';
    if (ch.views) {
      const cur = state.views[key] || ch.views[0].id;
      const v = ch.views.find((x) => x.id === cur) || ch.views[0];
      ch = { ...ch, values: v.values, format: v.format, target: v.target, breakeven: v.breakeven, marks: v.marks, mark_label: v.mark_label, below_marks: v.below_marks, orderBy: sec.chart.views[0].values, variancePct: sec.chart.views[0].values };
      toggle = `<div class="seg" role="group" aria-label="Show as">${sec.chart.views.map((x) => `<button type="button" data-view="${key}" data-id="${x.id}" aria-pressed="${x.id === v.id}">${esc(x.label)}</button>`).join('')}</div>`;
    }
    if (sec.highlight_filter && ch.labels.includes(fval())) ch = { ...ch, highlight: fval() };
    const det = (sec.chart.details || []).map((d) => sup(d));
    const one = sec.support ? sup(sec.support) : null;
    const svg = renderChart(ch, Math.min(cw(), 860)).replace(/data-detail="(\d+)"/g, (m, i) => `data-sup="${det.length ? det[+i] : one}"`);
    return `<div class="report-card"><div class="dash-chart-head"><h2 class="report-h">${esc(ch.title)}</h2>${toggle}</div>${ch.subtitle ? `<p class="dash-chart-sub">${esc(ch.subtitle)}</p>` : ''}${svg}${simple ? '<p class="dash-hint">Click or tap any bar for its workings.</p>' : ''}</div>`;
  }
  function seriesHtml(sec, key, hasFilter) {
    const dims = sec.dims || { line: ['All'], measure: [[Object.keys(sec.views)[0].split('|')[1], '']] };
    const cur = state.views[key] || { line: dims.line[0], measure: dims.measure[0][0] };
    state.views[key] = cur;
    const line = hasFilter && dims.line.includes(fval()) ? fval() : cur.line;
    const view = sec.views[`${line}|${cur.measure}`] || sec.views[`All|${cur.measure}`];
    const grp = (name, items, val) => (items.length > 1 ? `<div class="seg" role="group" aria-label="${name}">${items.map(([id, lab]) => `<button type="button" data-series="${key}" data-dim="${name}" data-id="${esc(id)}" aria-pressed="${id === val}">${esc(lab)}</button>`).join('')}</div>` : '');
    const ids = ((sec.supports || {})[line] || []).map((p) => sup(p));
    const s0 = Math.max(0, view.values.findIndex((v) => v != null));
    const chart = renderArea(sec.labels.slice(s0), view.values.slice(s0), sec.status.slice(s0), view.format, false, cw(), sec.target).replace(/data-point="(\d+)"/g, (m, i) => (ids.length ? `data-sup="${ids[+i + s0]}"` : ''));
    const measures = simple ? dims.measure.filter(([id]) => id !== 'margin') : dims.measure;
    const lineToggle = hasFilter || simple ? '' : grp('line', dims.line.map((l) => [l, l]), cur.line);
    const title = simple ? sec.title.replace(' by line', '').replace(' by type of work', '') : sec.title;
    const gmNote = simple && cur.measure.startsWith('margin') ? '<p class="dash-chart-sub">Gross margin is before overheads, so it is not profit. <a href="numbers-explained.html#gross-margin">What that means</a>.</p>' : '';
    const hint = simple ? '<p class="dash-hint">Click or tap any point for its workings.</p>' : '';
    return `<div class="report-card"><div class="dash-chart-head"><h2 class="report-h">${esc(title)}${hasFilter && line !== 'All' ? ` · ${esc(line)}` : ''}</h2><div class="report-toggles">${lineToggle}${grp('measure', measures, cur.measure)}</div></div>${chart}${sec.note && !simple ? `<p class="dash-chart-sub">${esc(sec.note)}</p>` : ''}${gmNote}${hint}</div>`;
  }
  function tableHtml(sec) {
    const hl = sec.highlight_filter ? fval() : null;
    return `<div class="report-card"><h2 class="report-h">${esc(sec.title)}</h2><div class="st-scroll" tabindex="0" role="region" aria-label="${esc(`${sec.title} (table, scrolls)`)}"><table class="st-table report-table"><thead><tr>${sec.head.map((h, i) => `<th scope="col"${i ? ' class="n"' : ''}>${esc(h)}</th>`).join('')}</tr></thead><tbody>${sec.rows.map((row, ri) => `<tr class="${row[0] === 'Total' ? 'st-total' : ''}${hl && hl !== 'All' && row[0] === hl ? ' st-hl' : ''}">${row.map((c, i) => { const t = sec.tones && sec.tones[ri] && sec.tones[ri][i]; return `<td${i ? ` class="n${negCls(c)}${t ? ` is-${t}` : ''}"` : ''}>${esc(c)}</td>`; }).join('')}</tr>`).join('')}</tbody></table></div>${sec.note ? `<p class="dash-chart-sub">${esc(sec.note)}</p>` : ''}</div>`;
  }
  function sectionHtml(sec, key, hasFilter) {
    if (sec.type === 'vary') sec = sec.by[fval()] || sec.by.All || Object.values(sec.by)[0];
    if (only && !only.includes(sec.type)) return '';
    if (sec.type === 'kpis') return kpiHtml(sec);
    if (sec.type === 'bars') return barsHtml(sec, key);
    if (sec.type === 'series') return seriesHtml(sec, key, hasFilter);
    if (sec.type === 'table') return tableHtml(sec);
    if (sec.type === 'text') return simple ? `<p class="report-feature-line">${esc(sec.shows)}</p>` : `<div class="report-text"><div><h2 class="report-h">What it shows</h2><p>${esc(sec.shows)}</p></div><div class="report-act"><h2 class="report-h">What you'd do about it</h2><p>${esc(sec.action)}</p></div></div>`;
    if (sec.type === 'list') { const tag = sec.numbered ? 'ol' : 'ul'; return `<div class="report-card"><h2 class="report-h">${esc(sec.title)}</h2><${tag} class="report-list${sec.numbered ? ' report-list--num' : ''}">${sec.items.map((x) => `<li>${esc(x)}</li>`).join('')}</${tag}></div>`; }
    if (sec.type === 'definition') return `<details class="report-def"><summary><strong>${esc(sec.title)}</strong> <span>What's the difference?</span></summary><p>${esc(sec.text)}</p>${sec.link ? `<a href="${esc(sec.link)}">The numbers, explained &rarr;</a>` : ''}</details>`;
    if (sec.type === 'insight') return `<button type="button" class="report-insight" data-sup="${sup(sec.support)}"><strong>${esc(sec.title)}</strong><span>${esc(sec.text)}</span><small class="dash-how">How it's worked out</small></button>`;
    return '';
  }
  const slots = [];
  function render() {
    supports.length = 0;
    const b = r.blocks[state.block];
    const parts = [];
    if (r.blocks.length > 1 && !simple) parts.push(`<div class="seg-bar report-blocks"><span class="seg-label">Business</span><div class="seg" role="group" aria-label="Business">${r.blocks.map((x, i) => `<button type="button" data-block="${i}" aria-pressed="${i === state.block}">${esc(x.label)}</button>`).join('')}</div></div>`);
    if (b.filter && !simple) parts.push(`<div class="report-filter seg-bar"><span class="seg-label">${esc(b.filter.label)}</span><div class="seg" role="group" aria-label="${esc(b.filter.label)}">${b.filter.options.map(([v, l]) => `<button type="button" data-filter="${esc(v)}" aria-pressed="${v === fval()}">${esc(l)}</button>`).join('')}</div></div>`);
    // on phones the definition waits until after the first chart, so the numbers come first
    const order = b.sections.map((sec, i) => i);
    const di = b.sections.findIndex((sec) => sec.type === 'definition');
    const fc = b.sections.findIndex((sec) => { const s1 = sec.type === 'vary' ? Object.values(sec.by)[0] : sec; return s1 && (s1.type === 'bars' || s1.type === 'series'); });
    if (di >= 0 && fc > di && window.matchMedia('(max-width: 640px)').matches) { order.splice(di, 1); order.splice(fc, 0, di); }
    order.forEach((i) => parts.push(sectionHtml(b.sections[i], `${state.block}-${i}`, !!b.filter)));
    if (!simple) {
      const kinds = new Set(b.sections.map((sec) => (sec.type === 'vary' ? (Object.values(sec.by)[0] || {}).type : sec.type)));
      const what = [kinds.has('kpis') || kinds.has('insight') ? 'number' : '', kinds.has('bars') ? 'bar' : '', kinds.has('series') ? (r.slug === 'runway' || r.slug === 'cash-payroll' ? 'day' : 'month') : ''].filter(Boolean);
      if (what.length) parts.push(`<p class="dash-hint">Click or tap any ${what.length > 1 ? `${what.slice(0, -1).join(', ')} or ${what[what.length - 1]}` : what[0]} for its workings.</p>`);
    }
    // only redraw (and so re-animate) sections whose content changed; others just get fresh workings links
    const norm = (h) => h.replace(/data-sup="\d+"/g, '').replace(/ag\d+/g, '');
    parts.forEach((h, i) => {
      if (!slots[i]) { slots[i] = document.createElement('div'); slots[i].className = 'report-slot'; root.appendChild(slots[i]); }
      const el = slots[i];
      if (el.dataset.h === h) return;
      const same = el.dataset.h !== undefined && (el.dataset.h === '' || norm(el.dataset.h) === norm(h));
      el.classList.toggle('no-anim', same);
      el.innerHTML = h;
      el.dataset.h = h;
    });
    while (slots.length > parts.length) slots.pop().remove();
    if (opts.onState) {
      const opt = b.filter ? b.filter.options.find(([v]) => v === fval()) : null;
      opts.onState({ business: r.blocks.length > 1 ? b.label : null, filter: b.filter ? fval() : null, filterLabel: opt ? opt[1] : null, isDefaultFilter: !b.filter || fval() === b.filter.options[0][0] });
    }
  }
  root.innerHTML = '';
  // redraw at the new width when the box resizes (no re-animation)
  let lastW = root.clientWidth;
  if ('ResizeObserver' in window) new ResizeObserver((entries, ro) => {
    if (!root.isConnected) { ro.disconnect(); return; }          // this report was replaced (e.g. a new period): stop
    if (Math.abs(root.clientWidth - lastW) < 8) return;
    lastW = root.clientWidth;
    slots.forEach((el) => el.classList.add('no-anim'));
    slots.forEach((el) => { el.dataset.h = ''; });
    render();
  }).observe(root);
  root.addEventListener('click', (e) => {
    const t = e.target.closest('[data-sup],[data-view],[data-series],[data-block],[data-filter]');
    if (!t) return;
    if (t.dataset.block) { state.block = +t.dataset.block; render(); }
    else if (t.dataset.filter !== undefined) { state.filter[state.block] = t.dataset.filter; render(); }
    else if (t.dataset.view) { state.views[t.dataset.view] = t.dataset.id; render(); }
    else if (t.dataset.series) { state.views[t.dataset.series][t.dataset.dim] = t.dataset.id; render(); }
    else if (t.dataset.sup !== undefined && t.dataset.sup !== 'null') openSupport(supports[+t.dataset.sup]);
  });
  root.addEventListener('keydown', (e) => {
    const t = e.target.closest('[data-sup]');
    if (t && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); openSupport(supports[+t.dataset.sup]); }
  });
  render();
}

function wireSupportDialog() {
  const dlg = document.getElementById('support-dialog');
  if (!dlg || dlg.dataset.wired) return;
  dlg.dataset.wired = '1';
  document.getElementById('support-close').addEventListener('click', () => dlg.close());
  dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });
}

function setupReport() {
  const box = document.getElementById('report');
  const features = document.querySelectorAll('[data-report-feature]');
  const cards = document.querySelectorAll('[data-report-card]');
  if (!box && !features.length && !cards.length) return;
  wireSupportDialog();
  if (box) {
    loadData(`data/reports/${box.dataset.report}.json`).then((f) => setupReportPage(f))
      .catch(() => dataFailed(document.getElementById('report-root')));
  }
  // the featured chart on the SME and not-for-profit pages, at the month picked on the site (or the report's default)
  features.forEach((el) => {
    const only = el.dataset.only ? el.dataset.only.split(',') : null;
    loadData(`data/reports/${el.dataset.reportFeature}.json`).then((f) => {
      const r = f.by_period[f.default];
      const p = pickPeriod(r.periods, sitePeriod());
      mountReport(el, (p && f.by_period[p]) || r, only, true);
    }).catch(() => dataFailed(el));
  });
  if (cards.length) loadData('data/reports/cards.json').then((c) => setupReportCards(cards, c.reports)).catch(() => {});
}

// a report page: the Period dropdown runs the report for another month (every period is built from the data by
// tools/3_publish_site/fourthsheet, all in the report's one file). ?period=YYYY-MM links straight to one.
function setupReportPage(f) {
  const base = f.by_period[f.default];
  const sel = document.getElementById('report-period');
  const meta = document.getElementById('report-meta');
  const metaStart = meta.innerHTML;
  const load = (p) => (f.by_period[p] ? Promise.resolve(f.by_period[p]) : Promise.reject(new Error(`no ${p}`)));
  const params = new URLSearchParams(window.location.search);
  let periodFallback = '';
  let view = { business: params.get('business'), filter: params.get('filter') };     // restored from a copied link
  let current = base;
  const exportBox = document.getElementById('report-export');
  // a report filled from its templates (assets/exports/): each download is made from the period on screen when it's chosen
  const ver = ((document.querySelector('script[src*="script.js"]') || {}).src || '').split('?v=')[1] || '';
  const builder = (r) => (r.exports_template ? (fmt) => loadExportKit(ver).then((kit) => kit.build(r, fmt, { ver })) : null);
  const menu = exportBox ? mountExportMenu(exportBox, { period: base.period_label, exports: base.exports, meta: base.exports_meta, build: builder(base) }) : null;
  const syncUrl = () => {
    const u = new URL(window.location.href);
    const set = (k, v) => (v ? u.searchParams.set(k, v) : u.searchParams.delete(k));
    set('period', current.period === base.default_period ? null : current.period);
    set('business', view.business && current.blocks.length > 1 && view.business !== current.blocks[0].label ? view.business.toLowerCase() : null);
    set('filter', view.isDefaultFilter ? null : view.filter);
    history.replaceState(null, '', u);
  };
  const show = (r) => {
    current = r;
    const st = r.status[0];
    meta.innerHTML = `${metaStart} · <span class="dash-status is-${st.status.toLowerCase()}" title="${esc(r.status.map((x) => x.note).join(' '))}">${esc(r.period_label)}: ${esc(st.status.toLowerCase())}</span>`;
    document.getElementById('report-period-note').textContent = [r.part_note || r.periods_note || '', periodFallback].filter(Boolean).join(' ');
    const root = document.getElementById('report-root');
    root.innerHTML = '';
    const inner = document.createElement('div');
    root.appendChild(inner);
    mountReport(inner, r, r.embed_url ? ['kpis', 'text', 'insight', 'definition', 'list', 'table'] : null, false, {
      initial: view,
      onState: (v) => {
        view = v;
        // separate businesses have separate files: the menu offers the business on screen, never both in one
        const ex = (r.exports_by_business || {})[v.business] || { exports: r.exports, meta: r.exports_meta };
        if (menu) menu.update({ period: r.period_label, filterLabel: [v.business, v.filterLabel].filter(Boolean).join(' · '), exports: ex.exports, meta: ex.meta, build: builder(r) });
        syncUrl();
      },
    });
    if (r.embed_url) {      // a live report in place of the charts, same shell (tools/3_publish_site/build_reports.py EMBEDS)
      const frame = document.createElement('div');
      frame.className = 'report-card report-embed';
      frame.setAttribute('data-embed', '');
      frame.dataset.slowMessage = 'This report is taking longer than usual to load. Try refreshing the page in a moment.';
      frame.innerHTML = `<div class="embed-status" role="status"><span class="spinner"></span><span class="embed-status-msg">Loading report…</span></div>`
        + `<iframe src="${esc(r.embed_url)}" title="${esc(r.question)}: live report" loading="lazy" allowfullscreen></iframe>`;
      const after = inner.querySelector('.report-kpis');
      if (after) after.closest('.report-slot').after(frame); else inner.prepend(frame);
      watchEmbedLoad(frame);
    }
  };
  const go = (p, push) => {
    sel.disabled = true;
    load(p).then((r) => {
      show(r);
      sel.value = p;
    }).catch(() => {
      document.getElementById('report-period-note').textContent = 'That period could not load. Try again, or pick another.';
      sel.value = base.period;
    }).finally(() => { sel.disabled = false; });
  };
  const asked = params.get('period') || sitePeriod();
  const want = pickPeriod(base.periods, asked);
  if (asked && want && want !== asked) {        // this report doesn't have that month: the nearest earlier one, said plainly
    periodFallback = `${monthLabel(asked)} isn't available for this report, so it opens on ${monthLabel(want)}.`;
  }
  if (want && want !== base.period) go(want, false); else show(base);
  if (sel) sel.addEventListener('change', () => { periodFallback = ''; setSitePeriod(sel.value); go(sel.value, true); });
}

// a small live chart on every example report card (cards.json: just what a card draws, every report and period)
function setupReportCards(cards, all) {
  const baseOf = (slug) => all[slug] && all[slug].by_period[all[slug].default];
  const drawCard = (el, override) => {
    const r = override || el._period || baseOf(el.dataset.reportCard);
    if (!r) return;
    const secs = r.blocks[0].sections.map((x) => (x.type === 'vary' ? (x.by.All || Object.values(x.by)[0]) : x));
    const k = secs.find((x) => x.type === 'kpis');
    const first = secs.find((x) => x.type === 'bars' || x.type === 'series');   // the report's main chart
    const bars = first && first.type === 'bars' ? first : null;
    const ser = first && first.type === 'series' ? first : null;
    let html = '';
    if (r.card) {   // a report can say what its card shows; groups are separate businesses, each on its own scale
      const c = r.card;
      el.innerHTML = c.groups.map((g) => {
        const fmt = CHART_FORMATS[g.format] || String;
        const max = Math.max(...g.values.map((v) => Math.abs(v))) || 1;
        return `<div class="card-group"><p class="card-kpi"><strong>${esc(g.value)}</strong> <span>${esc(g.name)} · ${esc(g.sub)}</span></p>`
          + `<ul class="mini-bars">${g.labels.map((l, i) => { const v = g.values[i]; return `<li data-tip="${esc(g.name)}, ${esc(l)}: ${fmt(v)}${g.tips ? ` · ${esc(g.tips[i])}` : ''}"><span class="mb-l">${esc(l)}</span><span class="mb-t"><i class="${v < 0 ? 'neg-bar' : ''}" style="width:${(100 * Math.abs(v) / max).toFixed(1)}%"></i></span><span class="mb-v${v < 0 ? ' neg' : ''}">${fmt(v)}</span></li>`; }).join('')}</ul></div>`;
      }).join('') + (c.note ? `<p class="card-chart-note">${esc(c.note)}</p>` : '');
      return;
    }
    if (k) { const k0 = k.items[0]; html += `<p class="card-kpi"><strong class="${k0.tone ? `is-${k0.tone}` : ''}">${esc(k0.value)}</strong> <span>${esc(k0.label)}${k0.tone ? ` · ${esc(k0.sub)}` : ''}</span></p>`; }
    if (ser) {
      const dims = ser.dims || { line: ['All'], measure: [[Object.keys(ser.views)[0].split('|')[1], '']] };
      const v = ser.views[`${dims.line[0]}|${dims.measure[0][0]}`];
      const n = 12;
      html += renderColumns(ser.labels.slice(-n), v.values.slice(-n), ser.status.slice(-n), v.format, chartWidth(el)).replace(/ data-point="\d+" (data-tip="[^"]*") tabindex="0" role="button"/g, ' $1');
    } else if (bars) {
      // a readable mini bar list (label, bar, value) for the biggest few, largest first
      const ch = bars.chart, v0 = ch.views ? ch.views[0] : ch;
      const fmt = CHART_FORMATS[v0.format] || String;
      const items = ch.labels.map((l, i) => [l, v0.values[i]]).sort((p, q) => q[1] - p[1]).slice(0, 5);
      const max = Math.max(...items.map((x) => x[1]), v0.target || 0) || 1;
      const below = (v) => !ch.plain && v0.target != null && v < v0.target;
      html += `<ul class="mini-bars">${items.map(([l, v]) => `<li data-tip="${esc(l)}: ${fmt(v)}"><span class="mb-l">${esc(l)}</span><span class="mb-t"><i class="${below(v) ? 'below' : ''}" style="width:${(100 * v / max).toFixed(1)}%"></i></span><span class="mb-v${v < 0 ? ' neg' : ''}">${fmt(v)}</span></li>`).join('')}</ul>`;
    }
    el.innerHTML = html;
  };
  const chosen = sitePeriod();
  cards.forEach((el) => {
    const base = baseOf(el.dataset.reportCard);
    const p = base && pickPeriod(base.periods, chosen);
    const r = p && p !== base.period && all[el.dataset.reportCard].by_period[p];
    if (r) {                               // the month picked on the home page (or a report page)
      el._period = r;
      const ans = el.nextElementSibling;
      if (ans && ans.tagName === 'P' && r.answer) ans.textContent = r.answer;
    }
    drawCard(el);
    if ('ResizeObserver' in window) { let w = el.clientWidth; new ResizeObserver(() => { if (Math.abs(el.clientWidth - w) >= 8) { w = el.clientWidth; drawCard(el); } }).observe(el); }
  });
}

/* ---------------------------------------------------------------------------
   SITE PERIOD — the month picked on the home page (or any report page) carries to every page for the rest of the
   visit: report pages open on it, report cards show it. Kept in sessionStorage ('fs-period') and in links as ?period=.
   A report that doesn't have that month opens on the nearest earlier one it does have (or its first, if the month is
   older than all its data), and says so.
--------------------------------------------------------------------------- */
const SITE_PERIOD_KEY = 'fs-period';
function sitePeriod() {
  const q = new URLSearchParams(window.location.search).get('period');
  if (/^\d{4}-\d{2}$/.test(q || '')) { setSitePeriod(q); return q; }   // a shared link sets the month for the rest of the visit
  try { return sessionStorage.getItem(SITE_PERIOD_KEY); } catch (e) { return null; }
}
function setSitePeriod(p) { try { if (p) sessionStorage.setItem(SITE_PERIOD_KEY, p); } catch (e) { /* storage blocked: the page still works */ } }
function pickPeriod(periods, want) {        // periods newest first, [{ value: 'yyyy-mm', … }]
  if (!want || !periods || !periods.length) return null;
  if (periods.some((o) => o.value === want)) return want;
  const earlier = periods.find((o) => o.value <= want);
  return earlier ? earlier.value : periods[periods.length - 1].value;   // older than all its data: its first month
}
function monthLabel(p) { const [y, m] = p.split('-').map(Number); return new Date(y, m - 1, 1).toLocaleString('en-AU', { month: 'long', year: 'numeric' }); }
const DATA_FILES = {};
function loadData(path) {        // a generated data file (data/*.json), fetched once per page with script.js's ?v=, so a publish refreshes it
  if (!DATA_FILES[path]) {
    const ver = ((document.querySelector('script[src*="script.js"]') || {}).src || '').split('?v=')[1] || '';
    DATA_FILES[path] = fetch(`${path}${ver ? `?v=${ver}` : ''}`)
      .then((res) => { if (!res.ok) throw new Error(`${path}: ${res.status}`); return res.json(); })
      .catch((e) => { delete DATA_FILES[path]; throw e; });      // a failed fetch can be tried again
  }
  return DATA_FILES[path];
}
function dataFailed(el) {
  if (el) el.innerHTML = '<p class="data-failed">This sample data could not load. Try refreshing the page.</p>';
}

function setupHeroDash() {
  const box = document.getElementById('hero-dash');
  if (!box) return;
  loadData('data/dashboard.json').then((d) => { window.FOURTH_SHEET_DASHBOARD = d; startHeroDash(box, d); })
    .catch(() => dataFailed(document.getElementById('dash-panel')));
}
function startHeroDash(box, data) {
  const askedFor = new URLSearchParams(window.location.search).get('business');
  if (data.orgs.some((o) => o.id === askedFor)) dash.org = askedFor;
  const exportBox = document.getElementById('dash-export');
  if (exportBox) dash.menu = mountExportMenu(exportBox, { period: data.status[0].label });
  // Period: every month the data has. It opens on the most recent locked month (list.default, from the period-lock
  // register); dashboard.json holds the month modelled end to end (list.base), every other month loads when picked
  const list = data.period_list;
  const perSel = document.getElementById('dash-period');
  if (list && perSel) {
    const base = data;
    const baseMonth = list.base || list.default;
    perSel.innerHTML = list.months.map((m) => `<option value="${m.value}">${esc(m.label)}${m.status === 'Incomplete' ? ' (incomplete)' : ''}</option>`).join('');
    const loadMonth = (mo) => (mo === baseMonth ? Promise.resolve(base)
      : loadData('data/dashboard-months.json').then((all) => all.by_month[mo] || Promise.reject(new Error(`no ${mo}`))));
    const showMonth = (mo, remember) => {
      perSel.disabled = true;
      loadMonth(mo).then((d) => {
        window.FOURTH_SHEET_DASHBOARD = d;
        perSel.value = mo;
        if (remember) setSitePeriod(mo);
        const u = new URL(window.location.href);
        if (mo === list.default) u.searchParams.delete('period'); else u.searchParams.set('period', mo);
        history.replaceState(null, '', u);
        renderDash();
      }).catch(() => { perSel.value = list.default; }).finally(() => { perSel.disabled = false; });
    };
    const start = pickPeriod(list.months, sitePeriod()) || list.default;
    perSel.value = start;
    if (start !== baseMonth) setTimeout(() => showMonth(start, false), 0);
    perSel.addEventListener('change', () => showMonth(perSel.value, true));
  }
  document.getElementById('dash-orgs').innerHTML = data.orgs.map((o) => `<button type="button" data-org="${o.id}" aria-pressed="false">${esc(o.toggle)}</button>`).join('');
  // switching organisation always opens on the fourth sheet
  box.querySelectorAll('[data-org]').forEach((b) => b.addEventListener('click', () => { dash.org = b.dataset.org; dash.tab = 'fourth'; renderDash(); }));
  const tabs = [...box.querySelectorAll('[role="tab"]')];
  tabs.forEach((t, i) => {
    t.addEventListener('click', () => { dash.tab = t.dataset.tab; renderDash(); });
    // arrow keys move between tabs (standard tab behaviour)
    t.addEventListener('keydown', (e) => {
      const d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
      if (!d) return;
      const next = tabs[(i + d + tabs.length) % tabs.length];
      dash.tab = next.dataset.tab; renderDash(); next.focus();
    });
  });
  const dlg = document.getElementById('assumptions-dialog');
  // "See all assumptions" sits in the workings dialog
  document.addEventListener('click', (e) => {
    if (!e.target.closest('[data-open-assumptions]')) return;
    const sd = document.getElementById('support-dialog');
    if (sd && sd.open) sd.close();
    if (dlg.showModal) dlg.showModal(); else dlg.setAttribute('open', '');
  });
  document.getElementById('assumptions-close').addEventListener('click', () => dlg.close());
  // workings: headline numbers, chart bars and the %/$ toggle
  const sdlg = document.getElementById('support-dialog');
  document.getElementById('support-close').addEventListener('click', () => sdlg.close());
  sdlg.addEventListener('click', (e) => { if (e.target === sdlg) sdlg.close(); });
  const panel = document.getElementById('dash-panel');
  const org = () => window.FOURTH_SHEET_DASHBOARD.orgs.find((x) => x.id === dash.org);
  panel.addEventListener('click', (e) => {
    const k = e.target.closest('[data-kpi]'), r = e.target.closest('[data-detail]'), v = e.target.closest('[data-view]');
    if (k) openSupport(org().fourth.kpis[+k.dataset.kpi].support);
    else if (r) openSupport((org().fourth.chart.details || [])[+r.dataset.detail]);
    else if (v) { dash.view = v.dataset.view; renderDash(); }
  });
  panel.addEventListener('keydown', (e) => {
    const r = e.target.closest('[data-detail]');
    if (r && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); openSupport((org().fourth.chart.details || [])[+r.dataset.detail]); }
  });
  dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); }); // click outside closes
  renderDash();
  if ('ResizeObserver' in window) {
    let w = panel.clientWidth;
    new ResizeObserver(() => { if (Math.abs(panel.clientWidth - w) >= 8) { w = panel.clientWidth; panel.classList.add('no-anim'); renderDash(); } }).observe(panel);
  }
}

/* ---------------------------------------------------------------------------
   INTRO — the opening animation on the home page (markup: index.html, styles: styles.css, search "INTRO").
   Plays once per visit, then the picture shrinks into the small illustration beside the headline.
   Skipped for reduced motion, automated tests, a link to a section (#…) or ?intro=off; ?intro=on forces it.
   Clicking the sheets beside the headline (.hero-sheets) plays it again, on request, whatever the settings.
--------------------------------------------------------------------------- */
const INTRO_HOLD_MS = 9000;   // when the picture starts to shrink away (the CSS timings finish at about 7.6s)

function setupIntro() {
  const intro = document.getElementById('intro');
  if (!intro) return;
  const fresh = intro.cloneNode(true);   // an untouched copy, so the sheets beside the headline can play it again
  const sheets = document.querySelector('.hero-sheets');
  if (sheets) sheets.addEventListener('click', (e) => {
    if (document.getElementById('intro')) return;          // already playing
    const again = fresh.cloneNode(true);
    document.body.prepend(again);
    playIntro(again, sheets, e.detail === 0);            // detail 0: pressed with Enter or Space, not tapped
  });
  const param = new URLSearchParams(location.search).get('intro');
  let seen = false;
  try { seen = sessionStorage.getItem('introSeen') === '1'; } catch (e) { /* storage blocked: play it */ }
  const skip = param === 'off' || (param !== 'on' && (seen || location.hash || window.scrollY > 0 || navigator.webdriver
    || window.matchMedia('(prefers-reduced-motion: reduce)').matches));
  if (skip) { intro.remove(); return; }
  try { sessionStorage.setItem('introSeen', '1'); } catch (e) { /* fine */ }
  playIntro(intro, null, !window.matchMedia('(pointer: coarse)').matches);
}

function playIntro(intro, returnFocus, focusClose) {   // returnFocus: where focus goes after (the sheets button on a replay);
                                                        // focusClose: put focus on × (keyboard and mouse; not on a touch screen, where its ring is clutter)
  const art = intro.querySelector('.intro-art');
  const target = document.querySelector('.hero-sheets img');
  intro.hidden = false;
  document.body.classList.add('intro-active');

  let leaving = false;
  const finish = () => {
    intro.remove(); document.body.classList.remove('intro-active'); document.removeEventListener('keydown', onKey);
    if (returnFocus && focusClose) returnFocus.focus({ preventScroll: true });
  };
  const leave = (skipped) => {
    if (leaving) return;
    leaving = true;
    clearTimeout(timer);
    if (skipped) intro.classList.add('intro--skipped');
    const from = art.getBoundingClientRect();
    const to = target && target.getBoundingClientRect();
    if (!to || !to.width || to.bottom < 0 || to.top > window.innerHeight) {
      intro.classList.add('intro--fade');   // nowhere on screen to land: just fade out
      setTimeout(finish, 520);
      return;
    }
    intro.classList.add('intro--leaving');
    art.style.transformOrigin = '0 0';
    art.style.transform = `translate(${to.left - from.left}px, ${to.top - from.top}px) scale(${to.width / from.width})`;
    art.addEventListener('transitionend', (e) => { if (e.target === art) finish(); });
    setTimeout(finish, 1200);   // in case transitionend never fires
  };
  const onKey = (e) => { if (e.key === 'Escape') leave(true); };
  const timer = setTimeout(() => leave(false), INTRO_HOLD_MS);
  const closeBtn = intro.querySelector('.intro-close');
  if (closeBtn && focusClose) closeBtn.focus({ preventScroll: true });   // keyboard users land on ×
  intro.querySelector('.intro-skip').addEventListener('click', () => leave(true));
  intro.addEventListener('click', (e) => { if (!e.target.closest('.intro-stage')) leave(true); });   // a click on the dimmed page closes it; clicks in the panel don't
  document.addEventListener('keydown', onKey);
}

/* ---------------------------------------------------------------------------
   Page start-up
--------------------------------------------------------------------------- */
document.addEventListener('DOMContentLoaded', () => {
  const year = document.getElementById('year');
  if (year) year.textContent = new Date().getFullYear();

  // Mobile menu toggle (the ☰ button shown on narrow screens).
  const toggle = document.querySelector('.nav-toggle');
  const navLinks = document.querySelector('.nav-links');

  if (toggle && navLinks) {
    const setOpen = (open) => {
      toggle.setAttribute('aria-expanded', String(open));
      toggle.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
      navLinks.classList.toggle('open', open);
    };
    const isOpen = () => toggle.getAttribute('aria-expanded') === 'true';
    toggle.addEventListener('click', () => setOpen(!isOpen()));
    // Close the menu after picking a section.
    navLinks.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => setOpen(false)));
    // Escape, or a tap anywhere outside the menu, closes it and puts focus back on ☰
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && isOpen()) { setOpen(false); toggle.focus(); }
    });
    document.addEventListener('pointerdown', (e) => {
      if (isOpen() && !navLinks.contains(e.target) && !toggle.contains(e.target)) { setOpen(false); toggle.focus({ preventScroll: true }); }
    });
  }

  // .seg groups: Left/Right (and Home/End) move to the next option and choose it
  document.addEventListener('keydown', (e) => {
    const btn = e.target.closest && e.target.closest('.seg[role="group"] > button');
    if (!btn || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return;
    const all = [...btn.parentElement.children];
    const i = all.indexOf(btn);
    const next = all[e.key === 'Home' ? 0 : e.key === 'End' ? all.length - 1 : (i + (e.key === 'ArrowRight' ? 1 : -1) + all.length) % all.length];
    e.preventDefault();
    next.click();
    const sel = next.dataset.org ? `[data-org="${next.dataset.org}"]` : next.dataset.view ? `[data-view="${next.dataset.view}"]${next.dataset.id ? `[data-id="${next.dataset.id}"]` : ''}`
      : next.dataset.filter !== undefined ? `[data-filter="${next.dataset.filter}"]` : next.dataset.block ? `[data-block="${next.dataset.block}"]`
      : next.dataset.series ? `[data-series="${next.dataset.series}"][data-id="${next.dataset.id}"]` : next.dataset.side ? `[data-side="${next.dataset.side}"]` : next.dataset.period ? `[data-period="${next.dataset.period}"]` : null;
    requestAnimationFrame(() => { const again = sel && document.querySelector(`.seg ${sel}`); (again || next).focus(); });   // the group may have been redrawn
  });

  setupIntro();
  setupAnalytics();
  setupGameSlot();
  applyPrices();
  setupHeroDash(); setupDeliveries(); setupReport(); mountStaticExportMenus(); setupContactForm(); setupLightbox(); setupChartTips(); setupTitleBar();
  renderReports(); // must run before watchEmbedLoad so live report cards get a loading state
  document.querySelectorAll('[data-embed]').forEach(watchEmbedLoad);
});
