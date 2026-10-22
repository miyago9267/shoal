"""python3 -m utilkit.cli <tool> <args...>: expose a few utilities."""
import sys

from . import bytesize, durations, paths, slug, versions

TOOLS = {
    "slug": lambda a: slug.slugify(" ".join(a)),
    "duration": lambda a: str(durations.parse_duration(" ".join(a))),
    "size": lambda a: bytesize.human_size(int(a[0])),
    "path": lambda a: paths.normalize(a[0]),
    "newest": lambda a: str(versions.newest(a)),
}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in TOOLS:
        print("usage: utilkit.cli {%s} ..." % "|".join(sorted(TOOLS)), file=sys.stderr)
        return 2
    try:
        print(TOOLS[argv[0]](argv[1:]))
    except (ValueError, TypeError, IndexError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
