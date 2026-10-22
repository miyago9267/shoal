"""template: a tiny {{ variable }} template engine."""
import re

_TOKEN = re.compile(r"\{\{\s*(\w+)\s*\}\}")
_FULL = re.compile(
    r"(?P<esc>\\\{\{)|\{\{\s*(?P<name>\w+(?:\.\w+)*)\s*"
    r"(?:\|\s*default\s*:\s*(?:\"(?P<dq>[^\"]*)\"|'(?P<sq>[^']*)'))?\s*\}\}"
)


# TODO(fix): render(template, ctx) must
#   * look up dotted names: {{ user.name }} walks dict keys, falling back to
#     attributes, one segment at a time,
#   * support a default filter: {{ nick|default:"anon" }} (single or double
#     quotes) is used only when the variable is missing,
#   * raise KeyError carrying the full dotted name for a missing variable that
#     has no default (today it renders as an empty string),
#   * render a backslash-escaped opening brace pair literally: \{{ stays {{ and
#     the text after it is not treated as a variable,
#   * convert values with str().


def render(template, ctx):
    """Fill ``template`` from ``ctx``."""
    return _TOKEN.sub(lambda m: str(ctx.get(m.group(1), "")), template)


def variables(template):
    """Names used by the template, in order of first appearance."""
    seen = []
    for match in _FULL.finditer(template):
        name = match.group("name")
        if not match.group("esc") and name not in seen:
            seen.append(name)
    return seen


def missing(template, ctx):
    names = []
    for name in variables(template):
        try:
            _lookup(ctx, name)
        except KeyError:
            names.append(name)
    return names


def render_many(template, contexts):
    """Render once per context; the first failure propagates."""
    return [render(template, ctx) for ctx in contexts]


def has_variables(template):
    return bool(variables(template))


def safe_render(template, ctx, placeholder="?"):
    """Like render, but missing variables become ``placeholder``."""
    bad = set(missing(template, ctx))
    if not bad:
        return render(template, ctx)
    patched = dict(ctx)
    for name in bad:
        if "." in name:
            continue
        patched[name] = placeholder
    try:
        return render(template, patched)
    except KeyError:
        return placeholder
