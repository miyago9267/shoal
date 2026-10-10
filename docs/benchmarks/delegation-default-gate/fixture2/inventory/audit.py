"""Stock audits: compare counted stock with the catalog and report drift."""

from inventory import catalog

TOLERANCE_UNITS = 1
TOLERANCE_PERCENT = 0.02


def drift(sku, counted):
    """Counted minus recorded on-hand for a SKU (positive = more than recorded)."""
    item = catalog.by_sku(sku)
    if item is None:
        raise KeyError(sku)
    return counted - item["on_hand"]


def within_tolerance(recorded, counted):
    """Small differences are noise: <=1 unit or <=2 percent of the recorded value."""
    diff = abs(counted - recorded)
    if diff <= TOLERANCE_UNITS:
        return True
    return recorded > 0 and diff / float(recorded) <= TOLERANCE_PERCENT


def audit(counts):
    """counts: {sku: counted_units}. Returns a list of findings, worst first."""
    findings = []
    for sku, counted in counts.items():
        item = catalog.by_sku(sku)
        if item is None:
            findings.append({"sku": sku, "kind": "unknown-sku", "drift": counted})
            continue
        if not within_tolerance(item["on_hand"], counted):
            findings.append(
                {"sku": sku, "kind": "drift", "drift": counted - item["on_hand"]}
            )
    findings.sort(key=lambda f: -abs(f["drift"]))
    return findings


def apply(findings):
    """Book the drift of every 'drift' finding into the catalog; returns the count."""
    applied = 0
    for finding in findings:
        if finding["kind"] == "drift":
            catalog.adjust(finding["sku"], finding["drift"])
            applied += 1
    return applied


def uncounted(counts):
    """Active SKUs that were not part of this count."""
    return sorted(i["sku"] for i in catalog.active_items() if i["sku"] not in counts)
