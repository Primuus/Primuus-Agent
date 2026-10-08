"""Validate the plan shared by initialization and the update_plan tool."""

import json
from typing import Any


def validate_plan(items: Any) -> None:
    if type(items) is not list or not items or any(
        type(item) is not dict
        or not {"description", "status"} <= set(item) <= {
            "description", "status", "files", "hypothesis", "next_action"
        }
        or type(item["description"]) is not str
        or item["status"] not in ("pending", "in_progress", "completed")
        or any(type(item[key]) is not str for key in ("hypothesis", "next_action") if key in item)
        or "files" in item and (type(item["files"]) is not list
                                or any(type(path) is not str for path in item["files"]))
        for item in items
    ):
        raise ValueError("Invalid plan fields")
    active = sum(item["status"] == "in_progress" for item in items)
    if active > 1 or any(item["status"] == "pending" for item in items) and active != 1:
        raise ValueError("Select one in_progress requirement while work remains")


def parse_initial_plan(content: str) -> list[dict[str, Any]]:
    data = json.loads(content)
    if type(data) is not dict or set(data) != {"items"}:
        raise ValueError("Return a JSON object containing only items")
    items = data["items"]
    validate_plan(items)
    if (not items or items[0]["status"] != "in_progress"
        or any(item["status"] != "pending" for item in items[1:])
        or any(set(item) != {"description", "status", "files", "hypothesis", "next_action"} for item in items)):
        raise ValueError("Initialize the first requirement as in_progress and all others as pending, with all five fields")
    return items
