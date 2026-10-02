#!/usr/bin/env python
"""contrct-wtch: space & defense contract tracker over USAspending (+ optional SBIR.gov, SAM.gov).

  python pipeline.py run [--source usaspending,sbir,sam]   fetch, tag, upsert, snapshot, verify
  python pipeline.py summary [--top N] [--command 'Space Force']   commands, tags, lanes, top awards
  python pipeline.py diff [--run ID --prev ID]              what changed since the previous run
  python pipeline.py retag                                  re-apply taxonomy/lanes to stored awards (offline)
  python pipeline.py report [--out report.html]             self-contained HTML dashboard, open in a browser
"""
import argparse
import logging
import sys

from tracker import config, db, report, runner


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd")
    r = sub.add_parser("run")
    r.add_argument("--source", default="usaspending", help="comma-separated: usaspending,sbir,sam")
    s = sub.add_parser("summary")
    s.add_argument("--top", type=int, default=5)
    s.add_argument("--command", help="filter to a command, e.g. 'Space Force'")
    d = sub.add_parser("diff")
    d.add_argument("--run", type=int)
    d.add_argument("--prev", type=int)
    sub.add_parser("retag")
    h = sub.add_parser("report")
    h.add_argument("--out", default="report.html")
    h.add_argument("--top", type=int, default=25)
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.cmd in (None, "run"):
        sources = tuple(x.strip() for x in (getattr(args, "source", "usaspending")).split(",") if x.strip())
        return runner.run(sources)
    if args.cmd == "retag":
        return runner.retag()
    conn = db.connect()
    if args.cmd == "summary":
        print(report.summary(conn, top=args.top, command=args.command))
    elif args.cmd == "diff":
        print(report.diff(conn, args.run, args.prev))
    elif args.cmd == "report":
        from tracker import html
        path, data = html.render(conn, args.out, args.top)
        print(f"wrote {path}: {data['totals']['awards']} awards, {len(data['new'])} new, {len(data['changed'])} changed")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
