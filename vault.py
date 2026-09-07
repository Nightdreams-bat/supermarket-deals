import re
from datetime import date
from pathlib import Path

from notify import discount_line, watchlist_line
from sources.base import Offer

VAULT_FILE = Path(r"D:\V A U L T\Brain\Deals\supermarket-deals.md")
HEADER = "# Supermarket Deals Log"


def _strip_bullet(line: str) -> str:
    return "- " + line[2:] if line.startswith("• ") else line


def build_section(watchlist_hits: list[Offer], top_discounts: list[Offer],
                  today: date) -> str:
    lines = [f"## {today.isoformat()}", ""]
    if watchlist_hits:
        lines.append("### ⭐ On your watchlist")
        lines += [_strip_bullet(watchlist_line(o, today)) for o in watchlist_hits]
        lines.append("")
    lines.append("### 🔥 Biggest discounts")
    lines += [_strip_bullet(discount_line(o, today)) for o in top_discounts]
    return "\n".join(lines).strip() + "\n"


def append(watchlist_hits: list[Offer], top_discounts: list[Offer],
           today: date | None = None, path: Path | None = None) -> Path:
    today = today or date.today()
    path = path or VAULT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)

    body = path.read_text(encoding="utf-8") if path.exists() else HEADER + "\n"
    section = build_section(watchlist_hits, top_discounts, today)

    pattern = re.compile(
        rf"^## {re.escape(today.isoformat())}\s*$.*?(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    if pattern.search(body):
        body = pattern.sub(lambda _: section + "\n", body)
    else:
        body = body.rstrip() + "\n\n" + section

    path.write_text(body.rstrip() + "\n", encoding="utf-8")
    return path
