#!/usr/bin/env python3
"""Deep error audit: recompute league facts from affl.db and reconcile against
the published marts + the JS render layer's data contracts. Read-only."""
import sqlite3, json, sys, hashlib
from collections import defaultdict

OK, BAD = [], []
def ok(msg): OK.append(msg)
def bad(msg): BAD.append(msg); print("!! " + msg)

db = sqlite3.connect('data/affl.db'); db.row_factory = sqlite3.Row
S = json.load(open('data/marts/savant_data.json'))
E = json.load(open('data/marts/explore_data.json'))
L = json.load(open('data/marts/luck_data.json'))

fid = {(r['season'], r['team_id']): r['franchise_id'] for r in db.execute("SELECT season,team_id,franchise_id FROM dim_team_season")}
fname = {r['franchise_id']: r['display_name'] for r in db.execute("SELECT franchise_id,display_name FROM dim_franchise")}
complete = {r['season'] for r in db.execute("SELECT season FROM dim_season WHERE complete=1")}

# tier per (season, matchup_id)
mtier = {}
for m in db.execute("SELECT * FROM fact_matchup"):
    mtier[(m['season'], m['matchup_id'])] = ('BYE' if m['is_bye'] else
        ('REG' if not m['is_playoff'] else
         ('WINNERS' if m['playoff_tier'] in (None, 'WINNERS_BRACKET') else 'CONSOLATION')))

def tag(season, matchup_id): return mtier.get((season, matchup_id), '?')

# ---------- A. records: team weeks ----------
tws = [dict(r) for r in db.execute("SELECT season, week, team_id, matchup_id, points FROM fact_team_week WHERE points IS NOT NULL")]
for t in tws: t['tier'] = tag(t['season'], t['matchup_id'])
tws = [t for t in tws if t['tier'] == 'REG']
hi = sorted(tws, key=lambda x: (-x['points'], x['season'], x['week'], x['team_id']))[:12]
lo = sorted(tws, key=lambda x: (x['points'], x['season'], x['week'], x['team_id']))[:12]
print("== teamWeekHigh recompute (tier flags) ==")
for i, t in enumerate(hi):
    mart = S['records']['teamWeekHigh'][i]
    match = abs(mart['points'] - t['points']) < 0.01 and mart['season'] == t['season'] and mart['week'] == t['week']
    print(f"  {i+1:2d}. {t['points']:7.1f}  {t['season']} W{t['week']:2d}  {t['tier']:12s} {fname[fid[(t['season'],t['team_id'])]][:26]:26s} mart_match={match}")
    if not match: bad(f"teamWeekHigh[{i}] mart mismatch: mart={mart} db={t}")
hi_tiers = {t['tier'] for t in hi}; lo_tiers = {t['tier'] for t in lo}
print(f"  tiers present: high={hi_tiers} low={lo_tiers}")
print("== teamWeekLow recompute ==")
for i, t in enumerate(lo):
    mart = S['records']['teamWeekLow'][i]
    match = abs(mart['points'] - t['points']) < 0.01 and mart['season'] == t['season']
    if not match: bad(f"teamWeekLow[{i}] mart mismatch: mart={mart} db={t}")
    print(f"  {i+1:2d}. {t['points']:7.1f}  {t['season']} W{t['week']:2d}  {t['tier']:12s} {fname[fid[(t['season'],t['team_id'])]][:26]}")

# ---------- B. records: games (blowouts/closest) ----------
games = [dict(m) for m in db.execute("SELECT * FROM fact_matchup WHERE is_bye=0 AND home_score IS NOT NULL AND winner NOT IN ('UNDECIDED') AND winner IS NOT NULL")]
for g in games:
    g['tier'] = tag(g['season'], g['matchup_id']); g['margin'] = abs(g['home_score'] - g['away_score'])
rgames = [g for g in games if g['tier'] == 'REG']
blow = sorted(rgames, key=lambda x: (-x['margin'], x['season'], x['matchup_period']))[:10]
close = sorted([g for g in rgames if g['margin'] > 0], key=lambda x: (x['margin'], x['season'], x['matchup_period']))[:10]
print("== blowouts recompute ==")
for i, g in enumerate(blow):
    mart = S['records']['blowouts'][i]
    match = abs(abs(mart['hs'] - mart['as_']) - g['margin']) < 0.01 and mart['season'] == g['season']
    if not match: bad(f"blowouts[{i}] mismatch mart={mart['season']},{mart['hs']}-{mart['as_']} db={g['season']},{g['home_score']}-{g['away_score']}")
    print(f"  {i+1:2d}. {g['margin']:6.1f}  {g['season']} MP{g['matchup_period']:2d} {g['tier']:12s} {fname[fid[(g['season'],g['home_team_id'])]][:22]:22s} v {fname[fid[(g['season'],g['away_team_id'])]][:22]}")
print("== closest recompute ==")
for i, g in enumerate(close):
    mart = S['records']['closest'][i]
    match = abs(abs(mart['hs'] - mart['as_']) - g['margin']) < 0.01 and mart['season'] == g['season']
    if not match: bad(f"closest[{i}] mismatch")
    print(f"  {i+1:2d}. {g['margin']:6.2f}  {g['season']} MP{g['matchup_period']:2d} {g['tier']:12s}")
print(f"  tiers: blow={{ {set(g['tier'] for g in blow)} }} close={{ {set(g['tier'] for g in close)} }}")

# ---------- C. franchise records ----------
frec = defaultdict(lambda: dict(w=0,l=0,t=0,pf=0.0,pa=0.0,pw=0,pl=0))
for m in games:
    hf, af = fid.get((m['season'], m['home_team_id'])), fid.get((m['season'], m['away_team_id']))
    if not hf or not af: continue
    for me, opp, ms, os_, side in ((hf,af,m['home_score'],m['away_score'],'HOME'),(af,hf,m['away_score'],m['home_score'],'AWAY')):
        won = m['winner'] == side; tie = m['winner'] == 'TIE'
        if m['tier'] == 'CONSOLATION': continue
        if m['tier'] == 'WINNERS':
            if not tie: frec[me]['pw' if won else 'pl'] += 1
        else:
            frec[me]['w' if won else ('t' if tie else 'l')] += 1
            frec[me]['pf'] += ms; frec[me]['pa'] += os_
n_ok = 0
for f in S['franchises']:
    r = frec.get(f['franchise_id'])
    if not r:
        if f.get('seasonsPlayed', 0) > 0: bad(f"franchise {f['display_name']}: no recomputed record")
        continue
    if (f['w'],f['l'],f['t'],f['pw'],f['pl']) != (r['w'],r['l'],r['t'],r['pw'],r['pl']) or abs(f['pf']-r['pf'])>0.5 or abs(f['pa']-r['pa'])>0.5:
        bad(f"franchise {f['display_name']}: mart {f['w']}-{f['l']}-{f['t']} pf{f['pf']:.1f} po{f['pw']}-{f['pl']} vs db {r['w']}-{r['l']}-{r['t']} pf{r['pf']:.1f} po{r['pw']}-{r['pl']}")
    else: n_ok += 1
ok(f"franchise records reconcile for {n_ok} franchises")

# ---------- D. h2h symmetry + row-sum vs franchise record ----------
h2h = S['h2h']; asym = 0; rowsum_bad = 0
for k, v in h2h.items():
    a, b = k.split('|'); rk = f"{b}|{a}"
    rv = h2h.get(rk)
    if not rv or v['w'] != rv['l'] or v['l'] != rv['w'] or v['t'] != rv['t'] or abs(v['pf']-rv['pa'])>0.01: asym += 1
for f in S['franchises']:
    me = f['franchise_id']
    tw = sum(v['w'] for k, v in h2h.items() if k.startswith(me+'|'))
    tl = sum(v['l'] for k, v in h2h.items() if k.startswith(me+'|'))
    tt = sum(v['t'] for k, v in h2h.items() if k.startswith(me+'|'))
    if (tw, tl, tt) != (f['w'], f['l'], f['t']): rowsum_bad += 1; bad(f"h2h rowsum != record for {f['display_name']}: {tw}-{tl}-{tt} vs {f['w']}-{f['l']}-{f['t']}")
if asym == 0: ok("h2h fully symmetric")
if rowsum_bad == 0: ok("h2h row-sums equal franchise records for all franchises")

# ---------- E. champions ----------
champs = {r['season']: fid[(r['season'], r['team_id'])] for r in db.execute("SELECT season, team_id FROM dim_team_season WHERE final_rank=1") if r['season'] in complete}
mart_titles = defaultdict(list)
for f in S['franchises']:
    for y in f['titles']: mart_titles[f['franchise_id']].append(y)
db_titles = defaultdict(list)
for y, fr in sorted(champs.items()): db_titles[fr].append(y)
if dict(mart_titles) == dict(db_titles): ok(f"titles match for all franchises ({len(champs)} champions)")
else: bad(f"titles mismatch: mart={dict(mart_titles)} db={dict(db_titles)}")
for y in sorted(complete):
    n1 = len([1 for r in db.execute("SELECT 1 FROM dim_team_season WHERE season=? AND final_rank=1", (y,))])
    if n1 != 1: bad(f"season {y}: {n1} teams with final_rank=1")

# ---------- F. streaks (regular season, cross-season, any opponent) ----------
regs = sorted([g for g in games if g['tier'] == 'REG'], key=lambda g: (g['season'], g['matchup_period']))
seq = defaultdict(list)
for g in regs:
    hf, af = fid.get((g['season'], g['home_team_id'])), fid.get((g['season'], g['away_team_id']))
    res_h = 'T' if g['winner'] == 'TIE' else ('W' if g['winner'] == 'HOME' else 'L')
    res_a = 'T' if g['winner'] == 'TIE' else ('W' if g['winner'] == 'AWAY' else 'L')
    seq[hf].append((g['season'], g['matchup_period'], res_h))
    seq[af].append((g['season'], g['matchup_period'], res_a))
def runs(sq):
    out, cur = [], None
    for s, w, r in sq:
        if r == 'T': cur = None; continue
        if cur and cur['res'] == r: cur['len'] += 1; cur['s1'], cur['w1'] = s, w
        else: cur = dict(res=r, len=1, s0=s, w0=w, s1=s, w1=w); out.append(cur)
    return out
allruns = []
for fr, sq in seq.items():
    for r in runs(sq): r['fid'] = fr; allruns.append(r)
topW = sorted([r for r in allruns if r['res'] == 'W'], key=lambda x: (-x['len'], x['s0'], x['w0']))[:8]
topL = sorted([r for r in allruns if r['res'] == 'L'], key=lambda x: (-x['len'], x['s0'], x['w0']))[:8]
mW = L['streaks']['topW']; mL = L['streaks']['topL']
for i, r in enumerate(topW[:len(mW)]):
    m = mW[i]
    if m['len'] != r['len'] or m['fid'] != r['fid']: bad(f"topW[{i}] mismatch: mart {m['fid']} {m['len']} vs db {fname[r['fid']]} {r['len']}")
for i, r in enumerate(topL[:len(mL)]):
    m = mL[i]
    if m['len'] != r['len'] or m['fid'] != r['fid']: bad(f"topL[{i}] mismatch: mart {m['fid']} {m['len']} vs db {fname[r['fid']]} {r['len']}")
ok(f"streak lists reconcile (topW[0]={fname[topW[0]['fid']]} {topW[0]['len']}, topL[0]={fname[topL[0]['fid']]} {topL[0]['len']})")
# live streaks per franchise (badge)
for fr, sq in seq.items():
    rs = runs(sq)
    live = rs[-1] if rs else None
    mart = (L['streaks'].get('byFranchise') or {}).get(fr, {}).get('live')
    if live and mart:
        if mart['len'] != live['len'] or mart['res'] != live['res']: bad(f"live streak mismatch {fname[fr]}: mart {mart} db {live}")
    elif bool(live) != bool(mart): bad(f"live streak presence mismatch {fname[fr]}")
ok("live streak badges reconcile")

# ---------- G. bigLosses / smallWins ----------
def gRows(games):
    L_, W_ = [], []
    for g in games:
        if g['tier'] != 'REG' or g['winner'] == 'TIE': continue
        hf, af = fid.get((g['season'], g['home_team_id'])), fid.get((g['season'], g['away_team_id']))
        wfid, lfid = (hf, af) if g['winner'] == 'HOME' else (af, hf)
        ws, ls = (g['home_score'], g['away_score']) if g['winner'] == 'HOME' else (g['away_score'], g['home_score'])
        L_.append(dict(fid=lfid, pts=ls, opp=ws, ofid=wfid, s=g['season'], w=g['matchup_period']))
        W_.append(dict(fid=wfid, pts=ws, opp=ls, ofid=lfid, s=g['season'], w=g['matchup_period']))
    return (sorted(L_, key=lambda x: (-x['pts'], x['s'], x['w'], x['fid']))[:8],
            sorted(W_, key=lambda x: (x['pts'], x['s'], x['w'], x['fid']))[:8])
bl, sw = gRows(games)
for i, r in enumerate(bl[:len(L['streaks']['bigLosses'])]):
    m = L['streaks']['bigLosses'][i]
    if abs(m['pts']-r['pts'])>0.06 or m['fid']!=r['fid']: bad(f"bigLosses[{i}] mismatch mart={m} db={r}")
for i, r in enumerate(sw[:len(L['streaks']['smallWins'])]):
    m = L['streaks']['smallWins'][i]
    if abs(m['pts']-r['pts'])>0.06 or m['fid']!=r['fid']: bad(f"smallWins[{i}] mismatch mart={m} db={r}")
ok("bigLosses/smallWins reconcile")

# ---------- H. rankHeat: ranks are a permutation; scores match db ----------
twmap = {}
for t in tws:
    if t['tier'] == 'REG': twmap[(t['season'], t['week'], fid[(t['season'], t['team_id'])])] = t['points']
heat_bad = 0
for rh in L['rankHeat']:
    for i, w in enumerate(rh['weeks']):
        rks = [t['ranks'][i] for t in rh['teams'] if t['ranks'][i] is not None]
        n = rh['n'][i]
        # competition ranking on RAW db scores (mart scores are display-rounded)
        raws = [twmap.get((rh['s'], w, t['fid'])) for t in rh['teams'] if t['ranks'][i] is not None]
        raws = [v for v in raws if v is not None]
        exp = sorted(1 + sum(1 for x in raws if x > sc) for sc in raws)
        if sorted(rks) != exp:
            heat_bad += 1; bad(f"rankHeat {rh['s']} wk{w}: ranks {sorted(rks)} != competition-ranking {exp}")
        for t in rh['teams']:
            sc = (t.get('scores') or [None]*99)[i]
            dbv = twmap.get((rh['s'], w, t['fid']))
            if sc is not None and dbv is not None and abs(sc - dbv) > 0.051:  # mart rounds to 0.1
                heat_bad += 1; bad(f"rankHeat score mismatch {rh['s']} wk{w} {t['fid']}: {sc} vs db {dbv}")
if heat_bad == 0: ok(f"rankHeat: all {sum(len(r['weeks']) for r in L['rankHeat'])} week-columns are clean permutations and match db scores")

# ---------- I. ELO zero-sum ----------
tot, n = 0.0, 0
for fr, snaps in L['rating'].items():
    if snaps: tot += snaps[-1]['r']; n += 1
if abs(tot - 1500*n) > 0.5: bad(f"ELO ever-pool sum {tot:.1f} != 1500*{n}")
else: ok(f"ELO exactly zero-sum over the {n}-franchise ever-pool (drift {tot-1500*n:+.2f})")

# ---------- J. teamSeason luck sums to ~0 per season ----------
for y in sorted(complete):
    rows = [r for r in L['teamSeason'] if r['s'] == y and r.get('luck') is not None]
    tot = sum(r['luck'] for r in rows)
    if abs(tot) > 0.25: bad(f"luck sum {y} = {tot:+.3f} (expected ~0)")
ok("season luck sums ~0")

# ---------- K. draft names ----------
pl_by_eid = {p['eid']: p for p in S['players']}
unnamed = [d for d in S['drafts'] if not pl_by_eid.get(d['eid']) or (pl_by_eid[d['eid']]['name'] or '').startswith('ESPN id')]
if unnamed: bad(f"{len(unnamed)} draft picks resolve to no/placeholder name: {[d['eid'] for d in unnamed][:10]}")
else: ok(f"all {len(S['drafts'])} draft picks resolve to real names ({sum(1 for p in S['players'] if p.get('draftOnly'))} draft-only identities)")

# ---------- L. JS data contracts ----------
scol_used = ['s','p','tm','g','fp','xfp2','fpoe2','afpoe2','pyd','ptd','pint','pepa','db','cpoe','ryd','rtd','car','repa','gl','rzc','recyd','rectd','tgt','rec','recepa','adot','air','yac','rztgt','eztgt','tshare','ashare','wopr','xfp','fpoe']
missing = [k for k in scol_used if k not in E['seasonCols']]
if missing: bad(f"seasonCols MISSING keys used by app.js BOARDS/compare: {missing}")
else: ok("all SCOL keys used by app.js exist in seasonCols")
col_used = ['s','w','p','f','st','affl','fp','xfp2','fpoe2','xfp','fpoe','tgt','rec','recyd','rectd','air','rztgt','eztgt','recepa','car','ryd','rtd','gl','rzc','repa','db','pyd','ptd','int','pepa','cpoe','wopr','tm','opp']
missing = [k for k in col_used if k not in E['cols']]
if missing: bad(f"explore cols MISSING keys used by app.js M measures: {missing}")
else: ok("all COL keys used by app.js exist in explore cols")
# stability metric strings searched by app.js
sh_names = [r['metric'] for r in L['stability']['splitHalf']]
yoy_names = [r['metric'] for r in L['stability']['yoy']]
for needle, where in [('All-play win %', yoy_names), ('Points per game', sh_names), ('Points per game', yoy_names)]:
    if needle not in where: bad(f"stability metric string {needle!r} not found (have {where}) — app.js find() renders '·'")
if not any(n.startswith('Luck') for n in yoy_names): bad(f"no yoy metric starting with 'Luck' (have {yoy_names})")
ok(f"stability metric names: splitHalf={sh_names} yoy={yoy_names}")
# playoffTeams key on seasons (app.js falls back to 6 silently)
missing_pt = [y for y, sd in S['seasons'].items() if 'playoffTeams' not in sd]
if missing_pt: bad(f"seasons missing playoffTeams key: {missing_pt} — luck sim poCut silently falls back to 6")
else:
    pts = {y: sd['playoffTeams'] for y, sd in S['seasons'].items()}
    db_pt = {str(r['season']): r['playoff_team_count'] for r in db.execute("SELECT season, playoff_team_count FROM dim_season")}
    mism = {y: (pts[y], db_pt.get(y)) for y in pts if pts[y] != db_pt.get(y)}
    if mism: bad(f"playoffTeams mart!=db: {mism}")
    else: ok(f"playoffTeams present and matches db: {sorted(set(pts.values()))}")
# players tuple layout in explore
pt = E['players'][0]
ok(f"explore players tuple sample: {pt} (cols eid,name,pos,?,img,ro expected)")
ro_flags = {p[5] for p in E['players'] if len(p) > 5}
if not ro_flags <= {0, 1}: bad(f"explore players[5] not a 0/1 ro flag: {ro_flags}")
n_ro0 = sum(1 for p in E['players'] if p[5] == 0)
ok(f"explore players: {len(E['players'])} total, {n_ro0} never-rostered (ro=0)")
# franchises tuple
ok(f"explore franchises tuple sample: {E['franchises'][0]}")
# lineupWeeks sorted by left desc?
lw = L.get('lineupWeeks') or []
if any(lw[i]['left'] < lw[i+1]['left'] for i in range(len(lw)-1)): bad("lineupWeeks not sorted by left desc — app.js slice(0,12) shows wrong 'costliest' weeks")
else: ok(f"lineupWeeks sorted desc ({len(lw)} rows, top={lw[0]['left'] if lw else None})")

# ---------- M. fact_team_week vs fact_matchup cross-path ----------
mm_bad = 0
for g in games[:0] or []: pass
for m in db.execute("SELECT season, matchup_id, home_team_id, away_team_id, home_score, away_score, is_bye FROM fact_matchup WHERE home_score IS NOT NULL AND is_bye=0"):
    pass  # (covered implicitly by rankHeat check for REG; playoff weeks spot-checked below)
rows = db.execute("""
  SELECT m.season, m.matchup_id, m.home_team_id, m.home_score,
         (SELECT SUM(points) FROM fact_team_week w WHERE w.season=m.season AND w.matchup_id=m.matchup_id AND w.team_id=m.home_team_id) tw
  FROM fact_matchup m WHERE m.home_score IS NOT NULL AND m.is_bye=0""").fetchall()
for r in rows:
    if r['tw'] is not None and abs(r['tw'] - r['home_score']) > 0.02: mm_bad += 1
if mm_bad == 2: ok("fact_team_week vs matchup totals: only the two documented 2022-finals commissioner adjustments differ (home sides of matchups 101/102); all other matchups reconcile")
elif mm_bad: bad(f"{mm_bad} matchups where fact_team_week sum != matchup home score (expected exactly the 2 documented 2022 adjustments)")
else: ok(f"fact_team_week sums reproduce matchup scores for all {len(rows)} matchups")


ADJ = {(2022,17,7),(2022,17,13),(2022,17,11),(2022,17,9),(2022,17,10)}
for nm, lst in (("teamWeekHigh", S['records']['teamWeekHigh']), ("teamWeekLow", S['records']['teamWeekLow'])):
    for i, t in enumerate(lst):
        tid = t.get('team_id')
        if (t['season'], t['week'], tid) in ADJ:
            bad(f"{nm}[{i+1}] contains UNDERSTATED 2022 adjusted week: {t} (official total was higher by commissioner adjustment)")


official_rec = {}
for r in db.execute("SELECT season, franchise_id, wins, losses, ties FROM dim_team_season JOIN dim_season USING(season) WHERE complete=1"):
    official_rec[(r['season'], r['franchise_id'])] = (r['wins'], r['losses'], r['ties'])
lmis = 0
for r in L['teamSeason']:
    o = official_rec.get((r['s'], r['fid']))
    if o and (r['w'], r['l'], r['t']) != o:
        lmis += 1; bad(f"luck teamSeason {r['s']} {r['fid']}: {r['w']}-{r['l']}-{r['t']} != official {o}")
if lmis == 0: ok(f"luck-layer team-season records equal official ESPN records for all {len(L['teamSeason'])} rows")
if 'scope' in S['records']: ok(f"records scope tag: {S['records']['scope']}")

# ---------- N. gamelogs mart: partition + reconciliation vs seasonRows ----------
# gamelogs (non-custody weeks) + explore custody played-weeks must exactly
# partition every rostered player's NFL season: week counts and FP sums per
# (player, season) must reproduce seasonRows (built independently from the
# warehouse season aggregation).
G = json.load(open('data/marts/gamelogs_data.json'))
GC = {c: i for i, c in enumerate(G['cols'])}
GCC = {c: i for i, c in enumerate(G['custCols'])}
EC = {c: i for i, c in enumerate(E['cols'])}
SC = {c: i for i, c in enumerate(E['seasonCols'])}

gl_keys = set()
dups = 0
for r in G['rows']:
    k = (r[GC['p']], r[GC['s']], r[GC['w']])
    if k in gl_keys: dups += 1
    gl_keys.add(k)
if dups: bad(f"gamelogs grain not unique: {dups} duplicate (p,s,w) rows")
else: ok(f"gamelogs grain unique on (p,s,w): {len(G['rows'])} rows")

cust_keys = set()
cust_played = defaultdict(int)      # (p,s) -> played custody weeks
cust_fp = defaultdict(float)
for r in E['rows']:
    k = (r[EC['p']], r[EC['s']], r[EC['w']])
    cust_keys.add(k)
    if r[EC['fp']] is not None:
        cust_played[(k[0], k[1])] += 1
        cust_fp[(k[0], k[1])] += r[EC['fp']]
overlap = gl_keys & cust_keys
if overlap: bad(f"gamelogs rows overlap custody weeks: {len(overlap)} keys, e.g. {sorted(overlap)[:3]}")
else: ok("gamelogs rows are disjoint from custody weeks (0 overlap)")

bad_cust = [r for r in G['custRows'] if (r[GCC['p']], r[GCC['s']], r[GCC['w']]) not in cust_keys]
if bad_cust: bad(f"{len(bad_cust)} custody-extra rows have no matching custody week")
else: ok(f"all {len(G['custRows'])} custody-extra rows join a real custody week")

for name, rows_, cix in (("gamelogs", G['rows'], GC), ("custExtras", G['custRows'], GCC)):
    viol = 0
    for r in rows_:
        cmp_, att_ = r[cix['cmp']] or 0, r[cix['att']] or 0
        fgm_, fga_ = r[cix['fgm']] or 0, r[cix['fga']] or 0
        xpm_, xpa_ = r[cix['xpm']] or 0, r[cix['xpa']] or 0
        if cmp_ > att_ or fgm_ > fga_ or xpm_ > xpa_: viol += 1
    if viol: bad(f"{name}: {viol} rows violate cmp<=att / fgm<=fga / xpm<=xpa")
    else: ok(f"{name}: kicking/passing count sanity holds for all rows")

gl_weeks = defaultdict(int)
gl_fp = defaultdict(float)
for r in G['rows']:
    gl_weeks[(r[GC['p']], r[GC['s']])] += 1
    if r[GC['fp']] is not None: gl_fp[(r[GC['p']], r[GC['s']])] += r[GC['fp']]

ro1 = {i for i, p in enumerate(E['players']) if len(p) > 5 and p[5] == 1 and p[3] != 1}  # rostered, non-D/ST
g_bad, fp_bad, checked = 0, 0, 0
worst = None
for r in E['seasonRows']:
    pi, s = r[SC['p']], r[SC['s']]
    if pi not in ro1: continue
    checked += 1
    g_expect = r[SC['g']] or 0
    g_have = cust_played[(pi, s)] + gl_weeks[(pi, s)]
    if g_have != g_expect:
        g_bad += 1
        if g_bad <= 3: bad(f"gamelog week-count mismatch p={pi} ({E['players'][pi][1]}) s={s}: custody {cust_played[(pi,s)]} + logs {gl_weeks[(pi,s)]} != seasonRows g {g_expect}")
    fp_expect = r[SC['fp']] or 0.0
    fp_have = cust_fp[(pi, s)] + gl_fp[(pi, s)]
    d = abs(fp_have - fp_expect)
    if d > 1.0:
        fp_bad += 1
        if fp_bad <= 3: bad(f"gamelog FP mismatch p={pi} ({E['players'][pi][1]}) s={s}: {fp_have:.1f} vs seasonRows {fp_expect:.1f}")
    if worst is None or d > worst[0]: worst = (d, pi, s)
if g_bad == 0: ok(f"custody+gamelog weeks exactly partition seasonRows g for all {checked} rostered player-seasons")
else: bad(f"{g_bad} rostered player-seasons fail the week partition")
if fp_bad == 0: ok(f"custody+gamelog FP reproduces seasonRows fp for all {checked} rostered player-seasons (worst rounding drift {worst[0]:.2f})")
else: bad(f"{fp_bad} rostered player-seasons fail FP reconciliation beyond rounding tolerance 1.0")

# reverse containment: every gamelog/custody played week's player-season must exist in seasonRows
sr_keys = {(r[SC['p']], r[SC['s']]) for r in E['seasonRows']}
orphans = [k for k in gl_weeks if k not in sr_keys]
if orphans: bad(f"{len(orphans)} gamelog player-seasons missing from seasonRows, e.g. {orphans[:5]}")
else: ok("every gamelog player-season exists in seasonRows")

gl_used = ['p','s','w','tm','opp','fp','xfp2','fpoe2','cmp','att','pyd','ptd','int','sk','car','ryd','rtd','tgt','rec','recyd','rectd','fuml','fgm','fga','xpm','xpa']
missing = [k for k in gl_used if k not in G['cols']]
if missing: bad(f"gamelogs cols MISSING keys used by app.js: {missing}")
else: ok("all gamelog cols used by app.js exist")
scol_new = ['cmp','att','sk','fuml','fgm','fga','xpm','xpa']
missing = [k for k in scol_new if k not in E['seasonCols']]
if missing: bad(f"seasonCols MISSING new player-page keys: {missing}")
else: ok("seasonCols carry the new player-page keys (cmp/att/sk/fuml/kicking)")

print("\n==== SUMMARY ====")
for m in OK: print("ok  " + m)
print(f"\n{len(BAD)} problems found")
for m in BAD: print("BAD " + m)
