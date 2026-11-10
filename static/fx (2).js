/* Fit Connect art kit: equipment illustrations and icons.
   Pure inline SVG - no external images. Shared by the app and the UI preview. */
(function () {
  const NAVY = "#1e1b4b", ACC = "#f97316";
  const TINT = { orange: ["#ffedd5", "#fdba74"], cyan: ["#cffafe", "#67e8f9"], purple: ["#ede9fe", "#c4b5fd"], peach: ["#ffe8df", "#fdba9f"], lav: ["#f3e8ff", "#d8b4fe"] };
  const EX = [
    { id: "squat", name: "Squat", tint: "orange", primary: ["quads", "glutes"], secondary: ["hamstrings", "core", "calves"], cue: "Chest up, sit back, knees track over toes.", posture: true },
    { id: "lunge", name: "Lunge", tint: "cyan", primary: ["quads", "glutes"], secondary: ["hamstrings", "calves", "core"], cue: "Long step, back knee towards the floor, upright torso.", posture: true },
    { id: "pushup", name: "Push-up", tint: "purple", primary: ["chest", "triceps"], secondary: ["shoulders", "core"], cue: "Body in one line, elbows about 45° from your sides.", posture: true },
    { id: "plank", name: "Plank", tint: "peach", primary: ["core"], secondary: ["shoulders", "glutes"], cue: "Shoulders over elbows, hips level, breathe steadily.", posture: true },
    { id: "deadlift", name: "Deadlift", tint: "lav", primary: ["hamstrings", "glutes", "back"], secondary: ["core", "forearms"], cue: "Hinge at the hips, flat back, bar close to your legs." },
    { id: "shoulder-press", name: "Shoulder press", tint: "orange", primary: ["shoulders"], secondary: ["triceps", "core"], cue: "Brace your core, press straight up, no back arching." },
    { id: "bicep-curl", name: "Bicep curl", tint: "cyan", primary: ["biceps"], secondary: ["forearms"], cue: "Elbows by your sides, curl with control." },
    { id: "crunch", name: "Crunch", tint: "purple", primary: ["core"], secondary: [], cue: "Lift shoulders only, chin neutral, slow and controlled." },
  ];
  const L = p => `<polyline points="${p.map(q => q.join(",")).join(" ")}"/>`;
  const dumb = (x, y, r = 0) => `<rect x="${x - 8}" y="${y - 3.5}" width="16" height="7" rx="3" fill="${ACC}" stroke="none" transform="rotate(${r} ${x} ${y})"/>`;
  const POSE = {
    squat: () => L([[78, 44], [62, 70], [92, 74], [86, 102], [98, 102]]) + L([[78, 44], [104, 50]]) + `<circle cx="82" cy="31" r="8" fill="${NAVY}" stroke="none"/>`,
    lunge: () => L([[72, 38], [72, 66]]) + L([[72, 66], [96, 76], [96, 102], [108, 102]]) + L([[72, 66], [54, 86], [36, 100], [44, 102]]) + L([[72, 40], [86, 52], [76, 64]]) + `<circle cx="74" cy="26" r="8" fill="${NAVY}" stroke="none"/>`,
    pushup: () => L([[108, 58], [68, 72], [34, 94], [28, 104]]) + L([[108, 58], [112, 82], [106, 104]]) + `<circle cx="122" cy="52" r="8" fill="${NAVY}" stroke="none"/>`,
    plank: () => L([[102, 70], [64, 76], [30, 92], [24, 104]]) + L([[102, 70], [102, 100], [122, 100]]) + `<circle cx="114" cy="63" r="8" fill="${NAVY}" stroke="none"/>`,
    deadlift: () => `<line x1="50" y1="92" x2="118" y2="92" stroke="${ACC}" stroke-width="5"/><circle cx="56" cy="92" r="10" fill="${ACC}" stroke="none"/><circle cx="112" cy="92" r="10" fill="${ACC}" stroke="none"/>` + L([[92, 46], [58, 62]]) + L([[58, 62], [64, 84], [60, 102], [72, 102]]) + L([[92, 46], [84, 92]]) + `<circle cx="102" cy="41" r="8" fill="${NAVY}" stroke="none"/>`,
    "shoulder-press": () => L([[80, 50], [80, 80]]) + L([[80, 80], [68, 104]]) + L([[80, 80], [92, 104]]) + L([[80, 52], [62, 46], [62, 22]]) + L([[80, 52], [98, 46], [98, 22]]) + dumb(62, 17) + dumb(98, 17) + `<circle cx="80" cy="38" r="8" fill="${NAVY}" stroke="none"/>`,
    "bicep-curl": () => L([[82, 40], [80, 70]]) + L([[80, 70], [80, 104], [92, 104]]) + L([[82, 42], [84, 62], [100, 48]]) + dumb(102, 45, -40) + `<circle cx="82" cy="28" r="8" fill="${NAVY}" stroke="none"/>`,
    crunch: () => L([[72, 96], [90, 72], [108, 96], [114, 104]]) + L([[72, 96], [46, 78]]) + L([[46, 78], [40, 64]]) + `<circle cx="37" cy="68" r="8" fill="${NAVY}" stroke="none"/>`,
  };
  let uid = 0;
  const find = id => EX.find(e => e.id === id || e.name.toLowerCase() === String(id).toLowerCase());
  function exSVG(id, label = true) {
    const e = find(id); if (!e) return "";
    const t = TINT[e.tint], g = "fcg" + (++uid);
    return `<svg viewBox="0 0 160 120" xmlns="http://www.w3.org/2000/svg" ${label ? `role="img" aria-label="${e.name} illustration"` : 'aria-hidden="true"'} preserveAspectRatio="xMidYMid slice"><defs><linearGradient id="${g}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${t[0]}"/><stop offset="1" stop-color="${t[1]}"/></linearGradient></defs><rect width="160" height="120" fill="url(#${g})"/><circle cx="132" cy="22" r="26" fill="#fff" opacity=".35"/><line x1="14" y1="106" x2="146" y2="106" stroke="${NAVY}" stroke-width="3" opacity=".14" stroke-linecap="round"/><g fill="none" stroke="${NAVY}" stroke-width="8" stroke-linecap="round" stroke-linejoin="round">${POSE[e.id]()}</g></svg>`;
  }
  const P = d => `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
  const ICON = {
    grid: P('<rect x="4" y="4" width="7" height="7" rx="2"/><rect x="13" y="4" width="7" height="7" rx="2"/><rect x="4" y="13" width="7" height="7" rx="2"/><rect x="13" y="13" width="7" height="7" rx="2"/>'),
    steps: P('<circle cx="13" cy="4" r="2"/><path d="M10 21l2-6-3-3 2-5 3 2 3 1M9 12l-3 2"/>'),
    utensils: P('<path d="M7 3v8M5 3v5a2 2 0 0 0 4 0V3M7 11v10M17 3c-2 2-3 5-3 8h3v10"/>'),
    dumbbell: P('<path d="M6.5 7v10M3.5 9.5v5M17.5 7v10M20.5 9.5v5M6.5 12h11"/>'),
    play: P('<circle cx="12" cy="12" r="9"/><path d="M10 8.5v7l6-3.5z"/>'),
    target: P('<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>'),
    chat: P('<path d="M4 5h16v11H9l-5 4z"/>'),
    heart: P('<path d="M12 20s-7-4.5-7-10a4 4 0 0 1 7-2.5A4 4 0 0 1 19 10c0 5.5-7 10-7 10z"/>'),
    ticket: P('<path d="M4 8V6h16v2a2 2 0 0 0 0 4v6H4v-6a2 2 0 0 0 0-4zM9 6v12"/>'),
    shield: P('<path d="M12 3l7 3v5c0 5-3 8-7 10-4-2-7-5-7-10V6z"/>'),
    flame: P('<path d="M12 3c1 3 4 4.5 4 8.5A4 4 0 0 1 12 16a4 4 0 0 1-4-4c0-1.5.6-2.6 1.5-3.6C10 9.5 11 8 12 3zM8 15a5 5 0 0 0 8 0"/>'),
    route: P('<circle cx="6" cy="18" r="2"/><circle cx="18" cy="6" r="2"/><path d="M8 18h6a3 3 0 0 0 0-6h-4a3 3 0 0 1 0-6h6"/>'),
    clock: P('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'),
    drop: P('<path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z"/>'),
    book: P('<path d="M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3zM8 4v16"/>'),
    chart: P('<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>'),
    user: P('<circle cx="12" cy="8" r="4"/><path d="M4 21c1-4 4-6 8-6s7 2 8 6"/>'),
    users: P('<circle cx="9" cy="8" r="3.5"/><path d="M2 20c.7-3.5 3.3-5 7-5s6.3 1.5 7 5M16 5a3.5 3.5 0 0 1 0 7M18 15c2 .6 3.5 2 4 5"/>'),
    calendar: P('<rect x="4" y="5" width="16" height="15" rx="3"/><path d="M4 10h16M9 15l2 2 4-4M8 3v4M16 3v4"/>'),
    bell: P('<path d="M6 17v-6a6 6 0 0 1 12 0v6l2 2H4zM10 21h4"/>'),
    gear: P('<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1"/>'),
    scale: P('<rect x="4" y="4" width="16" height="16" rx="4"/><path d="M8 10a4 4 0 0 1 8 0M12 10l2-2"/>'),
  };
  window.FCART = { EX, TINT, exSVG, ICON, find };
})();