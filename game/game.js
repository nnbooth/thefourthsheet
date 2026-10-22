/*
  game.js — "The Month-End Run" (The Fourth Sheet)

  A ~30-second story game on a 256x144 canvas (16:9). Its one job: show a
  business owner the month-end grind, then the same month with properly built
  reporting that's built once and refreshed on a schedule, then the numbers, then a call to action.

  STORY (states, in order)
    title    Title + "Month-end. 40 hours of copy-paste." (held)
    howto    One screen: how to play + pick a character (playable only)
    before   The three levels done BY HAND: scattered data to copy-paste,
             rogue invoices slipping past, overtime clocks multiplying
    switch   Reporting gets built (the Σ cell) and the sheet tidies itself
    after    The same three levels again: data pulls itself in, invoices
             get caught, each report publishes itself
    summary  Month-end report card (all numbers from CONFIG below)
    end      Call to action: book a call / play again

  Levels = the three reports on the site: A Sales, B Purchasing,
  C Payroll & overtime. Nobody "dies": clocks make you stumble, that's all.

  URL OPTIONS
    ?demo=1             plays the whole story by itself (scripted inputs,
                        seeded randomness: identical every time)
    ?demo=1&capture=1   same, but frozen until tools/archive/record_demo.py steps
                        it frame by frame (see window.__game at the bottom)
    ?embed=1            set by the website when the game runs in its iframe

  KEY LOCATIONS
    Numbers, names and links ....... CONFIG (just below)
    Level layout ................... LEVELS
    Colours ........................ PAL
    Story beats / timings .......... TIMING, and the start*() functions
    Summary screen ................. drawSummary()
    End card ....................... drawEnd() (+ END_BUTTONS for the clickable areas)
    Demo autopilot ................. autopilot()
*/

(() => {
  'use strict';

  /* ================================================================ CONFIG
     Everything the summary and end card say comes from here. Change a
     number, reload, done. All money is AUD.

     Placeholders: values written like '[[BOOKING_URL]]' are the same tokens as
     the website (see the project notes in OneDrive). Until you replace them, the game
     shows the fallback noted beside each one, so it never displays
     raw [[TOKENS]].                                                       */
  const CONFIG = {
    // --- Story ---
    manualHours: 40,            // opening line: "Month-end. 40 hours of copy-paste."
    monthLabel: 'October 2026', // summary heading
    daysToClose: '[[DAYS]]',    // "month-end done in N days". Fallback: 3

    // --- The month's numbers (ASSUMPTIONS: shown on the summary) ---
    hoursSaved: 32,             // hours of manual work automation takes off your plate this month
    hourlyRateAUD: 85,          // what an hour of that work costs you (stated as an assumption on screen)
    setupCostAUD: 1500,         // one-off build cost (illustrative). Keep in line with the real setup fee (PRICES.setup in script.js)
    runningCostAUD: 120,        // monthly running cost (software/hosting)
    weeksInMonth: 4,            // used for "Paid for itself in week N"

    // --- People and links ---
    name: 'Nathan Booth',       // end card "Nathan Booth" + "The Fourth Sheet". "CPA" is not shown until confirmed.
    bookingUrl: '[[BOOKING_URL]]', // "Book a free 20-min data check". Fallback: the website's Contact section
    domain: 'www.thefourthsheet.com.au', // shown as text on the end card
  };

  // Fallbacks used while a CONFIG value is still a [[TOKEN]]
  const FALLBACK = {
    daysToClose: 3,
    bookingUrl: '../#contact',
    domain: 'www.thefourthsheet.com.au',
  };

  // True for '' or anything still written like [[TOKEN]]
  const unfilled = v => v == null || (typeof v === 'string' && (/^\s*\[\[.*\]\]\s*$/.test(v) || !v.trim()));
  const cfg = (key, fallback) => (unfilled(CONFIG[key]) ? fallback : CONFIG[key]);

  // AUD with thousands separators: 1500 -> "$1,500", -120 -> "-$120"
  const aud = n => (n < 0 ? '-' : '') + '$' + Math.abs(Math.round(n)).toLocaleString('en-AU');

  // The month's money, all derived from CONFIG. Cash only: nothing here
  // is pipeline or "potential" revenue.
  function money() {
    const value = CONFIG.hoursSaved * CONFIG.hourlyRateAUD;
    const costs = CONFIG.setupCostAUD + CONFIG.runningCostAUD;
    const weekly = value / CONFIG.weeksInMonth;
    return {
      value, costs, net: value - costs,
      // First week in which cumulative savings cover setup + running cost
      paybackWeek: weekly > 0 ? Math.max(1, Math.ceil(costs / weekly)) : null,
    };
  }

  /* ================================================================ SETUP */

  const canvas = document.getElementById('game-canvas');
  if (!canvas) return;

  const params = new URLSearchParams(location.search);
  const DEMO = params.has('demo');
  const CAPTURE = DEMO && params.has('capture');
  const EMBED = params.has('embed') || window.self !== window.top;
  // Reduced motion: the game offers to go straight to the (static) results.
  const REDUCED = !DEMO && window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  const TOUCH = window.matchMedia && matchMedia('(pointer: coarse)').matches;

  const W = 256, H = 144;          // game pixels; drawn at a whole-number scale
  const HUD_H = 28;                // the two-number bar at the top
  const HEAD_Y = 28, HEAD_H = 10;  // column-header row (level signage)
  const GROUND_Y = 128;            // top of the floor
  const LEVEL_W = 256, WORLD_W = LEVEL_W * 3;

  const AUDIO = window.S3Audio || { sfx() {}, music() {}, layer() {}, unlock() {}, toggleMute() { return true; }, muted: true };
  const sfx = name => AUDIO.sfx(name);

  // Everything is drawn into this small buffer, then copied up to the
  // visible canvas at a whole-number scale (crisp pixels, see fit()).
  const view = canvas.getContext('2d');
  const buffer = document.createElement('canvas');
  buffer.width = W; buffer.height = H;
  const ctx = buffer.getContext('2d');
  const FONT_NAME = '"Press Start 2P", monospace';

  // Colours: taken from the website's styles.css so game and site match.
  const PAL = {
    bg: '#f4f7f2', paper: '#fbfdf9', white: '#ffffff', grid: '#dce8dc',
    ink: '#25342a', muted: '#5f6f63', accent: '#2f7a5d', accentDark: '#1f5a43',
    soft: '#eaf6ee', mint: '#cfe3d5', sage: '#9db8a6',
    alert: '#b93a3a', amber: '#d9922b', amberDark: '#8a5410', cream: '#fff4dc',
    // "Before" (by hand): a duller, messier sheet
    messBg: '#efebe2', messGrid: '#ddd5c4', messHead: '#e4dccb',
    sticky: ['#f3e3a0', '#f2c7b8', '#cfe0f0', '#e2d4f0'],
  };

  // Seeded random numbers (mulberry32) so the demo is identical every run.
  let seed = 1;
  const rand = () => {
    seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };

  /* ================================================================ TEXT
     Press Start 2P is a pixel font: every character is exactly `size`
     pixels wide. We only use sizes 8 and 16 so it stays crisp. Every
     piece of text goes through wrap()/fitText(), so nothing can run off
     the screen: lines wrap, and big text drops to 8px if it won't fit.  */

  function setFont(size) { ctx.font = `${size}px ${FONT_NAME}`; }
  function textW(str, size) { setFont(size); return ctx.measureText(str).width; }

  function wrap(str, maxW, size) {
    const lines = [];
    let line = '';
    for (const word of String(str).split(' ')) {
      const tryLine = line ? line + ' ' + word : word;
      if (textW(tryLine, size) <= maxW) { line = tryLine; continue; }
      if (line) lines.push(line);
      line = word;
      // A single word wider than the space: split it by characters
      while (textW(line, size) > maxW) {
        let cut = line.length - 1;
        while (cut > 1 && textW(line.slice(0, cut), size) > maxW) cut--;
        lines.push(line.slice(0, cut));
        line = line.slice(cut);
      }
    }
    if (line) lines.push(line);
    return lines;
  }

  // Largest size (16, then 8) whose wrapped lines fit in maxLines
  function fitText(str, maxW, maxLines, sizes = [16, 8]) {
    for (const size of sizes) {
      const lines = wrap(str, maxW, size);
      if (lines.length <= maxLines) return { size, lines };
    }
    const size = sizes[sizes.length - 1];
    return { size, lines: wrap(str, maxW, size) };
  }

  // TEXT AUDIT (capture mode only): every text and every covering box
  // (banner, popup, panel) drawn this frame, in order. tools/archive/record_demo.py
  // checks each frame for text that runs off screen, overlaps other text,
  // or is partly hidden behind a box. See auditFrame().
  const AUDIT = CAPTURE ? [] : null;
  const cover = (x, y, w, h) => { if (AUDIT) AUDIT.push({ kind: 'cover', x, y, w, h }); };

  function text(str, x, y, color = PAL.ink, size = 8, align = 'left') {
    setFont(size);
    if (AUDIT) {
      const w = ctx.measureText(str).width;
      const left = align === 'center' ? x - w / 2 : align === 'right' ? x - w : x;
      AUDIT.push({ kind: 'text', str, x: Math.round(left), y: Math.round(y), w: Math.round(w), h: size });
    }
    ctx.fillStyle = color;
    ctx.textBaseline = 'top';
    ctx.textAlign = align;
    ctx.fillText(str, Math.round(x), Math.round(y));
    ctx.textAlign = 'left';
  }

  const rect = (x, y, w, h, col) => { ctx.fillStyle = col; ctx.fillRect(Math.round(x), Math.round(y), w, h); };
  function box(x, y, w, h, fill, border) {
    rect(x, y, w, h, border);
    rect(x + 1, y + 1, w - 2, h - 2, fill);
  }

  // Blend two #rrggbb colours (t = 0..1). Used while the sheet tidies itself.
  const hexRgb = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
  function mix(a, b, t) {
    if (t <= 0) return a;
    if (t >= 1) return b;
    const A = hexRgb(a), B = hexRgb(b);
    return `rgb(${A.map((v, i) => Math.round(v + (B[i] - v) * t)).join(',')})`;
  }

  /* ================================================================ SPRITES
     Pixel maps: one string per row, one character per pixel, '.' is
     transparent. Each map's letters are coloured by the palette passed
     to sprite(). All original artwork.                                   */

  function sprite(rows, map) {
    const w = Math.max(...rows.map(r => r.length));
    const c = document.createElement('canvas');
    c.width = w; c.height = rows.length;
    const g = c.getContext('2d');
    rows.forEach((row, y) => {
      for (let x = 0; x < row.length; x++) {
        const col = map[row[x]];
        if (col) { g.fillStyle = col; g.fillRect(x, y, 1, 1); }
      }
    });
    return c;
  }

  function flipped(src) {
    const c = document.createElement('canvas');
    c.width = src.width; c.height = src.height;
    const g = c.getContext('2d');
    g.translate(src.width, 0); g.scale(-1, 1); g.drawImage(src, 0, 0);
    return c;
  }

  // The cast: five office workers (16x16). Heads...
  const HEADS = {
    glasses: ['.....hhhhhh.....', '...hhhhhhhhhh...', '..hhhhhhhhhhhh..', '..hhhsssssssh...', '..hhkkkkskkkk...', '..hsklllkklllk..', '..hSkkkkskkkks..', '...ssssssSsss...', '....sssskkss....'],
    puff:    ['....hhhhhhh.....', '...hhhhhhhhh....', '..hhhhhhhhhhh...', '..hhhhhhhhhhh...', '..hhhsssssssh...', '..hhssksssksS...', '..hySsssssssS...', '...ssssssSss....', '....sssrrss.....'],
    hijab:   ['.....hhhhhh.....', '...hhhhhhhhhh...', '..hhhhhhhhhhhh..', '..hhhhsssssshh..', '..hhhssksssksh..', '..hhhsssssssSh..', '..hhhsSssssSsh..', '..hhhhsssrrshh..', '..hhhhhhhhhhhh..'],
    swoop:   ['......hhhhhh....', '....hhhhhhhhhh..', '...hhhhhhhhhhhh.', '..HHHhsssssss...', '..HHssksssksS...', '..HHsssssssss...', '..HSysssssSss...', '...ssssssSss....', '....sssskss.....'],
    chair:   ['.....hhhhhh.....', '....hhhhhhhh....', '...hhhhhhhhhh...', '...hhsssssssh...', '...hkkkkskkkk...', '...sklllkklllk..', '...sSkkkskkkks..', '....sssssSss....', '.....sssskss....'],
  };
  // ...and bodies (standing, two running frames, jumping)
  const BODY = {
    stand: ['.....wwbbww.....', '....wwwwwwww....', '...swwwwwwwws...', '....wwwwwwww....', '....tttttttt....', '....ttt..ttt....', '...oooo..oooo...'],
    run1:  ['.....wwbbww.....', '...swwwwwwww....', '....wwwwwwwwws..', '....wwwwwwww....', '...tttttttttt...', '..ttt......ttt..', '.ooo........ooo.'],
    run2:  ['.....wwbbww.....', '....wwwwwwww....', '....swwwwwws....', '....wwwwwwww....', '.....tttttt.....', '......tttt......', '.....ooooo......'],
    jump:  ['.....wwbbww.sss.', '....wwwwwwwws...', '...swwwwwwww....', '....wwwwwwww....', '...ttttttttt....', '..ttt....ttt....', '..oo......ooo...'],
  };
  // Seated in a wheelchair (wheel spokes turn between run frames)
  const CHAIR_BODY = {
    stand: ['.kk..wwbbww.....', '..k.ggggwwwws...', '..kgwwGwgwwss...', '..kgttGGgtttt...', '..kgtGttg...tt..', '..kgGtttg..ktt..', '...kggggk.kkooo.'],
    run1:  ['.kk..wwbbww.....', '..k.ggggwwwws...', '..kgwGwwgwwss...', '..kgttGGgtttt...', '..kgtttGg...tt..', '..kgtttGg..ktt..', '...kggggk.kkooo.'],
    run2:  ['.kk..wwbbww.....', '..k.ggggwwwws...', '..kgGwwwgwwss...', '..kgGGGGgtttt...', '..kgttttg...tt..', '..kgtttGg..ktt..', '...kggggk.kkooo.'],
    jump:  ['.kk..wwbbww.ss..', '..k.ggggwwwws...', '..kgwwGwgwww....', '..kgttGGgtttt...', '..kgtGttg...tt..', '..kgGtttg..ktt..', '...kggggk.kkooo.'],
  };

  // Skin tones light to deep; glasses / no glasses; a hijab; a
  // non-binary character; a wheelchair user. Shirts in the site palette.
  const CAST = {
    sam:   { head: HEADS.glasses, hair: '#5c3a1a', skin: '#f2c4a8', shadeSkin: '#d99b78', shirt: PAL.white, shade: PAL.mint },
    ade:   { head: HEADS.puff,    hair: '#201008', skin: '#7c4a2c', shadeSkin: '#5c3018', shirt: PAL.accent, shade: PAL.accentDark },
    noor:  { head: HEADS.hijab,   hair: '#3f6b55', skin: '#b87050', shadeSkin: '#8c4c30', shirt: '#e8b931', shade: '#b88a17' },
    rio:   { head: HEADS.swoop,   hair: '#b8a0f8', hairShaved: '#5c4c7c', skin: '#fcc8a0', shadeSkin: '#e0a07c', shirt: PAL.ink, shade: '#101a14' },
    kai:   { head: HEADS.chair,   hair: '#101010', skin: '#9c5c38', shadeSkin: '#744024', shirt: PAL.sage, shade: '#6f8f7a', body: CHAIR_BODY },
  };
  const ROSTER = Object.keys(CAST);

  const PLAYER = {};
  for (const [id, ch] of Object.entries(CAST)) {
    const map = {
      h: ch.hair, H: ch.hairShaved || ch.hair, s: ch.skin, S: ch.shadeSkin, y: '#e8b931',
      k: PAL.ink, l: PAL.soft, r: '#b5523f', w: ch.shirt, b: ch.shade, t: '#3a4a40', o: PAL.ink,
      g: PAL.muted, G: PAL.ink,
    };
    PLAYER[id] = {};
    for (const f of Object.keys(BODY)) {
      const r = sprite([...ch.head, ...(ch.body || BODY)[f]], map);
      PLAYER[id][f] = { r, l: flipped(r) };
    }
  }

  // Overtime clock (enemy, Payroll & overtime level). Legs alternate.
  const CLOCK_TOP = ['....rrrrrrrr....', '..rrwwwwwwwwrr..', '.rwwwwwkwwwwwwr.', '.rwwwwwkwwwwwwr.', 'rwwwwwwkwwwwwwwr', 'rwwwwwwkwwwwwwwr', 'rwwwwwwkkkkkwwwr', 'rwwwwwwwwwwwwwwr', 'rwwkkwwwwwwkkwwr', '.rwwwkwwwwkwwwr.', '.rwwwwwwwwwwwwr.', '..rrwwwwwwwwrr..', '....rrrrrrrr....'];
  const CLOCK_MAP = { r: PAL.amberDark, w: PAL.cream, k: PAL.ink };
  const CLOCK = [
    sprite([...CLOCK_TOP, '...kk......kk...', '..kkkk....kkkk..', '..kkkk....kkkk..'], CLOCK_MAP),
    sprite([...CLOCK_TOP, '....kk....kk....', '...kkkk..kkkk...', '...kkkk..kkkk...'], CLOCK_MAP),
  ];

  // Rogue invoice (enemy, Purchasing level): an overcharge with legs.
  const INVOICE_TOP = ['..kkkkkkkkkk....', '..kwwwwwwwwwk...', '..kwkkwwkkwwwk..', '..kwwkwwkwwwwwk.', '..kwwwwwwwwwwwk.', '..kwbbbbbbbbwwk.', '..kwwwwwwwwwwwk.', '..kwbbbbbbwwwwk.', '..kwwwwwwwwwwwk.', '..kwwwwrrrwwwwk.', '..kwwwwrwwwwwwk.', '..kwwwwrrrwwwwk.', '..kwwwwwwrwwwwk.', '..kwwwwrrrwwwwk.', '..kkkkkkkkkkkkk.'];
  const INVOICE_MAP = { k: PAL.ink, w: PAL.white, b: PAL.sage, r: PAL.alert };
  const INVOICE = [
    sprite([...INVOICE_TOP, '...kk......kk...'], INVOICE_MAP),
    sprite([...INVOICE_TOP, '....kk....kk....'], INVOICE_MAP),
  ];

  // Σ "automation" cell: the switch from by-hand to built-for-you
  const SIGMA = sprite([
    'kkkkkkkkkkkkkkkk', 'kaaaaaaaaaaaaaak', 'kaaaaaaaaaaaaaak', 'kaaawwwwwwwaaaak', 'kaaawwaaaaaaaaak',
    'kaaaawwaaaaaaaak', 'kaaaaawwaaaaaaak', 'kaaaaaawwaaaaaak', 'kaaaaawwaaaaaaak', 'kaaaawwaaaaaaaak',
    'kaaawwaaaaaaaaak', 'kaaawwwwwwwaaaak', 'kaaaaaaaaaaaaaak', 'kaaaaaaaaaaaaaak', 'kddddddddddddddk', 'kkkkkkkkkkkkkkkk',
  ], { k: PAL.ink, a: PAL.accent, d: PAL.accentDark, w: PAL.white });

  // Small Σ helper that follows the player once reporting is built
  const HELPER = sprite([
    '.kkkkkkkk.', 'kaaaaaaaak', 'kawwwwwaak', 'kaawaaaaak', 'kaaawaaaak',
    'kaawaaaaak', 'kawwwwwaak', 'kaaaaaaaak', '.kkkkkkkk.',
  ], { k: PAL.ink, a: PAL.accent, w: PAL.white });

  // Tick (the font has no ✓, so it's a sprite)
  const TICK_ROWS = ['......kk', '.....kk.', 'kk..kk..', '.kkkk...', '..kk....'];
  const TICK = sprite(TICK_ROWS, { k: PAL.accent });
  const TICK_W = sprite(TICK_ROWS, { k: PAL.white });

  /* ================================================================ LEVELS
     One sheet, three columns: A Sales, B Purchasing, C Payroll & overtime.
     Each level is one screen wide (256px). x values are measured from the
     start of that level; y is the top edge (the floor is at y=128).
       platforms  [x, y, width]   ledger cells you can stand on (from above)
       cells      [x, y]          data to copy-paste by hand / pull in
       invoices   [x, delay]      rogue invoices walking in from the right
       clocks     [x]             overtime clocks (they multiply)
       clutter    [text, x, y]    mess in the "before" sheet               */
  const LEVELS = [
    {
      key: 'A', name: 'SALES', problem: 'ORDERS, CANCELLATIONS, PIPELINE',
      platforms: [[64, 104, 48], [160, 104, 48]],
      cells: [[30, 114], [84, 92], [128, 114], [176, 92], [212, 114]],
      invoices: [], clocks: [],
      clutter: [['#REF!', 22, 46], ['COPY (3)', 132, 58]],
    },
    {
      key: 'B', name: 'PURCHASING', problem: 'LATE SUPPLIERS, COST CHANGES',
      platforms: [[96, 104, 48]],
      cells: [[40, 114], [116, 92], [186, 114]],
      invoices: [[200, 10], [230, 70], [250, 125]],
      clocks: [],
      clutter: [['V7_FINAL', 30, 58], ['#N/A', 176, 46]],
    },
    {
      key: 'C', name: 'PAYROLL & OVERTIME', problem: 'OVERTIME, LABOUR COST, STAFFING',
      platforms: [[112, 104, 48]],
      cells: [[44, 114], [132, 92], [196, 114]],
      invoices: [],
      clocks: [[118], [190]],
      clutter: [['SEE EMAIL', 16, 46], ['#DIV/0!', 150, 58]],
    },
  ];
  const DOC_X = 222; // the report at the end of each level

  // How many things automation handles in the "after" run. Hours saved
  // accrue as each one is done, so the HUD lands exactly on CONFIG.
  const UNITS = LEVELS.reduce((n, l) => n + l.cells.length + l.invoices.length, 0);

  /* ================================================================ TIMING (60 ticks = 1 second) */
  const TIMING = {
    titleHold: 210,      // demo: opening title + line held 3.5s
    switchLen: 180,      // the switch: 3s
    summaryMin: 300,     // summary can't be skipped for 5s
    summaryDemo: 330,    // demo moves on after 5.5s
    summaryAuto: 540,    // playable moves on by itself after 9s
    countUp: 40,         // summary numbers count up in 0.67s (spec: under 1s)
    walkBefore: 2.0,     // by hand: slower...
    runAfter: 3.2,       // ...automated: quicker
    grabPause: 10,       // copy-paste stops you for a moment
  };

  /* ================================================================ STATE */

  let state = 'title';
  let stateT = 0;          // ticks since entering the state
  let tick = 0;            // ticks since the page loaded (never reset)
  let paused = false;
  const marks = {};        // tick at each story beat (read by the recorder)
  const mark = name => { marks[name] = tick; };

  let mode = 'before';     // which version of the sheet we're in
  let tidy = 0;            // 0 = messy (before) .. 1 = tidy (after)
  let camX = 0;
  let player, cells, invoices, clocks, docs, popups, banner, sigma;
  let level = -1;          // level the player is in (0..2)
  let units = 0;           // things automation has handled so far
  let paidBack = false, clockTimer = 0, clockWarned = false;
  let showHud = false, hudLive = false;
  let summaryReveal = 0;

  let character = 'sam';
  try { const saved = localStorage.getItem('s3-character'); if (CAST[saved]) character = saved; } catch (e) { /* storage blocked */ }

  const levelX = i => i * LEVEL_W;
  const hoursNow = () => Math.round(CONFIG.hoursSaved * units / UNITS);
  const netNow = () => hoursNow() * CONFIG.hourlyRateAUD - CONFIG.setupCostAUD - CONFIG.runningCostAUD;

  function enter(next) {
    state = next; stateT = 0;
    mark(next);
    updateDom();
  }

  /* ---------------------------------------------------------------- world setup */

  function buildWorld(newMode) {
    mode = newMode;
    tidy = newMode === 'after' ? 1 : 0;
    seed = 20261031; // same randomness every run (demo recordings repeat exactly)
    cells = []; invoices = []; clocks = []; docs = [];
    LEVELS.forEach((L, i) => {
      const x0 = levelX(i);
      for (const [x, y] of L.cells) {
        // Messy position: knocked a little off the grid, on a sticky-note colour
        const mx = x0 + x + Math.round(rand() * 8 - 4), my = y + Math.round(rand() * 6 - 3);
        // Tidy position: snapped to the sheet's cells
        const tx = x0 + Math.round(x / 16) * 16 + 2, ty = Math.round(y / 8) * 8 + 1;
        cells.push({ lvl: i, mx, my, tx, ty, x: mx, y: my, w: 12, h: 8, colour: PAL.sticky[Math.floor(rand() * 4)], state: 'idle', t: 0 });
      }
      for (const [x, delay] of L.invoices) invoices.push({ lvl: i, sx: x0 + x, delay, x: 0, y: GROUND_Y - 16, state: 'waiting', t: 0, anim: 0 });
      if (newMode === 'before') for (const [x] of L.clocks) clocks.push({ lvl: i, x: x0 + x, y: GROUND_Y - 16, vx: -0.5, anim: rand() * 4 });
      docs.push({ lvl: i, x: x0 + DOC_X, done: false });
    });
    if (newMode === 'after') for (const c of cells) { c.x = c.tx; c.y = c.ty; }
    popups = []; banner = null;
    level = -1; camX = 0; clockTimer = 0; clockWarned = false;
    player = {
      x: 12, y: GROUND_Y - 16, w: 10, h: 16, vx: 0, vy: 0, onGround: true, facing: 1,
      anim: 0, coyote: 0, jumpBuf: 0, busy: 0, hurt: 0, knock: 0, hidden: false,
    };
  }

  /* ---------------------------------------------------------------- story beats */

  function startTitle() { buildWorld('before'); showHud = false; enter('title'); }
  function startHowto() { enter('howto'); }

  function startBefore() {
    sfx('start');
    buildWorld('before');
    units = 0; paidBack = false; showHud = true; hudLive = false;
    enter('before');
  }

  function startSwitch() {
    player.vx = 0;
    sigma = { x: camX + 128 - 8, y: HUD_H - 16, vy: 0, landed: false };
    enter('switch');
  }

  function startAfter() {
    buildWorld('after');
    player.x = 12;
    enter('after');
  }

  function startSummary() {
    units = UNITS;
    showHud = false;
    summaryReveal = 0;
    banner = null;
    enter('summary');
    announceSummary();
  }

  function startEnd() { enter('end'); }

  /* ================================================================ UPDATE */

  const keys = { left: false, right: false, jump: false };
  let prevJump = false;
  const tapped = { jump: false };

  function update() {
    tick++; stateT++;
    if (DEMO) autopilot();
    const jumpPressed = (keys.jump && !prevJump) || tapped.jump;
    prevJump = keys.jump; tapped.jump = false;

    if (state === 'title' && DEMO && stateT >= TIMING.titleHold) startBefore();
    else if (state === 'before' || state === 'after') updatePlay(jumpPressed);
    else if (state === 'switch') updateSwitch();
    else if (state === 'summary') {
      const limit = DEMO ? TIMING.summaryDemo : TIMING.summaryAuto;
      if (stateT >= limit) startEnd();
    }

    for (const p of popups) { p.t--; if (!p.screen && !REDUCED) p.y -= 0.35; }
    popups = popups.filter(p => p.t > 0);
    if (banner && tick >= banner.until) banner = null;

    // Soundtrack (only if the visitor has turned sound on)
    AUDIO.music(!AUDIO.muted && !document.hidden && !paused && state !== 'summary' && state !== 'end');
    AUDIO.layer(state === 'after');
  }

  function popup(textStr, x, y, color = PAL.ink, t = 60, screen = false) {
    // The same message twice at once (two invoices slipping past) just refreshes it
    const same = popups.find(p => p.text === textStr);
    if (same) { same.t = t; return; }
    popups.push({ text: textStr, x, y, color, t, screen });
  }

  function showBanner(lines, frames, y = HEAD_Y + HEAD_H + 4) {
    banner = { lines, until: tick + frames, y };
  }

  /* ---------------------------------------------------------------- playing (before + after) */

  function updatePlay(jumpPressed) {
    const p = player;
    const speed = mode === 'before' ? TIMING.walkBefore : TIMING.runAfter;

    // Movement: walk while a direction is held. Copy-pasting (busy) and
    // stumbling (knock) take control away for a moment.
    if (p.busy > 0) { p.busy--; p.vx = 0; }
    else if (p.knock > 0) { p.knock--; p.vx = -1.5; }
    else if (keys.left && !keys.right) { p.vx = -speed; p.facing = -1; }
    else if (keys.right && !keys.left) { p.vx = speed; p.facing = 1; }
    else p.vx = 0;
    if (p.hurt > 0) p.hurt--;

    // Forgiving jumps: a press just before landing still counts, and you
    // can still jump just after walking off an edge.
    if (jumpPressed) p.jumpBuf = 8; else if (p.jumpBuf > 0) p.jumpBuf--;
    if (p.onGround) p.coyote = 7; else if (p.coyote > 0) p.coyote--;
    if (p.jumpBuf > 0 && (p.onGround || p.coyote > 0) && p.vy >= 0 && p.busy === 0) {
      p.vy = -5; p.jumpBuf = 0; p.coyote = 0; p.onGround = false;
      sfx('jump');
    }

    // Physics: gravity, then the floor and one-way ledger platforms
    p.x = Math.max(0, Math.min(WORLD_W - p.w, p.x + p.vx));
    const prevBottom = p.y + p.h;
    p.vy = Math.min(5, p.vy + 0.3);
    p.y += p.vy;
    p.onGround = false;
    if (p.vy >= 0) {
      if (p.y + p.h >= GROUND_Y) { p.y = GROUND_Y - p.h; p.vy = 0; p.onGround = true; }
      else {
        for (const [x, y, w] of platformsAll()) {
          if (prevBottom <= y && p.y + p.h >= y && p.x + p.w > x && p.x < x + w) {
            p.y = y - p.h; p.vy = 0; p.onGround = true; break;
          }
        }
      }
    }
    p.anim += Math.abs(p.vx) * 0.08;

    camX = Math.round(Math.max(0, Math.min(WORLD_W - W, p.x + 5 - 100)));

    // Entering a new level: put its name and problem up
    const lv = Math.max(0, Math.min(2, Math.floor((p.x + 5) / LEVEL_W)));
    if (lv !== level) {
      level = lv;
      const L = LEVELS[lv];
      mark(`${mode}${lv}`);
      if (mode === 'before') {
        // (the level name is always in the header row above)
        showBanner([{ t: 'DOING IT BY HAND', c: PAL.alert }, { t: L.problem, c: PAL.ink }], 110);
      } else {
        showBanner([{ t: `${L.key} · ${L.name}`, c: PAL.accent }, { t: L.problem, c: PAL.muted }], 75);
      }
    }

    updateCells();
    updateInvoices();
    if (mode === 'before') updateClocks();
    updateDocs();

    // End of the sheet
    if (p.x >= WORLD_W - 20) {
      if (mode === 'before') startSwitch();
      else { finishAll(); startSummary(); }
    }
  }

  function platformsAll() {
    const out = [];
    LEVELS.forEach((L, i) => { for (const [x, y, w] of L.platforms) out.push([levelX(i) + x, y, w]); });
    return out;
  }
  const overlap = (a, b) => a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;

  function updateCells() {
    const p = player;
    for (const c of cells) {
      if (mode === 'before') {
        // By hand: touch a cell to copy-paste it. It stops you briefly.
        if (c.state === 'idle' && overlap(p, c)) {
          c.state = 'done';
          p.busy = TIMING.grabPause;
          popup('COPY-PASTE', c.x - 14, Math.min(c.y, GROUND_Y - 16) - 20, PAL.muted, 40); // above head height
          sfx('grab');
        }
      } else {
        // Automated: cells ahead of you pull themselves into the report
        if (c.state === 'idle' && c.x < p.x + 72) startPull(c);
        if (c.state === 'fly') {
          c.t++;
          const k = Math.min(1, c.t / 18);
          const tx = camX + 30, ty = 6; // the HOURS SAVED number in the HUD
          c.x = c.fx + (tx - c.fx) * k;
          c.y = c.fy + (ty - c.fy) * k - Math.sin(k * Math.PI) * 18;
          if (k >= 1) { c.state = 'done'; addUnit(); }
        }
      }
    }
  }

  function startPull(c) {
    c.state = 'fly'; c.t = 0; c.fx = c.x; c.fy = c.y;
    sfx('pull');
  }

  function addUnit() {
    units = Math.min(UNITS, units + 1);
    if (!paidBack && hudLive && netNow() >= 0) {
      paidBack = true;
      popup('PAID FOR ITSELF', W - 8 - textW('PAID FOR ITSELF', 8), HEAD_Y + HEAD_H + 2, PAL.accent, 90, true);
      sfx('publish');
    }
  }

  function updateInvoices() {
    const p = player;
    for (const v of invoices) {
      if (v.state === 'waiting') {
        // Starts walking in once you reach its level
        if (p.x + 5 >= levelX(v.lvl) - 16) { v.t++; if (v.t >= v.delay) { v.state = 'walk'; v.x = Math.max(v.sx, camX + W + 4); } }
        continue;
      }
      if (v.state === 'walk') {
        v.x -= 1.1; v.anim += 0.08;
        if (mode === 'before') {
          // By hand: it walks straight past you and gets paid
          if (v.x + 16 < camX - 2) {
            v.state = 'gone';
            popup('OVERCHARGE PAID', camX + 4, 84, PAL.alert, 70);
            sfx('slip');
          }
        } else if (v.x < p.x + 110 && v.x < camX + W - 24) {
          // Automated: the reconciliation catches it on sight
          v.state = 'caught'; v.t = 0;
          popup('CAUGHT', v.x - 4, v.y - 12, PAL.accent, 45);
          sfx('caught');
        }
      } else if (v.state === 'caught' && ++v.t >= 24) {
        v.state = 'gone';
        addUnit();
      }
    }
  }

  function updateClocks() {
    const p = player;
    for (const c of clocks) {
      const x0 = levelX(c.lvl);
      c.x += c.vx; c.anim += 0.06;
      if (c.x < x0 + 8 || c.x > x0 + LEVEL_W - 40) c.vx *= -1;
      const hit = { x: c.x + 2, y: c.y + 2, w: 12, h: 14 };
      if (p.hurt === 0 && overlap(p, hit)) {
        if (p.vy > 0 && p.y + p.h - hit.y < 7) { p.vy = -4; } // landed on top: bounce off
        else {
          p.hurt = 40; p.knock = 10;
          popup('+OVERTIME', p.x - 12, p.y - 12, PAL.amberDark, 50);
          sfx('stumble');
        }
      }
    }
    // Overtime multiplies while you're in Payroll & overtime
    if (level === 2 && clocks.length && clocks.length < 6 && ++clockTimer % 70 === 0) {
      const src = clocks[Math.floor(rand() * clocks.length)];
      const dir = rand() < 0.5 ? -1 : 1;
      clocks.push({ lvl: src.lvl, x: Math.max(levelX(2) + 8, Math.min(levelX(2) + LEVEL_W - 40, src.x + dir * 18)), y: src.y, vx: 0.5 * dir, anim: 0 });
      if (!clockWarned) { clockWarned = true; popup('MORE OVERTIME', src.x - 20, src.y - 22, PAL.amberDark, 60); }
    }
  }

  function updateDocs() {
    const p = player;
    for (const d of docs) {
      if (d.done || p.x + 5 < d.x + 6) continue;
      d.done = true;
      if (mode === 'before') {
        popup('STILL A DRAFT', d.x - 30, 96, PAL.alert, 60);
      } else {
        // Anything automation hasn't finished in this level finishes now
        for (const c of cells) if (c.lvl === d.lvl && c.state === 'idle') startPull(c);
        for (const v of invoices) if (v.lvl === d.lvl && (v.state === 'waiting' || v.state === 'walk')) { v.state = 'caught'; v.t = 12; if (v.x === 0) v.x = d.x + 20; }
        popup('PUBLISHED', d.x - 18, 96, PAL.accent, 60);
        sfx('publish');
      }
    }
  }

  // Leaving the sheet early (or skipping): everything counts as done
  function finishAll() {
    units = UNITS;
    for (const c of cells) c.state = 'done';
    for (const v of invoices) v.state = 'gone';
  }

  /* ---------------------------------------------------------------- the switch */

  function updateSwitch() {
    const t = stateT;
    // 1. The Σ cell drops in and lands
    if (!sigma.landed) {
      sigma.vy = Math.min(6, sigma.vy + 0.4);
      sigma.y += sigma.vy;
      if (sigma.y >= GROUND_Y - 16) {
        sigma.y = GROUND_Y - 16; sigma.landed = true; sigma.at = t;
        sfx('build');
        hudLive = true; // costs are in: net saving starts below zero
        showBanner([{ t: 'BUILT ONCE. NO RE-KEYING.', c: PAL.accent, big: true }], TIMING.switchLen - t, 46);
      }
      return;
    }
    // 2. The sheet tidies itself (about 1 second)
    const k = Math.min(1, (t - sigma.at) / 60);
    tidy = k * k * (3 - 2 * k);
    for (const c of cells) if (c.state === 'idle') { c.x = c.mx + (c.tx - c.mx) * tidy; c.y = c.my + (c.ty - c.my) * tidy; }
    // 3. Pan back to the start of the sheet for the "after" run
    if (t >= 110) {
      player.hidden = true;
      const pk = Math.min(1, (t - 110) / 55);
      camX = Math.round((WORLD_W - W) * (1 - pk * pk * (3 - 2 * pk)));
    }
    if (t >= TIMING.switchLen) startAfter();
  }

  /* ---------------------------------------------------------------- demo autopilot
     Scripted inputs for ?demo=1: walk right, jump for data cells that sit
     above head height and over overtime clocks. Depends only on the game
     state (no clocks, no randomness), so every run is identical.         */
  function autopilot() {
    keys.left = false;
    keys.right = state === 'before' || state === 'after';
    keys.jump = false;
    const p = player;
    if (!keys.right || !p.onGround || p.busy > 0) return;
    if (state === 'before') {
      for (const c of clocks) { const d = c.x - (p.x + p.w); if (d > -2 && d < 24) keys.jump = true; }
      for (const c of cells) {
        const d = c.x - p.x;
        if (c.state === 'idle' && c.y + c.h <= p.y + 2 && d > -2 && d < 18) keys.jump = true;
      }
    }
  }

  /* ================================================================ RENDER */

  function render() {
    if (AUDIT) AUDIT.length = 0;
    ctx.imageSmoothingEnabled = false;
    if (state === 'summary') drawSummary();
    else if (state === 'end') drawEnd();
    else {
      drawWorld();
      if (showHud) drawHud(); else drawBrandBar();
      const bannerBox = banner ? drawBanner() : null;
      if (state !== 'title' && state !== 'howto') drawPopups(bannerBox);
      if (state === 'title') drawTitle();
      if (state === 'howto') drawHowto();
    }
    if (paused) drawPaused();

    view.imageSmoothingEnabled = false;
    view.drawImage(buffer, 0, 0, canvas.width, canvas.height);
  }

  // Problems with this frame's text (capture mode). [] means all clear.
  function auditFrame() {
    if (!AUDIT) return [];
    const issues = [];
    const inter = (a, b) => a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
    const inside = (a, b) => a.x >= b.x && a.y >= b.y && a.x + a.w <= b.x + b.w && a.y + a.h <= b.y + b.h;
    AUDIT.forEach((t, i) => {
      if (t.kind !== 'text') return;
      if (t.x < 0 || t.y < 0 || t.x + t.w > W || t.y + t.h > H) issues.push(`off screen: "${t.str}"`);
      for (let j = i + 1; j < AUDIT.length; j++) {
        const o = AUDIT[j];
        if (o.kind === 'cover' && inter(t, o) && !inside(t, o)) issues.push(`partly hidden: "${t.str}"`);
        if (o.kind === 'text' && inter(t, o)) {
          // only a clash if no cover between them hides the first one
          const hidden = AUDIT.slice(i + 1, j).some(c => c.kind === 'cover' && inside(t, c));
          if (!hidden) issues.push(`overlaps: "${t.str}" / "${o.str}"`);
        }
      }
    });
    return [...new Set(issues)];
  }

  /* ---------------------------------------------------------------- the sheet */

  let clutterRects = []; // where the background mess text is this frame (popups avoid it)

  function drawWorld() {
    clutterRects = [];
    const bg = mix(PAL.messBg, PAL.bg, tidy), grid = mix(PAL.messGrid, PAL.grid, tidy);
    rect(0, 0, W, H, bg);

    // Gridlines: the sheet's cells (16 wide x 8 tall)
    ctx.fillStyle = grid;
    for (let x = -(camX % 16); x < W; x += 16) ctx.fillRect(x, HEAD_Y + HEAD_H, 1, GROUND_Y - HEAD_Y - HEAD_H);
    for (let y = HEAD_Y + HEAD_H; y < GROUND_Y; y += 8) ctx.fillRect(0, y, W, 1);

    // Mess in the "before" sheet (fades out as it tidies)
    if (tidy < 1 && !banner) { // hidden while a banner is up, so nothing peeks out from behind it
      ctx.globalAlpha = 1 - tidy;
      LEVELS.forEach((L, i) => {
        for (const [str, x, y] of L.clutter) {
          const sx = levelX(i) + x - camX;
          const w = textW(str, 8);
          if (sx >= 2 && sx + w <= W - 2) { text(str, sx, y, '#b07a6a'); clutterRects.push({ x: sx - 2, y: y - 2, w: w + 4, h: 12 }); } // whole words only
        }
      });
      ctx.globalAlpha = 1;
    }

    drawHeaderRow();

    // Floor: two rows of ledger cells
    const edge = mix(PAL.muted, PAL.accent, tidy);
    rect(0, GROUND_Y, W, H - GROUND_Y, PAL.paper);
    ctx.fillStyle = grid;
    for (let x = -(camX % 16); x < W; x += 16) ctx.fillRect(x, GROUND_Y, 1, H - GROUND_Y);
    ctx.fillRect(0, GROUND_Y + 8, W, 1);
    rect(0, GROUND_Y, W, 2, edge);

    // Platforms: rows of cells you can stand on
    for (const [x, y, w] of platformsAll()) {
      const sx = x - camX;
      if (sx + w < 0 || sx > W) continue;
      box(sx, y, w, 8, PAL.paper, mix(PAL.muted, PAL.ink, tidy));
      for (let cx = 16; cx < w; cx += 16) rect(sx + cx, y + 1, 1, 6, grid);
      rect(sx + 1, y + 1, w - 2, 1, edge);
    }

    for (const d of docs) drawDoc(d);
    for (const c of cells) drawCell(c);
    for (const v of invoices) drawInvoice(v);
    if (state === 'switch') drawSwitchClocks(); else for (const c of clocks) drawClock(c.x, c.y, c.anim, 1);

    if (state === 'switch' && sigma) {
      if (!player.hidden) ctx.drawImage(SIGMA, Math.round(sigma.x - camX), Math.round(sigma.y));
    }
    drawPlayer();

  }

  // Column headers = level signage: "A · SALES" over the whole level
  function drawHeaderRow() {
    rect(0, HEAD_Y, W, HEAD_H, mix(PAL.messHead, PAL.soft, tidy));
    rect(0, HEAD_Y + HEAD_H - 1, W, 1, mix(PAL.messGrid, PAL.sage, tidy));
    const here = Math.max(0, level);
    LEVELS.forEach((L, i) => {
      const x0 = levelX(i) - camX;
      if (x0 > W || x0 + LEVEL_W < 0) return;
      rect(x0, HEAD_Y, 1, HEAD_H, mix(PAL.messGrid, PAL.sage, tidy));
      const label = `${L.key} · ${L.name}`;
      const w = textW(label, 8);
      // Centred over its column and slid to stay fully on screen. Another
      // column's label only shows if it fits in that column's visible part;
      // the level you're in is always labelled.
      const lo = Math.max(x0 + 4, 4);
      const hi = i === here ? W - w - 4 : Math.min(x0 + LEVEL_W - w - 4, W - w - 4);
      if (hi < lo) return;
      text(label, Math.max(lo, Math.min(hi, x0 + (LEVEL_W - w) / 2)), HEAD_Y + 1, mix(PAL.muted, PAL.accent, tidy));
    });
  }

  function drawCell(c) {
    if (c.state === 'done') return;
    const sx = Math.round(c.x - camX), y = Math.round(c.y);
    if (sx < -16 || sx > W) return;
    const fill = tidy >= 1 ? PAL.mint : c.colour;
    box(sx, y, 12, 8, fill, tidy >= 1 ? PAL.accent : PAL.muted);
    // two little rows of "figures"
    rect(sx + 2, y + 2, 6, 1, PAL.ink);
    rect(sx + 2, y + 5, 8, 1, PAL.ink);
  }

  function drawInvoice(v) {
    if (v.state === 'waiting' || v.state === 'gone') return;
    const sx = Math.round(v.x - camX);
    if (sx < -16 || sx > W) return;
    ctx.drawImage(INVOICE[Math.floor(v.anim * 4) % 2], sx, v.y);
    if (v.state === 'caught') {
      // a green reconciliation bracket closes on it, then a tick
      const k = Math.min(1, v.t / 10);
      ctx.strokeStyle = PAL.accent; ctx.lineWidth = 2;
      const pad = Math.round(8 * (1 - k));
      ctx.strokeRect(sx + 1 - pad, v.y - 1 - pad, 16 + pad * 2, 18 + pad * 2);
      if (k >= 1) { rect(sx + 3, v.y + 4, 11, 8, PAL.accent); ctx.drawImage(TICK_W, sx + 5, v.y + 6); }
    }
  }

  function drawClock(x, y, anim, scale) {
    const sx = Math.round(x - camX);
    if (sx < -16 || sx > W) return;
    const img = CLOCK[Math.floor(anim * 4) % 2];
    if (scale >= 1) ctx.drawImage(img, sx, y);
    else if (scale > 0) {
      const s = Math.max(1, Math.round(16 * scale));
      ctx.drawImage(img, sx + (16 - s) / 2, y + 16 - s, s, s);
    }
  }

  // During the switch the overtime clocks shrink away into ticks
  function drawSwitchClocks() {
    for (const c of clocks) {
      drawClock(c.x, c.y, c.anim, 1 - tidy);
      if (tidy > 0.6) ctx.drawImage(TICK, Math.round(c.x - camX + 4), c.y + 9);
    }
  }

  function drawDoc(d) {
    const sx = Math.round(d.x - camX), y = GROUND_Y - 18;
    if (sx < -16 || sx > W) return;
    box(sx, y, 14, 18, PAL.white, PAL.ink);
    rect(sx + 1, y + 1, 12, 3, mode === 'after' ? PAL.accent : PAL.sage);
    for (let r = 0; r < 3; r++) rect(sx + 3, y + 7 + r * 3, 8 - (r % 2) * 3, 1, PAL.sage);
    if (mode === 'before') {
      // a red "?" scribble: unfinished
      rect(sx + 9, y + 9, 3, 1, PAL.alert); rect(sx + 11, y + 10, 1, 2, PAL.alert); rect(sx + 10, y + 12, 1, 1, PAL.alert); rect(sx + 10, y + 14, 1, 1, PAL.alert);
    } else if (d.done) {
      ctx.drawImage(TICK, sx + 3, y + 10);
    }
  }

  function drawPlayer() {
    const p = player;
    if (p.hidden) return;
    if (p.hurt > 0 && Math.floor(p.hurt / 3) % 2 === 0) return; // flicker after a stumble
    let frame = 'stand';
    if (!p.onGround) frame = 'jump';
    else if (p.vx !== 0) frame = Math.floor(p.anim) % 2 ? 'run1' : 'run2';
    const img = PLAYER[character][frame][p.facing < 0 ? 'l' : 'r'];
    const sx = Math.round(p.x - camX) - 3;
    ctx.drawImage(img, sx, Math.round(p.y));
    // The Σ helper rides along once reporting is built
    if (mode === 'after') {
      const bob = REDUCED ? 0 : Math.round(Math.sin(tick / 10) * 1.5);
      ctx.drawImage(HELPER, sx - 8, Math.round(p.y) - 10 + bob);
    }
  }

  /* ---------------------------------------------------------------- HUD: two numbers only */

  function drawHud() {
    rect(0, 0, W, HUD_H, PAL.paper);
    rect(0, HUD_H - 1, W, 1, PAL.sage);
    const live = hudLive;
    const hours = live ? hoursNow() : 0;
    const net = live ? netNow() : 0;
    text('HOURS SAVED', 6, 2, PAL.muted);
    text(String(hours), 6, 11, live ? PAL.accent : PAL.muted, 16);
    text('NET SAVING (AUD)', W - 6, 2, PAL.muted, 8, 'right');
    text(aud(net), W - 6, 11, !live ? PAL.muted : net < 0 ? PAL.alert : PAL.accent, 16, 'right');
  }

  // Title / how-to: a plain brand bar where the HUD will be
  function drawBrandBar() {
    rect(0, 0, W, HUD_H, PAL.paper);
    rect(0, HUD_H - 1, W, 1, PAL.sage);
    // "4th" mark: a big 4 with a small raised "th"
    box(6, 4, 29, 20, PAL.accent, PAL.accentDark);
    text('4', 9, 6, PAL.white, 16);
    drawTh(24, 7, 1, PAL.white);
    text('THE FOURTH SHEET', 41, 10, PAL.ink);
  }

  // Lower-case "th" as a tiny pixel sprite (the font only has capitals at
  // one size, so a real superscript has to be drawn). 7 x 5 pixels per scale.
  const TH_PIXELS = ['.#..#..', '###.#..', '.#..##.', '.#..#.#', '.##.#.#'];
  function drawTh(x, y, scale, color) {
    TH_PIXELS.forEach((line, r) => [...line].forEach((ch, c) => {
      if (ch === '#') rect(x + c * scale, y + r * scale, scale, scale, color);
    }));
  }

  /* ---------------------------------------------------------------- banners */

  function drawBanner() {
    const maxW = 236;
    const blocks = banner.lines.map(l => {
      const f = l.big ? fitText(l.t, 240, 2, [16, 8]) : { size: 8, lines: wrap(l.t, maxW, 8) };
      return { ...f, c: l.c };
    });
    let w = 0, h = 6;
    for (const b of blocks) {
      for (const line of b.lines) w = Math.max(w, textW(line, b.size));
      h += b.lines.length * (b.size + 3);
    }
    w = Math.min(W - 8, w + 14);
    const x = Math.round((W - w) / 2), y = banner.y;
    cover(x, y, w, h + 2);
    box(x, y, w, h + 2, PAL.paper, blocks[0].c);
    let ty = y + 5;
    for (const b of blocks) for (const line of b.lines) { text(line, W / 2, ty, b.c, b.size, 'center'); ty += b.size + 3; }
    return { x, y, w, h: h + 2 };
  }

  // Popups ("COPY-PASTE", "CAUGHT"...). Each one is placed so it never
  // overlaps the banner or another popup and stays fully inside the play
  // area; if there's no free spot it waits rather than being cut off.
  function drawPopups(bannerBox) {
    const taken = [...clutterRects, ...(bannerBox ? [bannerBox] : [])];
    const hits = (r) => taken.some(t => r.x < t.x + t.w && r.x + r.w > t.x && r.y < t.y + t.h && r.y + r.h > t.y);
    const top = HEAD_Y + HEAD_H + 1, bottom = GROUND_Y - 12;
    for (const p of popups) {
      const w = textW(p.text, 8) + 4;
      const x = Math.max(2, Math.min(W - 2 - w, (p.screen ? p.x : p.x - camX) - 2));
      let y = Math.max(top, Math.min(bottom, Math.round(p.y) - 2));
      let r = { x, y, w, h: 12 };
      // try the spot, then nudge down/up in 12px steps
      for (let i = 1; hits(r) && i < 12; i++) {
        const dy = (i % 2 ? -1 : 1) * Math.ceil(i / 2) * 12; // up first, so the player stays visible
        r = { x, y: y + dy, w, h: 12 };
        if (r.y < top || r.y > bottom) r = { x, y: -100, w, h: 12 };
      }
      if (r.y < top || hits(r)) continue;
      taken.push(r);
      cover(r.x, r.y, r.w, r.h);
      rect(r.x, r.y, r.w, r.h, PAL.paper);
      text(p.text, r.x + 2, r.y + 2, p.color);
    }
  }

  /* ---------------------------------------------------------------- screens */

  // A centred panel with lines of text, each wrapped to fit
  function panel(lines, y, opts = {}) {
    const maxW = opts.maxW || 232;
    const blocks = lines.map(l => ({ ...(l.size === 16 ? fitText(l.t, maxW, l.maxLines || 2, [16, 8]) : { size: 8, lines: wrap(l.t, maxW, 8) }), c: l.c || PAL.ink, gap: l.gap || 0 }));
    let h = 8;
    for (const b of blocks) h += b.lines.length * (b.size + 3) + b.gap;
    const w = opts.w || 244;
    cover((W - w) / 2, y, w, h);
    box((W - w) / 2, y, w, h, PAL.paper, opts.border || PAL.accent);
    let ty = y + 6;
    for (const b of blocks) {
      ty += b.gap;
      for (const line of b.lines) { text(line, W / 2, ty, b.c, b.size, 'center'); ty += b.size + 3; }
    }
    return y + h;
  }

  function drawTitle() {
    const bottom = panel([
      { t: 'THE MONTH-END RUN', size: 16, c: PAL.accent },
      { t: `MONTH-END. ${CONFIG.manualHours} HOURS OF COPY-PASTE.`, c: PAL.ink, gap: 4 },
    ], 42);
    if (!DEMO && stateT > 40 && (REDUCED || Math.floor(stateT / 30) % 2 === 0)) {
      text(TOUCH ? 'TAP TO PLAY' : 'PRESS ENTER TO PLAY', W / 2, bottom + 8, PAL.ink, 8, 'center');
    }
  }

  // Character select geometry (also used for taps)
  const SELECT_Y = 82, SELECT_GAP = 30;
  const selectX = i => Math.round(W / 2 - (ROSTER.length * SELECT_GAP) / 2 + i * SELECT_GAP + 7);

  function drawHowto() {
    rect(0, 0, W, H, 'rgba(244,247,242,0.85)');
    // Two lines of instructions, before play (spec: two lines max)
    panel([
      { t: 'HOW TO PLAY', c: PAL.accent },
      { t: TOUCH ? 'USE THE BUTTONS BELOW.' : 'ARROWS MOVE, SPACE JUMPS.', c: PAL.ink, gap: 2 },
      { t: 'GRAB DATA. DODGE OVERTIME.', c: PAL.ink },
    ], 32);

    if (REDUCED) {
      // Reduced motion: offer the static results instead of the run
      panel([{ t: 'REDUCED MOTION IS ON.', c: PAL.ink }, { t: TOUCH ? 'TAP: RESULTS · P: PLAY' : 'ENTER: RESULTS · P: PLAY', c: PAL.accent }], 84, { border: PAL.sage });
      return;
    }

    // Pick a player
    ROSTER.forEach((id, i) => {
      const x = selectX(i);
      if (id === character) box(x - 4, SELECT_Y - 4, 24, 24, PAL.soft, PAL.accent);
      ctx.drawImage(PLAYER[id].stand.r, x, SELECT_Y);
    });
    text(TOUCH ? 'TAP A PLAYER TO PICK' : 'LEFT/RIGHT: PICK A PLAYER', W / 2, SELECT_Y + 24, PAL.muted, 8, 'center');
    if (Math.floor(stateT / 30) % 2 === 0) text(TOUCH ? 'TAP TO START' : 'PRESS ENTER TO START', W / 2, 126, PAL.ink, 8, 'center');
  }

  // Summary rows: label + value, revealed one after another
  function summaryRows() {
    const m = money();
    return [
      { label: 'HOURS SAVED', value: CONFIG.hoursSaved, fmt: v => `${Math.round(v)} H` },
      { label: '× RATE (ASSUMED)', value: CONFIG.hourlyRateAUD, fmt: v => `${aud(v)}/H` },
      { label: '= VALUE', value: m.value, fmt: aud },
      { label: 'LESS SETUP', value: -CONFIG.setupCostAUD, fmt: aud },
      { label: 'LESS RUNNING COST', value: -CONFIG.runningCostAUD, fmt: aud },
    ];
  }

  function drawSummary() {
    rect(0, 0, W, H, PAL.bg);
    box(4, 4, W - 8, H - 8, PAL.paper, PAL.accent);
    const m = money();
    const t = stateT;
    const days = cfg('daysToClose', FALLBACK.daysToClose);
    const head = wrap(`${CONFIG.monthLabel.toUpperCase()} – MONTH-END DONE IN ${days} DAYS`, 232, 8);
    head.forEach((line, i) => text(line, 12, 10 + i * 10, PAL.accent));

    // Count up quickly (under 1s), never during reduced motion
    const shown = (value, startAt) => {
      if (REDUCED) return value;
      const k = Math.max(0, Math.min(1, (t - startAt) / TIMING.countUp));
      return value * k;
    };

    // Layout (top to bottom): heading, 5 rows, net saving, payback, footnote
    let y = 10 + head.length * 10 + 4;
    summaryRows().forEach((r, i) => {
      const at = 6 + i * 8;
      if (REDUCED || t >= at) {
        text(r.label, 12, y, PAL.ink);
        text(r.fmt(shown(r.value, at)), W - 12, y, r.value < 0 ? PAL.alert : PAL.ink, 8, 'right');
      }
      y += 10;
    });

    // Bottom line: net saving (cash only)
    const netAt = 6 + 5 * 8;
    if (REDUCED || t >= netAt) {
      rect(10, y, W - 20, 1, PAL.ink);
      box(10, y + 2, W - 20, 13, PAL.soft, PAL.accent);
      text('NET SAVING', 14, y + 5, PAL.accentDark);
      text(aud(shown(m.net, netAt)), W - 14, y + 5, m.net < 0 ? PAL.alert : PAL.accentDark, 8, 'right');
    }
    y += 19;
    if (REDUCED || t >= netAt + TIMING.countUp) {
      const pay = m.paybackWeek ? `PAID FOR ITSELF IN WEEK ${m.paybackWeek}` : 'NOT PAID BACK THIS MONTH';
      text(wrap(pay, 232, 8)[0], W / 2, y, PAL.accent, 8, 'center');
    }

    // Required footnote: these are not real client results
    const foot = wrap('SIMULATED MONTH. ILLUSTRATIVE ONLY. YOUR RESULTS WILL VARY.', 232, 8);
    foot.forEach((line, i) => text(line, W / 2, H - 8 - (foot.length - i) * 10, PAL.muted, 8, 'center'));
  }

  // End card. END_BUTTONS are the clickable areas; game.html lays real
  // links/buttons over exactly these rectangles (see updateDom()).
  const END_BUTTONS = {
    book: { x: 8, y: 80, w: 240, h: 18 },
    again: { x: 80, y: 124, w: 96, h: 16 },
  };

  function drawEnd() {
    rect(0, 0, W, H, PAL.bg);
    // "4th" mark, then the business name and the person
    box(W / 2 - 17, 4, 34, 28, PAL.accent, PAL.accentDark);
    text('4', W / 2 - 13, 10, PAL.white, 16);
    drawTh(W / 2 + 1, 9, 2, PAL.white);
    text('THE FOURTH SHEET', W / 2, 34, PAL.accent, 8, 'center');

    const name = cfg('name', '');
    const byline = name ? String(name).toUpperCase() : 'THE NUMBERS UNDERNEATH';
    let y = 44;
    for (const line of wrap(byline, 236, 8)) { text(line, W / 2, y, PAL.muted, 8, 'center'); y += 10; }
    y += 4;
    for (const line of wrap('YOUR NUMBERS, WITHOUT THE MONTH-END GRIND.', 236, 8)) { text(line, W / 2, y, PAL.ink, 8, 'center'); y += 11; }

    const b = END_BUTTONS.book;
    box(b.x, b.y, b.w, b.h, PAL.accent, PAL.accentDark);
    const label = fitText('BOOK A FREE NUMBERS CHECK', b.w - 8, 1, [8]);
    text(label.lines[0], W / 2, b.y + 5, PAL.white, 8, 'center');

    // Web address: one line if it fits, otherwise split after the last "/"
    // (never cut short)
    const domain = String(cfg('domain', FALLBACK.domain));
    let lines = [domain];
    if (textW(domain, 8) > 236) {
      const cut = domain.lastIndexOf('/') + 1;
      lines = cut > 0 ? [domain.slice(0, cut), domain.slice(cut)] : wrap(domain, 236, 8);
    }
    lines.slice(0, 2).forEach((line, i) => text(line, W / 2, (lines.length > 1 ? 103 : 107) + i * 9, PAL.ink, 8, 'center'));

    const a = END_BUTTONS.again;
    box(a.x, a.y, a.w, a.h, PAL.paper, PAL.sage);
    text('PLAY AGAIN', W / 2, a.y + 4, PAL.ink, 8, 'center');
  }

  function drawPaused() {
    rect(0, 0, W, H, 'rgba(37,52,42,0.55)');
    panel([{ t: 'PAUSED', c: PAL.accent }, { t: TOUCH ? 'TAP TO CARRY ON' : 'PRESS P OR ENTER TO CARRY ON', c: PAL.ink }], 52);
  }

  /* ================================================================ PAGE CONTROLS (game.html) */

  const $ = id => document.getElementById(id);
  const skipBtn = $('skip-btn'), soundBtn = $('sound-btn');
  const ctaBook = $('cta-book'), ctaAgain = $('cta-again'), status = $('game-status');

  // Booking link: real URL once [[BOOKING_URL]] is filled in; until then
  // the website's Contact section (opened in the main window, not the iframe).
  const bookingUrl = cfg('bookingUrl', FALLBACK.bookingUrl);
  if (ctaBook) {
    ctaBook.href = bookingUrl;
    const external = /^https?:/i.test(bookingUrl);
    ctaBook.target = external ? '_blank' : '_top';
    if (external) ctaBook.rel = 'noopener';
  }

  // Lay the HTML buttons exactly over the drawn end-card buttons
  function place(el, r) {
    el.style.left = (r.x / W) * 100 + '%';
    el.style.top = (r.y / H) * 100 + '%';
    el.style.width = (r.w / W) * 100 + '%';
    el.style.height = (r.h / H) * 100 + '%';
  }
  if (ctaBook) place(ctaBook, END_BUTTONS.book);
  if (ctaAgain) place(ctaAgain, END_BUTTONS.again);

  function updateDom() {
    const atEnd = state === 'end' && !CAPTURE;
    if (ctaBook) ctaBook.hidden = !atEnd;
    if (ctaAgain) ctaAgain.hidden = !atEnd;
    if (skipBtn) skipBtn.disabled = state === 'summary' || state === 'end';
    document.documentElement.dataset.state = state;
  }

  function announceSummary() {
    if (!status) return;
    const m = money();
    status.textContent = `${CONFIG.monthLabel}: ${CONFIG.hoursSaved} hours saved at an assumed ${aud(CONFIG.hourlyRateAUD)} an hour, ` +
      `worth ${aud(m.value)}. Less setup ${aud(CONFIG.setupCostAUD)} and running cost ${aud(CONFIG.runningCostAUD)}: ` +
      `net saving ${aud(m.net)}. Simulated month, illustrative only.`;
  }

  function showSound() {
    if (!soundBtn) return;
    const on = !AUDIO.muted;
    soundBtn.textContent = on ? 'Sound: on' : 'Sound: off';
    soundBtn.setAttribute('aria-pressed', String(on));
  }
  function toggleSound() { AUDIO.unlock(); AUDIO.toggleMute(); showSound(); }
  if (soundBtn) soundBtn.addEventListener('click', () => { toggleSound(); canvas.focus({ preventScroll: true }); });
  showSound();

  if (skipBtn) skipBtn.addEventListener('click', () => {
    paused = false;
    if (state !== 'summary' && state !== 'end') { finishAll(); startSummary(); }
    canvas.focus({ preventScroll: true });
  });
  if (ctaAgain) ctaAgain.addEventListener('click', () => { startBefore(); canvas.focus({ preventScroll: true }); });

  /* ================================================================ INPUT */

  const KEYMAP = {
    ArrowLeft: 'left', KeyA: 'left',
    ArrowRight: 'right', KeyD: 'right',
    ArrowUp: 'jump', KeyW: 'jump', Space: 'jump', KeyZ: 'jump',
  };

  // Enter / tap / Space on a screen that's waiting for you
  function advance() {
    if (paused) { paused = false; return; }
    if (state === 'title') startHowto();
    else if (state === 'howto') { if (REDUCED) startSummary(); else startBefore(); }
    else if (state === 'summary' && stateT >= TIMING.summaryMin) startEnd();
  }

  function cycleCharacter(dir) {
    const i = ROSTER.indexOf(character);
    character = ROSTER[(i + dir + ROSTER.length) % ROSTER.length];
    try { localStorage.setItem('s3-character', character); } catch (e) { /* ignore */ }
    sfx('blip');
  }

  const playing = () => state === 'before' || state === 'after';

  if (!DEMO) {
    window.addEventListener('keydown', e => {
      const t = e.target;
      if (t && t !== canvas && t !== document.body && /^(A|BUTTON|INPUT|TEXTAREA|SELECT)$/.test(t.tagName) && (e.code === 'Enter' || e.code === 'Space')) return; // let buttons/links work
      AUDIO.unlock();
      if (e.code === 'KeyM') { e.preventDefault(); toggleSound(); return; }
      if ((e.code === 'KeyP' || e.code === 'Escape') && playing()) { e.preventDefault(); paused = !paused; releaseKeys(); return; }
      if (e.code === 'KeyP' && state === 'howto' && REDUCED) { e.preventDefault(); startBefore(); return; }
      if (state === 'howto' && (e.code === 'ArrowLeft' || e.code === 'ArrowRight')) { e.preventDefault(); if (!e.repeat) cycleCharacter(e.code === 'ArrowLeft' ? -1 : 1); return; }
      if (state === 'end' && (e.code === 'KeyR' || e.code === 'Space')) { e.preventDefault(); startBefore(); return; }
      if (e.code === 'Enter' || (e.code === 'Space' && !playing())) { e.preventDefault(); advance(); return; }
      const k = KEYMAP[e.code];
      if (k && playing()) {
        e.preventDefault();
        if (paused) paused = false;
        if (k === 'jump' && !e.repeat) tapped.jump = true;
        keys[k] = true;
      }
    });
    window.addEventListener('keyup', e => { const k = KEYMAP[e.code]; if (k) keys[k] = false; });

    canvas.addEventListener('pointerdown', e => {
      canvas.focus({ preventScroll: true });
      AUDIO.unlock();
      if (state === 'howto') {
        const r = canvas.getBoundingClientRect();
        const x = (e.clientX - r.left) * (W / r.width), y = (e.clientY - r.top) * (H / r.height);
        if (y > SELECT_Y - 6 && y < SELECT_Y + 22) {
          const i = ROSTER.findIndex((id, n) => x > selectX(n) - 6 && x < selectX(n) + 22);
          if (i >= 0) { character = ROSTER[i]; try { localStorage.setItem('s3-character', character); } catch (err) { /* ignore */ } sfx('blip'); return; }
        }
      }
      advance();
    });
  }

  function releaseKeys() { for (const k in keys) keys[k] = false; }

  // On-screen touch buttons (◀ ▶ JUMP)
  document.querySelectorAll('[data-key]').forEach(btn => {
    const k = btn.dataset.key;
    const on = e => {
      e.preventDefault();
      AUDIO.unlock();
      if (!playing()) { advance(); return; }
      paused = false;
      if (k === 'jump') tapped.jump = true;
      keys[k] = true;
      btn.classList.add('is-down');
    };
    const off = e => { e.preventDefault(); keys[k] = false; btn.classList.remove('is-down'); };
    btn.addEventListener('pointerdown', on);
    btn.addEventListener('pointerup', off);
    btn.addEventListener('pointerleave', off);
    btn.addEventListener('pointercancel', off);
    btn.addEventListener('contextmenu', e => e.preventDefault());
  });

  // Pause when the tab is hidden, or when the website asks (iframe scrolled away)
  document.addEventListener('visibilitychange', () => { if (document.hidden && playing()) { paused = true; releaseKeys(); } });
  window.addEventListener('message', e => {
    if (e.origin === location.origin && e.data === 's3:pause' && playing()) { paused = true; releaseKeys(); }
  });

  /* ================================================================ SIZE
     Scale by a whole number of device pixels so every game pixel is the
     same size (crisp text). In the website's iframe, tell the page how
     tall we are so it can size the iframe.                              */

  const wrapEl = canvas.closest('.game-wrap') || canvas.parentElement;

  function fit() {
    if (CAPTURE) {
      // Recorder: exactly 1280x720 (5x)
      canvas.width = W * 5; canvas.height = H * 5;
      canvas.style.width = canvas.width + 'px'; canvas.style.height = canvas.height + 'px';
      return;
    }
    const dpr = window.devicePixelRatio || 1;
    let scale = Math.floor((wrapEl.clientWidth * dpr) / W);
    if (!EMBED) {
      // Standalone page: also fit the window height, leaving room for the controls
      const below = document.querySelector('.game-below');
      const reserved = (below ? below.offsetHeight : 0) + 32;
      scale = Math.min(scale, Math.floor(((window.innerHeight - reserved) * dpr) / H));
    }
    scale = Math.max(1, scale);
    if (canvas.width !== W * scale) { canvas.width = W * scale; canvas.height = H * scale; }
    canvas.style.width = (W * scale) / dpr + 'px';
    canvas.style.height = (H * scale) / dpr + 'px';
    if (EMBED && window.parent !== window) {
      requestAnimationFrame(() => window.parent.postMessage({ type: 's3-game-height', height: document.documentElement.scrollHeight }, location.origin));
    }
  }

  fit();
  if ('ResizeObserver' in window) new ResizeObserver(fit).observe(wrapEl);
  window.addEventListener('resize', fit);

  /* ================================================================ LOOP */

  startTitle();
  if (DEMO) mark('open');

  const STEP = 1000 / 60;
  let last = 0, acc = 0;

  function frame(now) {
    let dt = Math.min(100, now - last);
    last = now;
    if (Math.abs(dt - STEP) < 2) dt = STEP; // smooth out timestamp wobble on 60Hz screens
    acc += dt;
    while (acc >= STEP) { if (!paused) update(); acc -= STEP; }
    render();
    requestAnimationFrame(frame);
  }

  // Recorder hook (capture mode only): the page doesn't run by itself;
  // tools/archive/record_demo.py calls __game.step(2) per video frame (30fps).
  const fontsReady = (document.fonts && document.fonts.load)
    ? document.fonts.load(`8px ${FONT_NAME}`).then(() => document.fonts.ready).catch(() => {})
    : Promise.resolve();

  if (CAPTURE) {
    window.__game = {
      ready: fontsReady.then(() => { render(); return true; }),
      step(n = 1) { for (let i = 0; i < n; i++) update(); render(); return state; },
      audit: () => auditFrame(),
      get state() { return state; },
      get tick() { return tick; },
      marks,
    };
  } else {
    fontsReady.then(() => requestAnimationFrame(t => { last = t; frame(t); }));
  }
})();
