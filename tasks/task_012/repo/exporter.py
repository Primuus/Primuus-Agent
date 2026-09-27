def render(rows, settings):
    columns = settings["columns"]
    lines = []
    if settings["include_header"]:
        lines.append(",".join(columns))
    for row in rows:
        lines.append(",".join(str(row[column]) for column in columns))
    return "\n".join(lines) + "\n"
