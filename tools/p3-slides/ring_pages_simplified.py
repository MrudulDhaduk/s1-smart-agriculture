import math, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from ring import hash_key
import gen  # noqa: reuse helpers (re-runs gen once; harmless)
from gen import COL, R, C, pt, f, arc, svg, lab, node_label, slide, write, base, ang
OUT = sys.argv[1]
POS4 = {"store-0": 30.0, "store-1": 120.0, "store-2": 210.0, "store-3": 300.0}
POS5 = dict(POS4, **{"store-4": 75.0})
def owner(a, pos):
    best = None
    for n, p in pos.items():
        d = (p - a) % 360
        if best is None or d < best[0]: best = (d, n)
    return best[1]
ALL = [f"farm{a}-plot{b}-s{c}" for a in range(1,6) for b in range(1,5) for c in range(1,11)]
S = []
for b in range(16):
    lo = b * 22.5
    for x in ALL:
        a = ang(hash_key(x))
        if lo <= a < lo + 22.5 and not (30 < a <= 75) and x not in S: S.append(x); break
inarc = sorted([x for x in ALL if 33 < ang(hash_key(x)) < 72], key=lambda x: ang(hash_key(x)))
S += inarc[::max(1, len(inarc)//3)][:3]
FOOT = "simplified, evenly spaced positions to show the idea · pages 3–4 use the real ring.py positions"

# page 1
body = base
for s in S:
    a = ang(hash_key(s)); x,y = pt(a)
    body += f'<circle cx="{f(x)}" cy="{f(y)}" r="8" fill="{COL[owner(a, POS4)]}" stroke="#F6F5F0" stroke-width="2"/>'
hl = next(x for x in S if 130 < ang(hash_key(x)) < 190)
ha = ang(hash_key(hl)); ho = owner(ha, POS4); hoa = POS4[ho]
body += arc(ha, hoa, R-34, "#C8611E", 5)
hx,hy = pt(ha, R-34); ex,ey = pt(hoa, R-34); span = (hoa-ha) % 360
body += (f'<circle cx="{f(hx)}" cy="{f(hy)}" r="9" fill="#C8611E"><animateMotion dur="2.4s" repeatCount="indefinite" '
         f'path="M0 0 A{R-34} {R-34} 0 {1 if span>180 else 0} 1 {f(ex-hx)} {f(ey-hy)}"/></circle>')
labels = []
for n,a in POS4.items():
    x,y = pt(a); body += f'<circle cx="{f(x)}" cy="{f(y)}" r="20" fill="{COL[n]}" stroke="#F6F5F0" stroke-width="4"/>'
    labels.append(node_label(a, n, COL[n]))
labels.append(lab(*pt(ha, R-84), hl, "#C8611E", 230))
right = f'''<div class="steps">
<p class="stepn">1</p><p class="stept">Each machine is hashed with MD5 to a spot on a circle (big dots).</p>
<p class="stepn">2</p><p class="stept">Each sensor is hashed to a spot too (small dots, coloured by owner).</p>
<p class="stepn">3</p><p class="stept">A sensor belongs to the <b>first machine clockwise</b>. Orange: {hl} → {ho}.</p>
</div>'''
html = slide("ring1", "The hash ring · 1 of 5", "Sensors walk clockwise to a machine", svg(body, "Hash ring with 4 machines; sensors coloured by the first machine clockwise"), labels, right,
 f"“Machines and sensors are both hashed onto the same circle. A sensor belongs to the first machine you reach going clockwise. Here {hl} walks clockwise and lands on {ho}.” This picture spaces the machines evenly to keep it readable.")
write("ring1", html.replace("drawn with the real ring.py (MD5 positions)", FOOT))

# page 2
body = base + arc(30, 75, R, COL["store-4"], 24, 0.3)
moved = 0
for s in S:
    a = ang(hash_key(s)); x,y = pt(a); o1 = owner(a, POS4); o2 = owner(a, POS5)
    if o1 != o2:
        moved += 1; body += f'<circle cx="{f(x)}" cy="{f(y)}" r="11" fill="{COL[o2]}" stroke="#14213D" stroke-width="3"/>'
    else:
        body += f'<circle cx="{f(x)}" cy="{f(y)}" r="8" fill="{COL[o1]}" fill-opacity="0.4"/>'
labels = []
for n,a in POS5.items():
    x,y = pt(a); body += f'<circle cx="{f(x)}" cy="{f(y)}" r="{24 if n=="store-4" else 20}" fill="{COL[n]}" stroke="#F6F5F0" stroke-width="4"/>'
    labels.append(node_label(a, n, COL[n]))
right = f'''<div class="steps">
<p class="stepn">1</p><p class="stept">New machine store-4 lands between store-0 and store-1.</p>
<p class="stepn">2</p><p class="stept">It takes only the sensors <b>just before it</b> (shaded arc): {moved} of {len(S)} dots. They used to go to store-1.</p>
<p class="stepn">3</p><p class="stept">Every faded dot keeps its machine. Old machines never swap sensors with each other.</p>
</div>
<div class="cmp"><p class="cmpn">80%</p><p class="cmpt">move with hash % N</p><p class="cmpn acc">18%</p><p class="cmpt">move with the ring (10,000 sensors)</p></div>'''
html = slide("ring2", "The hash ring · 2 of 5", "Add a 5th machine: only one arc moves", svg(body, "After adding store-4 only the sensors in the arc before it change owner"), labels, right,
 "“When store-4 joins, it only takes the sensors in the arc just before it, the shaded part. They used to belong to store-1. All the faded dots keep their machine. With hash mod N almost every sensor would move; with the ring only about 1 in 5.”", "alt")
write("ring2", html.replace("drawn with the real ring.py (MD5 positions)", FOOT))
print("page1", hl, "->", ho, "| page2 moved", moved, "of", len(S))

# page 5 (simplified: 2 spots per machine, one skip)
SP5 = [(15,"store-0"),(60,"store-1"),(100,"store-2"),(140,"store-1"),(185,"store-3"),(230,"store-0"),(275,"store-2"),(320,"store-3")]
ka = 38.0
body = base
for a,o in SP5:
    x,y = pt(a); body += f'<circle cx="{f(x)}" cy="{f(y)}" r="10" fill="{COL[o]}" fill-opacity="0.35"/>'
walk = [(60,"store-1",False),(100,"store-2",False),(140,"store-1",True),(185,"store-3",False)]
body += arc(ka, 185, R-30, "#C8611E", 5)
kx,ky = pt(ka); body += f'<circle cx="{f(kx)}" cy="{f(ky)}" r="11" fill="#C8611E" stroke="#14213D" stroke-width="3"/>'
labels = [lab(*pt(ka, R+40), "sensor", "#C8611E", 110)]
num = 0; got = []
for a,o,skip in walk:
    x,y = pt(a)
    if skip:
        body += f'<circle cx="{f(x)}" cy="{f(y)}" r="16" fill="#F6F5F0" stroke="{COL[o]}" stroke-width="4" stroke-dasharray="5 4"/>'
        labels.append(node_label(a, "skip (store-1 again)", "#6B7686"))
    else:
        num += 1; got.append(o)
        body += f'<circle cx="{f(x)}" cy="{f(y)}" r="20" fill="{COL[o]}" stroke="#F6F5F0" stroke-width="4"/>'
        labels.append(node_label(a, f"{num}. {o}", COL[o]))
right = f'''<div class="steps">
<p class="stepn">1</p><p class="stept">From the sensor, keep walking clockwise.</p>
<p class="stepn">2</p><p class="stept">Collect <b>3 different machines</b>: {got[0]} (primary), {got[1]}, {got[2]}.</p>
<p class="stepn">3</p><p class="stept">Another spot of store-1 is <b>skipped</b>: two copies on one machine would die together.</p>
</div>
<p class="note">A write is OK when 2 of the 3 confirm. Any one machine can break and nothing is lost.</p>'''
html = slide("ring5", "Three copies · 5 of 5", "Keep walking to find 3 different machines", svg(body, "A sensor walks clockwise collecting three different machines and skipping a repeat"), labels, right,
 "“For 3 copies, the sensor keeps walking clockwise and collects 3 different machines: store-1, store-2 and store-3. When it meets store-1’s second spot it skips it, because two copies on one machine would be lost together.” Simplified picture: 2 spots per machine; the real system uses 100.")
write("ring5", html.replace("drawn with the real ring.py (MD5 positions)", "simplified: 2 spots per machine to show the walk · the real system uses 100"))
print("page5 walk", got)
