"""versions: compare dotted version strings."""
import functools


def _split(version):
    version = version.strip().lstrip("v")
    release, _, pre = version.partition("-")
    return release.split("."), pre


# TODO(fix): compare_versions(a, b) -> -1, 0 or 1 must
#   * compare the dot separated segments as integers ("1.10" > "1.9"),
#   * treat missing segments as 0 ("1.0" == "1.0.0"),
#   * ignore a leading "v" ("v2.1" == "2.1"),
#   * rank a pre-release below its release ("1.0-rc1" < "1.0") and compare two
#     pre-release tags as plain strings,
#   * raise ValueError for a segment that is not a number.


def compare_versions(a, b):
    """Three-way compare of two version strings."""
    return (a > b) - (a < b)


def sort_versions(versions, reverse=False):
    key = functools.cmp_to_key(compare_versions)
    return sorted(versions, key=key, reverse=reverse)


def newest(versions):
    ordered = sort_versions(versions)
    return ordered[-1] if ordered else None


def satisfies(version, minimum):
    return compare_versions(version, minimum) >= 0


def bump(version, part="patch"):
    """Increase the major, minor or patch number and reset the lower ones."""
    release = _split(version)[0]
    nums = [int(x) for x in release] + [0] * (3 - len(release))
    index = {"major": 0, "minor": 1, "patch": 2}[part]
    nums[index] += 1
    for i in range(index + 1, 3):
        nums[i] = 0
    return ".".join(str(n) for n in nums[:3])


def major(version):
    return int(_split(version)[0][0])


def is_prerelease(version):
    return bool(_split(version)[1])
