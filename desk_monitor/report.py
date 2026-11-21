"""Plain-text daily report for the desk and for the audit trail."""


def write(path, date, readiness, recon_result, monitor_result):
    out = [f"# Desk monitor report: {date}", ""]
    out.append(f"## 1. Pre-open readiness: {readiness['status']}")
    out.append(f"Rows checked: {readiness['rows']}. Errors: {readiness['errors']}.")
    for issue in readiness["issues"][:20]:
        out.append(f"- [{issue['severity']}] {issue['check']}: {issue['detail']}")
    out.append("")

    if recon_result is None:
        out.append("## 2. Reconciliation: not run (readiness gate failed)")
        out.append("")
        out.append("## 3. Intraday monitoring: not run (readiness gate failed)")
    else:
        out.append(f"## 2. Reconciliation: {len(recon_result['breaks'])} breaks "
                   f"across {recon_result['orders']} orders")
        for kind, n in sorted(recon_result["by_kind"].items()):
            out.append(f"- {kind}: {n}")
        for b in recon_result["breaks"][:20]:
            out.append(f"  - {b['order_id']} {b['kind']}: {b['detail']}")
        out.append("")
        out.append(f"## 3. Intraday monitoring: {len(monitor_result['alerts'])} alerts "
                   f"over {monitor_result['buckets']} buckets of 100 ms")
        for a in monitor_result["alerts"][:20]:
            out.append(f"- {a['time_utc']} {a['metric']} {a['kind']} "
                       f"value={a['value']} z={a['z']}")
    with open(path, "w") as f:
        f.write("\n".join(out) + "\n")
