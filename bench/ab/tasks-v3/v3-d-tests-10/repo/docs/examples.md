# Usage examples

Examples use behaviour that already works today. Anything that depends on a
pending `TODO(fix)` is left out on purpose.

## slug

    >>> slug.slugify("Hello World")
    'hello-world'
    >>> slug.unique_slug("post", {"post", "post-2"})
    'post-3'
    >>> slug.slugs(["Intro", "Intro"])
    ['intro', 'intro-2']

## durations

    >>> durations.parse_duration("1h30m")
    5400
    >>> durations.format_duration(3725)
    '1h2m5s'
    >>> durations.clock(3725)
    '1:02:05'

## wrap

    >>> print(wrap.wrap("the quick brown fox", 9))
    the quick
    brown fox
    >>> print(wrap.fill("the quick brown fox", 11, "> "))
    > the quick
    > brown fox

## bytesize

    >>> bytesize.parse_size("2 KiB")
    2048
    >>> bytesize.split_evenly(10, 3)
    [4, 3, 3]

## csvline

    >>> csvline.split_csv_line("a,b,c")
    ['a', 'b', 'c']
    >>> csvline.join_csv_line(["a", "b,c"])
    'a,"b,c"'

## versions

    >>> versions.compare_versions("1.2.3", "1.2.4")
    -1
    >>> versions.bump("1.2.3", "minor")
    '1.3.0'

## retry

    >>> retry.backoff_delays(3, base=1)
    [1.0, 2.0, 4.0]
    >>> retry.describe([1, 2, 4])
    '3 retries, 7.0s total'

## paths

    >>> paths.normalize("a//b")
    'a/b'
    >>> paths.extension("report.final.pdf")
    'pdf'

## ranges

    >>> ranges.contains([(1, 3), (8, 9)], 9)
    True
    >>> ranges.overlaps((1, 3), (3, 5))
    True

## template

    >>> template.render("hello {{ name }}", {"name": "world"})
    'hello world'
    >>> template.variables("{{ a }} and {{ b }}")
    ['a', 'b']

## Command line

    $ python3 -m utilkit.cli slug Hello World
    hello-world
    $ python3 -m utilkit.cli duration 1h30m
    5400
