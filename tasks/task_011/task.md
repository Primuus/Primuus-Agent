# Repair paginated issue search

`api.get_cases(records, status, page, page_size)` returns a dictionary with `total` and `items`. Status matching is case-insensitive after trimming whitespace. Pages are numbered from 1. `total` counts every matching record before pagination, while `items` contains only the selected page. Fix the behavior across the existing modules without changing the public function signature.
