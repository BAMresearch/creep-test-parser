from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
from bam_masterdata.metadata.definitions import DataType
from bam_masterdata.metadata.entities import CollectionType, ObjectType
from bam_masterdata.parsing import AbstractParser

from creep_test_parser.annotations import ANNOTATIONS, FieldMapping

CATEGORY_COLUMNS = (
    "category_i",
    "category_ii",
    "category_iii",
    "category_iv",
)
ENTRY_COLUMN = "entry"
VALUE_COLUMN = "answer_options"
_MISSING = object()

DEFAULTS = {
    "bam_oe": "OE_5.2",
    "bam_location_complete": "UE_10_0_116",
    "manufacturer": "n/a",
}


class BaseFileParser(ABC):
    @abstractmethod
    def custom_parser(self) -> dict[str, pd.DataFrame]:
        """Return normalized dataframes keyed by sheet name."""
        raise NotImplementedError


class ExcelParser(BaseFileParser):
    """Read creep-test Excel files and normalize their schema rows.

    The template header is not assumed to be on a fixed row. Instead, the first
    rows of every sheet are searched for a row containing at least ``ENTRY`` and
    an answer/value column. Sheets that do not look like schema sheets are
    ignored.
    """

    HEADER_SCAN_ROWS = 50  # config value (scans first 50 rows to find the actual data)

    # After normalization, all of these become candidates for the canonical column name on the right.
    COLUMN_ALIASES = {
        "category_i": "category_i",
        "category_1": "category_i",
        "category_ii": "category_ii",
        "category_2": "category_ii",
        "category_iii": "category_iii",
        "category_3": "category_iii",
        "category_iv": "category_iv",
        "category_4": "category_iv",
        "category_iv_detailed_information": "category_iv",
        "entry": ENTRY_COLUMN,
        "answer_options": VALUE_COLUMN,
        "answer_option": VALUE_COLUMN,
        "answer": VALUE_COLUMN,
        "value": VALUE_COLUMN,
    }

    def __init__(self, filepath: str | Path):
        self.filepath = Path(filepath)

    def _find_header_row(self, df: pd.DataFrame) -> int | None:
        """
        Finds the index of the row where the template stores the data/

        Args:
            df (pd.DataFrame): The loaded pd.DataFrame.

        Returns:
            int | None: The index of the row where the data columns start in the source.
        """
        max_rows = min(len(df), self.HEADER_SCAN_ROWS)
        for row_index in range(max_rows):
            columns = {
                self._canonical_column_name(value)
                for value in df.iloc[row_index].tolist()
            }
            if ENTRY_COLUMN in columns and VALUE_COLUMN in columns:
                return row_index
        return None

    def _canonical_column_name(self, value: Any) -> str:
        """
        Given a value, returns a normalized string from the Excel source.

        Args:
            value (Any): The value to be normalized.

        Returns:
            str: The normalized string.
        """
        if value is None or pd.isna(value):
            return ""
        text = str(value).strip().casefold()
        text = re.sub(r"[^a-z0-9]+", "_", text)
        normalized = text.strip("_")
        return self.COLUMN_ALIASES.get(normalized, normalized)

    def _deduplicate_columns(self, columns: list[str]) -> list[str]:
        """
        Deduplicates columns in the pandas DataFrame.

        Args:
            columns (list[str]): The columns to be normalized.

        Returns:
            list[str]: The non-duplicated list of columns.
        """
        counts: Counter[str] = Counter()
        result: list[str] = []
        for column in columns:
            if not column:
                column = "unnamed"
            counts[column] += 1
            if counts[column] == 1:
                result.append(column)
            else:
                result.append(f"{column}_{counts[column]}")
        return result

    def custom_parser(self) -> dict[str, pd.DataFrame]:
        try:
            source = pd.read_excel(
                self.filepath,
                sheet_name=None,
                header=None,
                engine="openpyxl",
                dtype=object,
            )
        except (OSError, ValueError, ImportError) as exc:
            raise ValueError(
                f"Could not read Excel file '{self.filepath}': {exc}"
            ) from exc

        # Stores the extracted relevant columns into a dictionary whose key is the sheet name and value is the pd.DataFrame
        parsed: dict[str, pd.DataFrame] = {}
        for sheet_name, raw_df in source.items():
            if raw_df.empty:
                continue

            # Find the row index where the column data starts
            header_row = self._find_header_row(raw_df)
            if header_row is None:
                continue

            headers = [
                self._canonical_column_name(value)
                for value in raw_df.iloc[header_row].tolist()
            ]
            headers = self._deduplicate_columns(headers)

            df = raw_df.iloc[header_row + 1 :].copy()
            df.columns = headers
            # Excel row numbers are 1-based. Preserve them for diagnostics before
            # resetting the dataframe index.
            df["_excel_row"] = df.index + 1
            df = df.reset_index(drop=True)

            # Keep only rows that actually describe a schema entry.
            if ENTRY_COLUMN not in df.columns or VALUE_COLUMN not in df.columns:
                continue

            df = df[df[ENTRY_COLUMN].notna()].copy()
            if df.empty:
                continue

            parsed[sheet_name] = df

        return parsed


class CreepTestParser(AbstractParser):
    """Map creep test Excel template content into openBIS objects."""

    def __init__(self) -> None:
        self.annotation_index = self._build_annotation_index(ANNOTATIONS)

    def _normalize_label(self, value: Any) -> str | None:
        """
        Normalize labels while preserving their semantic wording. This intentionally collapses
        whitespace/newlines and ignores case so minor template formatting changes do not break
        annotation lookup.

        Args:
            value (Any): Any value to be normalized.

        Returns:
            str | None: The cleaned value.
        """
        if value is None:
            return None
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass

        text = str(value).replace("\xa0", " ")
        text = re.sub(r"\s+", " ", text).strip()
        return text.casefold() or None

    def _build_annotation_index(
        self, annotations: dict[str, Any] = ANNOTATIONS
    ) -> dict[tuple[str | None], FieldMapping | None]:
        """
        Flatten the nested ANNOTATIONS dict into normalized hierarchy tuples. Expected paths
        are CATEGORY I -> CATEGORY II -> (optional) CATEGORY III -> (optional) CATEGORY IV -> ENTRY.

        The flattened ANNOTATIONS is stored as a dictionary in whose keys are tuples containing the
        headers and value is the FieldMapping.

        Args:
            annotations (dict[str, Any]): The ANNOTATIONS dictionary to be flattened. This is
            typically defined in a separated module `annotations.py`.


        Returns:
            dict[tuple[str | None], FieldMapping | None]: The dictionary with the flattened annotations.
        """
        # Store ANNOTATIONS as tuple assigned to a FieldMapping in a global dict
        index: dict[tuple[str | None], FieldMapping | None] = {}

        def walk(node: dict | FieldMapping, path: list[str]) -> None:
            """
            Recursive walking through the annotations dictionary to flatten it.
            """
            if isinstance(node, dict):
                for key, value in node.items():
                    walk(value, [*path, key])
                return

            if len(path) not in (3, 4, 5):
                raise ValueError(
                    "Invalid ANNOTATIONS leaf path. Expected 3 levels "
                    "(CATEGORY I to II + ENTRY), 4 levels "
                    "(CATEGORY I to III + ENTRY), or 5 levels "
                    f"(CATEGORY I to IV + ENTRY), got: {len(path)}."
                )

            if len(path) == 3:
                cat_i, cat_ii, entry = path
                cat_iii = None
                cat_iv = None
            elif len(path) == 4:
                cat_i, cat_ii, cat_iii, entry = path
                cat_iv = None
            else:
                cat_i, cat_ii, cat_iii, cat_iv, entry = path

            normalized_key = tuple(
                self._normalize_label(value)
                for value in (cat_i, cat_ii, cat_iii, cat_iv, entry)
            )
            if normalized_key in index:
                raise ValueError(
                    f"Duplicate normalized ANNOTATIONS path detected: {normalized_key}"
                )
            index[normalized_key] = node

        walk(annotations, [])
        return index

    def _is_blank(self, value: Any) -> bool:
        """
        Returns a boolean depending if the `value` is blanked or not as read from the Excel.

        Args:
            value (Any): The value to be checked if it is blanked or not.

        Returns:
            bool: True if blanked, False otherwise.
        """
        if value is None:
            return True
        try:
            if pd.isna(value):
                return True
        except (TypeError, ValueError):
            pass
        if isinstance(value, str):
            return value.strip().casefold() in {"", "nan", "n/a", "not applicable"}
        return False

    def _display_path(self, row: pd.Series) -> str:
        """
        Transforms the row path into a single string for representation. The parts of the
        row values are joined separated with a "/" character.

        Args:
            row (pd.Series): The row composed of parts for categories I-IV and ENTRY.

        Returns:
            str: The full path of the row elements joined with a "/" character.
        """
        parts = []
        for column in (*CATEGORY_COLUMNS, ENTRY_COLUMN):
            value = row.get(column)
            if self._is_blank(value):
                continue
            parts.append(str(value).strip())
        return "/".join(parts)

    def get_field_mapping(self, row: pd.Series) -> FieldMapping | None | object:
        """
        Gets the FieldMapping of the element in ANNOTATIONS matching with row.

        Args:
            row (pd.Series): The row key to get the ANNOTATIONS value from.

        Returns:
            FieldMapping | None | object: The FieldMapping in the ANNOTATIONS dict.
        """
        key = tuple(
            self._normalize_label(row.get(column))
            for column in (*CATEGORY_COLUMNS, ENTRY_COLUMN)
        )
        return self.annotation_index.get(key, _MISSING)

    def get_or_create_object(
        self, object_type: type[ObjectType], objects: dict[type[ObjectType], ObjectType]
    ) -> ObjectType:
        obj = objects.get(object_type)
        if obj is None:
            obj = object_type()
            objects[object_type] = obj
        return obj

    def populate_default_properties(self, obj: ObjectType) -> None:
        # Use the concrete object type as its generated name.
        if "name" in obj._property_metadata and isinstance(
            getattr(obj, "name", None),
            type(obj._property_metadata["name"]),
        ):
            setattr(obj, "name", type(obj).__name__)  # use class name to define `name`

        for property_name, default_value in DEFAULTS.items():
            if property_name not in obj._property_metadata:
                continue

            current = getattr(obj, property_name, None)
            property_def = obj._property_metadata[property_name]

            # Property has not been populated yet.
            if current is property_def:
                setattr(obj, property_name, default_value)

    def add_objects(
        self,
        collection: CollectionType,
        objects: dict[type[ObjectType], ObjectType],
        touched_fields: dict[type[ObjectType], set[str]],
        logger,
    ) -> dict[type[ObjectType], str]:
        """
        Adds the objects to the collection if they have been populated with at least one non-empty
        property.

        Args:
            collection (CollectionType): The collection where to add the objects.
            objects (dict[type[ObjectType], ObjectType]): The dictionary of object types and object
            instances with populated metadata.
            touched_fields (dict[type[ObjectType], set[str]]): The fields populated in each object type.
            logger: The logger to log messages.

        Returns:
            dict[type[ObjectType], str]: A dictionary containing the object types associated with
            each added object ID in the collection.
        """
        object_ids: dict[type[ObjectType], str] = {}

        # Only add objects that received at least one actual value.
        for obj_type, obj in objects.items():
            if not touched_fields.get(obj_type):
                continue

            self.populate_default_properties(obj)

            try:
                object_id = collection.add(obj)
            except (TypeError, ValueError, KeyError, AttributeError) as exc:
                logger.error(
                    f"CreepTestParser: could not add {obj_type.__name__}: {exc}"
                )
                continue

            object_ids[obj_type] = object_id

        return object_ids

    def add_relationships(
        self,
        collection: CollectionType,
        objects: dict[type[ObjectType], ObjectType],
        object_ids: dict[type[ObjectType], str],
        logger,
    ) -> int:
        """
        Adds the relationships defined via `link_` properties in the objects and attach those to the collection.

        Args:
            collection (CollectionType): The collection in where to link the objects.
            objects (dict[type[ObjectType], ObjectType]): The objects being linked.
            object_ids (dict[type[ObjectType], str]): The dictionary of objects and objects id for linking.
            logger: The logger to log messages.

        Returns:
            int: The number of relationships found in totla in the collection.
        """

        def _find_link_property(parent: ObjectType, child: ObjectType) -> str | None:
            """Return the parent's `link_` property that points to the child type."""
            try:
                child_code = child.defs.code
            except Exception:
                return None

            for property_name, property_def in parent._property_metadata.items():
                if not property_name.startswith("link_"):
                    continue
                if property_def.data_type != DataType.OBJECT:
                    continue
                if property_def.object_code == child_code:
                    return property_name
            return None

        # Finding the link_ properties and appending the specific parent/child objects to `edges` list
        edges: list[tuple[type[ObjectType], type[ObjectType], str]] = []
        values = list(objects.values())

        for parent in values:
            for child in values:
                if parent is child:
                    continue
                link_property = _find_link_property(parent, child)
                if link_property is not None:
                    edges.append((type(parent), type(child), link_property))

        # Transforming `edges` into the collection relationships
        added = 0
        for parent_type, child_type, link_property in edges:
            parent_id = object_ids.get(parent_type)
            child_id = object_ids.get(child_type)
            if parent_id is None or child_id is None:
                continue

            try:
                _ = collection.add_relationship(parent=parent_id, child=child_id)
            except (TypeError, ValueError, KeyError) as exc:
                logger.error(
                    f"CreepTestParser: could not add relationship "
                    f"{parent_type.__name__}.{link_property} -> "
                    f"{child_type.__name__}: {exc}"
                )
                continue

            added += 1

        return added

    def parse(self, files: list[str], collection: CollectionType, logger) -> None:
        for filename in files:
            filepath = Path(filename)

            if filepath.suffix.casefold() != ".xlsx":
                logger.error(
                    f"CreepTestParser: unsupported file type '{filepath.suffix}' "
                    f"for '{filepath}'"
                )
                continue

            if not filepath.is_file():
                logger.error(f"CreepTestParser: file does not exist: '{filepath}'")
                continue
            try:
                sheets = ExcelParser(filepath).custom_parser()
            except Exception as exc:
                # File-level failure: continue with the next workbook. This is
                # deliberately broad because corrupt/odd Excel files can raise
                # several library-specific exception types.
                logger.exception(f"CreepTestParser: failed to read '{filepath}': {exc}")
                continue

            if not sheets:
                logger.error(
                    f"CreepTestParser: no recognizable creep-test schema sheets "
                    f"found in '{filepath}'"
                )
                continue

            # Mapping into bam-masterdata objects of each sheet in the Excel `filepath`
            objects: dict[type[ObjectType], ObjectType] = {}
            touched_fields: dict[type[ObjectType], set[str]] = defaultdict(set)
            stats = Counter()
            for sheet_name, df in sheets.items():
                logger.info(
                    f"CreepTestParser: processing '{filepath.name}' / sheet '{sheet_name}'"
                )

                # CATEGORY III and CATEGORY IV are optional and some template versions may not contain these columns
                for column in CATEGORY_COLUMNS:
                    if column not in df.columns:
                        df[column] = None

                for row_index, row in df.iterrows():
                    stats["rows"] += 1
                    source = (
                        f"'{filepath.name}', sheet '{sheet_name}', "
                        f"row {row.get('_excel_row', row_index + 1)}: "
                        f"{self._display_path(row)}"
                    )

                    # Gets the FieldMapping or assign an empty mapping object
                    mapping = self.get_field_mapping(row)
                    if mapping is _MISSING:
                        stats["unmapped"] += 1
                        logger.warning(
                            f"CreepTestParser: no annotation mapping for {source}"
                        )
                        continue
                    if mapping is None:
                        stats["ignored"] += 1
                        logger.info(
                            "CreepTestParser: ignoring row value to map into bam-masterdata objects"
                        )
                        continue

                    # Gets raw value of the specific row
                    raw_value = row.get(VALUE_COLUMN)
                    if self._is_blank(raw_value):
                        stats["blank"] += 1
                        stats["failed"] += 1
                        continue

                    obj = self.get_or_create_object(mapping.object_type, objects)
                    try:
                        value = mapping.convert(raw_value)
                    except (TypeError, ValueError, AttributeError) as exc:
                        logger.error(
                            f"CreepTestParser: conversion failed for {source}: {exc}"
                        )
                        stats["failed"] += 1
                        continue

                    if value is None:
                        stats["failed"] += 1
                        continue

                    try:
                        if mapping.merger is not None:
                            current = getattr(obj, mapping.property_map, None)
                            # Unset model properties are class-level PropertyTypeAssignment
                            # descriptors. They are not real existing values to merge.
                            if mapping.property_map in getattr(
                                obj, "_property_metadata", {}
                            ):
                                prop_def = obj._property_metadata[mapping.property_map]
                                if current is prop_def:
                                    current = None
                            value = mapping.merger(current, value)

                        setattr(obj, mapping.property_map, value)
                    except (TypeError, ValueError, KeyError, AttributeError) as exc:
                        logger.error(
                            f"CreepTestParser: assignment failed for {source} -> "
                            f"{mapping.object_type.__name__}.{mapping.property_map}: {exc}"
                        )
                        stats["failed"] += 1
                        continue

                    touched_fields[mapping.object_type].add(mapping.property_map)
                    stats["mapped"] += 1

                object_ids = self.add_objects(
                    collection=collection,
                    objects=objects,
                    touched_fields=touched_fields,
                    logger=logger,
                )
                relationship_count = self.add_relationships(
                    collection=collection,
                    objects=objects,
                    object_ids=object_ids,
                    logger=logger,
                )

                logger.info(
                    "CreepTestParser: completed "
                    f"'{filepath.name}': rows={stats['rows']}, "
                    f"mapped={stats['mapped']}, blank={stats['blank']}, "
                    f"ignored={stats['ignored']}, unmapped={stats['unmapped']}, "
                    f"failed={stats['failed']}, objects={len(object_ids)}, "
                    f"relationships={relationship_count}"
                )
