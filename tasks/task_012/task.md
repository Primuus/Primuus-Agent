# Respect export configuration

`app.export_customers(rows, config_path)` must read the JSON configuration and produce CSV text with its configured delimiter, header choice, and column order. Values containing a delimiter or quote must use ordinary CSV escaping. Repair the existing settings, exporter, and app wiring. Keep the public function signature.
