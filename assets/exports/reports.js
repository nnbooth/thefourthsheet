/* ---------------------------------------------------------------------------
   EXPORT DATA — for each report whose downloads are filled from templates (assets/exports/fill.js), the values, lists
   and charts its template's slots name, worked out from the period's data as the page has it
   (data/reports/<report>.json, by_period[YYYY-MM]). Every number here is one the page shows or one of its workings:
   nothing is calculated that the page doesn't already say. Rates stay formulas in the spreadsheet.
--------------------------------------------------------------------------- */
(function (root) {
  'use strict';

  const TONE = { bad: '#B42318', warn: '#8A6D3B' };
  const BRAND = '#2F7A5D';
  const AUDIENCE = { nfp: 'Not-for-profits', sme: 'Businesses' };
  const num = (s) => {
    if (s == null || s === '') return null;
    const n = Number(String(s).replace(/[^0-9.-]/g, ''));
    return Number.isFinite(n) ? n : null;
  };
  // a line of a set of workings, by its label (exactly, else the line that starts with it)
  function line(sup, label, col) {
    const rows = (sup && sup.rows) || [];
    const r = rows.find((x) => x[0] === label) || rows.find((x) => x[0].startsWith(label));
    if (!r) throw new Error(`No "${label}" line in the workings "${sup && sup.title}".`);
    return num(r[col]);
  }

  // "Generated 22 Oct 2026, 3:05pm" and "2026-10-22 1505", in Brisbane time (like every download)
  function stamps(now) {
    const p = Object.fromEntries(new Intl.DateTimeFormat('en-AU', {
      timeZone: 'Australia/Brisbane', year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', hour12: false,
    }).formatToParts(now).map((x) => [x.type, x.value]));
    const h = Number(p.hour) % 24;
    const mm = String(new Intl.DateTimeFormat('en-AU', { timeZone: 'Australia/Brisbane', month: '2-digit' }).format(now));
    const dd = String(p.day).padStart(2, '0');
    return {
      text: `Generated ${Number(p.day)} ${p.month.replace('.', '').slice(0, 3)} ${p.year}, ${(h % 12) || 12}:${p.minute}${h < 12 ? 'am' : 'pm'}`,
      file: `${p.year}-${mm}-${dd} ${String(h).padStart(2, '0')}${p.minute}`,
    };
  }

  // what every report's template can use
  function common(r, now) {
    const st = stamps(now);
    return {
      business: r.business,
      question: r.question,
      intro: r.intro,
      answer: r.answer,
      audience: AUDIENCE[r.audience] || '',
      period_label: r.period_label,
      period_short: r.period_short,
      period_status: r.period_status,
      part_note: r.part_note || '',
      status: r.status.map((s) => ({ label: s.label, status: s.status, note: s.note })),
      status_short: r.status.map((s) => `${s.label} ${s.status.toLowerCase()}`).join(' · '),
      status_lines: r.status.map((s) => `${s.label}: ${s.status}. ${s.note}`).join('\n'),
      generated: st.text,
      file_name: `${(r.exports_meta || {}).name || `${r.business} - ${r.slug} - ${r.period_label}`} - generated ${st.file}`,
    };
  }

  const kpiValues = (items) => Object.fromEntries(items.map((it, i) => [`kpi${i + 1}`, {
    label: it.label, value: it.value, sub: it.sub || '', colour: TONE[it.tone] || BRAND,
  }]));

  const REPORTS = {
    // Calls for help (report-calls.html)
    calls(r, now) {
      const secs = r.blocks[0].sections;
      const sec = (t) => secs.find((s) => s.type === t);
      const kp = sec('kpis').items, bars = sec('bars').chart, series = sec('series'), text = sec('text');
      const main = kp[0].support, wait = kp[3].support;
      const view = (id) => bars.views.find((v) => v.id === id);
      const sups = series.supports.All;
      const months = series.months.map((m, i) => ({
        label: series.labels[i],
        status: series.status[i],
        calls: line(sups[i], 'Calls', 1),
        staffed: line(sups[i], 'Calls while', 1),
        answered: line(sups[i], 'Answered', 1),
      }));
      months.forEach((m, i) => {       // the month table and the month chart are the same numbers
        if (m.calls !== series.views['All|calls'].values[i]) throw new Error(`${m.label}: ${m.calls} calls in the workings, ${series.views['All|calls'].values[i]} on the chart.`);
        const rate = series.views['All|rate'].values[i];
        Object.assign(m, {               // as the page shows them (the PDF's table; the spreadsheet works the rate out itself)
          calls_text: m.calls.toLocaleString('en-AU'), staffed_text: m.staffed.toLocaleString('en-AU'),
          answered_text: m.answered.toLocaleString('en-AU'), rate_text: rate == null ? '' : `${rate.toFixed(1)}%`,
        });
      });
      const target = num((/target ([\d.]+)%/.exec(kp[1].sub || '') || [])[1]);
      return {
        ...common(r, now),
        ...kpiValues(kp),
        cur: main.head[1],
        prev: main.head[2] || '',
        w: {
          calls: line(main, 'Calls', 1), calls_prev: line(main, 'Calls', 2),
          staffed: line(main, 'Calls while staffed', 1), staffed_prev: line(main, 'Calls while staffed', 2),
          answered: line(main, 'Answered', 1), answered_prev: line(main, 'Answered', 2),
          median_n: line(wait, 'Answered calls', 1), median_n_prev: line(wait, 'Answered calls', 2),
          median: line(wait, 'Median wait', 1), median_prev: line(wait, 'Median wait', 2),
          median_note: wait.note || '',
        },
        hours: bars.labels.map((label, i) => ({
          label, calls: line(bars.details[i], 'Calls', 1), answered: line(bars.details[i], 'Answered', 1),
        })),
        months,
        months_note: `${series.labels[0]} to ${series.labels[series.labels.length - 1]}`,
        shows: text.shows,
        action: text.action,
        charts: {
          hours: { categories: bars.labels, series: [{ name: 'Calls', values: view('calls').values, format: 'int' }] },
          hours_rate: { categories: bars.labels, series: [{ name: 'Answered %', values: view('answered').values, format: 'pct1' }] },
          months_calls: { categories: series.labels, status: series.status, series: [{ name: 'Calls', values: series.views['All|calls'].values, format: 'int' }] },
          months_rate: { categories: series.labels, status: series.status, target, series: [{ name: 'Answered while staffed %', values: series.views['All|rate'].values, format: 'pct1' }] },
        },
      };
    },
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = REPORTS;
  else root.FourthSheetReports = REPORTS;
}(typeof self !== 'undefined' ? self : this));
