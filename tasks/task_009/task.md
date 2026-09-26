# Parse key-value configuration

Fix `config_parser.parse(text)` to read `KEY=VALUE` lines into a dictionary. Ignore empty lines and lines beginning with `#`, trim whitespace around keys and values, and keep any additional `=` characters inside a value.
