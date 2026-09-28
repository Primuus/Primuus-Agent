# Repair bulk set removals and barrel list bounds

`boltons.listutils.BarrelList` should match built-in list indexing and insertion at either boundary, including after its data has split across internal sublists. Empty tail sublists must not break `pop()`. `boltons.setutils.IndexedSet` should preserve ordering and indexes after bulk difference and intersection updates; large removals should not trigger repeated full compactions.

Repository check: `python -m pytest -q tests/test_listutils.py tests/test_setutils.py`
