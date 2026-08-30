/* AFFL Savant — single-page application. Data: window.SAVANT, window.EXPLORE, window.VALID */
(function(){
"use strict";
const S = window.SAVANT, E = window.EXPLORE, V = window.VALID || {}, L = window.LUCK || {};
const $ = sel => document.querySelector(sel);
const app = $('#app');

/* ---------------- helpers ---------------- */
const esc = s => s==null ? '' : String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const f0 = v => v==null||isNaN(v) ? '·' : Math.round(v).toLocaleString('en-US');
const f1 = v => v==null||isNaN(v) ? '·' : (Math.round(v*10)/10).toLocaleString('en-US',{minimumFractionDigits:1,maximumFractionDigits:1});
const f2 = v => v==null||isNaN(v) ? '·' : v.toFixed(2);
const pct1 = v => v==null||isNaN(v) ? '·' : (100*v).toFixed(1)+'%';
const signed = (v,f) => v==null||isNaN(v) ? '·' : (v>0?'+':'')+f(v);
const cls = v => v==null||isNaN(v)||v===0 ? '' : (v>0?'posv':'neg');

const F = {}; S.franchises.forEach(f => F[f.franchise_id] = f);
const FIDX = {}; S.franchises.forEach((f,i) => FIDX[f.franchise_id] = i);
const PL = {}; S.players.forEach(p => PL[p.eid] = p);
const YEARS = Object.keys(S.seasons).map(Number).sort((a,b)=>a-b);
const DONE = YEARS.filter(y => S.seasons[y].complete);
const LAST = DONE[DONE.length-1];
const PALETTE = ['#00a2ff','#ff6a00','#c8ff00','#ffc400','#37d67a','#ff4d5e','#b078ff','#00e0d0',
 '#ff9dc7','#7dd3fc','#f97316','#a3e635','#facc15','#34d399','#f87171','#c084fc','#2dd4bf','#fda4af','#93c5fd'];
const fColor = fid => PALETTE[(FIDX[fid]||0) % PALETTE.length];
const teamOf = (s,tid) => (S.seasons[s]||{teams:[]}).teams.find(t=>t.tid===tid);
const teamOfF = (s,fid) => (S.seasons[s]||{teams:[]}).teams.find(t=>t.fid===fid);
const histName = (s,fid) => { const t = teamOfF(s,fid); return t ? t.name : (F[fid]||{}).display_name; };
const initials = n => (n||'?').split(/\s+/).filter(Boolean).map(w=>w[0]).join('').slice(0,3).toUpperCase();

const LOGOS = window.LOGOS || {};
/* Each logo's data URI is emitted exactly ONCE as a CSS class; markup refers by class. */
const logoCls = {};
(function(){
  const rules = [];
  let i = 0;
  for(const [url, uri] of Object.entries(LOGOS)){
    logoCls[url] = 'lg-'+i;
    rules.push(`.lg-${i}{background-image:url("${uri}")}`);
    i++;
  }
  rules.push('.lgbg{background-size:cover;background-position:center;display:inline-block}');
  const st = document.createElement('style');
  st.textContent = rules.join('\n');
  document.head.appendChild(st);
})();
const bestLogo = {};
S.franchises.forEach(f=>{
  const cands = [f.logo_url];
  YEARS.slice().reverse().forEach(y=>{ const t=teamOfF(y,f.franchise_id); if(t&&t.logo) cands.push(t.logo); });
  bestLogo[f.franchise_id] = cands.find(u=>u && LOGOS[u]) || null;
});
function logoHtml(fid, size, seasonCtx){
  const f = F[fid]; if(!f) return '';
  const t = seasonCtx!=null ? teamOfF(seasonCtx,fid) : null;
  const url = [(t&&t.logo), f.logo_url, bestLogo[fid]].find(u=>u && LOGOS[u]);
  const szCls = size==='lg'?'lg':size==='xl'?'xl':'';
  const px = size==='xl'?92:size==='lg'?64:26;
  if(url) return `<span class="logo lgbg ${szCls} ${logoCls[url]}" role="img" aria-label="${esc(f.display_name)} logo"></span>`;
  return `<span class="ini logo ${szCls}" style="background:${fColor(fid)};width:${px}px;height:${px}px;font-size:${size==='xl'?26:size==='lg'?19:11}px">${esc(initials(f.display_name))}</span>`;
}
const frLink = (fid, seasonCtx, nameOverride) => {
  const f = F[fid]; if(!f) return '·';
  const nm = nameOverride || (seasonCtx!=null ? histName(seasonCtx,fid) : f.display_name);
  return `<span class="fr">${logoHtml(fid,'',seasonCtx)}<a class="nm" href="#/f/${fid}">${esc(nm)}</a></span>`;
};
const plLink = eid => { const p = PL[eid]; return p ? `<a href="#/p/${eid}">${esc(p.name)}</a>` : '#'+eid; };
const posChip = p => p ? `<span class="pos">${esc(p)}</span>` : '';

function sortableTable(el){
  el.querySelectorAll('th.sortable').forEach((th)=>{
    th.tabIndex=0; th.role='button';
    const act = ()=>{
      const tb = th.closest('table').tBodies[0];
      const idx = [...th.parentNode.children].indexOf(th);
      const dir = th.dataset.dir==='a'?'d':'a'; th.dataset.dir=dir;
      th.closest('table').querySelectorAll('th').forEach(h=>h.classList.remove('sorted'));
      th.classList.add('sorted');
      [...tb.rows].sort((r1,r2)=>{
        const a=r1.cells[idx].dataset.v ?? r1.cells[idx].textContent, b=r2.cells[idx].dataset.v ?? r2.cells[idx].textContent;
        const na=parseFloat(a), nb=parseFloat(b);
        const c = (!isNaN(na)&&!isNaN(nb)) ? na-nb : String(a).localeCompare(String(b));
        return dir==='a'?c:-c;
      }).forEach(r=>tb.appendChild(r));
    };
    th.addEventListener('click',act);
    th.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();act();}});
  });
}

/* ---------------- chrome + router ---------------- */
const NAV = [['','Home'],['franchises','Franchises'],['players','Players'],['seasons','Seasons'],
 ['drafts','Draft Room'],['trades','Trades'],['luck','Luck & Skill'],['records','Records'],
 ['boards','Leaderboards'],['compare','Compare'],['methods','Methodology'],['explore','Explore']];
function chrome(route){
  $('#nav').innerHTML = NAV.map(([r,l]) =>
    `<a href="#/${r}" class="${r==='explore'?'explore-cta':''} ${route===r||(r&&route.startsWith(r))?'on':''}">${l}</a>`).join('');
}
function render(){
  _charts.forEach(c=>{ try{ c.dispose(); }catch(e){} });
  _charts = [];
  const h = location.hash.replace(/^#\/?/,'');
  const [path, qs] = h.split('?');
  const seg = path.split('/').filter(Boolean);
  const r = seg[0]||'';
  chrome(r);
  window.scrollTo(0,0);
  try{
    if(r==='') home();
    else if(r==='franchises') franchisesView();
    else if(r==='f') franchiseView(seg[1]);
    else if(r==='players') playersView();
    else if(r==='p') playerView(+seg[1]);
    else if(r==='seasons') seasonsView();
    else if(r==='s') seasonView(+seg[1]);
    else if(r==='drafts') draftsView(seg[1]?+seg[1]:null);
    else if(r==='trades') tradesView();
    else if(r==='luck') luckView(seg[1]?+seg[1]:null);
    else if(r==='records') recordsView(qs);
    else if(r==='boards') boardsView(qs);
    else if(r==='compare') compareView(qs);
    else if(r==='methods') methodsView();
    else if(r==='explore') exploreView(qs);
    else home();
  }catch(err){
    app.innerHTML = `<div class="wrap" style="padding:60px 0"><div class="notice">Render error: ${esc(err.message)}</div></div>`;
    console.error(err);
  }
}

/* ---------------- HOME ---------------- */
function champOf(y){ const sd=S.seasons[y]; if(!sd||!sd.complete) return null; return sd.teams.find(t=>t.finalRank===1); }
function home(){
  const champ = champOf(LAST);
  const tl = DONE.map(y=>{ const c=champOf(y); return `<div class="yr"><div class="y">${y}</div><div style="display:flex;justify-content:center;margin:6px 0 4px">${logoHtml(c.fid,'',y)}</div><div class="n">${esc(c.name)}</div></div>`;}).join('');
  const podium = {};
  DONE.forEach(y=>{ (S.seasons[y].teams||[]).forEach(t=>{ if(t.finalRank>=1&&t.finalRank<=3){ const p=podium[t.fid]=podium[t.fid]||[0,0,0]; p[t.finalRank-1]++; } }); });
  const at = S.franchises.filter(f=>f.seasonsPlayed>0).map(f=>{
    const g=f.w+f.l+f.t, wp = g? (f.w+f.t*0.5)/g : 0;
    return {f, g, wp};
  }).sort((a,b)=> (b.f.titles.length-a.f.titles.length) || (b.wp-a.wp));
  const trophyChips = fid=>{ const p=podium[fid]||[0,0,0];
    return [p[0]?`<span class="title-chip" title="championships">🏆${p[0]>1?'×'+p[0]:''}</span>`:'',
            p[1]?`<span class="chip" style="cursor:default;padding:2px 7px" title="runner-up finishes">🥈${p[1]>1?'×'+p[1]:''}</span>`:'',
            p[2]?`<span class="chip" style="cursor:default;padding:2px 7px" title="third-place finishes">🥉${p[2]>1?'×'+p[2]:''}</span>`:''].join(' ')||'·'; };
  const rows = at.map(({f,wp})=>`<tr class="click" data-href="#/f/${f.franchise_id}">
    <td class="l">${frLink(f.franchise_id)}${f.is_active_2026?'':' <span class="badge">alumni</span>'}</td>
    <td data-v="${f.seasonsPlayed}">${f.seasonsPlayed}</td>
    <td class="num" data-v="${f.w}">${f.w}–${f.l}${f.t?'–'+f.t:''}</td>
    <td data-v="${wp}">${pct1(wp)}</td>
    <td data-v="${f.pf}">${f0(f.pf)}</td>
    <td data-v="${f.pa}">${f0(f.pa)}</td>
    <td data-v="${f.pw}">${f.pw}–${f.pl}</td>
    <td class="l" data-v="${f.titles.length*100+(podium[f.franchise_id]||[0,0,0])[1]*10+(podium[f.franchise_id]||[0,0,0])[2]}">${trophyChips(f.franchise_id)}</td>
    <td class="l dim small">${f.titles.join(', ')||''}</td></tr>`).join('');
  const rec = S.records;
  const hi = rec.teamWeekHigh[0], pw = rec.playerWeeks[0], bl = rec.blowouts[0];
  const blH = teamOf(bl.season,bl.h), blA = teamOf(bl.season,bl.a);
  const field26 = S.seasons[2026] ? S.seasons[2026].teams.map(t=>`<span class="chip" style="cursor:default">${logoHtml(t.fid)} ${esc(t.name)}</span>`).join('') : '';
  app.innerHTML = `
  <div class="wrap">
    <div class="hero">
      <div class="kicker">The statistical record of the American Fantasy Football League · ESPN league 51418</div>
      <h1 class="display">AFFL <span style="color:var(--blue)">Savant</span></h1>
      <p class="tag">Twelve seasons of custody-tracked history: every franchise, roster week, auction dollar,
      trade, and NFL snap that mattered — joined at the player level and queryable in <a href="#/explore">Explore</a>.</p>
      <div class="statline">
        <div class="stat"><div class="v">${DONE.length}</div><div class="l">Seasons 2014–${LAST}</div></div>
        <div class="stat"><div class="v">${S.franchises.length}</div><div class="l">Owner franchises</div></div>
        <div class="stat"><div class="v">${f0(E.rows.length)}</div><div class="l">Custody weeks</div></div>
        <div class="stat"><div class="v">${f0(S.players.length)}</div><div class="l">Players held</div></div>
        <div class="stat"><div class="v">${f0(S.drafts.length)}</div><div class="l">Draft picks</div></div>
        <div class="stat"><div class="v">${S.trades.length}</div><div class="l">Executed trades</div></div>
      </div>
    </div>
    <div class="champbar">
      <span class="cup">🏆</span>${logoHtml(champ.fid,'lg',LAST)}
      <div><div class="kicker">Reigning champion · ${LAST}</div>
        <div style="font-family:'Barlow Condensed';font-weight:800;font-size:30px">${esc(champ.name)}</div>
        <div class="muted small">${esc((F[champ.fid]||{}).owners?.join(', ')||'')} · ${champ.w}–${champ.l} · ${f1(champ.pf)} PF</div></div>
      <a class="btn" style="margin-left:auto" href="#/s/${LAST}">Season page →</a>
    </div>
    <h2 class="sect">Championship timeline</h2>
    <div class="timeline">${tl}</div>
    <h2 class="sect">All-time franchise table <span class="sub">regular season 2014–${LAST} · playoff W–L is winners-bracket only</span></h2>
    <div class="tblwrap"><table class="tbl"><thead><tr>
      <th class="l sortable">Franchise</th><th class="sortable">Seasons</th><th class="sortable">Record</th>
      <th class="sortable">Win%</th><th class="sortable">PF</th><th class="sortable">PA</th>
      <th class="sortable">Playoffs</th><th class="l sortable">Trophy case</th><th class="l">Years</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
    <h2 class="sect">Franchise trajectories <span class="sub">every franchise, every season — pick the lens · alumni start hidden, click the legend</span></h2>
    <div class="presets" id="trajtabs">${TRAJ.map((t,i)=>`<span class="chip ${i===0?'on lime':''}" data-traj="${t.k}" style="cursor:pointer">${t.l}</span>`).join('')}</div>
    ${chartBox('trajchart', 430)}
    <p class="dim small" style="margin-top:6px" id="trajnote"></p>
    <h2 class="sect">League eras <span class="sub">scoring and parity by season</span></h2>
    ${chartBox('trendchart', 290)}
    <p class="dim small" style="margin-top:6px">The shaded band spans the best and worst team PPG each season — a narrow band is a tight league; dashed lines are the season's ceiling and floor teams.</p>
    <h2 class="sect">Record book highlights</h2>
    <div class="grid g3">
      <div class="card"><div class="kicker">Highest team week</div>
        <div class="stat"><div class="v">${f1(hi.points)}</div></div>
        <div>${frLink(hi.fid, hi.season)}</div><div class="dim small">${hi.season} · Week ${hi.week}</div></div>
      <div class="card"><div class="kicker">Best started player week</div>
        <div class="stat"><div class="v">${f1(pw.pts)}</div></div>
        <div>${plLink(pw.eid)} ${posChip((PL[pw.eid]||{}).pos)}</div>
        <div class="dim small">for ${esc(histName(pw.s,pw.fid))} · ${pw.s} Wk ${pw.w}</div></div>
      <div class="card"><div class="kicker">Biggest blowout</div>
        <div class="stat"><div class="v">${f1(Math.abs(bl.hs-bl.as_))}</div></div>
        <div class="small">${esc(blH.name)} ${f1(bl.hs)} — ${f1(bl.as_)} ${esc(blA.name)}</div>
        <div class="dim small">${bl.season} · MP ${bl.mp} · <a href="#/records">full record book →</a></div></div>
    </div>
    <h2 class="sect">Ask the archive <span class="sub">saved Explore queries over real custody data</span></h2>
    <div class="presets">${PRESETS.map(p=>`<a class="chip" href="#/explore?q=${encState(Object.assign(defState(),p.state))}">${p.icon} ${p.label}</a>`).join('')}</div>
    <h2 class="sect">2026 planning field <span class="sub">registered, pre-draft — contributes nothing to history yet</span></h2>
    <div class="pill-scroll">${field26}</div>
  </div>`;
  bindRows(); sortableTable(app);
  app.querySelectorAll('[data-traj]').forEach(c=>c.onclick=()=>{
    app.querySelectorAll('[data-traj]').forEach(x=>x.classList.remove('on','lime'));
    c.classList.add('on','lime');
    drawTraj(c.dataset.traj);
  });
  drawTraj('rating');
  drawLeagueTrend();
}
function bindRows(){ app.querySelectorAll('tr.click').forEach(tr=>tr.addEventListener('click',e=>{ if(e.target.closest('a'))return; location.hash = tr.dataset.href; })); }

/* ---------------- CHARTS (ECharts via CDN, lazy-loaded) ---------------- */
let _charts = [];
let _ecPromise = null;
function withEC(fn){
  if(window.echarts) return fn(window.echarts);
  if(!_ecPromise){
    _ecPromise = new Promise(res=>{
      const s = document.createElement('script');
      s.src = 'https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js';
      s.onload = ()=>res(window.echarts);
      s.onerror = ()=>res(null);
      document.head.appendChild(s);
    });
  }
  _ecPromise.then(ec=>{
    if(ec) fn(ec);
    else document.querySelectorAll('.chartbox').forEach(b=>{
      if(!b.dataset.failed){ b.dataset.failed=1; b.innerHTML='<p class="dim small" style="padding:22px">Charts need the ECharts CDN and it is unreachable right now — every number in them also lives in the tables on this page.</p>'; }
    });
  });
}
function mkChart(id, option, onInit){
  withEC(ec=>{
    const el = document.getElementById(id);
    if(!el) return;                                   // user navigated away
    const old = ec.getInstanceByDom(el);
    if(old) old.dispose();
    const c = ec.init(el, null, {renderer:'canvas'});
    c.setOption(option);
    _charts.push(c);
    if(onInit) onInit(c);
  });
}
addEventListener('resize', ()=>_charts.forEach(c=>{ try{ c.resize(); }catch(e){} }));
const ECX  = o=>Object.assign({type:'category', axisLine:{lineStyle:{color:'#26314a'}}, axisTick:{show:false},
  axisLabel:{color:'#8fa2bd', fontFamily:'IBM Plex Mono', fontSize:10.5}}, o||{});
const ECY  = o=>Object.assign({type:'value', axisLine:{show:false}, axisTick:{show:false}, scale:true,
  axisLabel:{color:'#8fa2bd', fontFamily:'IBM Plex Mono', fontSize:10.5}, splitLine:{lineStyle:{color:'#1a2334'}}}, o||{});
const ECTT = o=>Object.assign({trigger:'axis', backgroundColor:'#10141f', borderColor:'#2a3550', borderWidth:1,
  textStyle:{color:'#e6eefc', fontSize:12, fontFamily:'Inter'}, confine:true}, o||{});
const chartBox = (id, h)=>`<div class="card chartbox" style="padding:12px 10px 6px"><div id="${id}" style="width:100%;height:${h}px"></div></div>`;

/* -- franchise trajectories (League Legacy 'League Ratings' equivalent) -- */
const TRAJ = [
 {k:'rating', l:'League Rating', fmt:f0, note:'ELO, K=24, 1500 base (rating_v1)',
  get:(fid,y)=>{ const e=(L.rating&&L.rating[fid]||[]).find(x=>x.s===y); return e?e.r:null; }},
 {k:'ppg', l:'PPG', fmt:f1, ts:'ppg', note:'points per game, regular season'},
 {k:'ap', l:'All-play win %', fmt:pct1, ts:'apPct', note:'schedule-free scoring rank (allplay_v1)'},
 {k:'rank', l:'Final rank', fmt:f0, inv:true, note:'final standings placement (1 = champion)',
  get:(fid,y)=>{ const t=teamOfF(y,fid); return t&&t.finalRank?t.finalRank:null; }},
 {k:'luck', l:'Luck', fmt:v=>signed(v,f1), note:'actual wins − all-play expected wins', ts:'luck'},
 {k:'sos', l:'Opp PPG (SOS)', fmt:f1, ts:'sos', note:'average opponent score faced'},
 {k:'share', l:'Points share', fmt:pct1, note:'share of all points scored that season',
  get:(fid,y)=>{ const rows=(L.teamSeason||[]).filter(r=>r.s===y); const me=rows.find(r=>r.fid===fid);
    if(!me) return null; const tot=rows.reduce((a,b)=>a+(b.pf||0),0); return tot? me.pf/tot : null; }},
];
function drawTraj(mk){
  const m = TRAJ.find(t=>t.k===mk)||TRAJ[0];
  const tsIdx = {}; (L.teamSeason||[]).forEach(r=>tsIdx[r.fid+'|'+r.s]=r);
  const get = m.get || ((fid,y)=>{ const r=tsIdx[fid+'|'+y]; const v=r?r[m.ts]:null; return v==null?null:+v; });
  const fs = S.franchises.filter(f=>f.seasonsPlayed>0);
  const selected = {}; fs.forEach(f=>selected[f.display_name]=!!f.is_active_2026);
  mkChart('trajchart', {
    color: fs.map(f=>fColor(f.franchise_id)),
    tooltip: ECTT({valueFormatter:v=>v==null?'·':m.fmt(v), order:'valueDesc'}),
    legend: {type:'scroll', top:0, textStyle:{color:'#9fb0c8', fontSize:11}, inactiveColor:'#39445e',
             pageTextStyle:{color:'#9fb0c8'}, pageIconColor:'#8fa2bd', selected},
    grid: {left:54, right:20, top:56, bottom:28},
    xAxis: ECX({data:DONE, boundaryGap:false}),
    yAxis: ECY(m.inv?{inverse:true, minInterval:1, min:1}:{}),
    series: fs.map(f=>({name:f.display_name, type:'line', smooth:.3, connectNulls:false,
      symbol:'circle', symbolSize:5.5, lineStyle:{width:2},
      emphasis:{focus:'series', lineStyle:{width:3.5}},
      data: DONE.map(y=>{ const v=get(f.franchise_id,y); return v==null?null:(m.k==='ap'||m.k==='share'? +(100*v).toFixed(2) : v); }),
    })),
  });
  const note = $('#trajnote'); if(note) note.textContent = m.note + (m.k==='ap'||m.k==='share'?' · values in %':'');
}

/* -- league scoring & parity by season -- */
function drawLeagueTrend(){
  const ys = DONE;
  const rows = y=>(L.teamSeason||[]).filter(r=>r.s===y && r.ppg!=null);
  const mean = ys.map(y=>{ const r=rows(y); return r.length? +(r.reduce((a,b)=>a+b.ppg,0)/r.length).toFixed(1):null; });
  const lo = ys.map(y=>{ const r=rows(y); return r.length? Math.min(...r.map(x=>x.ppg)):null; });
  const hi = ys.map(y=>{ const r=rows(y); return r.length? Math.max(...r.map(x=>x.ppg)):null; });
  const band = ys.map((y,i)=>hi[i]!=null?+(hi[i]-lo[i]).toFixed(1):null);
  mkChart('trendchart', {
    tooltip: ECTT({formatter: ps=>{ const i=ps[0].dataIndex;
      return `<b>${ys[i]}</b><br>League PPG: <b>${f1(mean[i])}</b><br>Best team: ${f1(hi[i])} · Worst: ${f1(lo[i])}<br>Spread (parity): <b>${f1(band[i])}</b>`; }}),
    grid: {left:54, right:20, top:30, bottom:28},
    xAxis: ECX({data:ys, boundaryGap:false}),
    yAxis: ECY(),
    series: [
      {name:'floor', type:'line', data:lo, stack:'band', lineStyle:{opacity:0}, symbol:'none', silent:true},
      {name:'spread', type:'line', data:band, stack:'band', lineStyle:{opacity:0}, symbol:'none', silent:true,
       areaStyle:{color:'rgba(0,162,255,.10)'}},
      {name:'League PPG', type:'line', data:mean, smooth:.3, symbol:'circle', symbolSize:6,
       lineStyle:{width:2.5, color:'#00a2ff'}, itemStyle:{color:'#00a2ff'}},
      {name:'Best team PPG', type:'line', data:hi, smooth:.3, symbol:'none', lineStyle:{width:1, type:'dashed', color:'#37d67a'}},
      {name:'Worst team PPG', type:'line', data:lo, smooth:.3, symbol:'none', lineStyle:{width:1, type:'dashed', color:'#ff4d5e'}},
    ],
  });
}

/* -- rivalries: pair aggregation + active streaks from matchups -- */
function pairStats(){
  const seen = new Set(), pairs = [];
  Object.keys(S.h2h).forEach(k=>{
    const [a,b] = k.split('|');
    const key = a<b? a+'|'+b : b+'|'+a;
    if(seen.has(key)) return; seen.add(key);
    const r = S.h2h[a+'|'+b]; if(!r) return;
    const g = r.w+r.l+r.t; if(!g) return;
    pairs.push({a, b, g, aw:r.w, bw:r.l, t:r.t, apf:r.pf, bpf:r.pa});
  });
  // chronological per-pair winner runs for active streaks
  const runs = {};
  S.matchups.filter(m=>!m.po&&!m.bye&&m.hs!=null&&m.winner&&m.winner!=='UNDECIDED')
    .sort((x,y)=>x.season-y.season||x.mp-y.mp).forEach(m=>{
      const hf=fid_of(m.season,m.h), af=fid_of(m.season,m.a);
      if(!hf||!af) return;
      const key = hf<af? hf+'|'+af : af+'|'+hf;
      const winner = m.winner==='TIE'? null : (m.winner==='HOME'? hf : af);
      const cur = runs[key];
      if(winner==null){ runs[key]=null; return; }
      if(cur && cur.fid===winner) cur.n++;
      else runs[key] = {fid:winner, n:1};
    });
  pairs.forEach(p=>{ p.live = runs[p.a<p.b?p.a+'|'+p.b:p.b+'|'+p.a] || null; });
  return pairs;
}
function fid_of(s, tid){ const t = teamOf(s, tid); return t? t.fid : null; }

/* -- franchise weekly score heartbeat -- */
function drawFrHeartbeat(fid){
  const xs=[], mine=[], med=[];
  (L.rankHeat||[]).forEach(rh=>{
    const t = rh.teams.find(x=>x.fid===fid);
    rh.weeks.forEach((w,i)=>{
      const all = rh.teams.map(tt=>(tt.scores||[])[i]).filter(v=>v!=null).sort((a,b)=>a-b);
      if(!all.length) return;
      xs.push(rh.s+' W'+w);
      med.push(all[Math.floor(all.length/2)]);
      mine.push(t? (t.scores||[])[i] : null);
    });
  });
  if(!mine.some(v=>v!=null)) return;
  const seasonMarks = [];
  xs.forEach((x,i)=>{ if(x.endsWith(' W1')) seasonMarks.push({xAxis:i}); });
  mkChart('frheart', {
    tooltip: ECTT({}),
    grid: {left:50, right:16, top:30, bottom:26},
    xAxis: ECX({data:xs, axisLabel:{color:'#8fa2bd', fontSize:9.5, interval:(i,v)=>v.endsWith(' W1')&&(+v.slice(0,4))%2===0, formatter:v=>v.slice(0,4)}}),
    yAxis: ECY(),
    series: [
      {name:'League median', type:'line', data:med, symbol:'none', lineStyle:{width:1, color:'#5f7089', opacity:.55}, z:1},
      {name:'Weekly score', type:'line', data:mine, symbol:'none', connectNulls:false,
       lineStyle:{width:1.8, color:fColor(fid)}, z:3,
       markLine:{silent:true, symbol:'none', label:{show:false}, lineStyle:{color:'#26314a', width:1}, data:seasonMarks}},
    ],
  });
}

/* -- franchise skill radar (percentiles among franchises, min 2 seasons) -- */
function franchiseRadarData(){
  const pool = S.franchises.filter(f=>f.seasonsPlayed>=2);
  const lf = {}; (L.franchise||[]).forEach(r=>lf[r.fid]=r);
  const le = {}; (L.lineupFranchise||[]).forEach(r=>le[r.fid]=r);
  const draft = {}, trade = {};
  S.drafts.forEach(d=>{ if(d.bid>0&&d.par!=null){ const o=draft[d.fid]=draft[d.fid]||{par:0,bid:0}; o.par+=d.par; o.bid+=d.bid; } });
  S.trades.forEach(t=>Object.entries(t.alpha||{}).forEach(([fid,a])=>{ trade[fid]=(trade[fid]||0)+a; }));
  const raw = {};
  pool.forEach(f=>{
    const g=f.w+f.l+f.t, k=f.franchise_id;
    raw[k] = {
      ppg: g? f.pf/g : null,
      ap: (lf[k]||{}).apPct,
      eff: (le[k]||{}).eff,
      draft: draft[k]? draft[k].par/draft[k].bid : null,
      trade: trade[k]!=null? trade[k] : null,
      po: f.seasonsPlayed? (f.pw+f.pl>0? f.pw/(f.pw+f.pl||1) : 0) : null,
    };
  });
  const pct = key=>{
    const vals = pool.map(f=>raw[f.franchise_id][key]).filter(v=>v!=null).sort((a,b)=>a-b);
    return v=> v==null||!vals.length? null : Math.round(100*vals.filter(x=>x<=v).length/vals.length);
  };
  return {raw, P:{ppg:pct('ppg'), ap:pct('ap'), eff:pct('eff'), draft:pct('draft'), trade:pct('trade'), po:pct('po')}};
}
const RADAR_AXES = [['ppg','Scoring (PPG)'],['ap','All-play W%'],['eff','Lineup eff'],['draft','Draft PAR/$'],['trade','Trade α'],['po','Playoff W%']];
function drawFrRadar(fid){
  const {raw, P} = franchiseRadarData();
  const me = raw[fid]; if(!me) return;
  const vals = RADAR_AXES.map(([k])=>{ const p=P[k](me[k]); return p==null?0:p; });
  mkChart('frradar', {
    tooltip: ECTT({trigger:'item', formatter:()=>RADAR_AXES.map(([k,l],i)=>`${l}: <b>${vals[i]}</b>th pct`).join('<br>')}),
    radar: {indicator: RADAR_AXES.map(([k,l])=>({name:l, max:100})), radius:'62%',
      axisName:{color:'#9fb0c8', fontSize:10.5}, splitArea:{areaStyle:{color:['rgba(255,255,255,.015)','rgba(255,255,255,.03)']}},
      axisLine:{lineStyle:{color:'#26314a'}}, splitLine:{lineStyle:{color:'#26314a'}}},
    series: [{type:'radar', data:[{value:vals, name:'percentile'}],
      areaStyle:{color:fColor(fid)+'44'}, lineStyle:{color:fColor(fid), width:2}, itemStyle:{color:fColor(fid)}, symbolSize:4}],
  });
}

/* -- franchise ELO trajectory -- */
function drawFrRating(fid){
  const s = (L.rating&&L.rating[fid])||[]; if(s.length<2) return;
  mkChart('frrating', {
    tooltip: ECTT({valueFormatter:f0}),
    grid: {left:52, right:16, top:24, bottom:26},
    xAxis: ECX({data:s.map(x=>x.s)}),
    yAxis: ECY(),
    series: [{name:'League Rating', type:'line', data:s.map(x=>x.r), smooth:.3, symbol:'circle', symbolSize:6,
      lineStyle:{width:2.5, color:fColor(fid)}, itemStyle:{color:fColor(fid)},
      markLine:{symbol:'none', lineStyle:{color:'#5f7089', type:'dashed'}, label:{color:'#8fa2bd', fontFamily:'IBM Plex Mono', fontSize:10, formatter:'1500'}, data:[{yAxis:1500}]}}],
  });
}

/* -- season race: cumulative PF by week -- */
function drawSeasonRace(y){
  const rh = (L.rankHeat||[]).find(x=>x.s===y); if(!rh) return;
  const series = rh.teams.map(t=>{
    let acc=0;
    const data = t.ranks.map((_,i)=>{ const v=(t.scores||[])[i]; if(v!=null) acc+=v; return +acc.toFixed(1); });
    return {name: histName(y, t.fid)||t.fid, type:'line', smooth:.15, symbol:'none', lineStyle:{width:2},
      emphasis:{focus:'series', lineStyle:{width:3.5}}, data, _fid:t.fid};
  }).sort((a,b)=>b.data[b.data.length-1]-a.data[a.data.length-1]);
  mkChart('racechart', {
    color: series.map(s=>fColor(s._fid)),
    tooltip: ECTT({order:'valueDesc', valueFormatter:f1}),
    legend: {type:'scroll', top:0, textStyle:{color:'#9fb0c8', fontSize:10.5}, inactiveColor:'#39445e', pageTextStyle:{color:'#9fb0c8'}},
    grid: {left:56, right:18, top:52, bottom:26},
    xAxis: ECX({data: rh.weeks.map(w=>'W'+w)}),
    yAxis: ECY({scale:false}),
    series,
  });
}

/* -- draft: price vs PAR scatter + spend mix -- */
const POS_COLOR = {QB:'#ff4d5e', RB:'#37d67a', WR:'#00a2ff', TE:'#ffc400', K:'#8fa2bd', 'D/ST':'#b078ff'};
function drawDraftScatter(y){
  const picks = S.drafts.filter(d=>d.s===y && d.bid>0 && d.par!=null);
  if(!picks.length) return;
  const byPos = {};
  picks.forEach(d=>{ const p=(PL[d.eid]||{}).pos||'?'; (byPos[p]=byPos[p]||[]).push(d); });
  mkChart('draftscatter', {
    tooltip: ECTT({trigger:'item', formatter:p=>{ const d=p.data[2];
      return `<b>${esc((PL[d.eid]||{}).name||d.eid)}</b> · ${esc((PL[d.eid]||{}).pos||'')}<br>$${d.bid} → ${signed(d.par,f1)} PAR<br><span style="color:#8fa2bd">${esc((F[d.fid]||{}).display_name||'')}${d.keeper?' · keeper':''}</span>`; }}),
    legend: {top:0, textStyle:{color:'#9fb0c8', fontSize:11}},
    grid: {left:54, right:20, top:34, bottom:40},
    xAxis: Object.assign(ECY({name:'auction price $', nameLocation:'middle', nameGap:26, nameTextStyle:{color:'#8fa2bd'}}), {scale:false}),
    yAxis: ECY({name:'draft PAR', nameTextStyle:{color:'#8fa2bd'}}),
    series: Object.entries(byPos).map(([pos, ds])=>({name:pos, type:'scatter', symbolSize:7.5,
      itemStyle:{color:POS_COLOR[pos]||'#8fa2bd', opacity:.85},
      data: ds.map(d=>[d.bid, d.par, d]) })),
  });
}
function drawSpendMix(){
  const ys = DONE.filter(y=>S.seasons[y].auction);
  const POSL = ['QB','RB','WR','TE','K','D/ST'];
  const tot = {}, spend = {};
  S.drafts.forEach(d=>{ if(d.bid>0 && S.seasons[d.s] && S.seasons[d.s].auction){
    const p=(PL[d.eid]||{}).pos; if(!POSL.includes(p)) return;
    tot[d.s]=(tot[d.s]||0)+d.bid; spend[d.s+'|'+p]=(spend[d.s+'|'+p]||0)+d.bid; } });
  mkChart('spendmix', {
    tooltip: ECTT({valueFormatter:v=>v+'%'}),
    legend: {top:0, textStyle:{color:'#9fb0c8', fontSize:11}},
    grid: {left:44, right:18, top:34, bottom:26},
    xAxis: ECX({data:ys}),
    yAxis: ECY({scale:false, max:100, axisLabel:{formatter:'{value}%', color:'#8fa2bd', fontFamily:'IBM Plex Mono', fontSize:10.5}}),
    series: POSL.map(p=>({name:p, type:'bar', stack:'s', barWidth:'62%',
      itemStyle:{color:POS_COLOR[p]},
      data: ys.map(y=>tot[y]? +(100*(spend[y+'|'+p]||0)/tot[y]).toFixed(1) : null)})),
  });
}

/* -- league score distribution -- */
function drawScoreHist(){
  const all = [];
  (L.rankHeat||[]).forEach(rh=>rh.teams.forEach(t=>(t.scores||[]).forEach(v=>{ if(v!=null) all.push(v); })));
  if(!all.length) return;
  const lo = Math.floor(Math.min(...all)/10)*10, hi = Math.ceil(Math.max(...all)/10)*10;
  const bins = [], counts = [];
  for(let b=lo;b<hi;b+=10){ bins.push(b+'–'+(b+10)); counts.push(all.filter(v=>v>=b&&v<b+10).length); }
  const mean = all.reduce((a,b)=>a+b,0)/all.length;
  const sorted=[...all].sort((a,b)=>a-b), median=sorted[Math.floor(all.length/2)];
  mkChart('scorehist', {
    tooltip: ECTT({}),
    grid: {left:50, right:16, top:30, bottom:40},
    xAxis: ECX({data:bins, axisLabel:{rotate:38, color:'#8fa2bd', fontFamily:'IBM Plex Mono', fontSize:9.5}}),
    yAxis: ECY({scale:false}),
    series: [{name:'team-weeks', type:'bar', barWidth:'82%', data:counts,
      itemStyle:{color:'rgba(0,162,255,.55)', borderColor:'#00a2ff', borderWidth:.5},
      markLine:{symbol:'none', lineStyle:{color:'#ffc400'}, label:{color:'#ffc400', fontFamily:'IBM Plex Mono', fontSize:10},
        data:[{xAxis:bins.findIndex(b=>+b.split('–')[0]<=mean&&mean<+b.split('–')[0]+10), label:{formatter:'mean '+f1(mean)}}]}}],
  });
  const el = $('#histnote'); if(el) el.textContent = `${f0(all.length)} regular-season team-weeks 2014–${LAST} · mean ${f1(mean)} · median ${f1(median)} · min ${f1(sorted[0])} · max ${f1(sorted[sorted.length-1])}`;
}

/* -- compare radar (percentile within own position, careers min 16 g) -- */
function drawCmpRadar(sel, rowsBy){
  const axes = [['fpg','FP/g'],['xfpg','xFP/g'],['fpoeg','FPOE/g'],['afpoe','adj FPOE'],['tdg','TD/g'],['volg','Touches/g']];
  const careerOf = rs=>{
    const c={g:0,fp:0,xfp2:0,fpoe2:0,afpoe2:0,td:0,vol:0};
    rs.forEach(r=>{ c.g+=r[SCOL.g]||0; c.fp+=r[SCOL.fp]||0; c.xfp2+=r[SCOL.xfp2]||0; c.fpoe2+=r[SCOL.fpoe2]||0; c.afpoe2+=r[SCOL.afpoe2]||0;
      c.td+=(r[SCOL.ptd]||0)+(r[SCOL.rtd]||0)+(r[SCOL.rectd]||0);
      c.vol+=(r[SCOL.car]||0)+(r[SCOL.tgt]||0)+(r[SCOL.db]||0); });
    return c.g<16? null : {fpg:c.fp/c.g, xfpg:c.xfp2/c.g, fpoeg:c.fpoe2/c.g, afpoe:c.afpoe2, tdg:c.td/c.g, volg:c.vol/c.g, g:c.g};
  };
  const byPos = {};
  const byPlayer = {};
  E.seasonRows.forEach(r=>{ (byPlayer[r[SCOL.p]]=byPlayer[r[SCOL.p]]||[]).push(r); });
  Object.entries(byPlayer).forEach(([pi, rs])=>{
    const pos = EPOS[pi]; if(!pos) return;
    const c = careerOf(rs); if(!c) return;
    (byPos[pos]=byPos[pos]||[]).push(c);
  });
  const pctIn = (pos, key, v)=>{
    const vals = (byPos[pos]||[]).map(c=>c[key]).filter(x=>x!=null).sort((a,b)=>a-b);
    return !vals.length||v==null? 0 : Math.round(100*vals.filter(x=>x<=v).length/vals.length);
  };
  const data = sel.map(pi=>{
    const c = careerOf(rowsBy.get(pi)||[]); const pos = EPOS[pi];
    if(!c) return null;
    return {name: ENAME[pi], value: axes.map(([k])=>pctIn(pos,k,c[k]))};
  }).filter(Boolean);
  if(data.length<2) return;
  const colors = ['#00a2ff','#ff6a00','#c8ff00','#b078ff'];
  mkChart('cmpradar', {
    tooltip: ECTT({trigger:'item', formatter:p=>`<b>${esc(p.name)}</b><br>`+axes.map(([k,l],i)=>`${l}: <b>${p.value[i]}</b>th`).join('<br>')}),
    legend: {top:0, textStyle:{color:'#9fb0c8', fontSize:11}},
    color: colors,
    radar: {indicator: axes.map(([k,l])=>({name:l, max:100})), radius:'58%',
      axisName:{color:'#9fb0c8', fontSize:10.5}, splitArea:{areaStyle:{color:['rgba(255,255,255,.015)','rgba(255,255,255,.03)']}},
      axisLine:{lineStyle:{color:'#26314a'}}, splitLine:{lineStyle:{color:'#26314a'}}},
    series: [{type:'radar', data: data.map((d,i)=>({name:d.name, value:d.value,
      areaStyle:{color:colors[i%4]+'22'}, lineStyle:{width:2}, symbolSize:4}))}],
  });
}

/* ---------------- FRANCHISES ---------------- */
function franchisesView(){
  const cards = S.franchises.map(f=>{
    const g=f.w+f.l+f.t, wp=g?(f.w+0.5*f.t)/g:0;
    return `<div class="card" style="display:flex;gap:14px;align-items:center;cursor:pointer" onclick="location.hash='#/f/${f.franchise_id}'">
      ${logoHtml(f.franchise_id,'lg')}
      <div style="min-width:0">
        <div style="font-family:'Barlow Condensed';font-weight:700;font-size:21px">${esc(f.display_name)} ${f.glyph?`<span class="glyph">${esc(f.glyph)}</span>`:''}</div>
        <div class="dim small">${esc(f.owners.join(', '))} · ${f.first_season}–${f.last_season}${f.is_active_2026?'':' · alumni'}</div>
        <div class="small muted num">${f.w}–${f.l}${f.t?'–'+f.t:''} (${pct1(wp)}) · ${f.titles.length? '🏆 '.repeat(f.titles.length):'no titles'}</div>
      </div></div>`;
  }).join('');
  /* rivalries: pair-level aggregates + active runs */
  const ps = pairStats();
  const named = p=>({...p, an:(F[p.a]||{}).display_name||p.a, bn:(F[p.b]||{}).display_name||p.b});
  const q = ps.filter(p=>p.g>=8).map(named);
  const lop = [...q].sort((x,y)=>Math.abs((y.aw+0.5*y.t)/y.g-.5)-Math.abs((x.aw+0.5*x.t)/x.g-.5))[0];
  const even = [...q].sort((x,y)=>(Math.abs((x.aw+0.5*x.t)/x.g-.5)-Math.abs((y.aw+0.5*y.t)/y.g-.5))||(y.g-x.g))[0];
  const most = [...ps.map(named)].sort((x,y)=>y.g-x.g)[0];
  const marg = [...q].sort((x,y)=>Math.abs(y.apf-y.bpf)/y.g-Math.abs(x.apf-x.bpf)/x.g)[0];
  const shoot = [...q].sort((x,y)=>(y.apf+y.bpf)/y.g-(x.apf+x.bpf)/x.g)[0];
  const live = [...ps.map(named)].filter(p=>p.live&&p.live.n>=3).sort((x,y)=>y.live.n-x.live.n)[0];
  const rc = (icon,title,body,sub)=>`<div class="card"><div class="kicker">${icon} ${title}</div>
    <div style="font-family:'Barlow Condensed';font-weight:700;font-size:19px;margin:6px 0 2px">${body}</div>
    <div class="dim small">${sub}</div></div>`;
  const lopW = lop && ((lop.aw+0.5*lop.t)/lop.g>=.5? {w:lop.an, l:lop.bn, r:`${lop.aw}–${lop.bw}${lop.t?'–'+lop.t:''}`, p:(lop.aw+0.5*lop.t)/lop.g} : {w:lop.bn, l:lop.an, r:`${lop.bw}–${lop.aw}${lop.t?'–'+lop.t:''}`, p:(lop.bw+0.5*lop.t)/lop.g});
  const rivalCards = [
    lop? rc('👑','Most lopsided rivalry', `${esc(lopW.w)} owns ${esc(lopW.l)}`, `${lopW.r} · ${pct1(lopW.p)} win rate · min 8 meetings`):'',
    even? rc('⚖','Dead-even series', `${esc(even.an)} vs ${esc(even.bn)}`, `${even.aw}–${even.bw}${even.t?'–'+even.t:''} across ${even.g} meetings`):'',
    most? rc('🔁','Most meetings', `${esc(most.an)} vs ${esc(most.bn)}`, `${most.g} regular-season games since 2014`):'',
    marg? rc('💪','Widest average margin', `${esc(marg.apf>marg.bpf?marg.an:marg.bn)} by ${f1(Math.abs(marg.apf-marg.bpf)/marg.g)}/game`, `${f1(marg.apf/marg.g)} – ${f1(marg.bpf/marg.g)} average score, ${marg.g} meetings`):'',
    shoot? rc('🎆','Highest-scoring series', `${esc(shoot.an)} vs ${esc(shoot.bn)}`, `${f1((shoot.apf+shoot.bpf)/shoot.g)} combined points per meeting`):'',
    live? rc('🔥','Longest active run', `${esc((F[live.live.fid]||{}).display_name)} · ${live.live.n} straight`, `over ${esc(live.live.fid===live.a?live.bn:live.an)}, and counting`):'',
  ].join('');
  /* H2H grid, ordered by all-time win% */
  const ordered = S.franchises.filter(f=>f.seasonsPlayed>0)
    .sort((a,b)=>((b.w+0.5*b.t)/Math.max(1,b.w+b.l+b.t))-((a.w+0.5*a.t)/Math.max(1,a.w+a.l+a.t)));
  const gHdr = ordered.map(f=>`<th class="rot" title="${esc(f.display_name)}">${esc(f.code||'')}</th>`).join('');
  const gRows = ordered.map(me=>{
    const cells = ordered.map(op=>{
      if(op.franchise_id===me.franchise_id) return '<td class="dim">—</td>';
      const r = S.h2h[me.franchise_id+'|'+op.franchise_id];
      if(!r||(r.w+r.l+r.t)===0) return '<td class="dim">·</td>';
      const g = r.w+r.l+r.t, wp = (r.w+0.5*r.t)/g;
      const a = Math.min(0.14+g/28, 0.55)*Math.min(Math.abs(wp-.5)*4,1);
      const bg = wp>0.5? `rgba(55,214,122,${a})` : wp<0.5? `rgba(255,77,94,${a})` : 'transparent';
      return `<td style="background:${bg}" title="${esc(me.display_name)} vs ${esc(op.display_name)}: ${r.w}–${r.l}${r.t?'–'+r.t:''} · ${f1(r.pf)}–${f1(r.pa)} pts">${r.w}–${r.l}</td>`;
    }).join('');
    return `<tr><td class="l stick">${frLink(me.franchise_id)}</td>${cells}</tr>`;
  }).join('');
  app.innerHTML = `<div class="wrap"><div class="hero"><div class="kicker">Owner-continuity identities · ESPN slots are not franchises</div>
    <h1 class="display">Franchises</h1></div><div class="grid g2">${cards}</div>
    <h2 class="sect">Rivalries <span class="sub">pair records, regular season 2014–${LAST}</span></h2>
    <div class="grid g3">${rivalCards}</div>
    <h2 class="sect">Head-to-head grid <span class="sub">row's record vs column · shading = dominance × meetings</span></h2>
    <div class="tblwrap mtx"><table class="tbl mono"><thead><tr><th class="l stick">Franchise</th>${gHdr}</tr></thead><tbody>${gRows}</tbody></table></div>
    <p class="dim small" style="margin-top:8px">Hover a cell for the full series line. Every pairing that ever met is here — including alumni fossils.</p>
  </div>`;
}

function franchiseView(fid){
  const f = F[fid]; if(!f){ app.innerHTML='<div class="wrap"><p style="padding:40px 0">Unknown franchise.</p></div>'; return; }
  const seasonsRows = f.seasons.filter(y=>S.seasons[y]).map(y=>{
    const t = teamOfF(y,fid); if(!t) return '';
    const sd = S.seasons[y];
    const fin = !sd.complete ? '<span class="badge yellow">pre-draft</span>' :
      t.finalRank===1?'<span class="title-chip">🏆 Champion</span>': t.finalRank?('#'+t.finalRank):'·';
    return `<tr class="click" data-href="#/s/${y}"><td class="l num">${y}</td>
      <td class="l">${logoHtml(fid,'',y)} ${esc(t.name)}</td>
      <td>${sd.complete?`${t.w}–${t.l}${t.t?'–'+t.t:''}`:'·'}</td>
      <td>${sd.complete?f1(t.pf):'·'}</td><td>${sd.complete?f1(t.pa):'·'}</td>
      <td>${t.seed||'·'}</td><td class="l">${fin}</td></tr>`;
  }).join('');
  const rivals = S.franchises.filter(o=>o.franchise_id!==fid).map(o=>{
    const r = S.h2h[fid+'|'+o.franchise_id]; if(!r||(r.w+r.l+r.t)===0) return null;
    return {o, r, diff: r.pf-r.pa, g: r.w+r.l+r.t};
  }).filter(Boolean).sort((a,b)=>b.g-a.g);
  const rivalRows = rivals.map(({o,r,diff})=>`<tr>
    <td class="l">${frLink(o.franchise_id)}</td><td data-v="${r.w}">${r.w}–${r.l}${r.t?'–'+r.t:''}</td>
    <td data-v="${r.w/(r.w+r.l+r.t)}">${pct1((r.w+0.5*r.t)/(r.w+r.l+r.t))}</td>
    <td data-v="${r.pf}">${f1(r.pf)}</td><td data-v="${r.pa}">${f1(r.pa)}</td>
    <td class="${cls(diff)}" data-v="${diff}">${signed(diff,f1)}</td></tr>`).join('');
  const stints = [];
  S.players.forEach(p => p.stints.forEach(st => { if(st.fid===fid) stints.push({p, st}); }));
  stints.sort((a,b)=>(b.st.pts||0)-(a.st.pts||0));
  const stintRows = stints.slice(0,14).map(({p,st})=>`<tr>
    <td class="l">${plLink(p.eid)} ${posChip(p.pos)}</td><td>${st.s}</td>
    <td>Wk ${st.w0}–${st.w1}</td><td>${st.weeks}</td><td>${st.starts}</td>
    <td data-v="${st.pts}">${f1(st.pts)}</td><td class="${cls(st.par)}">${signed(st.par,f1)}</td></tr>`).join('');
  const myDrafts = S.drafts.filter(d=>d.fid===fid && d.bid>0);
  const best = [...myDrafts].sort((a,b)=>(b.par||-99)-(a.par||-99)).slice(0,6);
  const worst = [...myDrafts].filter(d=>d.bid>=20).sort((a,b)=>(a.par||0)-(b.par||0)).slice(0,4);
  const dRow = d=>`<tr><td class="l num">${d.s}</td><td class="l">${plLink(d.eid)}</td>
    <td>$${d.bid}</td>${d.keeper?'<td class="l"><span class="badge blue">keeper</span></td>':'<td>·</td>'}
    <td>${f1(d.pts)}</td><td class="${cls(d.par)}">${signed(d.par,f1)}</td></tr>`;
  const myTrades = S.trades.filter(t=>t.sides[fid]).sort((a,b)=>b.s-a.s || b.week-a.week);
  const tradeRows = myTrades.slice(0,12).map(t=>tradeCard(t, fid)).join('') || '<p class="dim">No executed trades recorded (transactions are available from 2018).</p>';
  const aliasChips = f.aliases.map(a=>`<span class="chip" style="cursor:default">${esc(a.name)} <span class="dim">${a.seasons[0]}–${a.seasons[a.seasons.length-1]}</span></span>`).join('');
  app.innerHTML = `<div class="wrap">
    <div class="hero" style="display:flex;gap:22px;align-items:center;flex-wrap:wrap">
      ${logoHtml(fid,'xl')}
      <div><div class="kicker">${f.is_active_2026?'Active franchise':'Alumni franchise'} · est. ${f.first_season}
        ${(function(){ const lv=((L.streaks||{}).byFranchise||{})[fid]; const s=lv&&lv.live;
          return s&&s.len>=2? ` · <span class="badge ${s.res==='W'?'green':'red'}">${s.res}${s.len} ${s.res==='W'?'streak':'skid'}${f.is_active_2026?'':' (final)'}</span>`:''; })()}</div>
      <h1 class="display" style="font-size:clamp(30px,5vw,52px)">${esc(f.display_name)}</h1>
      <div class="muted">${esc(f.owners.join(', '))} ${f.glyph?`· <span class="glyph">${esc(f.glyph)}</span>`:''} · code ${f.code}</div></div>
      <div class="statline" style="margin-left:auto">
        <div class="stat"><div class="v">${f.w}–${f.l}${f.t?'–'+f.t:''}</div><div class="l">Regular season</div></div>
        <div class="stat"><div class="v">${f.pw}–${f.pl}</div><div class="l">Playoffs</div></div>
        <div class="stat"><div class="v">${f.titles.length}</div><div class="l">Titles ${f.titles.length?('('+f.titles.join(', ')+')'):''}</div></div>
      </div></div>
    <div class="legend">${aliasChips}</div>
    <h2 class="sect">Season by season <span class="sub">names and logos as they were</span></h2>
    <div class="tblwrap"><table class="tbl"><thead><tr><th class="l">Year</th><th class="l">Team</th><th>Record</th><th>PF</th><th>PA</th><th>Seed</th><th class="l">Finish</th></tr></thead><tbody>${seasonsRows}</tbody></table></div>
    <h2 class="sect">The heartbeat <span class="sub">every regular-season week ever played, against the league median</span></h2>
    ${chartBox('frheart', 270)}
    <div class="grid g2" style="margin-top:22px">
      <div><h2 class="sect" style="margin-top:0">Skill radar <span class="sub">percentile among all franchises (min 2 seasons)</span></h2>
        ${chartBox('frradar', 320)}</div>
      <div><h2 class="sect" style="margin-top:0">League Rating <span class="sub">ELO, season-end (rating_v1)</span></h2>
        ${chartBox('frrating', 320)}</div>
    </div>
    ${(function(){
      const lk = (L.franchise||[]).find(x=>x.fid===fid);
      const le = (L.lineupFranchise||[]).find(x=>x.fid===fid);
      if(!lk && !le) return '';
      const seasonRows = (L.teamSeason||[]).filter(r=>r.fid===fid && r.luck!=null)
        .sort((a,b)=>a.s-b.s).map(r=>{
          const ls = (L.lineupSeason||[]).find(x=>x.fid===fid && x.s===r.s);
          return `<tr class="click" data-href="#/s/${r.s}"><td class="l num">${r.s}</td>
            <td>${r.w}\u2013${r.l}${r.t?'\u2013'+r.t:''}</td><td>${f1(r.expW)}</td>
            <td class="${cls(r.luck)}" data-v="${r.luck}">${signed(r.luck,f1)}</td>
            <td>${pct1(r.apPct)}</td><td class="dim">${r.medW}\u2013${r.medL}</td>
            <td>${f1(r.sos)}</td><td>${ls?pct1(ls.eff):'\u00b7'}</td>
            <td class="neg">${ls?f0(ls.left):'\u00b7'}</td></tr>`;
        }).join('');
      return `<h2 class="sect">Luck &amp; lineup record <span class="sub">what the schedule gave, and what the bench cost</span></h2>
      <div class="statline" style="margin-bottom:14px">
        ${lk?`<div class="stat"><div class="v ${cls(lk.luck)}">${signed(lk.luck,f1)}</div><div class="l">All-time luck (W \u2212 expected)</div></div>
        <div class="stat"><div class="v">${pct1(lk.apPct)}</div><div class="l">All-play win%</div></div>
        <div class="stat"><div class="v">${lk.luckyW}/${lk.unluckyL}</div><div class="l">Lucky W / unlucky L</div></div>`:''}
        ${le?`<div class="stat"><div class="v">${pct1(le.eff)}</div><div class="l">Lineup efficiency (2018+)</div></div>
        <div class="stat"><div class="v neg">${f0(le.left)}</div><div class="l">Points left on bench</div></div>`:''}
      </div>
      <div class="tblwrap"><table class="tbl"><thead><tr><th class="l">Year</th><th>Record</th><th>Exp W</th><th>Luck</th><th>All-play</th><th>vs med</th><th title="Average opponent score">Opp PPG</th><th>Lineup eff</th><th>Left on bench</th></tr></thead><tbody>${seasonRows}</tbody></table></div>
      <p class="dim small" style="margin-top:6px">Definitions and reliability testing on <a href="#/luck">Luck &amp; Skill</a>.</p>`;
    })()}
    <h2 class="sect">Head-to-head <span class="sub">all-time regular season</span></h2>
    <div class="tblwrap"><table class="tbl"><thead><tr><th class="l sortable">Opponent</th><th class="sortable">Record</th><th class="sortable">Win%</th><th class="sortable">PF</th><th class="sortable">PA</th><th class="sortable">Diff</th></tr></thead><tbody>${rivalRows}</tbody></table></div>
    <div class="grid g2" style="margin-top:26px">
      <div><h2 class="sect" style="margin-top:0">Greatest custody stints</h2>
        <div class="tblwrap"><table class="tbl"><thead><tr><th class="l">Player</th><th>Year</th><th>Span</th><th>Wks</th><th>Starts</th><th>AFFL pts</th><th>PAR</th></tr></thead><tbody>${stintRows}</tbody></table></div></div>
      <div><h2 class="sect" style="margin-top:0">Auction hits & misses <span class="sub">2016+ auctions</span></h2>
        <div class="tblwrap"><table class="tbl"><thead><tr><th class="l">Year</th><th class="l">Player</th><th>Bid</th><th class="l"></th><th>Pts</th><th>Draft PAR</th></tr></thead>
        <tbody>${best.map(dRow).join('')}${worst.length?`<tr><td colspan="6" class="l dim small" style="padding-top:12px">— costliest misses —</td></tr>${worst.map(dRow).join('')}`:''}</tbody></table></div></div>
    </div>
    <h2 class="sect">Trades</h2><div class="grid g2">${tradeRows}</div>
    <h2 class="sect">Explore this franchise</h2>
    <div class="presets">
      <a class="chip" href="#/explore?q=${encState(Object.assign(defState(),{sc:'started',gr:'playerSeason',f:[fid],ms:['affl','fp','xfp','fpoe'],sort:'affl'}))}">▦ Best player-seasons started</a>
      <a class="chip" href="#/explore?q=${encState(Object.assign(defState(),{sc:'bench',gr:'player',f:[fid],s0:2018,ms:['affl','tgt','car','fp'],sort:'affl'}))}">🪑 Points left on the bench</a>
      <a class="chip" href="#/explore?q=${encState(Object.assign(defState(),{sc:'rostered',gr:'nflTeam',f:[fid],ms:['weeks','affl','fp'],sort:'weeks'}))}">⛓ NFL team pipeline</a>
    </div>
  </div>`;
  bindRows(); sortableTable(app);
  drawFrHeartbeat(fid); drawFrRadar(fid); drawFrRating(fid);
}
function tradeCard(t, focusFid){
  const sideBlocks = Object.entries(t.sides).map(([fid, eids])=>{
    const a = t.alpha && t.alpha[fid];
    return `<div style="flex:1;min-width:200px"><div class="small" style="margin-bottom:4px">${frLink(fid, t.s)} <span class="dim">receives</span></div>
      ${eids.map(e=>`<div class="small">• ${plLink(e)} ${posChip((PL[e]||{}).pos)}</div>`).join('')}
      <div class="small" style="margin-top:6px">→ <b class="num">${f1(t.recv[fid])}</b> <span class="dim">pts rest of ${t.s}</span>
      ${a!=null?` <span class="badge ${a>0?'green':a<0?'red':''}">${signed(a,f1)} α</span>`:''}</div></div>`;
  }).join('<div style="align-self:center;color:var(--ink3)">⇄</div>');
  return `<div class="card"><div class="dim small" style="margin-bottom:8px">${t.s} · Week ${t.week}${t.method==='custody_inferred'?' · <span title="assets reconstructed from weekly custody movement">custody-inferred</span>':''}</div>
    <div style="display:flex;gap:14px;flex-wrap:wrap">${sideBlocks}</div></div>`;
}

/* ---------------- PLAYERS ---------------- */
let playerQ = '', playerPos = '';
function playersView(){
  const opts = ['','QB','RB','WR','TE','K','D/ST'].map(p=>`<option value="${p}" ${playerPos===p?'selected':''}>${p||'All positions'}</option>`).join('');
  app.innerHTML = `<div class="wrap"><div class="hero"><div class="kicker">Everyone ever rostered in the AFFL · ${S.players.length} identities</div>
    <h1 class="display">Players</h1></div>
    <div class="xrow" style="margin-bottom:14px">
      <input type="text" id="pq" class="searchbox" placeholder="Search players…" value="${esc(playerQ)}">
      <select id="ppos">${opts}</select></div>
    <div id="plist"></div></div>`;
  const draw = ()=>{
    const q = playerQ.toLowerCase();
    const list = S.players.filter(p => (!q || p.name.toLowerCase().includes(q)) && (!playerPos || p.pos===playerPos)).slice(0, 250);
    $('#plist').innerHTML = `<div class="tblwrap"><table class="tbl"><thead><tr>
      <th class="l">Player</th><th class="l">Pos</th><th class="sortable">Custody wks</th><th class="sortable">Starts</th>
      <th class="sortable">AFFL pts</th><th class="sortable">Franchises</th><th class="l">Custody</th></tr></thead><tbody>
      ${list.map(p=>{
        const wks = p.stints.reduce((a,s)=>a+s.weeks,0), sts = p.stints.reduce((a,s)=>a+s.starts,0);
        const fids = [...new Set(p.stints.map(s=>s.fid))];
        return `<tr class="click" data-href="#/p/${p.eid}">
        <td class="l">${p.img?`<img class="headshot" loading="lazy" src="${esc(p.img)}" alt="" onerror="this.style.display='none'"> `:''}${esc(p.name)}</td>
        <td class="l pos">${esc(p.pos||'')}</td><td data-v="${wks}">${wks}</td><td data-v="${sts}">${sts}</td>
        <td data-v="${p.afflPts}">${f1(p.afflPts)}</td><td data-v="${fids.length}">${fids.length}</td>
        <td class="l">${fids.slice(0,6).map(f=>logoHtml(f)).join(' ')}</td></tr>`;}).join('')}
      </tbody></table></div>
      <p class="dim small" style="margin-top:8px">Showing ${list.length}${list.length===250?' (refine search for more)':''} of ${S.players.length}, ranked by career AFFL points under custody.</p>`;
    bindRows(); sortableTable($('#plist'));
  };
  $('#pq').addEventListener('input', e=>{ playerQ=e.target.value; draw(); });
  $('#ppos').addEventListener('change', e=>{ playerPos=e.target.value; draw(); });
  draw();
}

function playerView(eid){
  const p = PL[eid]; if(!p){ app.innerHTML='<div class="wrap"><p style="padding:40px 0">Unknown player.</p></div>'; return; }
  const C = COL;
  const mine = E.rows.filter(r=>r[C.p]===EIDX[eid]);
  const bySeason = {};
  mine.forEach(r=>{ (bySeason[r[C.s]] = bySeason[r[C.s]]||[]).push(r); });
  const custYears = Object.keys(bySeason).map(Number).sort((a,b)=>a-b);
  const strip = custYears.map(y=>{
    const cells = [];
    for(let w=1; w<=18; w++){
      const r = bySeason[y].find(x=>x[C.w]===w);
      if(!r){ cells.push('<span class="cell"></span>'); continue; }
      const fid = E.franchises[r[C.f]][0];
      cells.push(`<span class="cell on ${r[C.st]?'st':''}" title="${y} Wk ${w} · ${esc(histName(y,fid))}${r[C.st]?' · started':' · bench'}${r[C.affl]!=null?' · '+f1(r[C.affl])+' pts':''}" style="background:${fColor(fid)}"></span>`);
    }
    return `<span>${y}</span>${cells.join('')}`;
  }).join('');
  const legFids = [...new Set(mine.map(r=>E.franchises[r[C.f]][0]))];
  const legend = legFids.map(f=>`<span><span class="sw" style="background:${fColor(f)}"></span>${esc((F[f]||{}).display_name)}</span>`).join('');
  const stintRows = p.stints.map(st=>`<tr>
    <td class="l num">${st.s}</td><td class="l">${frLink(st.fid, st.s)}</td>
    <td>Wk ${st.w0}–${st.w1}</td><td>${st.weeks}</td><td>${st.starts}</td>
    <td>${f1(st.pts)}</td><td class="${cls(st.par)}">${signed(st.par,f1)}</td>
    <td class="l dim small">${esc(st.acq||'')}</td></tr>`).join('');
  const isQB = p.pos==='QB', isK = p.pos==='K';
  const nflRows = p.nfl.map(n=>`<tr><td class="l num">${n.s}</td><td class="l">${esc(n.tm||'')}</td><td>${n.g}</td>
    ${isQB?`<td>${f0(n.pyd)}</td><td>${f0(n.ptd)}</td><td>${f0(n.pint)}</td>`:''}
    <td>${f0(n.car)}</td><td>${f0(n.ryd)}</td><td>${f0(n.rtd)}</td>
    <td>${f0(n.tgt)}</td><td>${f0(n.rec)}</td><td>${f0(n.recyd)}</td><td>${f0(n.rectd)}</td>
    <td>${f1(n.fp)}</td><td>${f1(n.xfp2)}</td><td class="${cls(n.fpoe2)}">${signed(n.fpoe2,f1)}</td>
    <td class="dim ${cls(n.fpoe)}">${signed(n.fpoe,f1)}</td></tr>`).join('');
  const drafted = S.drafts.filter(d=>d.eid===eid);
  const draftRows = drafted.map(d=>`<tr><td class="l num">${d.s}</td><td class="l">${frLink(d.fid,d.s)}</td>
    <td>${d.bid>0?'$'+d.bid:'#'+d.pick}</td><td class="l">${d.keeper?'<span class="badge blue">keeper</span>':''}</td>
    <td>${f1(d.pts)}</td><td class="${cls(d.par)}">${signed(d.par,f1)}</td></tr>`).join('');
  app.innerHTML = `<div class="wrap">
    <div class="hero" style="display:flex;gap:22px;align-items:center;flex-wrap:wrap">
      ${p.img?`<img src="${esc(p.img)}" alt="" style="width:118px;height:86px;object-fit:cover;object-position:top;border-radius:14px;border:1px solid var(--rule);background:var(--card2)" onerror="this.style.display='none'">`:''}
      <div><div class="kicker">${esc(p.pos||'')} ${p.team?'· '+esc(p.team):''} ${p.college?'· '+esc(p.college):''} ${p.rookie?'· rookie '+p.rookie:''}</div>
      <h1 class="display" style="font-size:clamp(30px,5vw,52px)">${esc(p.name)}</h1>
      <div class="statline">
        <div class="stat"><div class="v">${f1(p.afflPts)}</div><div class="l">AFFL pts under custody</div></div>
        <div class="stat"><div class="v">${p.stints.reduce((a,s)=>a+s.weeks,0)}</div><div class="l">Custody weeks</div></div>
        <div class="stat"><div class="v">${p.stints.reduce((a,s)=>a+s.starts,0)}</div><div class="l">Starts</div></div>
        <div class="stat"><div class="v">${[...new Set(p.stints.map(s=>s.fid))].length}</div><div class="l">Franchises</div></div>
      </div></div></div>
    ${p.stints.length===0?`<div class="notice" style="margin-top:8px">Drafted into the AFFL but never held for an observable roster week. Pre-2018, ESPN's historical rosters omit players dropped early — the draft pick below is this player's entire observable league record. Name resolved from ESPN's public player database.</div>`:`
    <h2 class="sect">Custody map <span class="sub">columns are NFL weeks · dot = started · pre-2018 bench custody is unobservable</span></h2>
    <div class="card" style="overflow-x:auto"><div class="cust" style="min-width:640px">${strip}</div></div>
    <div class="legend">${legend}</div>`}
    <div class="grid g2" style="margin-top:22px">
      <div><h2 class="sect" style="margin-top:0">AFFL custody stints</h2>
      <div class="tblwrap"><table class="tbl"><thead><tr><th class="l">Year</th><th class="l">Franchise</th><th>Span</th><th>Wks</th><th>Starts</th><th>Pts</th><th>PAR</th><th class="l">Acq</th></tr></thead><tbody>${stintRows}</tbody></table></div></div>
      <div><h2 class="sect" style="margin-top:0">Draft history</h2>
      ${draftRows?`<div class="tblwrap"><table class="tbl"><thead><tr><th class="l">Year</th><th class="l">By</th><th>Price</th><th class="l"></th><th>Pts for them</th><th>Draft PAR</th></tr></thead><tbody>${draftRows}</tbody></table></div>`:'<p class="dim">Never drafted — waiver/FA custody only.</p>'}</div>
    </div>
    ${p.dst?'':`<h2 class="sect">NFL production by season <span class="sub">nflverse weekly stats · std non-PPR · xFP v2 (ffopportunity canon) · FPOE v1 shown for comparison</span></h2>
    <div class="tblwrap"><table class="tbl"><thead><tr><th class="l">Year</th><th class="l">Team</th><th>G</th>
      ${isQB?'<th>PaYd</th><th>PaTD</th><th>INT</th>':''}
      <th>Car</th><th>RuYd</th><th>RuTD</th><th>Tgt</th><th>Rec</th><th>ReYd</th><th>ReTD</th>
      <th>FP</th><th title="Expected FP, xfp_v2 (ffopportunity CP+xYAC, AFFL-rescored)">xFP</th><th title="FP over expected, v2">FPOE</th>
      <th class="dim" title="Legacy bucket-model FPOE (xfp_v1), kept for comparison">FPOE v1</th></tr></thead><tbody>${nflRows||''}</tbody></table></div>`}
    ${EIDX[eid]!=null?`<div class="presets" style="margin-top:18px">
      <a class="chip" href="#/explore?q=${encState(Object.assign(defState(),{pq:p.name,gr:'weeks',sc:'rostered',ms:['affl','fp','tgt','car'],sort:'affl',lim:100}))}">▦ Every custody week</a>
      <a class="chip" href="#/compare?p=${EIDX[eid]}">⇄ Compare with…</a>
    </div>`:''}
  </div>`;
}

/* ---------------- SEASONS ---------------- */
function seasonsView(){
  const cards = YEARS.slice().reverse().map(y=>{
    const sd = S.seasons[y];
    if(!sd.complete) return `<div class="card"><div class="kicker">${y}</div>
      <div style="font-family:'Barlow Condensed';font-weight:700;font-size:22px">Pre-draft</div>
      <p class="dim small">${sd.teams.length} franchises registered. Excluded from all-time records until played.</p></div>`;
    const c = champOf(y); const ru = sd.teams.find(t=>t.finalRank===2);
    const pf = [...sd.teams].sort((a,b)=>b.pf-a.pf)[0];
    return `<div class="card" style="cursor:pointer" onclick="location.hash='#/s/${y}'">
      <div class="kicker">${y} · ${sd.teams.length} teams · ${sd.auction?'auction':'snake'}</div>
      <div style="display:flex;gap:10px;align-items:center;margin:8px 0 4px">${logoHtml(c.fid,'',y)}
        <div><div style="font-weight:700">${esc(c.name)}</div><div class="dim small">champion</div></div></div>
      <div class="small muted">Runner-up: ${esc(ru?ru.name:'—')}</div>
      <div class="small muted">Most PF: ${esc(pf.name)} (${f1(pf.pf)})</div></div>`;
  }).join('');
  app.innerHTML = `<div class="wrap"><div class="hero"><div class="kicker">Every season preserved with its own names and logos</div>
    <h1 class="display">Seasons</h1></div><div class="grid g3">${cards}</div></div>`;
}

function seasonView(y){
  const sd = S.seasons[y]; if(!sd){ app.innerHTML='<div class="wrap"><p style="padding:40px 0">Unknown season.</p></div>'; return; }
  const teams = [...sd.teams].sort((a,b)=>(a.finalRank||99)-(b.finalRank||99) || (b.w-a.w));
  const rows = teams.map(t=>`<tr class="click" data-href="#/f/${t.fid}">
    <td>${sd.complete?(t.finalRank||'·'):'·'}</td>
    <td class="l">${logoHtml(t.fid,'',y)} <a class="nm" href="#/f/${t.fid}">${esc(t.name)}</a> ${t.finalRank===1?'<span class="title-chip">🏆</span>':''}</td>
    <td class="l dim small">${esc((F[t.fid]||{}).owners?.join(', ')||'')}</td>
    <td>${sd.complete?`${t.w}–${t.l}${t.t?'–'+t.t:''}`:'·'}</td>
    <td data-v="${t.pf||0}">${sd.complete?f1(t.pf):'·'}</td><td data-v="${t.pa||0}">${sd.complete?f1(t.pa):'·'}</td>
    <td>${t.seed||'·'}</td></tr>`).join('');
  let bracket = '';
  if(sd.complete){
    const po = S.matchups.filter(m=>m.season===y && m.po && !m.bye && m.winner && m.winner!=='UNDECIDED');
    const wb = po.filter(m=>m.tier==='WINNERS_BRACKET');
    const list = (wb.length?wb:po);
    const mps = [...new Set(list.map(m=>m.mp))].sort((a,b)=>a-b);
    const roundName = (i,n)=> i===n-1?'Championship': i===n-2?'Semifinals':'Round '+(i+1);
    bracket = `<div class="bracket">${mps.map((mp,i)=>{
      const games = list.filter(m=>m.mp===mp);
      return `<div class="round"><h4>${roundName(i,mps.length)}${wb.length?'':' · playoff week'}</h4>${games.map(m=>{
        const ht=teamOf(y,m.h), at=teamOf(y,m.a);
        const hw = m.winner==='HOME';
        return `<div class="game">
          <div class="row"><span class="${hw?'w':'l2'}">${logoHtml(ht.fid,'',y)} ${esc(ht.name)}</span><span class="num ${hw?'w':'l2'}">${f1(m.hs)}</span></div>
          <div class="row"><span class="${!hw?'w':'l2'}">${logoHtml(at.fid,'',y)} ${esc(at.name)}</span><span class="num ${!hw?'w':'l2'}">${f1(m.as_)}</span></div></div>`;
      }).join('')}</div>`;}).join('')}</div>
      ${wb.length?'' : `<p class="dim small">ESPN did not record bracket tiers before 2018 — these are all playoff-week games; the title is per final standings.</p>`}`;
  }
  const cov = S.coverage.find(c=>c.season===y);
  const weeks = S.matchups.filter(m=>m.season===y && !m.po && !m.bye && m.winner && m.winner!=='UNDECIDED');
  const byMp = {};
  weeks.forEach(m=>{ (byMp[m.mp]=byMp[m.mp]||[]).push(m); });
  /* weekly storylines: high score, blowout, nailbiter per week */
  const stories = Object.keys(byMp).sort((a,b)=>a-b).map(mp=>{
    const games = byMp[mp];
    let hiT=null, hiV=-1;
    games.forEach(m=>{ if(m.hs>hiV){hiV=m.hs; hiT=teamOf(y,m.h);} if(m.as_>hiV){hiV=m.as_; hiT=teamOf(y,m.a);} });
    const blow = [...games].sort((a,b)=>Math.abs(b.hs-b.as_)-Math.abs(a.hs-a.as_))[0];
    const close = [...games].filter(g=>Math.abs(g.hs-g.as_)>0).sort((a,b)=>Math.abs(a.hs-a.as_)-Math.abs(b.hs-b.as_))[0];
    const nm = m=>{ const w=m.winner==='HOME'; const wt=teamOf(y,w?m.h:m.a), lt=teamOf(y,w?m.a:m.h);
      return `${esc((wt||{}).name||'?')} <span class="dim">over</span> ${esc((lt||{}).name||'?')} <span class="num dim">${f1(Math.max(m.hs,m.as_))}–${f1(Math.min(m.hs,m.as_))}</span>`; };
    return `<div class="card" style="min-width:295px">
      <div class="kicker">Week ${mp}</div>
      <div class="small" style="margin-top:6px">💥 <b>${f1(hiV)}</b> — ${esc((hiT||{}).name||'?')}</div>
      ${blow?`<div class="small" style="margin-top:4px">🔨 by <b>${f1(Math.abs(blow.hs-blow.as_))}</b>: ${nm(blow)}</div>`:''}
      ${close&&close!==blow?`<div class="small" style="margin-top:4px">😱 by <b>${f1(Math.abs(close.hs-close.as_))}</b>: ${nm(close)}</div>`:''}
    </div>`;
  }).join('');
  const weekBlocks = Object.keys(byMp).sort((a,b)=>a-b).map(mp=>`
    <div class="card"><div class="kicker">Week ${mp}</div>${byMp[mp].map(m=>{
      const ht=teamOf(y,m.h), at=teamOf(y,m.a); const hw=m.winner==='HOME';
      return `<div class="mrow"><span style="flex:1" class="${hw?'':'dim'}">${esc(ht.name)}</span><b class="num">${f1(m.hs)}</b>
        <span class="dim">—</span><b class="num">${f1(m.as_)}</b><span style="flex:1;text-align:right" class="${hw?'dim':''}">${esc(at.name)}</span></div>`;
    }).join('')}</div>`).join('');
  app.innerHTML = `<div class="wrap">
    <div class="hero"><div class="kicker">${sd.leagueName?esc(sd.leagueName)+' · ':''}${sd.auction?'$200 auction':'snake draft'} · ${sd.teams.length} teams</div>
    <h1 class="display">${y} Season</h1>
    ${!sd.complete?'<p class="tag notice" style="margin-top:14px">Pre-draft planning field. Nothing here counts toward history yet.</p>':''}</div>
    <h2 class="sect">Final standings</h2>
    <div class="tblwrap"><table class="tbl"><thead><tr><th>Fin</th><th class="l">Team</th><th class="l">Owner</th><th>Record</th><th class="sortable">PF</th><th class="sortable">PA</th><th>Seed</th></tr></thead><tbody>${rows}</tbody></table></div>
    ${sd.complete?`<h2 class="sect">The race <span class="sub">cumulative points by week — hover to relive it</span></h2>
    ${chartBox('racechart', 380)}
    <h2 class="sect">Playoffs</h2>${bracket}
    <h2 class="sect">Draft <span class="sub">${sd.auction?'auction prices':'snake — no auction values (2014–2015)'}</span></h2>
    <p><a class="btn ghost" href="#/drafts/${y}">Open the ${y} draft board →</a></p>
    <h2 class="sect">Weekly storylines <span class="sub">high score · hammer · heartbreaker</span></h2>
    <div class="pill-scroll" style="align-items:stretch">${stories}</div>
    <h2 class="sect">Regular season results</h2><div class="grid g2">${weekBlocks}</div>
    ${y<2018?`<div class="notice" style="margin-top:20px">Evidence note: ${y} weekly lineups come from ESPN matchup rosters. Exact lineup slots and bench custody are unavailable before 2018${cov&&cov.unattributed>0?`, and ${f1(cov.unattributed)} team points across ${cov.gaps} team-weeks belong to since-removed players ESPN no longer lists`:''}. Nothing here is inferred.</div>`:''}`:''}
  </div>`;
  bindRows(); sortableTable(app);
  if(sd.complete) drawSeasonRace(y);
}

/* ---------------- DRAFTS ---------------- */
function draftsView(year){
  const auctionYears = DONE.filter(y=>S.seasons[y].auction);
  const y = year && DONE.includes(year) ? year : auctionYears[auctionYears.length-1];
  const isAuction = S.seasons[y].auction;
  const picks = S.drafts.filter(d=>d.s===y).sort((a,b)=> isAuction ? b.bid-a.bid : a.pick-b.pick);
  const rows = picks.map(d=>{
    const perDollar = isAuction && d.bid>0 && d.par!=null ? d.par/d.bid : null;
    return `<tr><td>${isAuction?'$'+d.bid:('#'+d.pick)}</td>
    <td class="l">${plLink(d.eid)} ${posChip((PL[d.eid]||{}).pos)}</td>
    <td class="l">${frLink(d.fid, y)}</td>
    <td class="l">${d.keeper?'<span class="badge blue">keeper</span>':''}</td>
    <td data-v="${d.weeks}">${d.weeks}</td><td data-v="${d.starts}">${d.starts}</td>
    <td data-v="${d.pts}">${f1(d.pts)}</td>
    <td class="${cls(d.par)}" data-v="${d.par==null?-999:d.par}">${signed(d.par,f1)}</td>
    <td class="${cls(perDollar)}" data-v="${perDollar==null?-999:perDollar}">${perDollar==null?'·':f2(perDollar)}</td></tr>`;}).join('');
  const tabs = DONE.map(yy=>`<a class="chip ${yy===y?'on':''}" href="#/drafts/${yy}">${yy}${S.seasons[yy].auction?'':' ⛓'}</a>`).join('');
  const allAuction = S.drafts.filter(d=>S.seasons[d.s] && S.seasons[d.s].auction && d.bid>0 && d.par!=null);
  const bestVal = [...allAuction].filter(d=>d.bid>=2).sort((a,b)=>b.par/b.bid-a.par/a.bid).slice(0,10);
  const busts = [...allAuction].filter(d=>d.bid>=30).sort((a,b)=>a.par-b.par).slice(0,10);
  const mini = d=>`<div class="mrow"><span class="k">${d.s} · $${d.bid}</span><span style="flex:1">${plLink(d.eid)} <span class="dim small">→ ${esc((F[d.fid]||{}).display_name)}</span></span><b class="num ${cls(d.par)}">${signed(d.par,f1)}</b></div>`;
  app.innerHTML = `<div class="wrap">
    <div class="hero"><div class="kicker">$200 auctions since 2016 · 2014–2015 were snake drafts (excluded from price analysis)</div>
    <h1 class="display">Draft Room</h1></div>
    <div class="pill-scroll" style="margin-bottom:14px">${tabs}</div>
    ${isAuction?'':'<div class="notice" style="margin-bottom:14px">'+y+' was a snake draft — bid amounts do not exist; value analysis uses auction seasons only (canon).</div>'}
    ${isAuction?`<h2 class="sect" style="margin-top:0">Price vs. payoff <span class="sub">${y} · every dollar against the PAR it bought</span></h2>
    ${chartBox('draftscatter', 380)}
    <p class="dim small" style="margin:6px 0 18px">Up and left is a steal; down and right is a bust. Hover any dot. Draft PAR is par_v1 — points delivered to the drafting franchise above a replacement start.</p>`:''}
    <div class="tblwrap"><table class="tbl"><thead><tr><th>${isAuction?'Price':'Pick'}</th><th class="l">Player</th><th class="l">Franchise</th><th class="l"></th>
      <th class="sortable">Wks</th><th class="sortable">Starts</th><th class="sortable">Pts for them</th><th class="sortable">Draft PAR</th><th class="sortable">PAR/$</th></tr></thead><tbody>${rows}</tbody></table></div>
    <div class="grid g2" style="margin-top:26px">
      <div class="card"><div class="kicker">Best auction values, all-time (min $2)</div>${bestVal.map(mini).join('')}</div>
      <div class="card"><div class="kicker">Costliest busts, all-time (min $30)</div>${busts.map(mini).join('')}</div>
    </div>
    <h2 class="sect">Where the money goes <span class="sub">auction spend share by position, every draft since 2016</span></h2>
    ${chartBox('spendmix', 300)}
    <p class="dim small" style="margin-top:14px">Draft PAR (par_v1): AFFL points delivered to the drafting franchise while rostered, minus replacement-level points for the position over those weeks. Replacement baselines per season are listed in <a href="#/methods">Methodology</a>.</p>
  </div>`;
  sortableTable(app);
  if(isAuction) drawDraftScatter(y);
  drawSpendMix();
}

/* ---------------- TRADES ---------------- */
function tradesView(){
  const byS = {};
  S.trades.forEach(t=>{ (byS[t.s]=byS[t.s]||[]).push(t); });
  const blocks = Object.keys(byS).sort((a,b)=>b-a).map(s=>`
    <h2 class="sect">${s} <span class="sub">${byS[s].length} executed trades</span></h2>
    <div class="grid g2">${byS[s].sort((a,b)=>a.week-b.week).map(t=>tradeCard(t)).join('')}</div>`).join('');
  app.innerHTML = `<div class="wrap"><div class="hero">
    <div class="kicker">Every executed trade since transactions exist (2018) · outcome windows run to season end</div>
    <h1 class="display">Trades</h1>
    <p class="tag">α (Trade Alpha, trade_v1) = custody points received minus sent, execution week through the end of that season. ${V.trades?`${V.trades.items_direct} trades carry ESPN's own asset list; ${V.trades.items_inferred} are reconstructed from weekly custody movement; ${V.trades.unresolved} events remain unresolved and are excluded.`:''} Pre-2018 trades are not recorded by ESPN.</p></div>
    ${blocks}</div>`;
}

/* ---------------- RECORDS ---------------- */
function heatColor(rank, n){
  if(rank==null || !n || n<2) return 'transparent';
  const t = (rank-1)/(n-1);                    // 0 best -> 1 worst
  const hue = 145 - t*145;                     // green -> red
  return `hsla(${hue},70%,45%,0.55)`;
}
function rankHeatBlock(year){
  const rh = (L.rankHeat||[]).find(x=>x.s===year);
  if(!rh) return '';
  const sd = S.seasons[year]||{teams:[]};
  const rankOf = fid => { const t = sd.teams.find(t=>t.fid===fid); return t? (t.finalRank||99) : 99; };
  const teams = [...rh.teams].sort((a,b)=>rankOf(a.fid)-rankOf(b.fid));
  const head = `<tr><th class="l stick">Team</th>${rh.weeks.map(w=>`<th>${w}</th>`).join('')}<th title="mean weekly rank">Avg</th></tr>`;
  const body = teams.map(t=>{
    const cells = t.ranks.map((rk,i)=>{
      const n = rh.n[i];
      const sc = (t.scores||[])[i];
      return `<td class="heatc" style="background:${heatColor(rk,n)}" title="${year} Wk ${rh.weeks[i]} · ${esc(histName(year,t.fid))}${sc!=null?' · '+f1(sc)+' pts':''} · rank ${rk==null?'—':rk}/${n}">${rk==null?'·':rk}</td>`;
    }).join('');
    const known = t.ranks.filter(x=>x!=null);
    const avg = known.length? known.reduce((a,b)=>a+b,0)/known.length : null;
    return `<tr><td class="l stick">${frLink(t.fid,year)}</td>${cells}<td class="num"><b>${avg!=null?avg.toFixed(1):'·'}</b></td></tr>`;
  }).join('');
  return `<div class="tblwrap mtx"><table class="tbl mono heat"><thead>${head}</thead><tbody>${body}</tbody></table></div>
  <p class="dim small" style="margin-top:8px">Each cell is that team's <b>scoring rank inside the week</b> (1 = highest score in the league that week), regular season only — the schedule-free view of who actually showed up, week by week. Rows ordered by final standing.</p>`;
}
function recordsView(qs){
  const yq = +(((qs||'').split('&').find(x=>x.startsWith('y='))||'').slice(2));
  const heatYears = (L.rankHeat||[]).map(x=>x.s);
  const year = heatYears.includes(yq) ? yq : LAST;
  const st = (L.streaks||{});
  const spanTxt = x => `${x.s0} Wk ${x.w0}${(x.s1!==x.s0||x.w1!==x.w0)?` → ${x.s1===x.s0?'':x.s1+' '}Wk ${x.w1}`:''}`;
  const stRow = x=>`<tr><td class="l">${frLink(x.fid)}</td><td data-v="${x.len}"><b>${x.len}</b></td><td class="l dim small">${spanTxt(x)}</td></tr>`;
  const gRow = g=>`<tr><td class="l">${frLink(g.fid,g.s)}</td><td data-v="${g.pts}"><b>${f1(g.pts)}</b></td><td>${f1(g.opp)}</td><td class="l">${frLink(g.ofid,g.s)}</td><td class="dim">${g.s} Wk ${g.w}</td></tr>`;
  const r = S.records;
  const twRow = t=>`<tr><td class="l">${frLink(t.fid, t.season)}</td><td>${t.season}</td><td>${t.week}</td><td data-v="${t.points}">${f1(t.points)}</td></tr>`;
  const gmRow = m=>{ const ht=teamOf(m.season,m.h), at=teamOf(m.season,m.a);
    return `<tr><td class="l small">${esc(ht.name)} <b class="num">${f1(m.hs)}</b> — <b class="num">${f1(m.as_)}</b> ${esc(at.name)}</td><td>${m.season}</td><td>${m.mp}</td><td data-v="${Math.abs(m.hs-m.as_)}">${f1(Math.abs(m.hs-m.as_))}</td></tr>`; };
  const pwRow = x=>`<tr><td class="l">${plLink(x.eid)} ${posChip((PL[x.eid]||{}).pos)}</td><td class="l">${frLink(x.fid,x.s)}</td><td>${x.s}</td><td>${x.w}</td><td data-v="${x.pts}">${f1(x.pts)}</td></tr>`;
  const half = (title, head, rows) => `<div><h2 class="sect" style="margin-top:0">${title}</h2>
    <div class="tblwrap"><table class="tbl"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div></div>`;
  app.innerHTML = `<div class="wrap"><div class="hero"><div class="kicker">The AFFL record book · 2014–${LAST}</div>
    <h1 class="display">Records</h1></div>
    <div class="grid g2">
      ${half('Highest team weeks','<th class="l">Franchise</th><th>Year</th><th>Wk</th><th>Pts</th>', r.teamWeekHigh.map(twRow).join(''))}
      ${half('Lowest team weeks','<th class="l">Franchise</th><th>Year</th><th>Wk</th><th>Pts</th>', r.teamWeekLow.map(twRow).join(''))}
      ${half('Biggest blowouts','<th class="l">Game</th><th>Year</th><th>MP</th><th>Margin</th>', r.blowouts.map(gmRow).join(''))}
      ${half('Closest games','<th class="l">Game</th><th>Year</th><th>MP</th><th>Margin</th>', r.closest.map(gmRow).join(''))}
    </div>
    <h2 class="sect">Best started player-weeks</h2>
    <div class="tblwrap"><table class="tbl"><thead><tr><th class="l">Player</th><th class="l">For</th><th>Year</th><th>Wk</th><th>AFFL pts</th></tr></thead>
    <tbody>${r.playerWeeks.map(pwRow).join('')}</tbody></table></div>

    <h2 class="sect">Weekly rank heatmap <span class="sub">where every score landed, week by week (rankheat_v1)</span></h2>
    <div class="presets">${heatYears.map(y=>`<a class="chip ${y===year?'on':''}" href="#/records?y=${y}">${y}</a>`).join('')}</div>
    ${rankHeatBlock(year)}

    <h2 class="sect">Streaks <span class="sub">regular-season head-to-head runs, carried across seasons (streaks_v1)</span></h2>
    <div class="grid g2">
      <div><h3 class="sect small" style="margin-top:0">Longest winning streaks</h3>
        <div class="tblwrap"><table class="tbl"><thead><tr><th class="l">Franchise</th><th>W</th><th class="l">Span</th></tr></thead><tbody>${(st.topW||[]).map(stRow).join('')}</tbody></table></div></div>
      <div><h3 class="sect small" style="margin-top:0">Longest losing streaks</h3>
        <div class="tblwrap"><table class="tbl"><thead><tr><th class="l">Franchise</th><th>L</th><th class="l">Span</th></tr></thead><tbody>${(st.topL||[]).map(stRow).join('')}</tbody></table></div></div>
    </div>

    <h2 class="sect">Heartbreaks &amp; heists <span class="sub">the scoreboard vs the schedule</span></h2>
    <div class="grid g2">
      <div><h3 class="sect small" style="margin-top:0">Most points in a loss</h3>
        <div class="tblwrap"><table class="tbl"><thead><tr><th class="l">Team</th><th>Scored</th><th>Lost to</th><th class="l">Opponent</th><th>When</th></tr></thead><tbody>${(st.bigLosses||[]).map(gRow).join('')}</tbody></table></div></div>
      <div><h3 class="sect small" style="margin-top:0">Fewest points in a win</h3>
        <div class="tblwrap"><table class="tbl"><thead><tr><th class="l">Team</th><th>Scored</th><th>Beat</th><th class="l">Opponent</th><th>When</th></tr></thead><tbody>${(st.smallWins||[]).map(gRow).join('')}</tbody></table></div></div>
    </div>
  </div>`;
}

/* ---------------- METHODOLOGY ---------------- */
/* ================= LUCK & SKILL ================= */
function luckView(yArg){
  if(!L.franchise){ app.innerHTML='<div class="wrap"><div class="notice" style="margin:40px 0">Luck data unavailable in this build.</div></div>'; return; }
  const year = (yArg && L.schedSim.some(r=>r.s===yArg)) ? yArg : LAST;
  const simYears = [...new Set(L.schedSim.map(r=>r.s))].sort((a,b)=>a-b);

  /* ---- all-time ledger ---- */
  const led = [...L.franchise].sort((a,b)=>(b.apPct||0)-(a.apPct||0));
  const ledRows = led.map(r=>{
    const f=F[r.fid]; if(!f) return '';
    const medG=r.medW+r.medL+r.medT;
    return `<tr class="click" data-href="#/f/${r.fid}">
      <td class="l">${frLink(r.fid)}</td>
      <td data-v="${r.seasons}">${r.seasons}</td>
      <td data-v="${r.winPct}">${r.w}–${r.l}${r.t?'–'+r.t:''}</td>
      <td data-v="${r.expW}">${f1(r.expW)}</td>
      <td class="${cls(r.luck)}" data-v="${r.luck}">${signed(r.luck,f1)}</td>
      <td data-v="${r.apPct}">${pct1(r.apPct)}</td>
      <td data-v="${medG?r.medW/medG:0}" class="dim">${r.medW}–${r.medL}${r.medT?'–'+r.medT:''}</td>
      <td data-v="${r.luckyW}">${r.luckyW}</td>
      <td data-v="${r.unluckyL}">${r.unluckyL}</td></tr>`;
  }).join('');

  /* ---- team-season extremes ---- */
  const withLuck = L.teamSeason.filter(r=>r.luck!=null);
  const luckiest = [...withLuck].sort((a,b)=>b.luck-a.luck).slice(0,8);
  const unluckiest = [...withLuck].sort((a,b)=>a.luck-b.luck).slice(0,8);
  const extRow = r=>`<tr class="click" data-href="#/s/${r.s}">
    <td class="l num">${r.s}</td><td class="l">${frLink(r.fid,r.s)}</td>
    <td>${r.w}–${r.l}${r.t?'–'+r.t:''}</td><td>${f1(r.expW)}</td>
    <td class="${cls(r.luck)}" data-v="${r.luck}">${signed(r.luck,f1)}</td>
    <td>${pct1(r.apPct)}</td><td>${f1(r.ppg)}</td></tr>`;

  /* ---- schedule-luck sim for chosen year ---- */
  const yearPills = simYears.map(y=>`<a class="chip ${y===year?'on':''}" href="#/luck/${y}">${y}</a>`).join('');
  const sim = L.schedSim.filter(r=>r.s===year);
  const tsByTid = {}; L.teamSeason.filter(r=>r.s===year).forEach(r=>tsByTid[r.tid]=r);
  const poCut = (S.seasons[year]||{}).playoffTeams || 6;
  const simRows = [...sim].sort((a,b)=>(b.medW||0)-(a.medW||0)).map(r=>{
    const ts=tsByTid[r.tid]; if(!ts) return '';
    const t=teamOf(year,r.tid);
    const actualW = ts.w + 0.5*ts.t;
    const delta = actualW - (r.medW||0);
    const madeIt = t && t.seed && t.seed<=poCut;
    const span = (r.maxW||0)-(r.minW||0);
    const lo = span? ((r.p10-r.minW)/span)*100 : 0;
    const wd = span? ((r.p90-r.p10)/span)*100 : 100;
    const mk = span? ((actualW-r.minW)/span)*100 : 50;
    return `<tr>
      <td class="l">${frLink(r.fid,year)}</td>
      <td data-v="${actualW}">${ts.w}–${ts.l}${ts.t?'–'+ts.t:''}</td>
      <td data-v="${r.medW}">${f1(r.medW)}</td>
      <td class="${cls(delta)}" data-v="${delta}">${signed(delta,f1)}</td>
      <td data-v="${r.p10}" class="dim small">${f1(r.p10)}–${f1(r.p90)}</td>
      <td data-v="${lo}" style="min-width:150px"><span class="band"><span class="band-in" style="left:${lo}%;width:${wd}%"></span><span class="band-mk" style="left:${mk}%"></span></span></td>
      <td data-v="${r.poOdds}">${pct1(r.poOdds)}</td>
      <td class="l">${madeIt?'<span class="badge green">made it</span>':'<span class="badge">missed</span>'}</td></tr>`;
  }).join('');

  /* ---- swap matrix ---- */
  const swap = L.swap.filter(r=>r.s===year);
  const sOrd = (L.swapOrder||{})[String(year)] || [];
  const sIdx = {}; sOrd.forEach((fid,i)=>sIdx[fid]=i);
  const cellOf = (row,fid) => (sIdx[fid]==null ? null : (row.u||[])[sIdx[fid]]);
  const order = [...sim].sort((a,b)=>(b.medW||0)-(a.medW||0)).map(r=>r.fid);
  const hdr = order.map(fid=>`<th class="rot" title="${esc(histName(year,fid))}">${esc((F[fid]||{}).code||'')}</th>`).join('');
  const swapRows = order.map(me=>{
    const row = swap.find(r=>r.fid===me); if(!row) return '';
    const mine = cellOf(row,me) || [0,0,0];
    const actualW = mine[0];
    const cells = order.map(other=>{
      const v = cellOf(row,other); if(!v) return '<td class="dim">·</td>';
      const d = v[0]-actualW;
      const bg = d>0 ? `rgba(55,214,122,${Math.min(0.13*Math.abs(d),0.6)})`
               : d<0 ? `rgba(255,77,94,${Math.min(0.13*Math.abs(d),0.6)})` : 'transparent';
      return `<td style="background:${bg}" title="${esc(histName(year,me))} under ${esc(histName(year,other))}'s schedule: ${v[0]}–${v[1]}${v[2]?'–'+v[2]:''}">${v[0]}</td>`;
    }).join('');
    const vals = order.map(o=>(cellOf(row,o)||[0])[0]);
    return `<tr><td class="l stick">${frLink(me,year)}</td><td class="num"><b>${actualW}</b></td>${cells}
      <td class="dim">${Math.min(...vals)}–${Math.max(...vals)}</td></tr>`;
  }).join('');

  /* ---- lineup efficiency ---- */
  const lf = [...(L.lineupFranchise||[])].sort((a,b)=>(b.eff||0)-(a.eff||0));
  const effRows = lf.map(r=>{
    if(!F[r.fid]) return '';
    return `<tr class="click" data-href="#/f/${r.fid}">
      <td class="l">${frLink(r.fid)}</td><td data-v="${r.wks}">${r.wks}</td>
      <td data-v="${r.act}">${f0(r.act)}</td><td data-v="${r.opt}">${f0(r.opt)}</td>
      <td data-v="${r.left}" class="neg">${f0(r.left)}</td>
      <td data-v="${r.eff}"><b>${pct1(r.eff)}</b></td>
      <td data-v="${r.perfect}">${r.perfect}</td></tr>`;
  }).join('');
  const worstWeeks = (L.lineupWeeks||[]).slice(0,12).map(r=>`<tr class="click" data-href="#/s/${r.s}">
    <td class="l num">${r.s}</td><td>Wk ${r.w}</td><td class="l">${frLink(r.fid,r.s)}</td>
    <td>${f1(r.act)}</td><td>${f1(r.opt)}</td><td class="neg" data-v="${r.left}"><b>${f1(r.left)}</b></td></tr>`).join('');

  /* ---- stability ---- */
  const st = L.stability || {splitHalf:[],yoy:[]};
  const shRows = (st.splitHalf||[]).map(r=>`<tr><td class="l">${esc(r.metric)}</td><td>${f2(r.r)}</td><td>${r.n}</td>
    <td class="l">${(r.r||0)>=0.5?'<span class="badge green">repeatable within season</span>':'<span class="badge yellow">noisy</span>'}</td></tr>`).join('');
  const yoyRows = (st.yoy||[]).map(r=>{
    const a=Math.abs(r.r||0);
    const read = a<0.15 ? '<span class="badge">no carryover</span>' : a<0.35 ? '<span class="badge yellow">weak</span>' : '<span class="badge green">persistent</span>';
    return `<tr><td class="l">${esc(r.metric)}</td><td class="${cls(r.r)}">${f2(r.r)}</td><td>${r.n}</td><td class="l">${read}</td></tr>`;
  }).join('');

  const topLuck = luckiest[0], botLuck = unluckiest[0];
  const leagueEff = lf.length ? lf.reduce((a,b)=>a+(b.act||0),0)/lf.reduce((a,b)=>a+(b.opt||0),0) : null;

  app.innerHTML = `<div class="wrap">
    <div class="hero"><div class="kicker">Schedule luck, all-play records, and lineup decisions</div>
      <h1 class="display">Luck &amp; Skill</h1>
      <p class="tag">A head-to-head league pays you for the week you scored <em>and</em> the opponent you drew. All-play strips the opponent out: every team is scored against every other team, every week. The gap between the wins you got and the wins your scoring earned is schedule luck — and it is worth up to <b>${signed(topLuck?topLuck.luck:0,f1)}</b> wins in a single AFFL season.</p>
    </div>

    <div class="grid g4">
      <div class="card"><div class="kicker">Luckiest season</div>
        <p class="small" style="margin:6px 0">${topLuck?frLink(topLuck.fid,topLuck.s):'·'} <b>${topLuck?topLuck.s:''}</b></p>
        <p class="small muted">Went ${topLuck?`${topLuck.w}–${topLuck.l}`:''} on ${topLuck?f1(topLuck.expW):''} expected wins — <b class="posv">${signed(topLuck?topLuck.luck:0,f1)}</b> wins of schedule.</p></div>
      <div class="card"><div class="kicker">Unluckiest season</div>
        <p class="small" style="margin:6px 0">${botLuck?frLink(botLuck.fid,botLuck.s):'·'} <b>${botLuck?botLuck.s:''}</b></p>
        <p class="small muted">Went ${botLuck?`${botLuck.w}–${botLuck.l}`:''} on ${botLuck?f1(botLuck.expW):''} expected wins — <b class="neg">${signed(botLuck?botLuck.luck:0,f1)}</b> wins.</p></div>
      <div class="card"><div class="kicker">League lineup efficiency</div>
        <p class="small" style="margin:6px 0"><b style="font-size:22px">${pct1(leagueEff)}</b></p>
        <p class="small muted">of the best legal lineup, 2018–${LAST}. The rest is points left on benches.</p></div>
      <div class="card"><div class="kicker">Does a good season repeat?</div>
        <p class="small" style="margin:6px 0"><b style="font-size:22px">r = ${f2((st.yoy.find(x=>x.metric==='All-play win %')||{}).r)}</b></p>
        <p class="small muted">Year-over-year all-play win%. Near zero: in this league, this season tells you almost nothing about next.</p></div>
    </div>

    <h2 class="sect">All-time luck ledger <span class="sub">regular season, ${DONE[0]}–${LAST}</span></h2>
    <div class="tblwrap"><table class="tbl"><thead><tr>
      <th class="l sortable">Franchise</th><th class="sortable">Sns</th><th class="sortable">Actual</th>
      <th class="sortable">Expected W</th><th class="sortable">Luck</th><th class="sortable">All-play W%</th>
      <th class="l sortable">vs median</th><th class="sortable" title="Won despite scoring below the league median">Lucky W</th>
      <th class="sortable" title="Lost despite scoring above the league median">Unlucky L</th>
    </tr></thead><tbody>${ledRows}</tbody></table></div>
    <p class="dim small" style="margin-top:8px">Sorted by all-play win% — the closest thing to a luck-free ranking of how well each franchise actually scored. <b>Expected W</b> is all-play win% applied to games played; <b>Luck</b> is actual minus expected and sums to zero across the league.</p>

    <div class="grid g2" style="margin-top:26px">
      <div><h2 class="sect" style="margin-top:0">Wins the schedule gave away</h2>
        <div class="tblwrap"><table class="tbl"><thead><tr><th class="l">Year</th><th class="l">Team</th><th>Record</th><th>Exp W</th><th>Luck</th><th>All-play</th><th>PPG</th></tr></thead><tbody>${luckiest.map(extRow).join('')}</tbody></table></div></div>
      <div><h2 class="sect" style="margin-top:0">Wins the schedule stole</h2>
        <div class="tblwrap"><table class="tbl"><thead><tr><th class="l">Year</th><th class="l">Team</th><th>Record</th><th>Exp W</th><th>Luck</th><th>All-play</th><th>PPG</th></tr></thead><tbody>${unluckiest.map(extRow).join('')}</tbody></table></div></div>
    </div>

    <h2 class="sect">Schedule-luck simulation <span class="sub">${(sim[0]||{}).trials||2000} random schedules, real scores</span></h2>
    <div class="presets">${yearPills}</div>
    <p class="small muted" style="margin:10px 0 14px">Every team's weekly scores are held exactly as they were played; only <em>who played whom</em> is redrawn. There is no projection and no scoring model here — the spread is pure schedule.</p>
    <div class="tblwrap"><table class="tbl"><thead><tr>
      <th class="l sortable">Team</th><th class="sortable">Actual</th><th class="sortable">Median sim W</th>
      <th class="sortable">Δ</th><th class="sortable">10th–90th</th><th class="l">Win range</th>
      <th class="sortable">Playoff odds</th><th class="l">Actual</th>
    </tr></thead><tbody>${simRows}</tbody></table></div>
    <p class="dim small" style="margin-top:8px">Bar shows the full simulated win range; the shaded band is the 10th–90th percentile and the tick is what actually happened. A tick outside its own band means the schedule, not the scoring, decided that season. Playoff odds use the league's real ${poCut}-team cut with points-for as tiebreak.</p>

    <h2 class="sect">If you had played their schedule <span class="sub">${year} · exact, not simulated</span></h2>
    <div class="tblwrap mtx"><table class="tbl mono"><thead><tr><th class="l stick">Team</th><th>Real</th>${hdr}<th>Range</th></tr></thead><tbody>${swapRows}</tbody></table></div>
    <p class="dim small" style="margin-top:8px">Read across: each cell is that team's win total if it had faced the column team's actual opponent sequence, with all scores unchanged. Green means the borrowed schedule was kinder than their own.</p>

    <h2 class="sect">Lineup efficiency <span class="sub">2018–${LAST} · optimal lineup from the roster they held</span></h2>
    <div class="grid g2">
      <div><div class="tblwrap"><table class="tbl"><thead><tr><th class="l sortable">Franchise</th><th class="sortable">Wks</th><th class="sortable">Started</th><th class="sortable">Optimal</th><th class="sortable">Left on bench</th><th class="sortable">Efficiency</th><th class="sortable" title="Weeks where the lineup was exactly optimal">Perfect</th></tr></thead><tbody>${effRows}</tbody></table></div></div>
      <div><h3 class="sect small" style="margin-top:0">Costliest single weeks</h3>
        <div class="tblwrap"><table class="tbl"><thead><tr><th class="l">Year</th><th>Wk</th><th class="l">Team</th><th>Started</th><th>Optimal</th><th>Left</th></tr></thead><tbody>${worstWeeks}</tbody></table></div></div>
    </div>
    <p class="dim small" style="margin-top:8px">Optimal is the best <em>legal</em> lineup from players actually on the roster that week — QB/RB/RB/WR/WR/TE/FLEX/D-ST/K, with FLEX taking the best remaining RB, WR or TE. Players on IR are excluded because they could not have been started. Withheld before 2018: ESPN's historical payloads carry no lineup slots, so the counterfactual is unobservable and is not guessed.</p>

    <h2 class="sect">Is any of this repeatable? <span class="sub">reliability testing, Open Source Football convention</span></h2>
    <div class="grid g2">
      <div><h3 class="sect small" style="margin-top:0">Split-half <span class="sub">odd vs even weeks, same season</span></h3>
        <div class="tblwrap"><table class="tbl"><thead><tr><th class="l">Metric</th><th>r</th><th>n</th><th class="l">Read</th></tr></thead><tbody>${shRows}</tbody></table></div></div>
      <div><h3 class="sect small" style="margin-top:0">Year over year <span class="sub">season t vs t+1, same franchise</span></h3>
        <div class="tblwrap"><table class="tbl"><thead><tr><th class="l">Metric</th><th>r</th><th>n</th><th class="l">Read</th></tr></thead><tbody>${yoyRows}</tbody></table></div></div>
    </div>
    <p class="dim small" style="margin-top:8px">${esc(st.note||'')}</p>
    <div class="notice" style="margin-top:14px">The honest finding: scoring is <b>moderately repeatable inside a season</b> (split-half r ≈ ${f2((st.splitHalf.find(x=>x.metric==='Points per game')||{}).r)}) and <b>essentially unrepeatable across seasons</b> (year-over-year r ≈ ${f2((st.yoy.find(x=>x.metric==='Points per game')||{}).r)}). Luck sits at r ≈ ${f2((st.yoy.find(x=>x.metric&&x.metric.indexOf('Luck')===0)||{}).r)} year over year, which is exactly what a luck metric should do — if it persisted, it would not be luck.</div>

    <h2 class="sect">What a week is worth <span class="sub">every regular-season team score, 2014–${LAST}</span></h2>
    ${chartBox('scorehist', 290)}
    <p class="dim small" style="margin-top:6px" id="histnote"></p>

    <h2 class="sect">Explore the underlying weeks</h2>
    <div class="presets">
      <a class="chip" href="#/explore?q=${encState(Object.assign(defState(),{sc:'bench',gr:'franchise',s0:2018,ms:['benchAffl','fp'],sort:'benchAffl'}))}">🪑 Bench points by franchise</a>
      <a class="chip" href="#/explore?q=${encState(Object.assign(defState(),{sc:'started',gr:'teamSeason',ms:['affl','fp','xfp2','fpoe2'],sort:'affl'}))}">▦ Started points by team-season</a>
      <a class="chip" href="#/methods">§ How these metrics are defined</a>
    </div>
  </div>`;
  bindRows(); sortableTable(app);
  drawScoreHist();
}

function methodsView(){
  const covRows = S.coverage.map(c=>`<tr><td class="l num">${c.season}</td><td>${c.team_weeks}</td>
    <td>${c.season<2018?'starters only (matchup rosters)':'full weekly rosters'}</td>
    <td>${c.season<2018?'—':'✓'}</td><td>${c.gaps||0}</td><td>${c.unattributed?f1(c.unattributed):'0.0'}</td></tr>`).join('');
  const repRows = Object.keys(S.replacement).sort().map(s=>{
    const r=S.replacement[s]; return `<tr><td class="l num">${s}</td>${['QB','RB','WR','TE','K','D/ST'].map(p=>`<td>${r[p]!=null?f2(r[p]):'·'}</td>`).join('')}</tr>`;}).join('');
  app.innerHTML = `<div class="wrap"><div class="hero"><div class="kicker">Sources, identity, evidence, formulas, and what we refuse to infer</div>
  <h1 class="display">Methodology</h1></div>
  <div class="grid g2">
  <div class="card">
    <div class="kicker">Sources of truth</div>
    <div class="mrow"><span class="k">affl.db</span><span>League truth: owners, franchises, team-seasons, matchups, drafts, weekly rosters, transactions — built from authenticated ESPN Fantasy v3 snapshots of league 51418 (2014–2026).</span></div>
    <div class="mrow"><span class="k">nfl.duckdb</span><span>NFL truth: nflverse players, weekly stats, and the full 2014–2025 play-by-play corpus (${f0(V.pbp_plays||417739)} opportunity plays).</span></div>
    <div class="mrow"><span class="k">join</span><span>ESPN playerId → GSIS via nflverse reviewed provider IDs. ${V.bridge?`${V.bridge.rostered} rostered identities: ${V.bridge.gsis} players joined on espn_id, ${V.bridge.dst} D/ST joined as NFL team-seasons, ${V.bridge.quarantined} quarantined`:''}. A name is display data, not a join key.</span></div>
  </div>
  <div class="card">
    <div class="kicker">Identity canon</div>
    <p class="small muted" style="margin:6px 0">The owner is the franchise. ESPN recycles slot ids when owners leave (slot 2 hosted two unrelated franchises; slots 4 and 10 hosted three each), owners move slots (Honolulu Horndogs: slot 10 → 11 with a 2016 gap; Chula Vista Chupacabras: slot 10 → 14 with a two-year gap), and one owner can hold several ESPN accounts (three SWIDs for the Chupacabras owner). Identity therefore groups on owner display-name continuity with union-find. Result: ${S.franchises.length} franchises, ${S.franchises.filter(f=>f.is_active_2026).length} active in 2026. Season pages always show the name and logo of that season; cumulative views use today's identity.</p>
  </div>
  <div class="card">
    <div class="kicker">Scoring & custody</div>
    <p class="small muted" style="margin:6px 0">AFFL points are ESPN's own applied totals per lineup week — never recomputed. Custody scopes: <b>while rostered</b> (weeks a player occupied the roster), <b>while started</b> (weeks in the scoring lineup), <b>ever rostered</b> (full NFL seasons of anyone with AFFL history — season grain, never mixed with custody windows). Weekly attribution follows the lineup eligible to score that week.</p>
  </div>
  <div class="card">
    <div class="kicker">Metric versions</div>
    <div class="mrow"><span class="k">std_fp_v1</span><span>Standard non-PPR: 0.04/pass yd, 4 pass TD, −2 INT, 0.1/rush+rec yd, 6 TD, −2 fumble lost, +2 two-point, distance-tiered FG (3/4/5) + PAT.</span></div>
    <div class="mrow"><span class="k">xfp_v2</span><span><b>The expected-FP model this site now leads with.</b> ffverse/ffopportunity expected stats — the <code>nflreadr::load_ff_opportunity()</code> payload: XGBoost completion-probability and expected-YAC models trained on nflfastR play-by-play — rescored to AFFL scoring (0.04/pass yd, 4 pass TD, −2 INT, 0.1/rush+rec yd, 6 TD, +2 two-point). FPOE v2 = same-scope actual − expected. <b>Scope:</b> no fumble term on either side (ffopportunity does not model expected fumbles), no kicking/ST. <b>Known bias, disclosed not hidden:</b> QB expectation runs 3–7% above realized 2018–2023 (worst 2021), a property of the upstream model; within a position-season, rankings are unaffected.</span></div>
    <div class="mrow"><span class="k">xfp_v1</span><span>Legacy in-house bucket model (rushes by yardline band, targets by air-yards band × red zone, dropbacks by yardline band), fit in-sample on 2014–2025. <b>Superseded by xfp_v2</b> after a holdout test (below) — kept visible for comparison, not for judgment. Its buckets bake league-average fumble rates into expectation; v2 is silent on fumbles on both sides.</span></div>
    <div class="mrow"><span class="k">adjfac_v1</span><span>Opponent adjustment: defense × position factor on the v2 scope, computed leave-one-week-out (the week being judged is excluded from its own opponent's baseline) and shrunk toward 1 by g/(g+4). Adjusted FPOE = actual − expected × factor. Factors average exactly 1.0 by construction.</span></div>
    <div class="mrow"><span class="k">par_v1</span><span>Replacement PPG per season×position = PPG of the rank-R player (R = starter slots + flex allocation, min 4 weeks rostered). PAR = custody points − replacement × weeks.</span></div>
    <div class="mrow"><span class="k">allplay_v1</span><span>Every regular-season week, each team's score is ranked against every other team playing that week: all-play W/L/T = teams scored below / above / tied. Expected wins = all-play win% × games played; <b>luck = actual − expected</b> and sums to zero league-wide. Consolation and playoff games excluded.</span></div>
    <div class="mrow"><span class="k">median_v1</span><span>Weekly result against the league median score that week — a schedule-independent win. A <b>lucky win</b> is a win while scoring below the median; an <b>unlucky loss</b> is a loss while scoring above it.</span></div>
    <div class="mrow"><span class="k">lineup_v1</span><span>Optimal = highest-scoring legal lineup from the players actually rostered that week (FLEX takes the best remaining RB/WR/TE; IR excluded as unstartable). Efficiency = started ÷ optimal. <b>2018+ only</b> — pre-2018 ESPN payloads carry no lineup slots, so the counterfactual is unobservable and is withheld, not inferred.</span></div>
    <div class="mrow"><span class="k">schedluck_v1</span><span>Weekly scores held exactly as played; only the opponent pairing is redrawn over ${(L.meta&&L.meta.trials)||2000} random round-robins per season. No projection, no bootstrap of scores — the resulting win spread is pure schedule. The swap matrix is the exact (not simulated) record under every other team's real opponent sequence.</span></div>
    <div class="mrow"><span class="k">stability_v1</span><span>Reliability per Open Source Football convention: split-half (odd vs even weeks, Spearman-Brown corrected) and year-over-year correlation. Published so metrics that are mostly noise are labelled as noise. See <a href="#/luck">Luck &amp; Skill</a>.</span></div>
    <div class="mrow"><span class="k">trade_v1</span><span>Window = execution week → season end. Realized value = points while rostered by the receiver. α = received − sent. ${V.trades?`${V.trades.items_direct} direct / ${V.trades.items_inferred} custody-inferred / ${V.trades.unresolved} unresolved (excluded).`:''}</span></div>
  </div>
  </div>
  <h2 class="sect">Evidence coverage by season</h2>
  <div class="tblwrap"><table class="tbl"><thead><tr><th class="l">Season</th><th>Team-weeks</th><th class="l">Lineup evidence</th><th>Bench & slots</th><th>Gap weeks</th><th>Unattributed pts</th></tr></thead><tbody>${covRows}</tbody></table></div>
  <p class="dim small" style="margin-top:8px">Pre-2018, ESPN's historical matchup rosters omit players later dropped from the roster; their points (3.1% of pre-2018 scoring) remain at team level and are never re-assigned. Exact lineup slots before 2018 are NULL with an explicit “Unavailable” label — we do not infer them. Two-week playoff matchups (2014–2016) retain player points at matchup grain only.</p>
  <h2 class="sect">Validation results <span class="sub">verified by execution against independent paths</span></h2>
  <div class="grid g3">
    <div class="card"><div class="kicker">Lineup ⇄ matchup totals</div><p class="small muted">2018–${LAST}: starter sums equal ESPN team-week scores in <b>${V.modern_ok||1596}/${V.modern_ok||1596}</b> team-weeks (max |Δ| < 0.000001).</p></div>
    <div class="card"><div class="kicker">pbp ⇄ official weekly stats</div><p class="small muted">Std-FP recomputed from play-by-play matches nflverse official weekly stats within 1.0 pt for <b>${V.fp_recon_pct||99.55}%</b> of ${f0(V.fp_recon_n||60905)} QB/RB/WR/TE player-weeks (mean |Δ| ${V.fp_recon_mad||0.019}).</p></div>
    <div class="card"><div class="kicker">Custody ⇄ NFL weeks</div><p class="small muted"><b>${V.starter_match_pct||99.19}%</b> of ${f0(V.starter_weeks||18345)} non-D/ST starter-weeks join to an NFL stat week; every unmatched week scored exactly 0 AFFL points (inactive/DNP) — none carry unexplained points.</p></div>
    <div class="card"><div class="kicker">ffverse ⇄ official (xfp_v2)</div><p class="small muted">ffopportunity's play-by-play actuals, AFFL-rescored, match the same-scope FP from official gamebook stats within 1.0 pt for <b>${(V.xfp2&&V.xfp2.recon.pct_within_1)||99.8}%</b> of ${f0((V.xfp2&&V.xfp2.recon.n)||60892)} player-weeks (mean |Δ| ${(V.xfp2&&V.xfp2.recon.mean_abs_diff)||0.007}) — two independent aggregation paths agreeing on the actual side of FPOE v2.</p></div>
  </div>
  <h2 class="sect">Why xfp_v2 replaced xfp_v1 <span class="sub">holdout test: weeks 1–8 expectation → weeks 9+ actual, same players, 2014–2025</span></h2>
  <div class="tblwrap"><table class="tbl"><thead><tr><th class="l">Position</th><th>n player-seasons</th><th title="corr(mean xFP v2 wks 1-8, mean actual wks 9+)">xFP v2 predicts</th><th title="corr(mean actual wks 1-8, mean actual wks 9+)">Actual predicts</th><th title="corr(mean xFP v1 wks 1-8, mean actual wks 9+)">xFP v1 predicts</th></tr></thead><tbody>
  ${((V.xfp2&&V.xfp2.holdout)||[]).map(h=>`<tr><td class="l"><b>${esc(h.pos)}</b></td><td>${f0(h.n)}</td>
    <td data-v="${h.xfp2_pred_r}" class="${h.xfp2_pred_r>=Math.max(h.actual2_pred_r,h.xfp1_pred_r)?'posv':''}"><b>${f2(h.xfp2_pred_r)}</b></td>
    <td>${f2(h.actual2_pred_r)}</td><td class="dim">${f2(h.xfp1_pred_r)}</td></tr>`).join('')}
  </tbody></table></div>
  <p class="dim small" style="margin-top:8px">The one methodological debt the first draft carried: xfp_v1 was invented here and fit in-sample, with no holdout. The canon model beats it at <b>every position</b> on unseen future weeks (QB most dramatically), so v2 is now the expectation everywhere an xFP is shown; v1 stays visible as a labelled legacy column. Honest caveats that survive the upgrade: first-half <b>actual</b> still predicts second-half actual slightly better than xFP for QB and RB — expectation models earn their keep on pass-catchers — and FPOE v2 is <em>less</em> half-to-half stable than v1 (r ≈ 0.11 vs 0.23), which is what should happen when a richer model absorbs real skill into expectation and leaves purer luck in the residual.</p>
  <h2 class="sect">Replacement baselines (par_v1, AFFL PPG)</h2>
  <div class="tblwrap"><table class="tbl"><thead><tr><th class="l">Season</th><th>QB</th><th>RB</th><th>WR</th><th>TE</th><th>K</th><th>D/ST</th></tr></thead><tbody>${repRows}</tbody></table></div>
  <h2 class="sect">Privacy</h2>
  <p class="small muted">ESPN credentials were used only at import time and exist nowhere in this page. Raw ESPN member UUIDs and private identifiers are stripped from all published data; owners appear by display name only, as ESPN shows them in-league. Player headshots © NFL via nflverse; team logos are the league's own uploads served from their original hosts.</p>
  <p class="dim small" style="margin:16px 0 0">Dataset version ${esc(S.meta.version)} · ${esc(S.meta.seasons)} · built from ESPN league ${esc(S.meta.leagueId)} snapshots + nflverse ${esc(E.meta.coverage)}.</p>
  </div>`;
}

/* ================= LEADERBOARDS + COMPARE ================= */
// Season-grain board measures over E.seasonRows (NFL-wide, QB/RB/WR/TE/K).
const SC_ = () => SCOL;
const BOARDS = [
 {k:'fp',    l:'Fantasy points',        num:r=>r[SCOL.fp],  fmt:f1},
 {k:'fppg',  l:'FP per game',           num:r=>r[SCOL.fp],  den:r=>r[SCOL.g], fmt:f1, ming:8},
 {k:'xfp2',  l:'Expected FP (xFP)',     num:r=>r[SCOL.xfp2], fmt:f1},
 {k:'fpoe2', l:'FPOE — FP over expected', num:r=>r[SCOL.fpoe2], fmt:v=>signed(v,f1), sgn:1},
 {k:'afpoe2',l:'Opponent-adjusted FPOE', num:r=>r[SCOL.afpoe2], fmt:v=>signed(v,f1), sgn:1},
 {k:'fpoePg',l:'FPOE per game',         num:r=>r[SCOL.fpoe2], den:r=>r[SCOL.g], fmt:v=>signed(v,f2), sgn:1, ming:8},
 {k:'pyd',   l:'Pass yards',            num:r=>r[SCOL.pyd], fmt:f0},
 {k:'ptd',   l:'Pass TD',               num:r=>r[SCOL.ptd], fmt:f0},
 {k:'pint',  l:'Interceptions',         num:r=>r[SCOL.pint], fmt:f0},
 {k:'epaDb', l:'EPA per dropback',      num:r=>r[SCOL.pepa], den:r=>r[SCOL.db], fmt:f2, mind:150, minL:'dropbacks'},
 {k:'cpoe',  l:'CPOE',                  num:r=>r[SCOL.cpoe]!=null&&r[SCOL.db]?r[SCOL.cpoe]*r[SCOL.db]:null, den:r=>r[SCOL.db], fmt:v=>v==null?'·':signed(v,x=>x.toFixed(1))+'%', sgn:1, mind:150, minL:'dropbacks'},
 {k:'ryd',   l:'Rush yards',            num:r=>r[SCOL.ryd], fmt:f0},
 {k:'rtd',   l:'Rush TD',               num:r=>r[SCOL.rtd], fmt:f0},
 {k:'car',   l:'Carries',               num:r=>r[SCOL.car], fmt:f0},
 {k:'ypc',   l:'Yards per carry',       num:r=>r[SCOL.ryd], den:r=>r[SCOL.car], fmt:f2, mind:100, minL:'carries'},
 {k:'epaCar',l:'EPA per carry',         num:r=>r[SCOL.repa], den:r=>r[SCOL.car], fmt:f2, sgn:1, mind:100, minL:'carries'},
 {k:'gl',    l:'Goal-line carries',     num:r=>r[SCOL.gl],  fmt:f0},
 {k:'rzc',   l:'Red-zone carries',      num:r=>r[SCOL.rzc], fmt:f0},
 {k:'recyd', l:'Receiving yards',       num:r=>r[SCOL.recyd], fmt:f0},
 {k:'rectd', l:'Receiving TD',          num:r=>r[SCOL.rectd], fmt:f0},
 {k:'tgt',   l:'Targets',               num:r=>r[SCOL.tgt], fmt:f0},
 {k:'rec',   l:'Receptions',            num:r=>r[SCOL.rec], fmt:f0},
 {k:'ypt',   l:'Yards per target',      num:r=>r[SCOL.recyd], den:r=>r[SCOL.tgt], fmt:f2, mind:50, minL:'targets'},
 {k:'ctch',  l:'Catch rate',            num:r=>r[SCOL.rec], den:r=>r[SCOL.tgt], fmt:pct1, mind:50, minL:'targets'},
 {k:'epaTgt',l:'EPA per target',        num:r=>r[SCOL.recepa], den:r=>r[SCOL.tgt], fmt:f2, sgn:1, mind:50, minL:'targets'},
 {k:'adot',  l:'aDOT',                  num:r=>r[SCOL.adot]!=null&&r[SCOL.tgt]?r[SCOL.adot]*r[SCOL.tgt]:null, den:r=>r[SCOL.tgt], fmt:f1, mind:50, minL:'targets'},
 {k:'air',   l:'Air yards',             num:r=>r[SCOL.air], fmt:f0},
 {k:'yac',   l:'Yards after catch',     num:r=>r[SCOL.yac], fmt:f0},
 {k:'rztgt', l:'Red-zone targets',      num:r=>r[SCOL.rztgt], fmt:f0},
 {k:'eztgt', l:'End-zone targets',      num:r=>r[SCOL.eztgt], fmt:f0},
 {k:'tshare',l:'Target share (wk avg)', num:r=>r[SCOL.tshare]!=null?r[SCOL.tshare]*r[SCOL.g]:null, den:r=>r[SCOL.g], fmt:pct1, ming:8},
 {k:'ashare',l:'Air-yards share (wk avg)', num:r=>r[SCOL.ashare]!=null?r[SCOL.ashare]*r[SCOL.g]:null, den:r=>r[SCOL.g], fmt:pct1, ming:8},
 {k:'wopr',  l:'WOPR (wk avg)',         num:r=>r[SCOL.wopr]!=null?r[SCOL.wopr]*r[SCOL.g]:null, den:r=>r[SCOL.g], fmt:f2, ming:8},
 {k:'fpoe1', l:'FPOE v1 (legacy)',      num:r=>r[SCOL.fpoe], fmt:v=>signed(v,f1), sgn:1},
];
const BK = {}; BOARDS.forEach(b=>BK[b.k]=b);
const QUICK_BOARDS = [
 ['fpoe2','📈 FPOE leaders'], ['afpoe2','🛡 Adjusted FPOE'], ['fppg','⚡ FP per game'],
 ['epaTgt','🎯 EPA / target'], ['epaCar','🏃 EPA / carry'], ['cpoe','🎯 CPOE'],
 ['wopr','⚖ WOPR'], ['gl','🥅 Goal-line carries'], ['air','✈ Air yards'],
];
const bParams = o => '#/boards?'+new URLSearchParams(o).toString();
function playerCell(pi, seasonCtx){
  const p = E.players[pi]||[];
  const nm = esc(p[1]||'?');
  if(p[5]===1 && p[0]!=null) return `<a href="#/p/${p[0]}">${nm}</a> <span class="pos">${esc(p[2]||'')}</span>`;
  return `${nm} <span class="pos">${esc(p[2]||'')}</span> <span class="badge" title="never AFFL-rostered">NFL</span>`;
}
function boardsView(qs){
  const q = new URLSearchParams(qs||'');
  const y = q.has('y') ? +q.get('y') : LAST;
  const m = BK[q.get('m')] ? q.get('m') : 'fpoe2';
  const bm = BK[m];
  const pos = (q.get('pos')||'').split(',').filter(Boolean);
  const scope = q.get('scope')==='ro' ? 'ro' : 'all';
  const asc = q.get('d')==='a';
  const lim = +(q.get('n')||50) || 50;
  const ming = q.has('g') ? +q.get('g') : (bm.ming||0);
  const mind = q.has('v') ? +q.get('v') : (bm.mind||0);
  const dy = +(q.get('dy')||LAST);
  const dpos = q.get('dpos')||'RB';
  const st = {y, m, pos:pos.join(','), scope, d:asc?'a':'', n:lim, dy, dpos};
  const link = o => bParams(Object.assign({}, st, o));

  // ---- aggregate season rows ----
  const posSet = pos.length? new Set(pos) : null;
  const groups = new Map();
  for(const r of E.seasonRows){
    if(y>0 && r[SCOL.s]!==y) continue;
    const pi = r[SCOL.p];
    if(posSet && !posSet.has(EPOS[pi])) continue;
    if(scope==='ro' && (E.players[pi]||[])[5]!==1) continue;
    const k = y>0 ? pi+'|'+r[SCOL.s] : pi;
    let g = groups.get(k);
    if(!g){ g={pi, s:y>0?r[SCOL.s]:null, g:0, fp:0, num:0, den:0, hasNum:false, tms:new Set(), sns:new Set()}; groups.set(k,g); }
    g.g += r[SCOL.g]||0; g.fp += r[SCOL.fp]||0;
    if(r[SCOL.tm]) g.tms.add(r[SCOL.tm]);
    g.sns.add(r[SCOL.s]);
    const v = bm.num(r);
    if(v!=null && !isNaN(v)){ g.num += v; g.hasNum=true; }
    if(bm.den){ const d=bm.den(r); if(d!=null&&!isNaN(d)) g.den += d; }
  }
  let list = [...groups.values()].filter(g=>g.hasNum && g.g>=ming && (!bm.den || g.den>=mind));
  const val = g => bm.den ? (g.den? g.num/g.den : null) : g.num;
  list.sort((a,b)=>((val(b)??-1e18)-(val(a)??-1e18))*(asc?-1:1));
  const shown = list.slice(0,lim);
  const maxAbs = Math.max(1e-9, ...shown.map(g=>Math.abs(val(g)||0)));

  const rows = shown.map((g,i)=>{
    const v = val(g);
    const w = Math.min(100, Math.abs(v||0)/maxAbs*100);
    return `<tr>
      <td class="l dim">${i+1}</td>
      <td class="l">${playerCell(g.pi)}</td>
      ${y>0?'':`<td class="dim">${g.sns.size}</td>`}
      <td class="l dim small">${esc([...g.tms].slice(0,3).join(','))}</td>
      <td>${f0(g.g)}</td><td>${f1(g.fp)}</td>
      ${bm.den?`<td class="dim">${f0(g.den)}</td>`:''}
      <td data-v="${v==null?-1e18:v}" class="${bm.sgn?cls(v):''}"><b>${bm.fmt(v)}</b></td>
      <td class="l" style="min-width:120px"><span class="barw"><span class="bar ${bm.sgn&&v<0?'barneg':''}" style="width:${w}%"></span></span></td>
    </tr>`;
  }).join('');

  // ---- defense boards ----
  const DB_ = E.defBoards||[], DBC = {}; (E.defBoardCols||[]).forEach((c,i)=>DBC[c]=i);
  const dRows = DB_.filter(r=>r[DBC.s]===dy && r[DBC.pos]===dpos)
    .sort((a,b)=>(b[DBC.stdpg]||0)-(a[DBC.stdpg]||0))
    .map((r,i)=>{
      const idx = r[DBC.idx];
      const chip = idx==null?'·':`<span class="chip" style="background:${idx>1.05?'rgba(255,77,94,.18)':idx<0.95?'rgba(55,214,122,.16)':'transparent'}">${f2(idx)}</span>`;
      return `<tr><td class="l dim">${i+1}</td><td class="l"><b>${esc(r[DBC.def])}</b></td><td>${r[DBC.g]}</td>
        <td data-v="${r[DBC.stdpg]}"><b>${f1(r[DBC.stdpg])}</b></td>
        <td>${f1(r[DBC.afp2pg])}</td><td>${f1(r[DBC.xfp2pg])}</td>
        <td data-v="${idx==null?-9:idx}">${chip}</td></tr>`;
    }).join('');
  const dySel = [...new Set(DB_.map(r=>r[DBC.s]))].sort();
  const dposList = [...new Set(DB_.map(r=>r[DBC.pos]))];

  app.innerHTML = `<div class="wrap">
    <div class="hero"><div class="kicker">NFL-wide season boards · ${f0(E.seasonRows.length)} player-seasons 2014–${LAST} · every QB/RB/WR/TE/K, not just the rostered</div>
    <h1 class="display">Leaderboards</h1></div>
    <div class="presets">${QUICK_BOARDS.map(([k,l])=>`<a class="chip ${m===k?'on lime':''}" href="${link({m:k,g:'',v:''})}">${l}</a>`).join('')}</div>
    <div class="xbar">
      <div class="xrow"><span class="lbl">Season</span>
        <a class="chip ${y===0?'on':''}" href="${link({y:0})}">Career 2014–${LAST}</a>
        ${YEARS.filter(x=>x<=LAST).map(x=>`<a class="chip ${y===x?'on':''}" href="${link({y:x})}">${x}</a>`).join('')}</div>
      <div class="xrow"><span class="lbl">Position</span>
        ${['QB','RB','WR','TE','K'].map(p=>{
          const next = pos.includes(p)? pos.filter(x=>x!==p) : [...pos,p];
          return `<a class="chip ${pos.includes(p)?'on':''}" href="${link({pos:next.join(',')})}">${p}</a>`;}).join('')}</div>
      <div class="xrow"><span class="lbl">Measure</span>
        <select id="bmeasure">${BOARDS.map(b=>`<option value="${b.k}" ${b.k===m?'selected':''}>${b.l}</option>`).join('')}</select>
        <span class="lbl" style="width:auto;margin-left:14px">Min games</span><input id="bg" type="number" min="0" value="${ming}" style="width:64px">
        ${bm.den?`<span class="lbl" style="width:auto;margin-left:14px">Min ${bm.minL||'volume'}</span><input id="bv" type="number" min="0" value="${mind}" style="width:74px">`:''}
        <span class="lbl" style="width:auto;margin-left:14px">Show</span>
        <select id="bn">${[25,50,100,250].map(n=>`<option ${lim===n?'selected':''}>${n}</option>`).join('')}</select>
        <a class="chip ${asc?'on':''}" href="${link({d:asc?'':'a'})}" title="flip sort direction">${asc?'▲ ascending':'▼ descending'}</a>
        <a class="chip ${scope==='ro'?'on':''}" href="${link({scope:scope==='ro'?'all':'ro'})}" title="restrict to players who have been on an AFFL roster">AFFL-rostered only</a></div>
    </div>
    <div class="resmeta"><span>${shown.length} of ${f0(list.length)} qualifying</span><span>${y>0?y:'careers 2014–'+LAST}</span><span>${esc(bm.l)}${bm.den?' (rate)':''}</span><span>scoring: ESPN standard non-PPR · xFP v2</span></div>
    <div class="tblwrap"><table class="tbl"><thead><tr>
      <th class="l">#</th><th class="l">Player</th>${y>0?'':'<th>Sns</th>'}<th class="l">Team</th><th>G</th><th>FP</th>${bm.den?`<th>${esc(bm.minL||'den')}</th>`:''}<th>${esc(bm.l)}</th><th class="l"></th>
    </tr></thead><tbody>${rows}</tbody></table></div>
    <p class="dim small" style="margin-top:8px">Boards rank <b>all</b> NFL player-seasons at QB/RB/WR/TE/K (2014–${LAST}), not only AFFL-rostered players — the <span class="badge">NFL</span> badge marks players no AFFL manager has ever held. Expected FP is xfp_v2 (ffopportunity canon); adjusted FPOE applies leave-one-week-out opponent factors (adjfac_v1). Rate boards enforce the volume minimum shown. Weekly single-game boards live in <a href="#/explore">Explore</a> under the “weeks” grain.</p>

    <h2 class="sect">Defense vs position <span class="sub">fantasy points allowed per game (defense × position boards)</span></h2>
    <div class="xrow"><span class="lbl">Season</span>${dySel.map(x=>`<a class="chip ${dy===x?'on':''}" href="${link({dy:x})}">${x}</a>`).join('')}</div>
    <div class="xrow"><span class="lbl">Position</span>${dposList.map(p=>`<a class="chip ${dpos===p?'on':''}" href="${link({dpos:p})}">${p}</a>`).join('')}</div>
    <div class="tblwrap" style="max-width:760px"><table class="tbl"><thead><tr>
      <th class="l">#</th><th class="l">Defense</th><th>G</th><th title="std_fp_v1 allowed per game (includes fumbles/kicking scope)">Std FP/g</th><th title="v2-scope actual allowed per game">v2 FP/g</th><th title="expected (xfp_v2) allowed per game">xFP/g</th><th title="afp2 allowed vs league average (1.00 = league)">Index</th>
    </tr></thead><tbody>${dRows}</tbody></table></div>
    <p class="dim small" style="margin-top:8px">Most generous defenses first. <b>Index</b> is v2-scope points allowed per game vs the league average for that position-season (1.00 = league); it is the season-level cousin of the leave-one-week-out factor used in adjusted FPOE. ${dpos==='K'?'K boards show the std scope only — kicking is outside the v2 model.':''}</p>
  </div>`;
  $('#bmeasure').onchange = e=>{ location.hash = link({m:e.target.value, g:'', v:''}); };
  $('#bg').onchange = e=>{ location.hash = link({g:+e.target.value||0}); };
  const bv=$('#bv'); if(bv) bv.onchange = e=>{ location.hash = link({v:+e.target.value||0}); };
  $('#bn').onchange = e=>{ location.hash = link({n:+e.target.value}); };
  sortableTable(app);
}

/* ---------------- COMPARE ---------------- */
function compareView(qs){
  const q = new URLSearchParams(qs||'');
  const sel = (q.get('p')||'').split(',').filter(Boolean).map(Number).filter(i=>!isNaN(i)&&E.players[i]).slice(0,4);
  const m = BK[q.get('m')] ? q.get('m') : 'fp';
  const bm = BK[m];
  const cLink = (ps,mk) => '#/compare?'+new URLSearchParams({p:ps.join(','), m:mk||m}).toString();

  const rowsBy = new Map();
  for(const r of E.seasonRows){
    const pi = r[SCOL.p];
    if(!sel.includes(pi)) continue;
    (rowsBy.get(pi)||rowsBy.set(pi,[]).get(pi)).push(r);
  }
  const seasons = [...new Set([].concat(...sel.map(pi=>(rowsBy.get(pi)||[]).map(r=>r[SCOL.s]))))].sort();
  const vOf = r => { const v=bm.num(r); if(v==null||isNaN(v)) return null; return bm.den? (bm.den(r)? v/bm.den(r):null) : v; };
  const careers = sel.map(pi=>{
    const rs = rowsBy.get(pi)||[];
    const c = {g:0,fp:0,xfp2:0,fpoe2:0,num:0,den:0,has:false};
    rs.forEach(r=>{ c.g+=r[SCOL.g]||0; c.fp+=r[SCOL.fp]||0; c.xfp2+=r[SCOL.xfp2]||0; c.fpoe2+=r[SCOL.fpoe2]||0;
      const v=bm.num(r); if(v!=null&&!isNaN(v)){c.num+=v;c.has=true;} if(bm.den){const d=bm.den(r); if(d!=null&&!isNaN(d))c.den+=d;} });
    c.val = !c.has? null : bm.den? (c.den? c.num/c.den:null) : c.num;
    return c;
  });
  const allVals = [];
  seasons.forEach(s=>sel.forEach(pi=>{ const r=(rowsBy.get(pi)||[]).find(x=>x[SCOL.s]===s); if(r){const v=vOf(r); if(v!=null)allVals.push(Math.abs(v));} }));
  const mx = Math.max(1e-9, ...allVals);

  const cards = sel.map((pi,ci)=>{
    const p = E.players[pi], c = careers[ci];
    const affl = p[5]===1 && p[0]!=null ? PL[p[0]] : null;
    return `<div class="card" style="position:relative">
      <a class="chip" style="position:absolute;top:10px;right:10px" href="${cLink(sel.filter(x=>x!==pi))}" title="remove">✕</a>
      <div style="display:flex;gap:12px;align-items:center">
        ${p[4]?`<img src="${esc(p[4])}" alt="" style="width:72px;height:54px;object-fit:cover;object-position:top;border-radius:10px;border:1px solid var(--rule)" onerror="this.style.display='none'">`:''}
        <div><div style="font-family:'Barlow Condensed';font-weight:700;font-size:20px">${p[5]===1&&p[0]!=null?`<a href="#/p/${p[0]}">${esc(p[1])}</a>`:esc(p[1])}</div>
        <div class="dim small">${esc(p[2]||'')}${p[5]!==1?' · never AFFL-rostered':''}</div></div></div>
      <div class="statline" style="margin-top:10px">
        <div class="stat"><div class="v">${f0(c.g)}</div><div class="l">G</div></div>
        <div class="stat"><div class="v">${f1(c.fp)}</div><div class="l">FP</div></div>
        <div class="stat"><div class="v">${f1(c.xfp2)}</div><div class="l">xFP</div></div>
        <div class="stat"><div class="v ${cls(c.fpoe2)}">${signed(c.fpoe2,f1)}</div><div class="l">FPOE</div></div>
        ${affl?`<div class="stat"><div class="v">${f1(affl.afflPts)}</div><div class="l">AFFL pts</div></div>`:''}
      </div></div>`;
  }).join('');

  const seasonRowsHtml = seasons.map(s=>{
    const cells = sel.map(pi=>{
      const r = (rowsBy.get(pi)||[]).find(x=>x[SCOL.s]===s);
      if(!r) return '<td class="dim">·</td><td class="l"></td>';
      const v = vOf(r);
      const w = v==null?0:Math.min(100,Math.abs(v)/mx*100);
      return `<td data-v="${v==null?-1e18:v}" class="${bm.sgn?cls(v):''}"><b>${bm.fmt(v)}</b> <span class="dim small">${r[SCOL.g]}g</span></td>
        <td class="l" style="min-width:90px"><span class="barw"><span class="bar ${bm.sgn&&v<0?'barneg':''}" style="width:${w}%"></span></span></td>`;
    }).join('');
    return `<tr><td class="l num"><b>${s}</b></td>${cells}</tr>`;
  }).join('');
  const careerCells = careers.map(c=>`<td data-v="${c.val==null?-1e18:c.val}" class="${bm.sgn?cls(c.val):''}"><b>${bm.fmt(c.val)}</b> <span class="dim small">${f0(c.g)}g</span></td><td class="l"></td>`).join('');

  app.innerHTML = `<div class="wrap">
    <div class="hero"><div class="kicker">Any two to four of the ${f0(E.players.length)} players in the record — rostered or not</div>
    <h1 class="display">Compare</h1></div>
    <div class="xbar">
      <div class="xrow"><span class="lbl">Add player</span><input type="text" id="cq" class="searchbox" placeholder="Type a name…" autocomplete="off"><div id="csug" class="presets" style="margin-left:10px"></div></div>
      <div class="xrow"><span class="lbl">Measure</span><select id="cm">${BOARDS.map(b=>`<option value="${b.k}" ${b.k===m?'selected':''}>${b.l}</option>`).join('')}</select></div>
    </div>
    ${sel.length? `<div class="grid g${Math.min(4,Math.max(2,sel.length))}" style="margin-top:16px">${cards}</div>` : '<p class="dim" style="margin-top:20px">Add two or more players to compare their NFL seasons on any measure.</p>'}
    ${sel.length>=2? `<h2 class="sect">Career shape <span class="sub">percentile within each player's own position · careers with 16+ games</span></h2>
    ${chartBox('cmpradar', 360)}
    <h2 class="sect">${esc(bm.l)} by season <span class="sub">bars share one scale${bm.den?' · rate over each season':''}</span></h2>
    <div class="tblwrap"><table class="tbl"><thead><tr><th class="l">Season</th>${sel.map(pi=>`<th colspan="2" class="l">${esc(E.players[pi][1])}</th>`).join('')}</tr></thead>
    <tbody>${seasonRowsHtml}
    <tr style="border-top:2px solid var(--rule)"><td class="l"><b>Career</b></td>${careerCells}</tr></tbody></table></div>
    <p class="dim small" style="margin-top:8px">Season grain, regular season only, 2014–${LAST}. Expected FP is xfp_v2; AFFL custody totals appear on each player's card when they have league history.</p>`:''}
  </div>`;

  if(sel.length>=2) drawCmpRadar(sel, rowsBy);
  const cq=$('#cq'), sug=$('#csug');
  cq.oninput = ()=>{
    const t = cq.value.trim().toLowerCase();
    if(t.length<2){ sug.innerHTML=''; return; }
    const hits = [];
    for(let i=0;i<E.players.length && hits.length<400;i++){
      const nm=(ENAME[i]||'').toLowerCase();
      if(nm.includes(t) && !sel.includes(i)) hits.push(i);
    }
    hits.sort((a,b)=>{ const an=(ENAME[a]||'').toLowerCase().startsWith(t)?0:1, bn=(ENAME[b]||'').toLowerCase().startsWith(t)?0:1; return an-bn; });
    sug.innerHTML = hits.slice(0,10).map(i=>`<a class="chip" href="${cLink([...sel,i])}">${esc(ENAME[i])} <span class="pos">${esc(EPOS[i]||'')}</span></a>`).join('');
  };
  $('#cm').onchange = e=>{ location.hash = cLink(sel, e.target.value); };
}

/* ================= EXPLORE ================= */
const COL = {}; E.cols.forEach((c,i)=>COL[c]=i);
const SCOL = {}; E.seasonCols.forEach((c,i)=>SCOL[c]=i);
const EIDX = {}; E.players.forEach((p,i)=>EIDX[p[0]]=i);
const EPOS = E.players.map(p=>p[2]);
const ENAME = E.players.map(p=>p[1]);

function defState(){ return {sc:'started', gr:'player', s0:2014, s1:LAST, w0:1, w1:18, f:[], pos:[], pq:'',
  ms:['affl','fp','xfp2','fpoe2'], sort:'affl', dir:-1, lim:50, md:0}; }
const encState = st => encodeURIComponent(btoa(unescape(encodeURIComponent(JSON.stringify(st)))));
const decState = q => { try{ return Object.assign(defState(), JSON.parse(decodeURIComponent(escape(atob(decodeURIComponent(q)))))); }catch(e){ return defState(); } };

const R = COL; // row col idx
const M = [
 {k:'weeks', l:'Weeks', num:r=>1, fmt:f0, everOk:false},
 {k:'starts', l:'Starts', num:r=>r[R.st], fmt:f0},
 {k:'startRate', l:'Start rate', num:r=>r[R.st], den:r=>1, fmt:pct1},
 {k:'affl', l:'AFFL pts', num:r=>r[R.affl], fmt:f1},
 {k:'afflPg', l:'AFFL pts/wk', num:r=>r[R.affl], den:r=>1, fmt:f1},
 {k:'benchAffl', l:'Bench AFFL pts', num:r=>r[R.st]?0:r[R.affl], fmt:f1, needBench:true},
 {k:'fp', l:'NFL FP', num:r=>r[R.fp], fmt:f1, everOk:true, sNum:r=>r[SCOL.fp]},
 {k:'startedFp', l:'FP started', num:r=>r[R.st]?r[R.fp]:0, fmt:f1},
 {k:'benchFp', l:'FP on bench', num:r=>r[R.st]?0:r[R.fp], fmt:f1, needBench:true},
 {k:'xfp2', l:'xFP (v2)', num:r=>r[R.xfp2], fmt:f1, everOk:true, sNum:r=>r[SCOL.xfp2]},
 {k:'fpoe2', l:'FPOE (v2)', num:r=>r[R.fpoe2], fmt:v=>signed(v,f1), everOk:true, sNum:r=>r[SCOL.fpoe2]},
 {k:'xfp', l:'xFP v1 (legacy)', num:r=>r[R.xfp], fmt:f1, everOk:true, sNum:r=>r[SCOL.xfp]},
 {k:'fpoe', l:'FPOE v1 (legacy)', num:r=>r[R.fpoe], fmt:v=>signed(v,f1), everOk:true, sNum:r=>r[SCOL.fpoe]},
 {k:'tgt', l:'Targets', num:r=>r[R.tgt], fmt:f0, everOk:true, sNum:r=>r[SCOL.tgt]},
 {k:'rec', l:'Receptions', num:r=>r[R.rec], fmt:f0, everOk:true, sNum:r=>r[SCOL.rec]},
 {k:'recyd', l:'Rec yds', num:r=>r[R.recyd], fmt:f0, everOk:true, sNum:r=>r[SCOL.recyd]},
 {k:'rectd', l:'Rec TD', num:r=>r[R.rectd], fmt:f0, everOk:true, sNum:r=>r[SCOL.rectd]},
 {k:'air', l:'Air yards', num:r=>r[R.air], fmt:f0},
 {k:'adot', l:'aDOT', num:r=>r[R.air], den:r=>r[R.tgt], fmt:f1, minLabel:'targets'},
 {k:'ypt', l:'Yds/target', num:r=>r[R.recyd], den:r=>r[R.tgt], fmt:f2, minLabel:'targets'},
 {k:'catch', l:'Catch %', num:r=>r[R.rec], den:r=>r[R.tgt], fmt:pct1, minLabel:'targets'},
 {k:'rztgt', l:'RZ targets', num:r=>r[R.rztgt], fmt:f0},
 {k:'eztgt', l:'End-zone tgts', num:r=>r[R.eztgt], fmt:f0},
 {k:'epaTgt', l:'EPA/target', num:r=>r[R.recepa], den:r=>r[R.tgt], fmt:f2, minLabel:'targets'},
 {k:'car', l:'Carries', num:r=>r[R.car], fmt:f0, everOk:true, sNum:r=>r[SCOL.car]},
 {k:'ryd', l:'Rush yds', num:r=>r[R.ryd], fmt:f0, everOk:true, sNum:r=>r[SCOL.ryd]},
 {k:'rtd', l:'Rush TD', num:r=>r[R.rtd], fmt:f0, everOk:true, sNum:r=>r[SCOL.rtd]},
 {k:'ypc', l:'Yds/carry', num:r=>r[R.ryd], den:r=>r[R.car], fmt:f2, minLabel:'carries'},
 {k:'gl', l:'Goal-line carries', num:r=>r[R.gl], fmt:f0},
 {k:'rzc', l:'RZ carries', num:r=>r[R.rzc], fmt:f0},
 {k:'epaCar', l:'EPA/carry', num:r=>r[R.repa], den:r=>r[R.car], fmt:f2, minLabel:'carries'},
 {k:'db', l:'Dropbacks', num:r=>r[R.db], fmt:f0},
 {k:'pyd', l:'Pass yds', num:r=>r[R.pyd], fmt:f0, everOk:true, sNum:r=>r[SCOL.pyd]},
 {k:'ptd', l:'Pass TD', num:r=>r[R.ptd], fmt:f0, everOk:true, sNum:r=>r[SCOL.ptd]},
 {k:'int', l:'INT', num:r=>r[R.int], fmt:f0, everOk:true, sNum:r=>r[SCOL.pint]},
 {k:'epaDb', l:'EPA/dropback', num:r=>r[R.pepa], den:r=>r[R.db], fmt:f2, minLabel:'dropbacks'},
 {k:'cpoe', l:'CPOE', num:r=>r[R.cpoe]!=null&&r[R.db]?r[R.cpoe]*r[R.db]:null, den:r=>r[R.db], fmt:v=>v==null?'·':v.toFixed(1)+'%', minLabel:'dropbacks'},
 {k:'wopr', l:'WOPR (avg)', num:r=>r[R.wopr], den:r=>r[R.wopr]!=null?1:0, fmt:f2},
];
const MK = {}; M.forEach(m=>MK[m.k]=m);
const GRAINS = [
 ['player','Player'], ['playerSeason','Player-season'], ['franchise','Franchise'],
 ['teamSeason','Team-season'], ['season','Season'], ['nflTeam','NFL team'],
 ['college','College'], ['pos','Position'], ['weeks','Individual weeks']];

const PRESETS = [
 {id:'bench', icon:'🪑', label:'Workload left on benches', blurb:'Bench weeks only, 2018+',
  state:{sc:'bench', gr:'player', s0:2018, ms:['benchAffl','tgt','car','rztgt','fp'], sort:'benchAffl'}},
 {id:'heldstarted', icon:'⚖', label:'Talent held vs started', blurb:'FP realized vs left on bench, by franchise',
  state:{sc:'rostered', gr:'franchise', s0:2018, ms:['fp','startedFp','benchFp','startRate'], sort:'benchFp'}},
 {id:'fpoe', icon:'📈', label:'Opportunity vs realized', blurb:'xFP v2 vs FP by franchise (started)',
  state:{sc:'started', gr:'franchise', ms:['xfp2','fp','fpoe2','affl'], sort:'fpoe2'}},
 {id:'rz', icon:'🎯', label:'Red-zone custody', blurb:'RZ opportunity by franchise',
  state:{sc:'started', gr:'franchise', ms:['rztgt','rzc','gl','eztgt'], sort:'rztgt'}},
 {id:'pipeline', icon:'⛓', label:'NFL-team pipelines', blurb:'Which NFL rosters feed the AFFL',
  state:{sc:'rostered', gr:'nflTeam', ms:['weeks','affl','fp'], sort:'weeks'}},
 {id:'college', icon:'🎓', label:'College pipelines', blurb:'Custody weeks by college',
  state:{sc:'rostered', gr:'college', ms:['weeks','affl','fp'], sort:'affl'}},
 {id:'bestweeks', icon:'💥', label:'Best started weeks', blurb:'Single-week custody explosions',
  state:{sc:'started', gr:'weeks', ms:['affl','fp','tgt','car'], sort:'affl', lim:100}},
 {id:'careers', icon:'👑', label:'Custody careers', blurb:'Career AFFL value by player',
  state:{sc:'rostered', gr:'player', ms:['weeks','starts','affl','fp','fpoe'], sort:'affl'}},
];

let X = null; // current explore state
let lastAgg = null;
function exploreView(qs){
  const q = (qs||'').split('&').find(x=>x.startsWith('q='));
  X = q ? decState(q.slice(2)) : (X || defState());
  const fChips = E.franchises.map((f,i)=>`<span class="chip ${X.f.includes(f[0])?'on':''}" data-f="${f[0]}">${esc(f[2])}</span>`).join('');
  const posChips = ['QB','RB','WR','TE','K','D/ST'].map(p=>`<span class="chip ${X.pos.includes(p)?'on':''}" data-pos="${p}">${p}</span>`).join('');
  const msChips = M.map(m=>`<span class="chip ${X.ms.includes(m.k)?'on lime':''}" data-ms="${m.k}">${m.l}</span>`).join('');
  const yearOpts = lo => YEARS.filter(y=>y<=LAST).map(y=>`<option ${((lo?X.s0:X.s1)===y)?'selected':''}>${y}</option>`).join('');
  app.innerHTML = `<div class="wrap">
    <div class="hero" style="padding-bottom:0"><div class="kicker">Query the league's custody-joined NFL record · ${f0(E.rows.length)} weekly rows · v${esc(E.meta.version)}</div>
    <h1 class="display">Explore</h1></div>
    <div class="presets">${PRESETS.map(p=>`<span class="chip" data-preset="${p.id}" title="${esc(p.blurb)}">${p.icon} ${p.label}</span>`).join('')}</div>
    <div class="xbar">
      <details class="mobile-filters" open>
      <summary>Filters</summary>
      <div class="xrow"><span class="lbl">Custody</span>
        ${[['started','While started'],['rostered','While rostered'],['bench','Bench weeks'],['ever','Ever rostered (NFL seasons)']].map(([v,l])=>`<span class="chip ${X.sc===v?'on':''}" data-sc="${v}">${l}</span>`).join('')}</div>
      <div class="xrow"><span class="lbl">Grain</span>
        ${GRAINS.map(([v,l])=>`<span class="chip ${X.gr===v?'on':''}" data-gr="${v}" ${X.sc==='ever'&&!['player','playerSeason','nflTeam','season'].includes(v)?'style="opacity:.35;pointer-events:none"':''}>${l}</span>`).join('')}</div>
      <div class="xrow"><span class="lbl">Seasons</span>
        <select id="xs0">${yearOpts(1)}</select><span class="dim">→</span><select id="xs1">${yearOpts(0)}</select>
        <span class="lbl" style="width:auto;margin-left:14px">Weeks</span>
        <input id="xw0" type="number" min="1" max="18" value="${X.w0}" style="width:60px">
        <span class="dim">→</span>
        <input id="xw1" type="number" min="1" max="18" value="${X.w1}" style="width:60px">
        <span class="lbl" style="width:auto;margin-left:14px">Min sample</span>
        <input id="xmd" type="number" min="0" value="${X.md}" style="width:70px" title="Minimum denominator for the sort measure (targets/carries/dropbacks for rates)">
        <span class="lbl" style="width:auto;margin-left:14px">Limit</span>
        <select id="xlim">${[25,50,100,250,1000].map(n=>`<option ${X.lim===n?'selected':''}>${n}</option>`).join('')}</select></div>
      <div class="xrow"><span class="lbl">Franchise</span>${fChips}</div>
      <div class="xrow"><span class="lbl">Position</span>${posChips}</div>
      <div class="xrow"><span class="lbl">Player</span><input type="text" id="xpq" class="searchbox" placeholder="Name contains…" value="${esc(X.pq)}"></div>
      <div class="xrow"><span class="lbl">Measures</span><div style="display:flex;flex-wrap:wrap;gap:6px">${msChips}</div></div>
      </details>
      <div class="xrow" style="justify-content:flex-end;gap:8px">
        <span id="xwarn"></span>
        <button class="btn ghost" id="xreset">Reset</button>
        <button class="btn ghost" id="xcsv">⇩ CSV</button>
        <button class="btn ghost" id="xchart">◔ Chart</button>
        <button class="btn lime" id="xrun">Run query</button></div>
    </div>
    <div class="sentence" id="xsentence"></div>
    <div class="resmeta" id="xmeta"></div>
    <div id="xout"></div>
    <div id="scatterbox" style="display:none"><div class="card">
      <div class="xrow"><span class="lbl">X axis</span><select id="cx"></select><span class="lbl" style="width:auto">Y axis</span><select id="cy"></select><span class="dim small" id="pinhint">click a mark to pin it</span></div>
      <canvas id="scatter" width="1180" height="620"></canvas>
      <div class="legend" id="pins"></div></div>
      <div id="scattertip"></div></div>
  </div>`;
  // bindings
  app.querySelectorAll('[data-sc]').forEach(c=>c.onclick=()=>{ X.sc=c.dataset.sc; if(X.sc==='ever'&&!['player','playerSeason','nflTeam','season'].includes(X.gr)) X.gr='playerSeason'; if(X.sc==='bench'&&X.s0<2018) X.s0=2018; syncHash(); });
  app.querySelectorAll('[data-gr]').forEach(c=>c.onclick=()=>{ X.gr=c.dataset.gr; syncHash(); });
  app.querySelectorAll('[data-f]').forEach(c=>c.onclick=()=>{ const f=c.dataset.f; X.f = X.f.includes(f)?X.f.filter(x=>x!==f):[...X.f,f]; syncHash(); });
  app.querySelectorAll('[data-pos]').forEach(c=>c.onclick=()=>{ const p=c.dataset.pos; X.pos = X.pos.includes(p)?X.pos.filter(x=>x!==p):[...X.pos,p]; syncHash(); });
  app.querySelectorAll('[data-ms]').forEach(c=>c.onclick=()=>{ const k=c.dataset.ms; X.ms = X.ms.includes(k)?X.ms.filter(x=>x!==k):[...X.ms,k]; if(!X.ms.includes(X.sort)) X.sort=X.ms[0]||'affl'; syncHash(); });
  app.querySelectorAll('[data-preset]').forEach(c=>c.onclick=()=>{ const p=PRESETS.find(x=>x.id===c.dataset.preset); X=Object.assign(defState(), p.state); syncHash(); });
  $('#xs0').onchange=e=>{X.s0=+e.target.value; syncHash();};
  $('#xs1').onchange=e=>{X.s1=+e.target.value; syncHash();};
  $('#xw0').onchange=e=>{X.w0=+e.target.value||1; syncHash();};
  $('#xw1').onchange=e=>{X.w1=+e.target.value||18; syncHash();};
  $('#xmd').onchange=e=>{X.md=+e.target.value||0; syncHash();};
  $('#xlim').onchange=e=>{X.lim=+e.target.value; syncHash();};
  $('#xpq').onchange=e=>{X.pq=e.target.value; syncHash();};
  $('#xreset').onclick=()=>{ X=defState(); syncHash(); };
  $('#xrun').onclick=()=>syncHash();
  $('#xcsv').onclick=exportCsv;
  $('#xchart').onclick=()=>{ const b=$('#scatterbox'); b.style.display = b.style.display==='none'?'':'none'; if(b.style.display!=='none') drawScatter(); };
  runQuery();
}
function syncHash(){ location.hash = '#/explore?q='+encState(X); }

function groupDefs(){
  const C = COL;
  return {
    player:{ key:r=>r[C.p], label:k=>{ const p=E.players[k]; return `<a href="#/p/${p[0]}">${esc(p[1])}</a> <span class="pos">${esc(p[2]||'')}</span>`; }, plain:k=>E.players[k][1]},
    playerSeason:{ key:r=>r[C.p]+'|'+r[C.s], label:k=>{ const [pi,s]=k.split('|'); const p=E.players[+pi]; return `<a href="#/p/${p[0]}">${esc(p[1])}</a> <span class="pos">${esc(p[2]||'')}</span> <span class="dim">${s}</span>`; }, plain:k=>{const [pi,s]=k.split('|'); return E.players[+pi][1]+' '+s;}},
    franchise:{ key:r=>r[C.f], label:k=>frLink(E.franchises[k][0]), plain:k=>E.franchises[k][1], fid:k=>E.franchises[k][0]},
    teamSeason:{ key:r=>r[C.f]+'|'+r[C.s], label:k=>{ const [fi,s]=k.split('|'); const fid=E.franchises[+fi][0]; return frLink(fid,+s)+` <span class="dim">${s}</span>`; }, plain:k=>{const [fi,s]=k.split('|'); return histName(+s, E.franchises[+fi][0])+' '+s;}, fid:k=>E.franchises[+k.split('|')[0]][0]},
    season:{ key:r=>r[C.s], label:k=>`<b>${k}</b>`, plain:k=>String(k)},
    nflTeam:{ key:r=>r[C.tm]||'—', label:k=>`<b>${esc(k)}</b>`, plain:k=>k},
    college:{ key:r=>{ const p=E.players[r[C.p]]; const pl=PL[p[0]]; return (pl&&pl.college)||'—'; }, label:k=>esc(k), plain:k=>k},
    pos:{ key:r=>EPOS[r[C.p]]||'—', label:k=>`<b>${esc(k)}</b>`, plain:k=>k},
    weeks:{ key:(r,i)=>i, label:(k,g)=>{ const r=E.rows[k]; const p=E.players[r[COL.p]]; const fid=E.franchises[r[COL.f]][0];
      return `<a href="#/p/${p[0]}">${esc(p[1])}</a> <span class="pos">${esc(p[2]||'')}</span> <span class="dim">· ${r[COL.s]} Wk ${r[COL.w]} · ${esc(histName(r[COL.s],fid))}</span>`; }, plain:k=>{const r=E.rows[k]; return E.players[r[COL.p]][1]+' '+r[COL.s]+' wk'+r[COL.w];}},
  };
}

function filterRows(){
  const C = COL;
  const fSet = X.f.length? new Set(X.f.map(fid=>E.franchises.findIndex(f=>f[0]===fid))) : null;
  const posSet = X.pos.length? new Set(X.pos) : null;
  const pq = X.pq.trim().toLowerCase();
  const out = [];
  for(let i=0;i<E.rows.length;i++){
    const r = E.rows[i];
    if(r[C.s]<X.s0||r[C.s]>X.s1) continue;
    if(r[C.w]<X.w0||r[C.w]>X.w1) continue;
    if(X.sc==='started' && !r[C.st]) continue;
    if(X.sc==='bench' && (r[C.st] || r[C.s]<2018)) continue;
    if(fSet && !fSet.has(r[C.f])) continue;
    if(posSet && !posSet.has(EPOS[r[C.p]])) continue;
    if(pq && !(ENAME[r[C.p]]||'').toLowerCase().includes(pq)) continue;
    out.push(i);
  }
  return out;
}

function aggregate(){
  if(X.sc==='ever') return aggregateEver();
  const gd = groupDefs()[X.gr];
  const idx = filterRows();
  const groups = new Map();
  const active = X.ms.map(k=>MK[k]).filter(Boolean);
  for(const i of idx){
    const r = E.rows[i];
    const k = gd.key(r, i);
    let g = groups.get(k);
    if(!g){ g = {k, n:0, sums:{}, dens:{}, rows:[]}; groups.set(k,g); }
    g.n++;
    if(g.rows.length<400) g.rows.push(i);
    for(const m of active){
      const v = m.num(r);
      if(v!=null && !isNaN(v)) g.sums[m.k]=(g.sums[m.k]||0)+v;
      if(m.den){ const d=m.den(r); if(d!=null&&!isNaN(d)) g.dens[m.k]=(g.dens[m.k]||0)+d; }
    }
  }
  let list = [...groups.values()];
  const sm = MK[X.sort]||active[0];
  const val = (g,m)=> m.den ? (g.dens[m.k]? (g.sums[m.k]||0)/g.dens[m.k] : null) : (g.sums[m.k]||0);
  if(X.md>0 && sm){ list = list.filter(g=> (sm.den? (g.dens[sm.k]||0) : g.n) >= X.md); }
  list.sort((a,b)=> ((val(b,sm)??-1e18)-(val(a,sm)??-1e18)) * (X.dir<0?1:-1));
  return {list: list.slice(0, X.lim), scanned: idx.length, total: groups.size, gd, active, val};
}
function aggregateEver(){
  const posSet = X.pos.length? new Set(X.pos) : null;
  const pq = X.pq.trim().toLowerCase();
  // "ever rostered" keeps its historical meaning: AFFL-rostered players only.
  // seasonRows now carry ALL NFL player-seasons (for Leaderboards); filter on
  // the rostered flag (players[i][5]) here.
  const rows = E.seasonRows.filter(r => r[SCOL.s]>=X.s0 && r[SCOL.s]<=X.s1
    && (E.players[r[SCOL.p]]||[])[5]===1
    && (!posSet || posSet.has(EPOS[r[SCOL.p]])) && (!pq || (ENAME[r[SCOL.p]]||'').toLowerCase().includes(pq)));
  const gd = {
    player:{key:r=>r[SCOL.p], label:k=>{const p=E.players[k];return `<a href="#/p/${p[0]}">${esc(p[1])}</a> <span class="pos">${esc(p[2]||'')}</span>`;}, plain:k=>E.players[k][1]},
    playerSeason:{key:r=>r[SCOL.p]+'|'+r[SCOL.s], label:k=>{const [pi,s]=k.split('|');const p=E.players[+pi];return `<a href="#/p/${p[0]}">${esc(p[1])}</a> <span class="pos">${esc(p[2]||'')}</span> <span class="dim">${s}</span>`;}, plain:k=>{const [pi,s]=k.split('|');return E.players[+pi][1]+' '+s;}},
    nflTeam:{key:r=>r[SCOL.tm]||'—', label:k=>`<b>${esc(k)}</b>`, plain:k=>k},
    season:{key:r=>r[SCOL.s], label:k=>`<b>${k}</b>`, plain:k=>String(k)},
  }[X.gr] || null;
  const active = X.ms.map(k=>MK[k]).filter(m=>m&&m.everOk);
  const groups = new Map();
  rows.forEach(r=>{
    const k = gd.key(r);
    let g = groups.get(k); if(!g){ g={k,n:0,sums:{},dens:{},rows:[]}; groups.set(k,g);} g.n += r[SCOL.g]||0;
    active.forEach(m=>{ const v = m.sNum ? m.sNum(r) : null; if(v!=null&&!isNaN(v)) g.sums[m.k]=(g.sums[m.k]||0)+v; });
  });
  let list=[...groups.values()];
  const sm = active.find(m=>m.k===X.sort)||active[0];
  const val=(g,m)=>g.sums[m.k]??null;
  if(sm) list.sort((a,b)=>((val(b,sm)??-1e18)-(val(a,sm)??-1e18)));
  return {list:list.slice(0,X.lim), scanned:rows.length, total:groups.size, gd, active, val, ever:true};
}

function sentence(){
  const msL = X.ms.map(k=>(MK[k]||{}).l).filter(Boolean).slice(0,5).join(', ');
  const scope = {started:'during weeks <b>started</b>', rostered:'during weeks <b>rostered</b>', bench:'during <b>bench</b> weeks', ever:'across <b>entire NFL seasons</b> of ever-rostered players'}[X.sc];
  const by = (GRAINS.find(g=>g[0]===X.gr)||['',''])[1].toLowerCase();
  const fr = X.f.length? ' by '+X.f.map(f=>'<b>'+esc((F[f]||{}).display_name)+'</b>').join(', ') : '';
  const pos = X.pos.length? ', '+X.pos.join('/') : '';
  const wk = (X.w0!==1||X.w1!==18)? `, weeks ${X.w0}–${X.w1}`:'';
  const md = X.md>0? `, minimum ${X.md} ${(MK[X.sort]&&MK[X.sort].den)?(MK[X.sort].minLabel||'sample'):'weeks'}`:'';
  return `${msL} by <b>${by}</b>, ${scope}${fr}${pos}, <b>${X.s0}–${X.s1}</b>${wk}${md}, sorted by <b>${(MK[X.sort]||{}).l}</b>.`;
}

function runQuery(){
  const t0 = performance.now();
  const agg = aggregate();
  lastAgg = agg;
  const {list, scanned, total, gd, active, val} = agg;
  $('#xsentence').innerHTML = sentence();
  const warns = [];
  if((X.sc==='bench'||X.ms.some(k=>MK[k]&&MK[k].needBench)) ) warns.push('bench custody exists 2018+ only');
  if(X.s0<2018 && X.sc!=='ever') warns.push('pre-2018: starter membership only; slots & bench unavailable');
  $('#xwarn').innerHTML = warns.map(w=>`<span class="chip warn">⚠ ${w}</span>`).join(' ');
  $('#xmeta').innerHTML = `<span>${list.length} of ${f0(total)} groups</span><span>${f0(scanned)} rows scanned</span><span>${(performance.now()-t0).toFixed(0)} ms</span><span>dataset v${esc(E.meta.version)}</span><span>coverage ${esc(E.meta.coverage)}</span>`;
  const head = `<tr><th class="l">#</th><th class="l">${esc((GRAINS.find(g=>g[0]===X.gr)||[])[1]||'')}</th><th>Wks</th>${active.map(m=>`<th class="sortable ${m.k===X.sort?'sorted':''}" data-ms="${m.k}">${m.l}${m.den?'*':''}</th>`).join('')}</tr>`;
  const body = list.map((g,i)=>`<tr class="click xrowr" data-k="${esc(String(g.k))}">
    <td class="l dim">${i+1}</td><td class="l">${gd.label(g.k,g)}</td><td class="dim">${f0(g.n)}</td>
    ${active.map(m=>{ const v=val(g,m); return `<td data-v="${v==null?-1e18:v}" class="${(m.k==='fpoe'||m.k==='benchAffl')?cls(v):''}">${m.fmt(v)}</td>`; }).join('')}</tr>
    <tr class="drillrow" data-k="${esc(String(g.k))}" style="display:none"><td colspan="${3+active.length}" class="l"></td></tr>`).join('');
  $('#xout').innerHTML = `<div class="tblwrap"><table class="tbl"><thead>${head}</thead><tbody>${body}</tbody></table></div>
    <p class="dim small" style="margin-top:8px">* rate measures divide by their denominator over the whole group. Click a header to re-sort, click a row for its weekly detail. AFFL points are ESPN applied totals; NFL measures are nflverse/std_fp_v1; expected FP is xfp_v2 (ffopportunity canon) with the legacy bucket model kept as xFP v1.</p>`;
  $('#xout').querySelectorAll('th.sortable').forEach(th=>th.onclick=()=>{ X.sort=th.dataset.ms; syncHash(); });
  if(X.gr!=='weeks') $('#xout').querySelectorAll('tr.xrowr').forEach(tr=>tr.onclick=e=>{ if(e.target.closest('a'))return; toggleDrill(tr.dataset.k); });
  if($('#scatterbox').style.display!=='none') drawScatter();
}

function toggleDrill(k){
  const g = lastAgg.list.find(x=>String(x.k)===k); if(!g||lastAgg.ever) return;
  const dr = $('#xout').querySelector(`tr.drillrow[data-k="${CSS.escape(k)}"]`);
  if(dr.style.display!=='none'){ dr.style.display='none'; return; }
  const C = COL;
  const rows = (g.rows||[]).map(i=>E.rows[i]).sort((a,b)=>(b[C.affl]||0)-(a[C.affl]||0)).slice(0,40);
  dr.firstChild.innerHTML = `<div class="tblwrap" style="margin:6px 0"><table class="tbl"><thead><tr>
    <th class="l">Player</th><th class="l">For</th><th>Year</th><th>Wk</th><th class="l">St</th><th>AFFL</th><th>FP</th><th>Tgt</th><th>Car</th><th class="l">NFL</th></tr></thead><tbody>
    ${rows.map(r=>{ const p=E.players[r[C.p]]; const fid=E.franchises[r[C.f]][0];
      return `<tr><td class="l">${esc(p[1])}</td><td class="l">${esc(histName(r[C.s],fid))}</td><td>${r[C.s]}</td><td>${r[C.w]}</td>
      <td class="l">${r[C.st]?'●':'bench'}</td><td>${f1(r[C.affl])}</td><td>${f1(r[C.fp])}</td><td>${f0(r[C.tgt])}</td><td>${f0(r[C.car])}</td>
      <td class="l dim small">${esc(r[C.tm]||'')}${r[C.opp]?' v '+esc(r[C.opp]):''}</td></tr>`; }).join('')}
    </tbody></table></div>`;
  dr.style.display='';
}

function exportCsv(){
  if(!lastAgg) return;
  const {list, active, gd, val} = lastAgg;
  const lines = [
    '# AFFL Savant Explore export',
    '# query: '+$('#xsentence').textContent,
    '# dataset: v'+E.meta.version+' · coverage '+E.meta.coverage+' · scoring: ESPN standard non-PPR',
    '# custody scope: '+X.sc+' · generated: '+new Date().toISOString(),
    ['group','weeks',...active.map(m=>m.l)].map(s=>'"'+String(s).replace(/"/g,'""')+'"').join(',')
  ];
  list.forEach(g=>{
    lines.push([gd.plain(g.k), g.n, ...active.map(m=>{ const v=val(g,m); return v==null?'':(Math.round(v*1000)/1000); })]
      .map(s=>'"'+String(s).replace(/"/g,'""')+'"').join(','));
  });
  const blob = new Blob([lines.join('\n')], {type:'text/csv'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = 'affl-savant-explore.csv'; a.click();
  URL.revokeObjectURL(a.href);
}

/* scatter */
let pinned = new Set();
function drawScatter(){
  if(!lastAgg) return;
  const {list, active, gd, val} = lastAgg;
  const sel = (id, def)=>{ const el=$(id); const opts=active.map(m=>`<option value="${m.k}">${m.l}</option>`).join('');
    if(el.innerHTML!==opts){ el.innerHTML=opts; el.value=def; el.onchange=drawScatter; } return el.value; };
  const xk = sel('#cx', active[0]?active[0].k:null), yk = sel('#cy', (active[1]||active[0]||{}).k);
  const mx = MK[xk], my = MK[yk]; if(!mx||!my) return;
  const cv = $('#scatter'), ctx = cv.getContext('2d');
  const Wd = cv.width, H = cv.height, P = {l:70,r:24,t:22,b:52};
  ctx.clearRect(0,0,Wd,H);
  const pts = list.map(g=>({g, x:val(g,mx), y:val(g,my)})).filter(p=>p.x!=null&&p.y!=null&&!isNaN(p.x)&&!isNaN(p.y));
  if(!pts.length) return;
  const xs = pts.map(p=>p.x), ys = pts.map(p=>p.y);
  const pad = (a,b)=>{ const d=(b-a)||1; return [a-d*.06, b+d*.06]; };
  let [x0,x1] = pad(Math.min(...xs), Math.max(...xs));
  let [y0,y1] = pad(Math.min(...ys), Math.max(...ys));
  const sx = v=>P.l+(v-x0)/(x1-x0)*(Wd-P.l-P.r), sy = v=>H-P.b-(v-y0)/(y1-y0)*(H-P.t-P.b);
  ctx.strokeStyle='#1c2536'; ctx.fillStyle='#5f7089'; ctx.font='11px IBM Plex Mono'; ctx.lineWidth=1;
  const ticks=(a,b,n)=>{ const step=(b-a)/n; return Array.from({length:n+1},(_,i)=>a+i*step); };
  ticks(x0,x1,6).forEach(t=>{ ctx.beginPath(); ctx.moveTo(sx(t),P.t); ctx.lineTo(sx(t),H-P.b); ctx.stroke();
    ctx.textAlign='center'; ctx.fillText(Math.abs(t)>=100?Math.round(t):t.toFixed(Math.abs(x1-x0)<5?2:1), sx(t), H-P.b+18); });
  ticks(y0,y1,6).forEach(t=>{ ctx.beginPath(); ctx.moveTo(P.l,sy(t)); ctx.lineTo(Wd-P.r,sy(t)); ctx.stroke();
    ctx.textAlign='right'; ctx.fillText(Math.abs(t)>=100?Math.round(t):t.toFixed(Math.abs(y1-y0)<5?2:1), P.l-8, sy(t)+4); });
  const med = a=>{ const s=[...a].sort((x,y)=>x-y); return s[Math.floor(s.length/2)]; };
  ctx.setLineDash([5,5]); ctx.strokeStyle='#5f708966';
  ctx.beginPath(); ctx.moveTo(sx(med(xs)),P.t); ctx.lineTo(sx(med(xs)),H-P.b); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(P.l,sy(med(ys))); ctx.lineTo(Wd-P.r,sy(med(ys))); ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle='#9fb0c8'; ctx.font='600 12px Inter'; ctx.textAlign='center';
  ctx.fillText(mx.l, (P.l+Wd-P.r)/2, H-14);
  ctx.save(); ctx.translate(16,(P.t+H-P.b)/2); ctx.rotate(-Math.PI/2); ctx.fillText(my.l,0,0); ctx.restore();
  const withF = ['franchise','teamSeason'].includes(X.gr);
  pts.forEach(p=>{
    const X_=sx(p.x), Y_=sy(p.y);
    const fid = withF && gd.fid ? gd.fid(p.g.k) : null;
    const col = fid? fColor(fid) : '#00a2ff';
    ctx.beginPath(); ctx.arc(X_,Y_,11,0,7); ctx.fillStyle='#0e1119'; ctx.fill();
    ctx.lineWidth = pinned.has(String(p.g.k))?3:2;
    ctx.strokeStyle = pinned.has(String(p.g.k))?'#ffc400':col; ctx.stroke();
    ctx.fillStyle='#eef4ff'; ctx.font='700 8.5px Barlow Condensed'; ctx.textAlign='center';
    ctx.fillText(initials(gd.plain(p.g.k)).slice(0,2), X_, Y_+3);
    p._x=X_; p._y=Y_;
  });
  const tip = $('#scattertip');
  cv.onmousemove = e=>{
    const rect = cv.getBoundingClientRect();
    const mxp=(e.clientX-rect.left)*(cv.width/rect.width), myp=(e.clientY-rect.top)*(cv.height/rect.height);
    const p = pts.find(p=>Math.hypot(p._x-mxp,p._y-myp)<12);
    if(p){ tip.style.display='block'; tip.style.left=(e.clientX-rect.left+16)+'px'; tip.style.top=(e.clientY-rect.top-10)+'px';
      tip.innerHTML = `<b>${gd.label(p.g.k,p.g).replace(/<a [^>]+>|<\/a>/g,'')}</b><br>${mx.l}: <b>${mx.fmt(p.x)}</b> · ${my.l}: <b>${my.fmt(p.y)}</b><br><span class="dim">${f0(p.g.n)} weeks in sample</span>`; }
    else tip.style.display='none';
  };
  cv.onclick = e=>{
    const rect = cv.getBoundingClientRect();
    const mxp=(e.clientX-rect.left)*(cv.width/rect.width), myp=(e.clientY-rect.top)*(cv.height/rect.height);
    const p = pts.find(p=>Math.hypot(p._x-mxp,p._y-myp)<12);
    if(p){ const k=String(p.g.k); pinned.has(k)?pinned.delete(k):pinned.add(k); drawScatter(); }
  };
  $('#pins').innerHTML = [...pinned].map(k=>{ const p=pts.find(x=>String(x.g.k)===k); if(!p) return '';
    return `<span class="chip on" style="background:#ffc400;border-color:#ffc400;color:#131a02">${esc(gd.plain(p.g.k))} · ${mx.fmt(p.x)} / ${my.fmt(p.y)}</span>`; }).join('') || '<span class="dim small">no pinned marks</span>';
}

/* ---------------- boot ---------------- */
window.addEventListener('hashchange', render);
render();
})();
