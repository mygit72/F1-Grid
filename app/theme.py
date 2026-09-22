"""Shared visual theme: an F1 timing-tower aesthetic — near-black background,
monospace numerals for positions/times, a single vermillion accent (chosen to
evoke timing screens without mimicking any official F1 branding/colors)."""

THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap');

:root {
  --bg: #0B0E11;
  --panel: #14181D;
  --line: #232830;
  --text: #E7EAEE;
  --muted: #8A92A0;
  --accent: #E8462E;
  --accent-dim: #5A2218;
  --good: #2FB67C;
  --warn: #E0A52E;
}

html, body, [class*="css"] { 
  font-family: 'Inter', sans-serif;
  color: var(--text);
}

.stApp { background-color: var(--bg); }

/* Timing-tower position card */
.pos-card {
  display: flex;
  align-items: center;
  background: var(--panel);
  border: 1px solid var(--line);
  border-left: 3px solid var(--accent);
  border-radius: 4px;
  padding: 10px 14px;
  margin-bottom: 6px;
  font-family: 'JetBrains Mono', monospace;
}
.pos-card .pos-num {
  font-size: 1.1rem;
  font-weight: 700;
  width: 2.2rem;
  color: var(--accent);
}
.pos-card .drv-code {
  font-weight: 700;
  font-size: 1.0rem;
  width: 3.5rem;
  letter-spacing: 0.05em;
}
.pos-card .team-name {
  flex: 1;
  color: var(--muted);
  font-family: 'Inter', sans-serif;
  font-size: 0.85rem;
}
.pos-card .conf-bar-wrap {
  width: 90px;
  height: 5px;
  background: var(--line);
  border-radius: 3px;
  overflow: hidden;
  margin-right: 10px;
}
.pos-card .conf-bar {
  height: 100%;
  background: var(--accent);
}
.pos-card .prob {
  width: 3.2rem;
  text-align: right;
  font-size: 0.85rem;
  color: var(--text);
}

.section-eyebrow {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem;
  letter-spacing: 0.12em;
  color: var(--accent);
  text-transform: uppercase;
  margin-bottom: 2px;
}

.metric-box {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 14px 16px;
}
.metric-box .val { font-family:'JetBrains Mono',monospace; font-size:1.6rem; font-weight:700; }
.metric-box .lbl { color: var(--muted); font-size: 0.78rem; margin-top: 2px; }

.assumption-tag {
  display: inline-block;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.68rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 3px;
  margin-left: 6px;
}
.tag-real { background: rgba(47,182,124,0.15); color: var(--good); border:1px solid rgba(47,182,124,0.35);}
.tag-assumed { background: rgba(224,165,46,0.15); color: var(--warn); border:1px solid rgba(224,165,46,0.35);}

hr { border-color: var(--line); }
</style>
"""
