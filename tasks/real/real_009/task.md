# Repair spooled stream write and text seek behavior

`boltons.ioutils` spooled byte and text streams should follow the standard write contract: return the number of bytes or characters written. Byte streams must accept bytes-like objects and work inside `io.BufferedWriter`. Text streams must seek backward relative to the current character position even with multibyte UTF-8 characters, and reject a negative destination without moving the cursor. Check both in-memory and rolled-over streams.

Repository check: `python -m pytest -q tests/test_ioutils.py`
