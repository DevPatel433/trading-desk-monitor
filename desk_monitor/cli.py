"""Command-line interface.

Exit codes: 0 clean, 1 breaks or alerts found, 2 readiness failed.
"""
import argparse
import json
import os
import sys

from . import generator, monitor, readiness, recon, report


def _parse_faults(text):
    faults = {}
    for part in filter(None, text.split(",")):
        kind, _, n = part.partition(":")
        if kind not in generator.FAULT_KINDS:
            raise SystemExit(f"unknown fault '{kind}', choose from {generator.FAULT_KINDS}")
        faults[kind] = int(n or 1)
    return faults


def _dump(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)


def cmd_generate(args):
    burst = (args.burst_start, args.burst_seconds, args.burst_orders) if args.burst_orders else None
    truth = generator.write_events(args.out, n_orders=args.orders, seed=args.seed,
                                   faults=_parse_faults(args.faults), burst=burst)
    if args.truth:
        _dump(args.truth, truth)
    print(f"wrote {args.out} with {len(truth)} injected faults")
    return 0


def cmd_check(args):
    res = readiness.check(args.events)
    print(json.dumps({"status": res["status"], "errors": res["errors"]}))
    return 0 if res["status"] == "PASS" else 2


def cmd_recon(args):
    res = recon.reconcile(args.events)
    if args.out:
        _dump(args.out, res)
    print(f"orders={res['orders']} breaks={len(res['breaks'])} by_kind={res['by_kind']}")
    return 1 if res["breaks"] else 0


def cmd_monitor(args):
    res = monitor.monitor(args.events)
    if args.out:
        _dump(args.out, res)
    print(f"buckets={res['buckets']} alerts={len(res['alerts'])}")
    return 1 if res["alerts"] else 0


def cmd_run(args):
    os.makedirs(args.outdir, exist_ok=True)
    ready = readiness.check(args.events)
    _dump(os.path.join(args.outdir, "readiness.json"), ready)

    if ready["status"] == "FAIL":
        report.write(os.path.join(args.outdir, "report.md"), args.date, ready, None, None)
        print("readiness FAILED: processing halted, see report", file=sys.stderr)
        return 2

    rec = recon.reconcile(args.events)
    mon = monitor.monitor(args.events)
    _dump(os.path.join(args.outdir, "recon.json"), rec)
    _dump(os.path.join(args.outdir, "alerts.json"), mon)
    report.write(os.path.join(args.outdir, "report.md"), args.date, ready, rec, mon)
    print(f"readiness PASS | breaks={len(rec['breaks'])} alerts={len(mon['alerts'])} "
          f"| report: {os.path.join(args.outdir, 'report.md')}")
    return 1 if rec["breaks"] or mon["alerts"] else 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="desk_monitor",
                                description="Trading desk readiness, reconciliation and monitoring.")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="create a synthetic day of events")
    g.add_argument("--out", required=True)
    g.add_argument("--orders", type=int, default=20000)
    g.add_argument("--seed", type=int, default=7)
    g.add_argument("--faults", default="", help="e.g. drop_fill:2,price_breach:1")
    g.add_argument("--burst-start", type=float, default=15.0)
    g.add_argument("--burst-seconds", type=float, default=3.0)
    g.add_argument("--burst-orders", type=int, default=0)
    g.add_argument("--truth", help="write injected-fault ground truth to this JSON file")
    g.set_defaults(func=cmd_generate)

    c = sub.add_parser("check", help="pre-open readiness gate")
    c.add_argument("--events", required=True)
    c.set_defaults(func=cmd_check)

    r = sub.add_parser("recon", help="post-trade reconciliation")
    r.add_argument("--events", required=True)
    r.add_argument("--out")
    r.set_defaults(func=cmd_recon)

    m = sub.add_parser("monitor", help="intraday anomaly monitoring")
    m.add_argument("--events", required=True)
    m.add_argument("--out")
    m.set_defaults(func=cmd_monitor)

    run = sub.add_parser("run", help="full daily pipeline with report")
    run.add_argument("--events", required=True)
    run.add_argument("--outdir", required=True)
    run.add_argument("--date", default="unknown")
    run.set_defaults(func=cmd_run)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
