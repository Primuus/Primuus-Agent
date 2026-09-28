# Preserve marker quote semantics on serialization

Serializing a marker value that contains a double quote currently changes its meaning. Choose a delimiter that preserves an embedded quote when converting a `Marker` or `Requirement` back to text. A value containing both quote delimiters cannot be serialized and should raise `ValueError`.

Repository check: `PYTHONPATH=src python -m pytest -q tests/test_markers.py tests/test_requirements.py`
