"""JSON wire values contain decimal strings rather than binary floats."""

from typing import TypeAlias

JSONValue: TypeAlias = str | int | bool | None | list["JSONValue"] | dict[str, "JSONValue"]
JSONObject: TypeAlias = dict[str, JSONValue]
