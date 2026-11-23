import math, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from ring import HashRing, hash_key
OUT = sys.argv[1]
M = 2**128
COL = {"store-0":"#2F6FB3","store-1":"#2A9D8F","store-2":"#7B5EA7","store-3":"#9A7B1C","store-4":"#D9622B"}
S = 560; C = S/2; R = 190
def ang(h): return h / M * 360.0
def pt(a, r=R): t = math.radians(a); return (C + r*math.sin(t), C - r*math.cos(t))
def f(v): return f"{v:.1f}"
def arc(a0, a1, r=R, color="#000", w=10, op=1):
    span = (a1 - a0) % 360
    if span < 0.05: return ""
    x0,y0 = pt(a0,r); x1,y1 = pt(a1,r)
    large = 1 if span > 180 else 0
    return f'<path d="M{f(x0)} {f(y0)} A{R if r==R else r} {R if r==R else r} 0 {large} 1 {f(x1)} {f(y1)}" fill="none" stroke="{color}" stroke-width="{w}" stroke-opacity="{op}"/>'
def svg(body, label):
    return f'<svg aria-label="{label}" width="{S}" height="{S}" viewBox="0 0 {S} {S}" xmlns="http://www.w3.org/2000/svg">{body}</svg>'
def spots(ring): return [(p, ring._owner[p]) for p in ring._positions]
_ALL = [f"farm{f_}-plot{p}-s{s}" for f_ in range(1,6) for p in range(1,5) for s in range(1,11)]
_r4 = HashRing(vnodes=1, replicas=1)
for _n in ["store-0","store-1","store-2","store-3"]: _r4.add_node(_n)
_na = ang(hash_key("store-4#0"))
_prev = max([ang(p) for p in _r4._positions if ang(p) < _na] or [ang(max(_r4._positions))])
def _inarc(a): return (a - _prev) % 360 < (_na - _prev) % 360
SENS = []
for b in range(16):
    lo = b * 22.5
    for x in _ALL:
        a = ang(hash_key(x))
        if lo <= a < lo + 22.5 and not _inarc(a) and x not in SENS:
            SENS.append(x); break
_arcs = [x for x in _ALL if _inarc(ang(hash_key(x)))]
_arcs.sort(key=lambda x: ang(hash_key(x)))
step = max(1, len(_arcs)//4)
SENS += _arcs[::step][:4]
def lab(x, y, text, color, w=180, align="center"):
    left = x - (w/2 if align=="center" else (0 if align=="left" else w))
    return f'<p class="rl" style="left:{f(left)}px;top:{f(y-17)}px;width:{w}px;text-align:{align};color:{color}">{text}</p>'
def node_label(a, name, color, r=R+36):
    x,y = pt(a, r)
    w = int(len(name) * 14 + 16)
    align = "left" if math.sin(math.radians(a)) > 0.35 else ("right" if math.sin(math.radians(a)) < -0.35 else "center")
    if align=="left": x -= 10
    if align=="right": x += 10
    return lab(x, y, name, color, w, align)

def slide(sid, eyebrow, title, svgcode, labels, right, notes, cls="", extra_css=""):
    return f'''<section id="{sid}" class="{cls}">
<div class="head">
<p class="eyebrow">{eyebrow}</p>
<h2>{title}</h2>
</div>
<div class="ringrow">
<div class="ringbox">
{svgcode}
{"".join(labels)}
</div>
<div class="ringtext">
{right}
</div>
</div>
<div class="footer"><p>S1 Smart Agriculture · Person 3 · drawn with the real ring.py (MD5 positions)</p><p class="pg"></p></div>
<aside>{notes}</aside>
</section>
'''
def write(sid, html):
    open(os.path.join(OUT, sid + ".html"), "w").write(html)

base = '<circle cx="{c}" cy="{c}" r="{r}" fill="none" stroke="#C9D2DC" stroke-width="10"/>'.format(c=C, r=R)

# ---------- 1. the ring: 4 machines, sensors go clockwise ----------
r1 = HashRing(vnodes=1, replicas=1)
for n in ["store-0","store-1","store-2","store-3"]: r1.add_node(n)
body = base
for s in SENS:
    a = ang(hash_key(s)); x,y = pt(a); o = r1.get_node(s)
    body += f'<circle cx="{f(x)}" cy="{f(y)}" r="8" fill="{COL[o]}" stroke="#F6F5F0" stroke-width="2"/>'
hl = "farm3-plot2-s5"; ha = ang(hash_key(hl)); ho = r1.get_node(hl); hoa = ang(hash_key(ho + "#0"))
body += arc(ha, hoa, R-34, "#C8611E", 5)
hx,hy = pt(ha, R-34); ex,ey = pt(hoa, R-34)
span = (hoa-ha) % 360; large = 1 if span>180 else 0
body += (f'<circle cx="{f(hx)}" cy="{f(hy)}" r="9" fill="#C8611E"><animateMotion dur="2.4s" repeatCount="indefinite" '
         f'path="M0 0 A{R-34} {R-34} 0 {large} 1 {f(ex-hx)} {f(ey-hy)}"/></circle>')
labels = []
for n in ["store-0","store-1","store-2","store-3"]:
    a = ang(hash_key(n + "#0")); x,y = pt(a)
    body += f'<circle cx="{f(x)}" cy="{f(y)}" r="20" fill="{COL[n]}" stroke="#F6F5F0" stroke-width="4"/>'
    labels.append(node_label(a, n, COL[n]))
hx2,hy2 = pt(ha, R-80)
labels.append(lab(hx2, hy2, hl, "#C8611E", 230))
right = f'''<div class="steps">
<p class="stepn">1</p><p class="stept">Each machine is hashed with MD5 to a spot on a circle (big dots).</p>
<p class="stepn">2</p><p class="stept">Each sensor is hashed to a spot too (small dots).</p>
<p class="stepn">3</p><p class="stept">A sensor belongs to the <b>first machine clockwise</b>. The orange arrow: {hl} → {ho}.</p>
</div>'''
write("ring1", slide("ring1", "The hash ring · 1 of 5", "Sensors walk clockwise to a machine", svg(body, "Hash ring with 4 machines and sensors coloured by owner"), labels, right,
 f"“Machines and sensors are both hashed onto the same circle. A sensor belongs to the first machine you reach going clockwise. Here {hl} walks clockwise and lands on {ho}. The colour of each small dot is the machine that owns it.”"))

# ---------- 2. add a 5th machine: only one arc moves ----------
r2 = HashRing(vnodes=1, replicas=1)
for n in ["store-0","store-1","store-2","store-3","store-4"]: r2.add_node(n)
na = ang(hash_key("store-4#0"))
prev = max([ang(p) for p,o in spots(r1) if ang(p) < na] or [ang(max(r1._positions))])
body = base + arc(prev, na, R, "#D9622B", 22, 0.35)
moved = 0
for s in SENS:
    a = ang(hash_key(s)); x,y = pt(a); o1 = r1.get_node(s); o2 = r2.get_node(s)
    if o1 != o2:
        moved += 1
        body += f'<circle cx="{f(x)}" cy="{f(y)}" r="11" fill="{COL[o2]}" stroke="#14213D" stroke-width="3"/>'
    else:
        body += f'<circle cx="{f(x)}" cy="{f(y)}" r="8" fill="{COL[o1]}" fill-opacity="0.45"/>'
labels = []
for n in ["store-0","store-1","store-2","store-3","store-4"]:
    a = ang(hash_key(n + "#0")); x,y = pt(a)
    body += f'<circle cx="{f(x)}" cy="{f(y)}" r="{24 if n=="store-4" else 20}" fill="{COL[n]}" stroke="#F6F5F0" stroke-width="4"/>'
    labels.append(node_label(a, n + (" (new)" if n=="store-4" else ""), COL[n]))
right = f'''<div class="steps">
<p class="stepn">1</p><p class="stept">store-4 lands on the circle.</p>
<p class="stepn">2</p><p class="stept">It takes only the sensors <b>just before it</b> (the shaded arc). Here {moved} of {len(SENS)} dots changed.</p>
<p class="stepn">3</p><p class="stept">Every other sensor still walks to the same machine. Nothing else moves.</p>
</div>
<div class="cmp"><p class="cmpn">80%</p><p class="cmpt">move with hash % N</p><p class="cmpn acc">18%</p><p class="cmpt">move with the ring (10,000 sensors)</p></div>'''
write("ring2", slide("ring2", "The hash ring · 2 of 5", "Add a 5th machine: only one arc moves", svg(body, "Ring after adding store-4; only sensors in the arc before it change owner"), labels, right,
 "“When store-4 joins, it only takes the sensors in the arc just before it, the shaded part. All the faded dots keep their machine. With hash mod N almost every sensor would move; with the ring only about 1 in 5.”", "alt"))

# ---------- helpers for share bars ----------
SENS10K = [f"farm{f_}-plot{p}-s{s}" for f_ in range(50) for p in range(20) for s in range(10)]
def shares(ring):
    cnt = {n:0 for n in sorted(ring.nodes)}
    for s in SENS10K: cnt[ring.get_node(s)] += 1
    return cnt
def bars(cnt):
    tot = sum(cnt.values()); mx = max(cnt.values())
    out = '<div class="bars">'
    for n,c in cnt.items():
        w = int(560 * c / mx)
        out += f'<div class="barrow"><p class="barn">{n}</p><div class="bar" style="width:{w}px;background:{COL[n]}"></div><p class="barv">{100*c/tot:.0f}%</p></div>'
    return out + '</div>'
def ownership_svg(ring):
    sp = spots(ring); body = ""
    for i,(p,o) in enumerate(sp):
        a1 = ang(p); a0 = ang(sp[i-1][0])
        body += arc(a0, a1, R, COL[o], 30)
    return body

# ---------- 3. 1 spot per machine: uneven ----------
r3 = HashRing(vnodes=1, replicas=1)
for n in ["store-0","store-1","store-2","store-3"]: r3.add_node(n)
body = ownership_svg(r3); labels = []
for n in ["store-0","store-1","store-2","store-3"]:
    a = ang(hash_key(n + "#0")); x,y = pt(a)
    body += f'<circle cx="{f(x)}" cy="{f(y)}" r="20" fill="{COL[n]}" stroke="#F6F5F0" stroke-width="4"/>'
    labels.append(node_label(a, n, COL[n]))
c3 = shares(r3)
right = f'''<p class="stept">With <b>1 spot</b> per machine, each machine owns one random-length arc. Share of 10,000 sensors:</p>
{bars(c3)}
<p class="note">store-2 got a huge arc, so it holds most of the data. Fair would be 25% each.</p>'''
write("ring3", slide("ring3", "Virtual nodes · 3 of 5", "1 spot per machine: very uneven", svg(body, "Ring with one spot per machine; arcs coloured by owner are very unequal"), labels, right,
 "“With only one spot per machine, each machine’s share is one random gap on the circle. Here store-2 owns a huge arc and gets 62% of the data, while others get about 10%.”"))

# ---------- 4. 100 spots per machine: even ----------
r4 = HashRing(vnodes=100, replicas=1)
for n in ["store-0","store-1","store-2","store-3"]: r4.add_node(n)
body = ownership_svg(r4)
c4 = shares(r4)
right = f'''<p class="stept">With <b>100 spots</b> per machine (virtual nodes), the colours are mixed all around the circle. Share of 10,000 sensors:</p>
{bars(c4)}
<p class="note">Many small arcs average out the luck: every machine is close to 25%. A new machine also takes a little from everyone.</p>'''
write("ring4", slide("ring4", "Virtual nodes · 4 of 5", "100 spots per machine: nearly even", svg(body, "Ring with 100 spots per machine; colours interleave all around"), [], right,
 "“Now each machine gets 100 spots, called virtual nodes, like store-2#0 to store-2#99. Each machine owns many small arcs instead of one big one, so the luck averages out: every machine gets close to a quarter. This is what we run: 100 virtual nodes.”", "alt"))

# ---------- 5. three copies: keep walking, skip repeats ----------
r5 = HashRing(vnodes=6, replicas=3)
for n in ["store-0","store-1","store-2","store-3"]: r5.add_node(n)
def _walk(k):
    st = bisect.bisect_right(r5._positions, hash_key(k)); g = []; w = []; j = st
    while len(g) < 3:
        p_ = r5._positions[j % len(r5._positions)]; o_ = r5._owner[p_]; w.append(o_ in g)
        if o_ not in g: g.append(o_)
        j += 1
    return w
import bisect
def _spread(k):
    st = bisect.bisect_right(r5._positions, hash_key(k)); g = []; a = [ang(hash_key(k))]; j = st
    while len(g) < 3:
        p_ = r5._positions[j % len(r5._positions)]; o_ = r5._owner[p_]; a.append(ang(p_))
        if o_ not in g: g.append(o_)
        j += 1
    return min((a[i+1] - a[i]) % 360 for i in range(len(a)-1))
_cands = [k for k in [f"farm{f_}-plot{p}-s{s}" for f_ in range(50) for p in range(20) for s in range(10)] if sum(_walk(k)) == 1 and len(_walk(k)) == 4]
key = max(_cands[:3000], key=_spread)
ka = ang(hash_key(key))
sp = spots(r5)
import bisect
start = bisect.bisect_right(r5._positions, hash_key(key))
got = []; walk = []; i = start
while len(got) < 3:
    p = r5._positions[i % len(r5._positions)]; o = r5._owner[p]
    walk.append((p, o, o in got))
    if o not in got: got.append(o)
    i += 1
body = base
for p,o in sp:
    x,y = pt(ang(p)); body += f'<circle cx="{f(x)}" cy="{f(y)}" r="9" fill="{COL[o]}" fill-opacity="0.35"/>'
body += arc(ka, ang(walk[-1][0]), R-34, "#C8611E", 5)
kx,ky = pt(ka); body += f'<circle cx="{f(kx)}" cy="{f(ky)}" r="10" fill="#C8611E" stroke="#14213D" stroke-width="3"/>'
labels = [lab(*pt(ka, R-78), key, "#C8611E", 220)]
num = 0
for p,o,skip in walk:
    x,y = pt(ang(p))
    if skip:
        body += f'<circle cx="{f(x)}" cy="{f(y)}" r="14" fill="#F6F5F0" stroke="{COL[o]}" stroke-width="4" stroke-dasharray="4 4"/>'
        labels.append(lab(*pt(ang(p), R-34), "skip", "#6B7686", 80))
    else:
        num += 1
        body += f'<circle cx="{f(x)}" cy="{f(y)}" r="18" fill="{COL[o]}" stroke="#F6F5F0" stroke-width="4"/>'
        labels.append(node_label(ang(p), f"{num}. {o}", COL[o]))
right = f'''<div class="steps">
<p class="stepn">1</p><p class="stept">From the sensor, keep walking clockwise.</p>
<p class="stepn">2</p><p class="stept">Collect <b>3 different machines</b>: {got[0]} (primary), {got[1]}, {got[2]}.</p>
<p class="stepn">3</p><p class="stept">A spot of a machine already picked is <b>skipped</b>: two copies on one machine would die together.</p>
</div>
<p class="note">A write is OK when 2 of the 3 confirm. Any one machine can break and nothing is lost.</p>'''
write("ring5", slide("ring5", "Three copies · 5 of 5", "Keep walking to find 3 different machines", svg(body, "Sensor walks clockwise collecting three different machines and skipping a repeat"), labels, right,
 f"“For 3 copies, the sensor keeps walking clockwise and collects 3 different machines: here {got[0]}, {got[1]} and {got[2]}. If it meets another spot of a machine it already has, it skips it, because two copies on one machine would be lost together.” (This page uses 6 spots per machine so the picture stays readable; the real system uses 100.)"))
print("ring1 sensor", hl, "->", ho, "| moved", moved, "| shares1", c3, "| shares100", c4, "| walk", got, [w[2] for w in walk])
for sid in ["ring1","ring2","ring3","ring4","ring5"]:
    print(sid, os.path.getsize(os.path.join(OUT, sid+".html")))
