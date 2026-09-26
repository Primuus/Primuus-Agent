# Fix the zero-count error

The attached `error.log` shows a crash in `ratio.py`. Fix `ratio(total, count)` so it returns `0.0` when `count` is zero and otherwise returns `total / count`.
