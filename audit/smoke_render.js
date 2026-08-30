#!/usr/bin/env node
/* Headless render smoke test: stub DOM, load marts, run app.js against a
   battery of routes, and fail on any 'Render error' or thrown exception.
   Chart calls no-op (ECharts CDN never loads); binder callbacks no-op
   (querySelectorAll returns []). Template/aggregation logic runs for real. */
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');

function makeEl(sel) {
  const el = {
    _sel: sel, innerHTML: '', textContent: '', value: '', style: {}, dataset: {},
    classList: { add(){}, remove(){}, contains(){ return false; } },
    children: [], firstChild: null,
    addEventListener(){}, appendChild(){}, removeChild(){}, remove(){}, scrollIntoView(){},
    setAttribute(){}, getAttribute(){ return null; }, closest(){ return null; },
    querySelector(s){ return makeEl(s); }, querySelectorAll(){ return []; },
    getContext(){ return new Proxy({}, { get: (t,k)=> (k==='canvas'? el : (...a)=>0), set: ()=>true }); },
    getBoundingClientRect(){ return {left:0,top:0,width:100,height:100}; },
  };
  el.firstChild = { innerHTML: '' };
  return el;
}
const byId = new Map();
function getEl(sel) {
  if (!byId.has(sel)) byId.set(sel, makeEl(sel));
  return byId.get(sel);
}

let renderFn = null;
global.window = new Proxy({
  addEventListener(t, fn){ if (t === 'hashchange') renderFn = fn; },
  scrollTo(){}, GAMELOGS_URLS: null,
}, { get(t, k){ return k in t ? t[k] : global[k]; }, set(t, k, v){ t[k] = v; return true; } });
global.document = {
  querySelector: s => getEl(s), getElementById: id => getEl('#' + id),
  createElement: () => makeEl('created'),
  querySelectorAll: () => [],
  head: { appendChild(){} }, body: makeEl('body'),
  addEventListener(){},
};
global.location = { hash: '#/', replace(h){ this.hash=h; } };
global.addEventListener = (t, fn) => { if (t === 'hashchange') renderFn = fn; };
global.CSS = { escape: s => s };
global.performance = { now: () => Date.now() };
global.requestAnimationFrame = fn => fn();
global.fetch = () => new Promise(() => {});   // never resolves; lazy paths stay pending
global.URL = { createObjectURL: () => '', revokeObjectURL(){} };
global.Blob = class {};

const marts = p => JSON.parse(fs.readFileSync(path.join(ROOT, 'data/marts', p)));
const docs = p => JSON.parse(fs.readFileSync(path.join(ROOT, 'docs/data', p)));
window.SAVANT = marts('savant_data.json');
if (fs.existsSync(path.join(ROOT, 'data/marts/explore_data.json'))) window.EXPLORE = marts('explore_data.json');
else { const a=docs('explore_a.json'); a.rows=a.rows.concat(docs('explore_b.json').rows, docs('explore_c.json').rows); window.EXPLORE=a; }
window.LUCK = marts('luck_data.json');
window.LOGOS = {};
window.VALID = { modern_ok: true, fp_recon_n: 0, fp_recon_pct: 0, fp_recon_mad: 0, starter_weeks: 0,
  starter_match_pct: 0, pbp_plays: 0, bridge: { rostered: 0, gsis: 0, dst: 0, quarantined: 0 },
  trades: { events: 0, items_direct: 0, items_inferred: 0, unresolved: 0, custody_confirmed: 0 },
  xfp2: { recon: { mean_abs_diff: 0, pct_within_1: 0, n: 0 }, holdout: [], worst_bias_pct: 0 } };
window.GAMELOGS = fs.existsSync(path.join(ROOT, 'data/marts/gamelogs_data.json')) ? marts('gamelogs_data.json') : docs('gamelogs.json');
Object.assign(global, { SAVANT: window.SAVANT, EXPLORE: window.EXPLORE });

eval(fs.readFileSync(path.join(ROOT, 'site/app.js'), 'utf8'));
if (!renderFn) { console.error('FATAL: hashchange render hook not captured'); process.exit(1); }

const S = window.SAVANT, E = window.EXPLORE;
const eidByPos = {};
for (const p of S.players) {
  if (p.pos && !eidByPos[p.pos] && p.stints.length) eidByPos[p.pos] = p.eid;
}
const dstEid = (S.players.find(p => p.dst) || {}).eid;
const draftOnlyEid = (S.players.find(p => p.draftOnly) || {}).eid;
const tradedEid = (() => { const t = S.trades[0]; return t ? Object.values(t.sides)[0][0] : null; })();
const nflPi = E.players.findIndex(p => p[5] === 0);
const fid = S.franchises[0].franchise_id;

const routes = [
  '#/', '#/franchises', `#/f/${fid}`, '#/players',
  `#/p/${eidByPos.QB}`, `#/p/${eidByPos.RB}`, `#/p/${eidByPos.WR}`, `#/p/${eidByPos.TE}`,
  `#/p/${eidByPos.K}`, `#/p/${dstEid}`, `#/p/${draftOnlyEid}`, `#/p/${tradedEid}`,
  `#/pn/${nflPi}`,
  '#/seasons', '#/s/2026', '#/s/2024', '#/s/2014', '#/drafts', '#/drafts/all', '#/drafts/2014',
  '#/trades', '#/luck', '#/luck/2024', '#/records', '#/boards', '#/boards?dy=0&dpos=RB', '#/boards?m=fp&pos=K',
  '#/compare', '#/methods', '#/explore',
];
let bad = 0;
const appEl = getEl('#app');
for (const r of routes) {
  global.location.hash = r;
  appEl.innerHTML = '';
  try {
    renderFn();
    const html = appEl.innerHTML;
    if (/Render error/.test(html)) { bad++; console.log(`FAIL ${r}: ${html.match(/Render error[^<]*/)[0]}`); }
    else if (!html || html.length < 200) { bad++; console.log(`FAIL ${r}: empty render (${html.length} chars)`); }
    else console.log(`ok   ${r}  (${(html.length/1024).toFixed(0)}KB html)`);
  } catch (e) { bad++; console.log(`THROW ${r}: ${e.message}`); }
}
console.log(bad ? `\n${bad} ROUTES FAILED` : '\nALL ROUTES RENDER CLEAN');
process.exit(bad ? 1 : 0);
