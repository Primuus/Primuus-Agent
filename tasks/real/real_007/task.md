# Handle zero interquartile range in histograms

`boltons.statsutils.Stats` divides by zero when selecting histogram bins for constant data or data whose interquartile range is zero. These datasets should produce a usable histogram with one bin containing every observation.

Repository check: `python -m pytest -q tests/test_statsutils.py`
