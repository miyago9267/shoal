import unittest

from utilkit import (
    bytesize, csvline, durations, paths, ranges, retry, slug, template, versions, wrap,
)


class TestSlug(unittest.TestCase):
    def test_fold_and_trim(self):
        self.assertEqual(slug.slugify("  Caf\u00e9 cr\u00e8me -- Br\u00fbl\u00e9e!  "), "cafe-creme-brulee")
        self.assertEqual(slug.slugify("***"), "")
        self.assertEqual(slug.slugify("--A--B--"), "a-b")

    def test_max_len_word_boundary(self):
        self.assertEqual(slug.slugify("hello big wide world", 12), "hello-big")
        self.assertEqual(slug.slugify("hello big wide world", 13), "hello-big")
        self.assertEqual(slug.slugify("hello big wide world", 14), "hello-big-wide")
        self.assertEqual(slug.slugify("hello big", 100), "hello-big")

    def test_max_len_long_word(self):
        self.assertEqual(slug.slugify("extraordinary day", 5), "extra")
        self.assertEqual(slug.slugify("a extraordinary", 3), "a")

    def test_helpers_still_work(self):
        self.assertEqual(slug.slugs(["Caf\u00e9", "Cafe", "cafe!"]), ["cafe", "cafe-2", "cafe-3"])


class TestDurations(unittest.TestCase):
    def test_units(self):
        self.assertEqual(durations.parse_duration("2d"), 172800)
        self.assertEqual(durations.parse_duration("1w"), 604800)
        self.assertEqual(durations.parse_duration("1w2d3h4m5s"), 604800 + 172800 + 10800 + 240 + 5)

    def test_decimals_and_spaces(self):
        self.assertEqual(durations.parse_duration("1.5h"), 5400)
        self.assertIsInstance(durations.parse_duration("1.5h"), int)
        self.assertEqual(durations.parse_duration("0.5s"), 0.5)
        self.assertEqual(durations.parse_duration(" 1h  30m "), 5400)

    def test_garbage(self):
        for text in ["", "   ", "5", "5x", "h", "1h x", "1h30", "-5s", "1..5h"]:
            with self.assertRaises(ValueError, msg=repr(text)):
                durations.parse_duration(text)

    def test_helpers(self):
        self.assertEqual(durations.total(["1h", "30m"]), 5400)
        self.assertEqual(durations.longest(["90m", "1h", "1d"]), "1d")


class TestWrap(unittest.TestCase):
    def test_paragraphs(self):
        text = "aaa bbb ccc\n\n\nddd   eee\n \nfff"
        self.assertEqual(wrap.wrap(text, 7), "aaa bbb\nccc\n\nddd eee\n\nfff")

    def test_inner_newlines_collapse(self):
        self.assertEqual(wrap.wrap("aa\nbb\ncc", 20), "aa bb cc")

    def test_long_words(self):
        self.assertEqual(wrap.wrap("abcdefghij", 4), "abcd\nefgh\nij")
        self.assertEqual(wrap.wrap("x abcdefghij y", 4), "x\nabcd\nefgh\nij y")

    def test_blank_and_width(self):
        self.assertEqual(wrap.wrap("  \n\n ", 10), "")
        with self.assertRaises(ValueError):
            wrap.wrap("x", 0)

    def test_fill_helper(self):
        self.assertEqual(wrap.fill("aaa bbb ccc", 9, "> "), "> aaa bbb\n> ccc")


class TestBytesize(unittest.TestCase):
    def test_table(self):
        cases = {
            0: "0 B", 1: "1 B", 1023: "1023 B", 1024: "1 KiB", 1536: "1.5 KiB",
            1024 * 1024: "1 MiB", 1048575: "1 MiB", 1024 ** 3: "1 GiB", 1024 ** 4: "1 TiB",
            1024 ** 5: "1024 TiB", 1100: "1.1 KiB", -1536: "-1.5 KiB", -5: "-5 B",
        }
        for n, want in cases.items():
            self.assertEqual(bytesize.human_size(n), want, n)

    def test_types(self):
        for bad in (True, "12", None):
            with self.assertRaises(TypeError):
                bytesize.human_size(bad)

    def test_float_input(self):
        self.assertEqual(bytesize.human_size(2048.0), "2 KiB")


class TestCsvline(unittest.TestCase):
    def test_quotes(self):
        self.assertEqual(csvline.split_csv_line('a,"b,c",d'), ["a", "b,c", "d"])
        self.assertEqual(csvline.split_csv_line('"he said ""hi"""'), ['he said "hi"'])
        self.assertEqual(csvline.split_csv_line('"",x'), ["", "x"])

    def test_plain_edges(self):
        self.assertEqual(csvline.split_csv_line(""), [""])
        self.assertEqual(csvline.split_csv_line("a,,b"), ["a", "", "b"])
        self.assertEqual(csvline.split_csv_line("a,"), ["a", ""])
        self.assertEqual(csvline.split_csv_line(' a , b'), [" a ", " b"])
        self.assertEqual(csvline.split_csv_line('ab"c,d'), ['ab"c', "d"])

    def test_errors(self):
        for line in ['"abc', 'a,"b', '"a"x,b', '"a""']:
            with self.assertRaises(ValueError, msg=line):
                csvline.split_csv_line(line)

    def test_roundtrip_helper(self):
        self.assertTrue(csvline.roundtrip_ok(["a", "b,c", 'd"e', ""]))
        self.assertEqual(csvline.column(['x,"y,z"', "1,2"], 1), ["y,z", "2"])


class TestVersions(unittest.TestCase):
    def test_numeric(self):
        self.assertEqual(versions.compare_versions("1.10", "1.9"), 1)
        self.assertEqual(versions.compare_versions("1.2", "1.10"), -1)
        self.assertEqual(versions.compare_versions("10.0.0", "9.99.99"), 1)

    def test_missing_segments_and_v(self):
        self.assertEqual(versions.compare_versions("1.0", "1.0.0"), 0)
        self.assertEqual(versions.compare_versions("v2.1", "2.1"), 0)
        self.assertEqual(versions.compare_versions("1", "1.0.1"), -1)

    def test_prerelease(self):
        self.assertEqual(versions.compare_versions("1.0-rc1", "1.0"), -1)
        self.assertEqual(versions.compare_versions("1.0", "1.0-rc1"), 1)
        self.assertEqual(versions.compare_versions("1.0-beta", "1.0-rc1"), -1)
        self.assertEqual(versions.compare_versions("1.0-rc1", "1.0-rc1"), 0)
        self.assertEqual(versions.compare_versions("1.1-rc1", "1.0"), 1)

    def test_bad_segment(self):
        with self.assertRaises(ValueError):
            versions.compare_versions("1.x", "1.0")

    def test_helpers(self):
        self.assertEqual(versions.sort_versions(["1.10", "1.9", "1.9-rc1", "1.2"]), ["1.2", "1.9-rc1", "1.9", "1.10"])
        self.assertEqual(versions.newest(["1.9", "1.10", "1.8"]), "1.10")
        self.assertTrue(versions.satisfies("1.10", "1.9"))
        self.assertFalse(versions.satisfies("1.9-rc1", "1.9"))


class TestRetry(unittest.TestCase):
    def test_cap(self):
        self.assertEqual(retry.backoff_delays(5, base=1, factor=2, cap=5), [1, 2, 4, 5, 5])
        self.assertEqual(retry.backoff_delays(0), [])
        self.assertEqual(retry.backoff_delays(3, base=1, factor=3), [1, 3, 9])

    def test_jitter(self):
        values = iter([0.0, 0.5, 0.99])
        got = retry.backoff_delays(3, base=10, factor=1, jitter=0.5, rng=lambda: next(values))
        self.assertEqual(got, [10.0, 7.5, 10 * (1 - 0.5 * 0.99)])

    def test_cap_before_jitter(self):
        got = retry.backoff_delays(2, base=100, factor=1, cap=10, jitter=1.0, rng=lambda: 0.5)
        self.assertEqual(got, [5.0, 5.0])

    def test_rng_not_called_without_jitter(self):
        def boom():
            raise AssertionError("rng called")

        self.assertEqual(retry.backoff_delays(2, base=1, factor=1, rng=boom), [1, 1])

    def test_errors(self):
        for kwargs in ({"attempts": -1}, {"attempts": 2, "jitter": 1.5}, {"attempts": 2, "jitter": -0.1},
                       {"attempts": 2, "jitter": 0.5}):
            with self.assertRaises(ValueError, msg=repr(kwargs)):
                retry.backoff_delays(**kwargs)

    def test_schedule_helper(self):
        self.assertEqual(retry.schedule(3, base=1, factor=2, cap=3), [1, 3, 6])


class TestPaths(unittest.TestCase):
    def test_table(self):
        cases = {
            "a/./b": "a/b", "a/b/../c": "a/c", "/a/b/": "/a/b", "/": "/", "//": "/",
            "/../a": "/a", "/a/../../b": "/b", "../a": "../a", "a/../../b": "../b",
            "": ".", ".": ".", "a/..": ".", "./": ".", "../..": "../..", "a//b/./c/..": "a/b",
        }
        for path, want in cases.items():
            self.assertEqual(paths.normalize(path), want, path)

    def test_helpers(self):
        self.assertEqual(paths.join("/srv", "data/../logs", "x.txt"), "/srv/logs/x.txt")
        self.assertEqual(paths.join("/srv", "/etc", "passwd"), "/etc/passwd")
        self.assertTrue(paths.is_inside("/srv", "/srv/a/../b"))
        self.assertFalse(paths.is_inside("/srv", "/srv/../etc"))
        self.assertEqual(paths.split("/a/b/c/"), ("/a/b", "c"))
        self.assertEqual(paths.basename("a/b/../c.txt"), "c.txt")


class TestRanges(unittest.TestCase):
    def test_adjacent_and_overlap(self):
        self.assertEqual(ranges.merge_ranges([(4, 6), (1, 3)]), [(1, 6)])
        self.assertEqual(ranges.merge_ranges([(1, 3), (3, 5)]), [(1, 5)])
        self.assertEqual(ranges.merge_ranges([(1, 3), (5, 6)]), [(1, 3), (5, 6)])

    def test_reversed_pairs(self):
        self.assertEqual(ranges.merge_ranges([(9, 7), (1, 2), (3, 3)]), [(1, 3), (7, 9)])

    def test_nested_and_empty(self):
        self.assertEqual(ranges.merge_ranges([(1, 10), (2, 3), (4, 5)]), [(1, 10)])
        self.assertEqual(ranges.merge_ranges([]), [])

    def test_returns_tuples_and_keeps_input(self):
        data = [(5, 1), (7, 9)]
        out = ranges.merge_ranges(data)
        self.assertEqual(data, [(5, 1), (7, 9)])
        self.assertTrue(all(isinstance(r, tuple) for r in out))
        self.assertEqual(out, [(1, 5), (7, 9)])

    def test_helpers(self):
        self.assertEqual(ranges.total_length([(1, 3), (4, 6), (10, 10)]), 7)
        self.assertEqual(ranges.gaps([(3, 4), (8, 9)], 1, 10), [(1, 2), (5, 7), (10, 10)])


class TestTemplate(unittest.TestCase):
    def test_dotted(self):
        class User:
            nick = "bo"

        ctx = {"user": {"name": "Ann", "tags": {"first": "x"}}, "obj": User(), "n": 3}
        self.assertEqual(template.render("{{ user.name }}/{{user.tags.first}}/{{ obj.nick }}/{{n}}", ctx), "Ann/x/bo/3")

    def test_default_filter(self):
        self.assertEqual(template.render('{{ nick|default:"anon" }}', {}), "anon")
        self.assertEqual(template.render("{{ nick | default:'anon' }}", {}), "anon")
        self.assertEqual(template.render('{{ nick|default:"anon" }}', {"nick": "bo"}), "bo")
        self.assertEqual(template.render('{{ a.b|default:"z" }}', {"a": {}}), "z")

    def test_default_not_used_for_falsy_values(self):
        self.assertEqual(template.render('{{ n|default:"x" }}', {"n": 0}), "0")
        self.assertEqual(template.render('{{ n|default:"x" }}', {"n": ""}), "")

    def test_missing_raises(self):
        with self.assertRaises(KeyError) as ctx:
            template.render("hi {{ user.name }}", {"user": {}})
        self.assertEqual(ctx.exception.args[0], "user.name")
        with self.assertRaises(KeyError):
            template.render("{{ nope }}", {})

    def test_escape(self):
        self.assertEqual(template.render("a \\{{ x }} b", {}), "a {{ x }} b")
        self.assertEqual(template.render("\\{{ x }}{{ x }}", {"x": 1}), "{{ x }}1")

    def test_helpers(self):
        self.assertEqual(template.variables("{{ a }} {{ b.c }} {{ a }} \\{{ z }}"), ["a", "b.c"])
        self.assertEqual(template.missing("{{ a }} {{ b.c }}", {"a": 1}), ["b.c"])


if __name__ == "__main__":
    unittest.main()
