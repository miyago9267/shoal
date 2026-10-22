import unittest

from utilkit import bytesize, csvline, durations, paths, ranges, retry, slug, template, versions, wrap


class SlugHelpers(unittest.TestCase):
    def test_common_prefix(self):
        self.assertEqual(slug.common_prefix(["a-b-c", "a-b-d", "a-b"]), "a-b")
        self.assertEqual(slug.common_prefix(["a", "b"]), "")
        self.assertEqual(slug.common_prefix([]), "")

    def test_words(self):
        self.assertEqual(slug.words("a-b"), ["a", "b"])
        self.assertEqual(slug.words(""), [])
        self.assertEqual(slug.join_words(["a", "", "b"]), "a-b")
        self.assertEqual(slug.with_suffix("a", "2"), "a-2")


class DurationHelpers(unittest.TestCase):
    def test_clamp_and_parts(self):
        self.assertEqual(durations.clamp(50, 0, 10), 10)
        self.assertEqual(durations.clamp(-5, 0, 10), 0)
        with self.assertRaises(ValueError):
            durations.clamp(1, 5, 2)
        self.assertEqual(durations.split_parts(3723), (1, 2, 3))
        self.assertEqual(durations.clock(3723), "1:02:03")

    def test_ratio(self):
        self.assertEqual(durations.ratio(1, 4), 0.25)
        with self.assertRaises(ValueError):
            durations.ratio(1, 0)


class WrapHelpers(unittest.TestCase):
    def test_center_and_longest(self):
        self.assertEqual(wrap.center("ab", 6), "  ab")
        self.assertEqual(wrap.center("abcdef", 4), "abcdef")
        self.assertEqual(wrap.longest_line("a\nbbb\ncc"), 3)

    def test_dedent_and_truncate(self):
        self.assertEqual(wrap.dedent_lines(["  a", "", "    b"]), ["a", "", "  b"])
        self.assertEqual(wrap.truncate("abcdefgh", 6), "abc...")
        self.assertEqual(wrap.truncate("abc", 6), "abc")
        with self.assertRaises(ValueError):
            wrap.truncate("abc", 2)


class BytesizeHelpers(unittest.TestCase):
    def test_percent_and_split(self):
        self.assertEqual(bytesize.percent(1, 4), 25)
        self.assertEqual(bytesize.percent(1, 0), 0)
        self.assertEqual(bytesize.split_evenly(10, 3), [4, 3, 3])
        with self.assertRaises(ValueError):
            bytesize.split_evenly(10, 0)

    def test_units_for(self):
        self.assertEqual(bytesize.units_for(10), 0)
        self.assertEqual(bytesize.units_for(5000), 1)
        self.assertTrue(bytesize.fits(5, 5))


class CsvHelpers(unittest.TestCase):
    def test_pad_and_dict(self):
        self.assertEqual(csvline.pad(["a"], 3), ["a", "", ""])
        with self.assertRaises(ValueError):
            csvline.pad(["a", "b"], 1)
        self.assertEqual(csvline.to_dict(["k", "v"], ["1", "2"]), {"k": "1", "v": "2"})
        with self.assertRaises(ValueError):
            csvline.to_dict(["k"], [])
        self.assertEqual(csvline.strip_all([" a ", "b "]), ["a", "b"])


class VersionHelpers(unittest.TestCase):
    def test_bump(self):
        self.assertEqual(versions.bump("1.2.3"), "1.2.4")
        self.assertEqual(versions.bump("1.2.3", "minor"), "1.3.0")
        self.assertEqual(versions.bump("1.2.3", "major"), "2.0.0")
        self.assertEqual(versions.bump("1.2"), "1.2.1")

    def test_major_and_pre(self):
        self.assertEqual(versions.major("v7.1"), 7)
        self.assertTrue(versions.is_prerelease("1.0-rc1"))
        self.assertFalse(versions.is_prerelease("1.0"))


class RetryHelpers(unittest.TestCase):
    def test_describe_and_attempts(self):
        self.assertEqual(retry.describe([1, 2, 4]), "3 retries, 7.0s total")
        self.assertEqual(retry.attempts_within(7, base=1, factor=2), 3)
        self.assertEqual(retry.constant(3, 0.5), [0.5, 0.5, 0.5])


class PathHelpers(unittest.TestCase):
    def test_extension(self):
        self.assertEqual(paths.extension("a/b.tar.gz"), "gz")
        self.assertEqual(paths.extension("a/.bashrc"), "")
        self.assertEqual(paths.extension("a/noext"), "")

    def test_with_extension(self):
        self.assertEqual(paths.with_extension("a/b.txt", "md"), "a/b.md")
        self.assertEqual(paths.with_extension("b.txt", "md"), "b.md")

    def test_parents(self):
        self.assertEqual(paths.parents("/a/b/c"), ["/a/b", "/a", "/"])


class RangeHelpers(unittest.TestCase):
    def test_overlaps_span_clip(self):
        self.assertTrue(ranges.overlaps((1, 3), (3, 5)))
        self.assertFalse(ranges.overlaps((1, 2), (3, 5)))
        self.assertEqual(ranges.span([(5, 1), (7, 9)]), (1, 9))
        with self.assertRaises(ValueError):
            ranges.span([])
        self.assertEqual(ranges.clip([(0, 5), (8, 20), (30, 40)], 2, 10), [(2, 5), (8, 10)])


class TemplateHelpers(unittest.TestCase):
    def test_render_many(self):
        self.assertEqual(template.render_many("{{ n }}", [{"n": 1}, {"n": 2}]), ["1", "2"])

    def test_has_variables(self):
        self.assertTrue(template.has_variables("a {{ b }}"))
        self.assertFalse(template.has_variables("plain"))
