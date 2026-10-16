"""Build the shared transparent metallic ring and GitHub title assets."""
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "readme"
FONT = "-apple-system,BlinkMacSystemFont,Segoe UI,Microsoft YaHei,PingFang SC,sans-serif"

# The supplied icon's annulus: dark navy crown, lavender sides, silver base.
# Both the hole and the space outside the ring are transparent.
RING = '''<defs>
    <linearGradient id="metal" x1="0" y1="0" x2="0.12" y2="1">
      <stop offset="0" stop-color="#192c3b"/>
      <stop offset=".25" stop-color="#344455"/>
      <stop offset=".58" stop-color="#7b7d98"/>
      <stop offset=".82" stop-color="#b5afbe"/>
      <stop offset="1" stop-color="#d4ccc6"/>
    </linearGradient>
    <linearGradient id="rim" x1="0" y1="0" x2=".8" y2="1">
      <stop stop-color="#b6c0c8" stop-opacity=".65"/>
      <stop offset=".35" stop-color="#354351" stop-opacity=".35"/>
      <stop offset=".8" stop-color="#f2e8ed" stop-opacity=".85"/>
      <stop offset="1" stop-color="#787783" stop-opacity=".8"/>
    </linearGradient>
  </defs>'''
ANNULUS = '''<g id="ring">
    <path fill="url(#metal)" fill-rule="evenodd" d="M80 10a70 70 0 1 1 0 140 70 70 0 1 1 0-140Zm0 21a49 49 0 1 0 0 98 49 49 0 1 0 0-98Z"/>
    <circle cx="80" cy="80" r="69.6" fill="none" stroke="url(#rim)" stroke-width=".8"/>
    <circle cx="80" cy="80" r="49.4" fill="none" stroke="url(#rim)" stroke-width=".8"/>
  </g>'''


def svg(width, height, title, body, description):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
  <title id="title">{escape(title)}</title>
  <desc id="desc">{escape(description)}</desc>
  {RING}
  {body}
</svg>
'''


def ring_at(x, y, size):
    return f'<g transform="translate({x} {y}) scale({size / 160})">{ANNULUS}</g>'


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "ring.svg").write_text(svg(160, 160, "OPPO AI Pin ring", ANNULUS,
        "Transparent metallic ring inspired by the supplied icon; navy, lavender and silver."), encoding="utf-8")
    sections = {
        "overview": "课程里的三件事", "start": "开始使用",
        "customize": "选择你的笔记风格", "privacy": "数据与边界", "development": "开发与许可",
    }
    for dark in (False, True):
        suffix = "-dark" if dark else ""
        foreground, muted, rule = ("#e6edf3", "#aeb8c5", "#303943") if dark else ("#202b35", "#626d77", "#d9dee2")
        hero = ring_at(20, 17, 76) + f'''
  <text x="118" y="70" font-family="{FONT}" font-size="42" letter-spacing="1" fill="{muted}">OPPO AI Pin</text>
  <text x="24" y="175" font-family="{FONT}" font-size="88" font-weight="600" letter-spacing="-2" fill="{foreground}">Course Companion</text>
  <path d="M28 227H1172" stroke="{rule}"/>
'''
        (OUT / f"hero{suffix}.svg").write_text(svg(1200, 250, "OPPO AI Pin Course Companion", hero,
            "Course Companion title with a transparent metallic ring matching the OPPO AI Pin motif."), encoding="utf-8")
        for key, title in sections.items():
            body = ring_at(0, 4, 48) + f'''
  <text x="64" y="41" font-family="{FONT}" font-size="34" font-weight="600" fill="{foreground}">{title}</text>
  <path d="M4 70H756" stroke="{rule}"/>
'''
            (OUT / f"section-{key}{suffix}.svg").write_text(svg(760, 80, title, body,
                f"{title}；透明金属圆环与统一的左对齐标题。"), encoding="utf-8")


if __name__ == "__main__":
    build()
