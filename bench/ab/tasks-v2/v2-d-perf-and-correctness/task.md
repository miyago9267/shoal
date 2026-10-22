`logpipe` is slow on big logs: a day of traffic from our larger customers takes minutes, and it
should take seconds at most. Also, the totals look off sometimes when we compare them against the
proxy's own request counters. Please make it fast and make the numbers right. The report format and
`logpipe.pipeline.run` should stay as documented in the README.
