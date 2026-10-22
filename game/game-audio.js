/*
  game-audio.js — sound for "The Month-End Run"

  A tiny chiptune synth on the Web Audio API: pulse waves, a triangle and
  noise. No audio files. Exposes window.S3Audio:

    S3Audio.unlock()          call from any key/click (browsers need a gesture)
    S3Audio.sfx(name)         play a sound effect (names in SFX below)
    S3Audio.music(on)         start/stop the soundtrack loop
    S3Audio.layer(on)         extra arpeggio while automation is running
    S3Audio.toggleMute()      sound on/off; remembered between visits
    S3Audio.muted             current state

  SOUND IS OFF BY DEFAULT. Nothing plays until the visitor turns it on
  (the SOUND button or the M key), and that choice is remembered.

  The soundtrack is "Synergy Breeze": smooth-jazz corporate training video
  music squeezed into 8 bits (original composition).
*/

(() => {
  'use strict';

  let ac = null, master, musicBus, sfxBus, noiseBuf;
  const waves = {};
  // Off unless the visitor has turned sound on before.
  let muted = true;
  try { muted = localStorage.getItem('s3-sound') !== 'on'; } catch (e) { /* storage blocked */ }

  const midi = n => 440 * Math.pow(2, (n - 69) / 12);

  // Pulse wave with a given duty cycle, built from its Fourier series
  function pulseWave(duty) {
    const n = 64, re = new Float32Array(n), im = new Float32Array(n);
    for (let k = 1; k < n; k++) im[k] = (2 / (k * Math.PI)) * Math.sin(k * Math.PI * duty);
    return ac.createPeriodicWave(re, im);
  }

  function init() {
    if (ac) return true;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return false;
    ac = new AC();
    master = ac.createGain();
    master.gain.value = muted ? 0 : 0.32;
    master.connect(ac.destination);
    musicBus = ac.createGain(); musicBus.gain.value = 0.55; musicBus.connect(master);
    sfxBus = ac.createGain(); sfxBus.gain.value = 0.8; sfxBus.connect(master);
    waves.p12 = pulseWave(0.125);
    waves.p25 = pulseWave(0.25);
    waves.p50 = pulseWave(0.5);
    // Noise: random samples, like the NES noise channel
    noiseBuf = ac.createBuffer(1, ac.sampleRate, ac.sampleRate);
    const d = noiseBuf.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    return true;
  }

  /* ---------------------------------------------------------------- voices */

  // One tone. type: 'p12' | 'p25' | 'p50' | 'tri'. env: attack/decay/sustain level.
  function tone(bus, t, { note, freq, type = 'p50', dur = 0.15, vol = 0.3, slideTo, vibrato = 0, attack = 0.005, release = 0.04, lowpass }) {
    const o = ac.createOscillator();
    if (type === 'tri') o.type = 'triangle'; else o.setPeriodicWave(waves[type]);
    const f0 = freq || midi(note);
    o.frequency.setValueAtTime(f0, t);
    if (slideTo) o.frequency.exponentialRampToValueAtTime(slideTo, t + dur);
    let out = o;
    if (vibrato) {
      const lfo = ac.createOscillator(), lg = ac.createGain();
      lfo.frequency.value = 5.5; lg.gain.value = f0 * vibrato;
      lfo.connect(lg); lg.connect(o.frequency);
      lfo.start(t + 0.08); lfo.stop(t + dur + release);
    }
    if (lowpass) {
      const f = ac.createBiquadFilter(); f.type = 'lowpass'; f.frequency.value = lowpass;
      out.connect(f); out = f;
    }
    const g = ac.createGain();
    g.gain.setValueAtTime(0, t);
    g.gain.linearRampToValueAtTime(vol, t + attack);
    g.gain.setValueAtTime(vol, t + Math.max(attack, dur - 0.01));
    g.gain.linearRampToValueAtTime(0, t + dur + release);
    out.connect(g); g.connect(bus);
    o.start(t); o.stop(t + dur + release + 0.02);
  }

  function noise(bus, t, { dur = 0.08, vol = 0.2, filter = 'highpass', freq = 6000, q = 0.7 }) {
    const s = ac.createBufferSource();
    s.buffer = noiseBuf;
    const f = ac.createBiquadFilter(); f.type = filter; f.frequency.value = freq; f.Q.value = q;
    const g = ac.createGain();
    g.gain.setValueAtTime(vol, t);
    g.gain.exponentialRampToValueAtTime(0.001, t + dur);
    s.connect(f); f.connect(g); g.connect(bus);
    s.start(t, Math.random() * 0.5); s.stop(t + dur + 0.02);
  }

  /* ---------------------------------------------------------------- sound effects */

  const seq = (t, notes, step, opts) => notes.forEach((n, i) => n != null && tone(sfxBus, t + i * step, { note: n, dur: step * 0.9, ...opts }));

  // Sound effects used by game.js
  const SFX = {
    jump:    t => tone(sfxBus, t, { freq: 280, slideTo: 720, type: 'p25', dur: 0.12, vol: 0.22 }),
    // grabbing a data cell by hand (copy-paste)
    grab:    t => { tone(sfxBus, t, { note: 79, type: 'p12', dur: 0.04, vol: 0.14 }); tone(sfxBus, t + 0.04, { note: 84, type: 'p12', dur: 0.12, vol: 0.14, release: 0.08 }); },
    // bumped into an overtime clock
    stumble: t => tone(sfxBus, t, { freq: 160, slideTo: 110, type: 'tri', dur: 0.12, vol: 0.5 }),
    // a rogue invoice slipped past
    slip:    t => { tone(sfxBus, t, { note: 67, type: 'p25', dur: 0.1, vol: 0.14 }); tone(sfxBus, t + 0.11, { note: 62, type: 'p25', dur: 0.2, vol: 0.14, release: 0.1 }); },
    // automation caught an invoice / pulled a cell
    caught:  t => seq(t, [72, 76, 79, 84], 0.05, { type: 'p25', vol: 0.16, release: 0.08 }),
    pull:    t => tone(sfxBus, t, { note: 88, type: 'p12', dur: 0.05, vol: 0.1 }),
    // a report publishes itself
    publish: t => { tone(sfxBus, t, { note: 76, type: 'p25', dur: 0.06, vol: 0.18 }); tone(sfxBus, t + 0.06, { note: 84, type: 'p25', dur: 0.12, vol: 0.18 }); },
    // the switch: reporting gets built
    build:   t => { seq(t, [67, 72, 76, 79, 84], 0.09, { type: 'p50', vol: 0.2 }); [72, 76, 79, 83].forEach(n => tone(sfxBus, t + 0.5, { note: n, type: 'p25', dur: 0.6, vol: 0.09, release: 0.3 })); tone(sfxBus, t + 0.5, { note: 48, type: 'tri', dur: 0.6, vol: 0.4 }); },
    tick:    t => tone(sfxBus, t, { note: 96, type: 'p12', dur: 0.025, vol: 0.12 }),
    blip:    t => tone(sfxBus, t, { note: 81, type: 'p25', dur: 0.04, vol: 0.15 }),
    start:   t => seq(t, [72, 76, 79, 84], 0.06, { type: 'p25', vol: 0.18 }),
  };

  /* ---------------------------------------------------------------- the soundtrack */

  // "Synergy Breeze" — 8 bars, swung eighths, 100 bpm.
  // Fmaj7 | Em7 | Dm7 | G7 | Cmaj7 | Am7 | Dm7 | G7
  const BPM = 100;
  const EIGHTH = 60 / BPM / 2;
  const SWING = 0.62;             // late off-beats: the smooth bit
  const BARS = 8, STEPS = BARS * 8;

  const CHORDS = [
    { root: 41, notes: [57, 60, 64, 65] }, // Fmaj7
    { root: 40, notes: [55, 59, 62, 64] }, // Em7
    { root: 38, notes: [53, 57, 60, 62] }, // Dm7
    { root: 43, notes: [53, 55, 59, 62] }, // G7
    { root: 36, notes: [55, 59, 60, 64] }, // Cmaj7
    { root: 45, notes: [55, 57, 60, 64] }, // Am7
    { root: 38, notes: [53, 57, 60, 64] }, // Dm9-ish
    { root: 43, notes: [53, 57, 59, 62] }, // G13-ish
  ];

  // Lead: [step, midi note, length in eighths]
  const LEAD = [
    [2, 69, 1], [3, 72, 1], [4, 76, 3], [7, 74, 1],
    [8, 72, 2], [10, 71, 1], [11, 67, 4],
    [18, 65, 1], [19, 69, 1], [20, 72, 3], [23, 74, 1],
    [24, 77, 2], [26, 76, 1], [27, 74, 1], [28, 71, 4],
    [34, 76, 1], [35, 79, 1], [36, 83, 3], [39, 81, 1],
    [40, 79, 2], [42, 76, 1], [43, 72, 4],
    [50, 77, 1], [51, 76, 1], [52, 74, 1], [53, 72, 1], [54, 74, 2],
    [56, 71, 2], [58, 74, 1], [59, 77, 1], [60, 79, 3], [63, 78, 1],
  ];
  const LEAD_AT = new Map(LEAD.map(n => [n[0], n]));

  // Bass per bar (eighths): root, ., ., root, fifth, ., octave, fifth
  const BASS = [[0, 0, 3], [3, 0, 1], [4, 7, 2], [6, 12, 1], [7, 7, 1]];

  let playing = false, step = 0, nextTime = 0, timer = null, loopCount = 0;
  let autoLayer = false; // busy arpeggio while automation is running

  function stepTime(i, base) {
    const beat = Math.floor(i / 2), off = i % 2;
    return base + beat * EIGHTH * 2 + (off ? EIGHTH * 2 * SWING : 0);
  }

  function scheduleStep(i, t) {
    const bar = Math.floor(i / 8), pos = i % 8, ch = CHORDS[bar];
    // Drum machine: kick on 1 and 3, snare-ish on 2 and 4, shaker on every eighth
    if (pos === 0 || pos === 4) tone(musicBus, t, { freq: 130, slideTo: 45, type: 'tri', dur: 0.09, vol: 0.55 });
    if (pos === 2 || pos === 6) noise(musicBus, t, { dur: 0.12, vol: 0.13, filter: 'bandpass', freq: 1800, q: 0.8 });
    noise(musicBus, t, { dur: 0.03, vol: pos % 2 ? 0.05 : 0.03, freq: 9000 });
    // Walking triangle bass
    for (const [p, interval, len] of BASS) if (p === pos) tone(musicBus, t, { note: ch.root + interval, type: 'tri', dur: EIGHTH * len * 0.9, vol: 0.42 });
    // Electric-piano-ish stabs on the "and" of 2 and on 4
    if (pos === 3 || pos === 6) ch.notes.forEach(n => tone(musicBus, t, { note: n, type: 'p25', dur: 0.16, vol: 0.045, lowpass: 2600, release: 0.12 }));
    // Automation on: a busy, bubbly arpeggio over the chords
    if (autoLayer) tone(musicBus, t, { note: ch.notes[pos % 4] + 12, type: 'p12', dur: EIGHTH * 0.5, vol: 0.05, release: 0.03 });
    // The cheesy lead (an octave lower on alternate loops for variety)
    const ld = LEAD_AT.get(i);
    if (ld) tone(musicBus, t, { note: ld[1] - (loopCount % 4 === 3 ? 12 : 0), type: 'p50', dur: EIGHTH * ld[2] * 0.95, vol: 0.085, vibrato: 0.012, attack: 0.02, release: 0.08, lowpass: 3200 });
  }

  let loopStart = 0;
  function pump() {
    if (!playing) return;
    const ahead = ac.currentTime + 0.15;
    while (nextTime < ahead) {
      scheduleStep(step, nextTime);
      step++;
      if (step >= STEPS) { step = 0; loopCount++; loopStart += EIGHTH * STEPS; }
      nextTime = stepTime(step, loopStart);
    }
  }

  function music(on) {
    if (on === playing) return;
    if (!ac || ac.state !== 'running') { if (!on) playing = false; return; }
    playing = on;
    if (on) {
      step = 0; loopCount = 0;
      loopStart = ac.currentTime + 0.08;
      nextTime = loopStart;
      musicBus.gain.cancelScheduledValues(ac.currentTime);
      musicBus.gain.setValueAtTime(0.55, ac.currentTime);
      pump();
      timer = setInterval(pump, 30);
    } else {
      clearInterval(timer); timer = null;
      // quick fade so already-scheduled notes don't hang on
      const now = ac.currentTime;
      musicBus.gain.cancelScheduledValues(now);
      musicBus.gain.setValueAtTime(musicBus.gain.value, now);
      musicBus.gain.linearRampToValueAtTime(0, now + 0.12);
      setTimeout(() => { if (!playing) musicBus.gain.setValueAtTime(0.55, ac.currentTime); }, 400);
    }
  }

  /* ---------------------------------------------------------------- offline render (demo recordings)

     tools/archive/record_demo.py steps the game frame by frame, so sound can't be recorded live. Instead it logs every
     cue with its time and asks for the soundtrack to be rendered offline, through this same synth:
       events: [[seconds, 'sfx', name] | [seconds, 'music', true/false] | [seconds, 'layer', true/false]]
     Returns a Promise of 16-bit stereo WAV bytes, base64. Noise uses seeded randomness, so a render repeats exactly. */

  async function renderOffline(events, seconds, rate = 44100) {
    const OAC = window.OfflineAudioContext || window.webkitOfflineAudioContext;
    const keep = { ac, master, musicBus, sfxBus, noiseBuf, waves: { ...waves }, autoLayer, loopCount };
    let seed = 20261031;
    const rnd = () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
    const realRandom = Math.random;
    Math.random = rnd;
    try {
      ac = new OAC(2, Math.ceil(seconds * rate), rate);
      master = ac.createGain(); master.gain.value = 0.32; master.connect(ac.destination);
      musicBus = ac.createGain(); musicBus.gain.value = 0.55; musicBus.connect(master);
      sfxBus = ac.createGain(); sfxBus.gain.value = 0.8; sfxBus.connect(master);
      waves.p12 = pulseWave(0.125); waves.p25 = pulseWave(0.25); waves.p50 = pulseWave(0.5);
      noiseBuf = ac.createBuffer(1, ac.sampleRate, ac.sampleRate);
      const d = noiseBuf.getChannelData(0);
      for (let i = 0; i < d.length; i++) d[i] = rnd() * 2 - 1;

      const ev = events.slice().sort((a, b) => a[0] - b[0]);
      const layers = ev.filter(e => e[1] === 'layer');
      const layerAt = t => { let on = false; for (const [lt, , v] of layers) { if (lt <= t) on = !!v; else break; } return on; };
      // music: each on..off stretch plays the loop from its start, exactly as live
      let on = null;
      const play = (t0, t1) => {
        let st = 0; loopCount = 0; let base = t0 + 0.08, t = base;
        while (t < t1) {
          autoLayer = layerAt(t);
          scheduleStep(st, t);
          st++;
          if (st >= STEPS) { st = 0; loopCount++; base += EIGHTH * STEPS; }
          t = stepTime(st, base);
        }
        musicBus.gain.setValueAtTime(0.55, t1);            // the live version's quick fade at "off"
        musicBus.gain.linearRampToValueAtTime(0, t1 + 0.12);
        musicBus.gain.setValueAtTime(0.55, t1 + 0.4);
      };
      for (const [t, kind, v] of ev) {
        if (kind === 'sfx' && SFX[v]) SFX[v](t + 0.005);
        if (kind === 'music') {
          if (v && on === null) on = t;
          if (!v && on !== null) { play(on, t); on = null; }
        }
      }
      if (on !== null) play(on, seconds);
      const buf = await ac.startRendering();
      // 16-bit PCM WAV
      const n = buf.length, ch = buf.numberOfChannels, out = new DataView(new ArrayBuffer(44 + n * ch * 2));
      const str = (o, x) => { for (let i = 0; i < x.length; i++) out.setUint8(o + i, x.charCodeAt(i)); };
      str(0, 'RIFF'); out.setUint32(4, 36 + n * ch * 2, true); str(8, 'WAVE'); str(12, 'fmt ');
      out.setUint32(16, 16, true); out.setUint16(20, 1, true); out.setUint16(22, ch, true); out.setUint32(24, rate, true);
      out.setUint32(28, rate * ch * 2, true); out.setUint16(32, ch * 2, true); out.setUint16(34, 16, true); str(36, 'data'); out.setUint32(40, n * ch * 2, true);
      const data = []; for (let c = 0; c < ch; c++) data.push(buf.getChannelData(c));
      let o = 44;
      for (let i = 0; i < n; i++) for (let c = 0; c < ch; c++) { const x = Math.max(-1, Math.min(1, data[c][i])); out.setInt16(o, x < 0 ? x * 0x8000 : x * 0x7fff, true); o += 2; }
      let bin = ''; const bytes = new Uint8Array(out.buffer);
      for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
      return btoa(bin);
    } finally {
      Math.random = realRandom;
      ({ ac, master, musicBus, sfxBus, noiseBuf, autoLayer, loopCount } = keep);
      Object.assign(waves, keep.waves);
    }
  }

  /* ---------------------------------------------------------------- public */

  window.S3Audio = {
    get muted() { return muted; },
    unlock() {
      if (!init()) return;
      if (ac.state === 'suspended') ac.resume();
    },
    sfx(name) {
      if (muted || !ac || ac.state !== 'running' || !SFX[name]) return;
      SFX[name](ac.currentTime + 0.005);
    },
    music,
    layer(on) { autoLayer = !!on; },
    renderOffline,
    toggleMute() {
      muted = !muted;
      try { localStorage.setItem('s3-sound', muted ? 'off' : 'on'); } catch (e) { /* ignore */ }
      if (ac) {
        master.gain.cancelScheduledValues(ac.currentTime);
        master.gain.setValueAtTime(muted ? 0 : 0.32, ac.currentTime);
      }
      return muted;
    },
  };
})();
