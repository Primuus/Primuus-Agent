# Fix intword rounding carry at large magnitudes

`humanize.intword` can display a value just below the next named power as `1000.0` of the lower unit. When formatting rounds to the next named unit, carry the result to that unit. Preserve the documented gap between decillion and googol.

Repository check: `PYTHONPATH=src python -m pytest -q tests/test_number.py`
