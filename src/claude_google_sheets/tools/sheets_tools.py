"""Google Sheets API tools for data manipulation and sheet management."""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from googleapiclient.errors import HttpError
from mcp.types import TextContent, Tool

from ..auth.oauth_manager import GoogleSheetsAuth
from ..core.exceptions import InvalidRangeError, SheetsAPIError
from ..core.tool_handler import SheetsToolHandler

logger = logging.getLogger(__name__)


class ReadRangeHandler(SheetsToolHandler):
    """Handler for reading data from spreadsheet ranges."""

    def __init__(self, auth: GoogleSheetsAuth) -> None:
        super().__init__(
            name="read_range",
            description="Read data from a specified range in a Google Sheet",
        )
        self.auth = auth

    def get_tool_definition(self) -> Tool:
        return Tool(
            name=self.name,
            description=self.description,
            inputSchema={
                "type": "object",
                "properties": {
                    "spreadsheet_id": {
                        "type": "string",
                        "description": "The ID of the spreadsheet",
                    },
                    "range": {
                        "type": "string",
                        "description": "The A1 notation range to read (e.g., 'Sheet1!A1:C10' or 'A1:C10')",
                    },
                    "value_render_option": {
                        "type": "string",
                        "description": "How values should be represented",
                        "enum": ["FORMATTED_VALUE", "UNFORMATTED_VALUE", "FORMULA"],
                        "default": "FORMATTED_VALUE",
                    },
                    "date_time_render_option": {
                        "type": "string",
                        "description": "How dates should be represented",
                        "enum": ["SERIAL_NUMBER", "FORMATTED_STRING"],
                        "default": "FORMATTED_STRING",
                    },
                },
                "required": ["spreadsheet_id", "range"],
            },
        )

    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the read range operation."""
        try:
            self.validate_arguments(arguments, ["spreadsheet_id", "range"])

            spreadsheet_id = arguments["spreadsheet_id"]
            range_name = arguments["range"]
            value_render_option = arguments.get(
                "value_render_option", "FORMATTED_VALUE"
            )
            date_time_render_option = arguments.get(
                "date_time_render_option", "FORMATTED_STRING"
            )

            sheets_service = self.auth.get_sheets_service()

            result = (
                sheets_service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                    valueRenderOption=value_render_option,
                    dateTimeRenderOption=date_time_render_option,
                )
                .execute()
            )

            values = result.get("values", [])

            if not values:
                return self.format_success_response(
                    "No data found in the specified range."
                )

            response_data = {
                "range": result.get("range"),
                "major_dimension": result.get("majorDimension", "ROWS"),
                "row_count": len(values),
                "column_count": max(len(row) for row in values) if values else 0,
                "values": values,
            }

            return self.format_success_response(
                json.dumps(response_data, indent=2),
                f"Read {len(values)} rows from range {range_name}",
            )

        except HttpError as e:
            if e.resp.status == 400:
                raise InvalidRangeError(f"Invalid range: {range_name}")
            elif e.resp.status == 404:
                raise SheetsAPIError("Spreadsheet not found", 404)
            else:
                raise SheetsAPIError(f"Sheets API error: {e.reason}", e.resp.status)
        except Exception as e:
            return self.format_error_response(e)


class WriteRangeHandler(SheetsToolHandler):
    """Handler for writing data to spreadsheet ranges."""

    def __init__(self, auth: GoogleSheetsAuth) -> None:
        super().__init__(
            name="write_range",
            description="Write data to a specified range in a Google Sheet",
        )
        self.auth = auth

    def get_tool_definition(self) -> Tool:
        return Tool(
            name=self.name,
            description=self.description,
            inputSchema={
                "type": "object",
                "properties": {
                    "spreadsheet_id": {
                        "type": "string",
                        "description": "The ID of the spreadsheet",
                    },
                    "range": {
                        "type": "string",
                        "description": "The A1 notation range to write to (e.g., 'Sheet1!A1:C10')",
                    },
                    "values": {
                        "type": "array",
                        "description": "2D array of values to write",
                        "items": {"type": "array", "items": {"type": "string"}},
                    },
                    "value_input_option": {
                        "type": "string",
                        "description": "How input data should be interpreted",
                        "enum": ["RAW", "USER_ENTERED"],
                        "default": "USER_ENTERED",
                    },
                },
                "required": ["spreadsheet_id", "range", "values"],
            },
        )

    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the write range operation."""
        try:
            self.validate_arguments(arguments, ["spreadsheet_id", "range", "values"])

            spreadsheet_id = arguments["spreadsheet_id"]
            range_name = arguments["range"]
            values = arguments["values"]
            value_input_option = arguments.get("value_input_option", "USER_ENTERED")

            sheets_service = self.auth.get_sheets_service()

            body = {"values": values}

            result = (
                sheets_service.spreadsheets()
                .values()
                .update(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                    valueInputOption=value_input_option,
                    body=body,
                )
                .execute()
            )

            response_data = {
                "updated_range": result.get("updatedRange"),
                "updated_rows": result.get("updatedRows"),
                "updated_columns": result.get("updatedColumns"),
                "updated_cells": result.get("updatedCells"),
            }

            return self.format_success_response(
                json.dumps(response_data, indent=2),
                f"Successfully updated {result.get('updatedCells', 0)} cells in range {range_name}",
            )

        except HttpError as e:
            if e.resp.status == 400:
                raise InvalidRangeError(f"Invalid range or data: {range_name}")
            elif e.resp.status == 404:
                raise SheetsAPIError("Spreadsheet not found", 404)
            else:
                raise SheetsAPIError(f"Sheets API error: {e.reason}", e.resp.status)
        except Exception as e:
            return self.format_error_response(e)


class AppendDataHandler(SheetsToolHandler):
    """Handler for appending data to a spreadsheet."""

    def __init__(self, auth: GoogleSheetsAuth) -> None:
        super().__init__(
            name="append_data",
            description="Append rows of data to the end of a Google Sheet",
        )
        self.auth = auth

    def get_tool_definition(self) -> Tool:
        return Tool(
            name=self.name,
            description=self.description,
            inputSchema={
                "type": "object",
                "properties": {
                    "spreadsheet_id": {
                        "type": "string",
                        "description": "The ID of the spreadsheet",
                    },
                    "range": {
                        "type": "string",
                        "description": "The A1 notation range indicating the sheet and columns (e.g., 'Sheet1!A:C')",
                    },
                    "values": {
                        "type": "array",
                        "description": "2D array of values to append",
                        "items": {"type": "array", "items": {"type": "string"}},
                    },
                    "value_input_option": {
                        "type": "string",
                        "description": "How input data should be interpreted",
                        "enum": ["RAW", "USER_ENTERED"],
                        "default": "USER_ENTERED",
                    },
                    "insert_data_option": {
                        "type": "string",
                        "description": "How data should be inserted",
                        "enum": ["OVERWRITE", "INSERT_ROWS"],
                        "default": "INSERT_ROWS",
                    },
                },
                "required": ["spreadsheet_id", "range", "values"],
            },
        )

    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the append data operation."""
        try:
            self.validate_arguments(arguments, ["spreadsheet_id", "range", "values"])

            spreadsheet_id = arguments["spreadsheet_id"]
            range_name = arguments["range"]
            values = arguments["values"]
            value_input_option = arguments.get("value_input_option", "USER_ENTERED")
            insert_data_option = arguments.get("insert_data_option", "INSERT_ROWS")

            sheets_service = self.auth.get_sheets_service()

            body = {"values": values}

            result = (
                sheets_service.spreadsheets()
                .values()
                .append(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                    valueInputOption=value_input_option,
                    insertDataOption=insert_data_option,
                    body=body,
                )
                .execute()
            )

            response_data = {
                "spreadsheet_id": result.get("spreadsheetId"),
                "table_range": result.get("tableRange"),
                "updates": result.get("updates", {}),
            }

            return self.format_success_response(
                json.dumps(response_data, indent=2),
                f"Successfully appended {len(values)} rows to {range_name}",
            )

        except HttpError as e:
            if e.resp.status == 400:
                raise InvalidRangeError(f"Invalid range or data: {range_name}")
            elif e.resp.status == 404:
                raise SheetsAPIError("Spreadsheet not found", 404)
            else:
                raise SheetsAPIError(f"Sheets API error: {e.reason}", e.resp.status)
        except Exception as e:
            return self.format_error_response(e)


class ClearRangeHandler(SheetsToolHandler):
    """Handler for clearing data from spreadsheet ranges."""

    def __init__(self, auth: GoogleSheetsAuth) -> None:
        super().__init__(
            name="clear_range",
            description="Clear data from a specified range in a Google Sheet",
        )
        self.auth = auth

    def get_tool_definition(self) -> Tool:
        return Tool(
            name=self.name,
            description=self.description,
            inputSchema={
                "type": "object",
                "properties": {
                    "spreadsheet_id": {
                        "type": "string",
                        "description": "The ID of the spreadsheet",
                    },
                    "range": {
                        "type": "string",
                        "description": "The A1 notation range to clear (e.g., 'Sheet1!A1:C10')",
                    },
                },
                "required": ["spreadsheet_id", "range"],
            },
        )

    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the clear range operation."""
        try:
            self.validate_arguments(arguments, ["spreadsheet_id", "range"])

            spreadsheet_id = arguments["spreadsheet_id"]
            range_name = arguments["range"]

            sheets_service = self.auth.get_sheets_service()

            result = (
                sheets_service.spreadsheets()
                .values()
                .clear(spreadsheetId=spreadsheet_id, range=range_name, body={})
                .execute()
            )

            response_data = {
                "cleared_range": result.get("clearedRange"),
                "spreadsheet_id": result.get("spreadsheetId"),
            }

            return self.format_success_response(
                json.dumps(response_data, indent=2),
                f"Successfully cleared range {range_name}",
            )

        except HttpError as e:
            if e.resp.status == 400:
                raise InvalidRangeError(f"Invalid range: {range_name}")
            elif e.resp.status == 404:
                raise SheetsAPIError("Spreadsheet not found", 404)
            else:
                raise SheetsAPIError(f"Sheets API error: {e.reason}", e.resp.status)
        except Exception as e:
            return self.format_error_response(e)


def _column_letters_to_index(letters: str) -> int:
    """Convert spreadsheet column letters (A, B, ..., AA) to a 0-based index."""
    index = 0
    for char in letters.upper():
        if not char.isalpha():
            raise InvalidRangeError(f"Invalid column reference: {letters}")
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def _parse_a1_range(a1_range: str) -> Dict[str, Any]:
    """Parse an A1 notation range into a sheet title and grid boundaries.

    Row and column bounds are omitted when the range leaves them open, which
    is what makes a filter cover every current and future row (e.g. 'A:C').
    """
    sheet_title: Optional[str] = None
    cell_part = a1_range.strip()

    if "!" in cell_part:
        sheet_title, cell_part = cell_part.rsplit("!", 1)
        sheet_title = sheet_title.strip().strip("'").replace("''", "'")

    grid: Dict[str, Any] = {}

    if not cell_part:
        return {"sheet_title": sheet_title, "grid": grid}

    endpoints = cell_part.split(":")
    if len(endpoints) > 2:
        raise InvalidRangeError(f"Invalid range: {a1_range}")

    parsed = []
    for endpoint in endpoints:
        match = re.fullmatch(r"([A-Za-z]*)(\d*)", endpoint.strip())
        if not match or endpoint.strip() == "":
            raise InvalidRangeError(f"Invalid range: {a1_range}")
        column, row = match.groups()
        parsed.append(
            (
                _column_letters_to_index(column) if column else None,
                int(row) - 1 if row else None,
            )
        )

    start_column, start_row = parsed[0]
    end_column, end_row = parsed[1] if len(parsed) == 2 else parsed[0]

    if start_column is not None:
        grid["startColumnIndex"] = start_column
    if start_row is not None:
        grid["startRowIndex"] = start_row
    if end_column is not None:
        grid["endColumnIndex"] = end_column + 1
    if end_row is not None:
        grid["endRowIndex"] = end_row + 1

    return {"sheet_title": sheet_title, "grid": grid}


class SetFilterRangeHandler(SheetsToolHandler):
    """Handler for setting the basic filter range on a sheet."""

    def __init__(self, auth: GoogleSheetsAuth) -> None:
        super().__init__(
            name="set_filter_range",
            description=(
                "Set the basic filter range on a sheet so newly added rows are "
                "included. Use an open-ended range such as 'Sheet1!A:C' to cover "
                "every future row."
            ),
        )
        self.auth = auth

    def get_tool_definition(self) -> Tool:
        return Tool(
            name=self.name,
            description=self.description,
            inputSchema={
                "type": "object",
                "properties": {
                    "spreadsheet_id": {
                        "type": "string",
                        "description": "The ID of the spreadsheet",
                    },
                    "range": {
                        "type": "string",
                        "description": (
                            "The A1 notation range the filter should cover (e.g., "
                            "'Sheet1!A:C'). Omit the row numbers so the filter "
                            "keeps covering rows added later. Defaults to all "
                            "columns of the first sheet."
                        ),
                    },
                    "preserve_criteria": {
                        "type": "boolean",
                        "description": (
                            "Carry the existing filter's criteria and sort order "
                            "over to the new range (default: true)"
                        ),
                        "default": True,
                    },
                },
                "required": ["spreadsheet_id"],
            },
        )

    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the set filter range operation."""
        range_name = arguments.get("range", "")
        try:
            self.validate_arguments(arguments, ["spreadsheet_id"])

            spreadsheet_id = arguments["spreadsheet_id"]
            preserve_criteria = arguments.get("preserve_criteria", True)

            parsed = _parse_a1_range(range_name) if range_name else {
                "sheet_title": None,
                "grid": {},
            }

            sheets_service = self.auth.get_sheets_service()
            metadata = (
                sheets_service.spreadsheets()
                .get(
                    spreadsheetId=spreadsheet_id,
                    fields="sheets(properties(sheetId,title),basicFilter)",
                )
                .execute()
            )

            sheets = metadata.get("sheets", [])
            if not sheets:
                raise SheetsAPIError("Spreadsheet contains no sheets", 404)

            target_title = parsed["sheet_title"]
            if target_title:
                target = next(
                    (
                        sheet
                        for sheet in sheets
                        if sheet["properties"]["title"] == target_title
                    ),
                    None,
                )
                if target is None:
                    raise SheetsAPIError(f"Sheet not found: {target_title}", 404)
            else:
                target = sheets[0]

            grid_range = dict(parsed["grid"])
            grid_range["sheetId"] = target["properties"]["sheetId"]
            grid_range.setdefault("startRowIndex", 0)
            grid_range.setdefault("startColumnIndex", 0)

            filter_spec: Dict[str, Any] = {"range": grid_range}

            existing_filter = target.get("basicFilter") or {}
            carried_over = False
            if preserve_criteria and existing_filter:
                existing_range = existing_filter.get("range", {})
                same_start_column = existing_range.get(
                    "startColumnIndex", 0
                ) == grid_range.get("startColumnIndex", 0)
                # Criteria are keyed by column offset from the filter's first
                # column, so they only transfer when that column is unchanged.
                if same_start_column:
                    for key in ("criteria", "filterSpecs", "sortSpecs"):
                        if existing_filter.get(key):
                            filter_spec[key] = existing_filter[key]
                            carried_over = True

            sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": [{"setBasicFilter": {"filter": filter_spec}}]},
            ).execute()

            response_data = {
                "spreadsheet_id": spreadsheet_id,
                "sheet": target["properties"]["title"],
                "filter_range": grid_range,
                "criteria_preserved": carried_over,
                "covers_new_rows": "endRowIndex" not in grid_range,
            }

            return self.format_success_response(
                json.dumps(response_data, indent=2),
                f"Filter set on {target['properties']['title']}"
                f"{' (existing criteria kept)' if carried_over else ''}",
            )

        except HttpError as e:
            if e.resp.status == 400:
                raise InvalidRangeError(f"Invalid range: {range_name}")
            elif e.resp.status == 404:
                raise SheetsAPIError("Spreadsheet not found", 404)
            else:
                raise SheetsAPIError(f"Sheets API error: {e.reason}", e.resp.status)
        except Exception as e:
            return self.format_error_response(e)

# Registry of all sheets tool handlers
SHEETS_HANDLERS = [
    ReadRangeHandler,
    WriteRangeHandler,
    AppendDataHandler,
    ClearRangeHandler,
    SetFilterRangeHandler,
]
