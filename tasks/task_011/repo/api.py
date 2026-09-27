from query import matching, page as select_page


def get_cases(records, status, page, page_size):
    found = matching(records, status)
    items = select_page(found, page, page_size)
    return {"total": len(items), "items": items}
