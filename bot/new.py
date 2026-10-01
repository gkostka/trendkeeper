"""tk new: create a strategy step by step and follow it, alongside the strategies followed now or instead of them.

The rules come from the funds the config already trades (each trend fund keeps its signal and averages, a held
fund stays held), so the questions are only the name, the weights, the capital and the start. The capital and
the start are the strategy's own, so strategies followed together don't share them; they share the daily summary.
The config is edited as text, so its comments survive, and the result is loaded and checked before it is saved.
"""
import re
from datetime import date, datetime
from pathlib import Path

from bot import config

PRESETS = [("30/30/40", (0.30, 0.30, 0.40)), ("25/25/50", (0.25, 0.25, 0.50)),
           ("33/33/34", (0.33, 0.33, 0.34)), ("40/40/20", (0.40, 0.40, 0.20))]


def menu(cfg) -> list[config.Slice]:
    """The funds the configured strategies trade, each with its rule: the followed strategy's first."""
    order = [cfg.strategies[sid] for sid in cfg.follow]
    order += [s for s in cfg.strategies.values() if not s.benchmark and s.id not in cfg.follow]
    funds = {}
    for s in order:
        for sl in s.slices:
            funds.setdefault(sl.fund, sl)
    return list(funds.values())


def label(cfg, sl) -> str:
    name = cfg.instruments[sl.fund].name or sl.fund
    rule = f"held while {sl.signal} > {'/'.join(map(str, sl.windows))}d avg" if sl.rule == "trend" else "always held"
    return f"{name} ({sl.fund.split('.')[0]}), {rule}"


def describe(cfg, funds, weights, monthly: bool) -> str:
    parts = []
    for sl, w in zip(funds, weights):
        if w:
            name = cfg.instruments[sl.fund].name or sl.fund
            parts.append(f"{w:.0%} {name}" + (f" while above its {'/'.join(map(str, sl.windows))}-day averages"
                                               if sl.rule == "trend" else ""))
    return "; ".join(parts) + ("; rebalanced monthly." if monthly else ".")


def block(sid, name, description, funds, weights, monthly, tax_rate, capital, start) -> str:
    lines = ["", "[[strategy]]", f'id = "{sid}"', f'name = "{name}"', f'description = "{description}"',
             f"start_value = {capital:g}", f"start = {start.isoformat()}"]
    if monthly:
        lines.append('rebalance = "monthly"')
    lines.append(f"tax_rate = {tax_rate}")
    for sl, w in zip(funds, weights):
        if not w:
            continue
        lines += ["", "  [[strategy.slice]]", f"  weight = {round(w, 4)}", f'  fund = "{sl.fund}"', f'  rule = "{sl.rule}"']
        if sl.rule == "trend":
            lines += [f'  signal = "{sl.signal}"', f"  windows = [{', '.join(map(str, sl.windows))}]"]
    return "\n".join(lines) + "\n"


def set_top(text: str, key: str, value: str, note: str) -> str:
    """Sets a top-level `key = value` in place, or adds it at the top, where top-level keys must go."""
    line = f"{key} = {value}   # {note}"
    pattern = re.compile(rf"^{re.escape(key)}\s*=.*$", re.M)
    return pattern.sub(line, text, count=1) if pattern.search(text) else line + "\n" + text


def run(ask=input, say=print, cfg_path: Path | None = None) -> int:
    cfg_path = cfg_path or config.path()
    text = cfg_path.read_text()
    cfg = config.loads(text)
    funds = menu(cfg)

    def question(prompt, parse, default=None):
        while True:
            raw = ask(f"{prompt}" + (f" [{default}]" if default not in (None, "") else "") + ": ").strip()
            try:
                return parse(raw if raw else ("" if default is None else str(default)))
            except ValueError as e:
                say(f"  {e}")

    def unique_name(raw):
        sid = re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_")
        if not sid:
            raise ValueError("give the strategy a name")
        if sid in cfg.strategies or raw in {s.name for s in cfg.strategies.values()}:
            raise ValueError(f"{raw!r} is taken; the strategies are {', '.join(s.name for s in cfg.strategies.values())}")
        return raw, sid

    def money(raw):
        value = float(raw.replace(",", "").replace("_", ""))
        if value <= 0:
            raise ValueError("the capital must be more than 0")
        return value

    def day(raw):
        try:
            return date.fromisoformat(raw)
        except ValueError:
            raise ValueError("a date as YYYY-MM-DD") from None

    def one_or_two(raw):
        if raw not in ("1", "2"):
            raise ValueError("1 or 2")
        return int(raw)

    def yes(raw):
        if raw.lower() in ("y", "yes"):
            return True
        if raw.lower() in ("n", "no"):
            return False
        raise ValueError("y or n")

    say("New strategy, with its own capital and start date.\n")
    name, sid = question("Name", unique_name)

    say("\nFunds:")
    for sl in funds:
        say(f"  {label(cfg, sl)}")
    presets = PRESETS if len(funds) == 3 else []
    say("\nAllocation:")
    for k, (title, _) in enumerate(presets, 1):
        say(f"  {k}. {title}")
    say(f"  {len(presets) + 1}. custom: a weight for each fund")

    def choice(raw):
        k = int(raw) if raw.isdigit() else 0
        if not 1 <= k <= len(presets) + 1:
            raise ValueError(f"a number from 1 to {len(presets) + 1}")
        return k

    k = question("Choose", choice, 1)
    if k <= len(presets):
        weights = presets[k - 1][1]
    else:
        while True:
            weights = tuple(question(f"  % in {label(cfg, sl)}", lambda raw: float(raw) / 100, 0) for sl in funds)
            if abs(sum(weights) - 1) < 1e-9 and all(0 <= w <= 1 for w in weights):
                break
            say(f"  The weights add up to {sum(weights):.0%}; they must add up to 100%.")

    capital = question(f"Starting capital in {cfg.base_currency}", money, int(cfg.start_value))
    start = question("Start date", day, date.today().isoformat())
    monthly = question("Rebalance monthly? (y/n)", yes, "y")
    description = question("Description", lambda raw: raw.replace('"', "'"), describe(cfg, funds, weights, monthly))

    followed = [cfg.strategies[k] for k in cfg.follow]
    alongside = True
    if followed:
        names = ", ".join(s.name for s in followed)
        say(f"\nFollowed now: {names}.\n  1. follow {name} alongside them\n  2. follow {name} instead of them")
        alongside = question("Choose", one_or_two, 1) == 1
    follow = ([s.id for s in followed] if alongside else []) + [sid]
    tax_rate = followed[0].tax_rate if followed else 0.0
    new_text = text.rstrip("\n") + "\n" + block(sid, name, description, funds, weights, monthly, tax_rate, capital,
                                                 start)
    new_text = set_top(new_text, "follow", "[" + ", ".join(f'"{k}"' for k in follow) + "]",
                       f"set by tk new on {date.today().isoformat()}")
    try:
        config.loads(new_text)
    except config.ConfigError as e:
        say(f"\nThat strategy doesn't pass the config check: {e}")
        return 1

    say(f"\n{name} ({sid})")
    for sl, w in zip(funds, weights):
        if w:
            say(f"  {w:>4.0%}  {label(cfg, sl)}")
    say(f"  {'rebalanced monthly' if monthly else 'never rebalanced'}; tax rate {tax_rate:.0%} (from "
        f"{followed[0].name if followed else 'the default'}; edit tax_rate in the config to change it)")
    say(f"  {capital:,.0f} {cfg.base_currency} from {start.isoformat()}, starting in cash")
    say(f"  Followed: {', '.join(cfg.strategies[k].name if k in cfg.strategies else name for k in follow)}")
    if not question("Save and follow it? (y/n)", yes, "y"):
        say("Nothing saved.")
        return 1

    backup = cfg_path.with_name(f"{cfg_path.name}.bak-{datetime.now():%Y%m%d-%H%M%S}")
    backup.write_text(text)
    cfg_path.write_text(new_text)
    say(f"Saved to {cfg_path} (the old config is {backup.name}).")
    say("The next daily run (or `tk daily`) advises its first trades from cash, in the daily summary.")
    return 0
