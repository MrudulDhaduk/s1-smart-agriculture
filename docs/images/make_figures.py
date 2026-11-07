"""
make_figures.py - draws the charts used in docs/p3-concept-scaling-monitoring.md.

    python docs/images/make_figures.py

The ring picture uses the REAL HashRing (MD5 positions), just with 6 virtual nodes per
node instead of 100 so it stays readable. The bar charts use numbers measured by demo.py.
"""

import math
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "services", "partition-manager"))
from ring import HashRing, hash_key  # noqa: E402

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]  # validated categorical order
plt.rcParams.update({"font.size": 11, "text.color": INK, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.edgecolor": GRID})


def angle(position):
    """Ring position (0 .. 2^128) -> clockwise angle from 12 o'clock, in radians."""
    return 2 * math.pi * position / 2**128


def xy(theta, r):
    return r * math.sin(theta), r * math.cos(theta)


def walk_angles(ring, sensor):
    """Angles of the sensor and of the first spot of each of its 3 owners (clockwise)."""
    spots, start = ring._positions, angle(hash_key(sensor))
    i = next((k for k, p in enumerate(spots) if p > hash_key(sensor)), 0)
    found, out = [], []
    while len(found) < 3:
        spot = spots[i % len(spots)]
        if ring._owner[spot] not in found:
            found.append(ring._owner[spot])
            a = angle(spot)
            out.append(a if a >= start else a + 2 * math.pi)
        i += 1
    return start, out


def pick_readable_sensor(ring):
    best, best_gap = "farm7-plot2-s3", 0
    for f in range(1, 200):
        for s in range(1, 11):
            sensor = f"farm{f}-plot2-s{s}"
            start, a = walk_angles(ring, sensor)
            gap = min(a[0] - start, a[1] - a[0], a[2] - a[1])
            if gap > best_gap and a[2] - start < 3.6:
                best, best_gap = sensor, gap
    return best


def ring_figure():
    nodes = ["store-0", "store-1", "store-2", "store-3"]
    color = dict(zip(nodes, SERIES))
    ring = HashRing(vnodes=6, replicas=3)
    for n in nodes:
        ring.add_node(n)
    spots = ring._positions

    fig, ax = plt.subplots(figsize=(9, 7), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    ax.set_aspect("equal")
    ax.axis("off")

    # each node owns the arc that ENDS at its spot (coming from the previous spot)
    for i, spot in enumerate(spots):
        start = angle(spots[i - 1]) if i else angle(spots[-1]) - 2 * math.pi
        end = angle(spot)
        ts = [start + (end - start) * k / 40 for k in range(41)]
        ax.plot(*zip(*[xy(t, 1.0) for t in ts]), color=color[ring._owner[spot]], lw=9,
                solid_capstyle="butt", alpha=0.85)
    for spot in spots:  # the virtual-node ticks
        x1, y1 = xy(angle(spot), 0.93)
        x2, y2 = xy(angle(spot), 1.07)
        ax.plot([x1, x2], [y1, y2], color=INK, lw=1.2)

    # one sensor and its clockwise walk to 3 different nodes. Pick an example whose walk is
    # spread out enough to label clearly (any sensor works the same way).
    sensor = pick_readable_sensor(ring)
    owners = ring.get_nodes(sensor)
    s_angle = angle(hash_key(sensor))
    sx, sy = xy(s_angle, 1.0)
    ax.plot(sx, sy, "o", ms=11, color=INK, zorder=5)

    def outside_label(theta, text):
        lx, ly = xy(theta, 1.3)
        ha = "left" if math.sin(theta) > 0.25 else "right" if math.sin(theta) < -0.25 else "center"
        ax.text(lx, ly, text, ha=ha, va="center", fontsize=10, color=INK)
        x1, y1 = xy(theta, 1.06)
        x2, y2 = xy(theta, 1.22)
        ax.plot([x1, x2], [y1, y2], color=INK2, lw=0.8)

    outside_label(s_angle, f"sensor {sensor}")
    i, found = next((k for k, p in enumerate(spots) if p > hash_key(sensor)), 0), []
    roles = ["primary", "replica 2", "replica 3"]
    while len(found) < 3:
        spot = spots[i % len(spots)]
        node = ring._owner[spot]
        if node not in found:
            found.append(node)
            px, py = xy(angle(spot), 1.0)
            ax.plot(px, py, "o", ms=13, mfc=SURFACE, mec=INK, mew=2, zorder=6)
            outside_label(angle(spot), f"{len(found)}. {roles[len(found) - 1]}: {node}")
        i += 1
    end_angle = angle(spots[(i - 1) % len(spots)])
    if end_angle < s_angle:
        end_angle += 2 * math.pi
    ts = [s_angle + (end_angle - s_angle) * k / 60 for k in range(61)]
    ax.plot(*zip(*[xy(t, 0.86) for t in ts]), color=INK, lw=1.5)
    ax.annotate("", xy=xy(ts[-1], 0.86), xytext=xy(ts[-3], 0.86),
                arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.5))
    assert found == owners, "figure must match the real get_nodes()"

    ax.text(0, 0.08, "walk clockwise", ha="center", fontsize=11, color=INK2)
    ax.text(0, -0.08, "to 3 different nodes", ha="center", fontsize=11, color=INK2)
    handles = [plt.Line2D([], [], color=color[n], lw=8, label=n) for n in nodes]
    handles.append(plt.Line2D([], [], color=INK, lw=1.2, label="virtual node (spot)"))
    ax.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.08), ncol=5, frameon=False,
              fontsize=9.5, handlelength=1.6)
    ax.set_xlim(-2.1, 2.1)
    ax.set_ylim(-1.55, 1.55)
    fig.savefig(os.path.join(HERE, "ring.png"), dpi=160, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)
    return owners


def style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)


def keys_moved_figure():
    labels = ["hash(key) % N", "consistent hashing ring"]
    values = [80.2, 18.4]  # demo.py, 10,000 sensors, 4 -> 5 nodes
    fig, ax = plt.subplots(figsize=(7.5, 2.6), facecolor=SURFACE)
    style(ax)
    bars = ax.barh(labels, values, color=[SERIES[1], SERIES[0]], height=0.5)
    ax.axvline(20, color=INK, ls="--", lw=1.2)
    ax.text(20.8, -0.48, "minimum possible: 1/5 = 20%", fontsize=9.5, color=INK, va="center")
    for b, v in zip(bars, values):
        ax.text(max(v, 20) + 1.5, b.get_y() + b.get_height() / 2, f"{v}%", va="center", fontsize=11, color=INK)
    ax.set_ylim(1.45, -0.7)
    ax.set_xlim(0, 100)
    ax.set_xlabel("sensors that change node when a 5th node joins (%)")
    fig.savefig(os.path.join(HERE, "keys-moved.png"), dpi=160, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def balance_figure():
    nodes = ["store-0", "store-1", "store-2", "store-3"]
    one = [1063, 929, 6204, 1804]      # demo.py, vnodes=1
    hundred = [2613, 2649, 2596, 2142]  # demo.py, vnodes=100
    fig, ax = plt.subplots(figsize=(7.5, 3.4), facecolor=SURFACE)
    style(ax)
    y = range(len(nodes))
    h = 0.36
    ax.barh([i - h / 2 - 0.02 for i in y], one, height=h, color=SERIES[1], label="1 spot per node")
    ax.barh([i + h / 2 + 0.02 for i in y], hundred, height=h, color=SERIES[0], label="100 spots per node")
    def label_x(v):  # keep the number from sitting on the dashed line
        return 2560 if v + 60 < 2500 < v + 520 else v + 60

    for i in y:
        ax.text(label_x(one[i]), i - h / 2 - 0.02, f"{one[i]:,}", va="center", fontsize=9.5, color=INK)
        ax.text(label_x(hundred[i]), i + h / 2 + 0.02, f"{hundred[i]:,}", va="center", fontsize=9.5, color=INK)
    ax.axvline(2500, color=INK, ls="--", lw=1.2)
    ax.text(2560, -0.75, "fair share 2,500", fontsize=9.5, color=INK)
    ax.set_yticks(list(y), nodes)
    ax.set_xlim(0, 7000)
    ax.set_ylim(len(nodes) - 0.4, -0.95)
    ax.set_xlabel("sensors owned (10,000 sensors, 4 nodes)")
    ax.legend(loc="lower right", frameon=False, fontsize=9.5)
    fig.savefig(os.path.join(HERE, "balance.png"), dpi=160, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


if __name__ == "__main__":
    print("example sensor owners:", ring_figure())
    keys_moved_figure()
    balance_figure()
    print("wrote ring.png, keys-moved.png, balance.png")
