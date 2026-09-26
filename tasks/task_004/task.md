# Correct JSON setting types

In `settings.json`, keep the host and configured port number, but make `port` a JSON number and `debug` a JSON boolean set to false. The current string values break consumers of this configuration.
