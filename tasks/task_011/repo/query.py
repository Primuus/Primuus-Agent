from records import normalize_status


def matching(records, status):
    expected = normalize_status(status)
    return [record for record in records if normalize_status(record["status"]) == expected]


def page(records, number, size):
    start = number * size
    return records[start:start + size]
