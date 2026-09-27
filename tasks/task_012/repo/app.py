from exporter import render
from settings import load_settings


def export_customers(rows, config_path):
    settings = load_settings(config_path)
    return render(rows, {**settings, "include_header": False})
