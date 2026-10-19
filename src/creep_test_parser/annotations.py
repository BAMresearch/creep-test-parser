import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from bam_masterdata.datamodel.creep_test import vocabularies
from bam_masterdata.datamodel.creep_test.object_types import (
    CreepTest,
    CreepTestChemicalCompositionMeasured,
    CreepTestChemicalCompositionNominal,
    CreepTestDataProcessingProcedures,
    CreepTestExtensionValuesContactingExtensometer,
    CreepTestExtensometerSystem,
    CreepTestLaboratoryConditions,
    CreepTestLoadDataAcquisition,
    CreepTestLoadSensor,
    CreepTestMaterialHistoryAndCondition,
    CreepTestMaterialHistoryMechanicalTestsResults,
    CreepTestMaterialHistoryNDTResults,
    CreepTestPrimaryValuesRecordedAfterEndOfTest,
    CreepTestPrimaryValuesRecordedAtTestStart,
    CreepTestPrimaryValuesRecordedDuringTestRun,
    CreepTestSecondaryElongationValues,
    CreepTestSecondaryExtensionValues,
    CreepTestSecondaryValuesRecordedDuringTestRun,
    CreepTestTemperatureDataAcquisition,
    CreepTestTemperatureMeasuringSystem,
    CreepTestTemperatureSensor,
    CreepTestTestMachine,
    CreepTestTestMachineDataAcquisition,
    CreepTestTestMachineHeatingSystem,
    CreepTestTestMachineLoadingSystem,
    CreepTestTestPiece,
)


def parse_optional_string(value: Any) -> str | None:
    if value is None:
        return None

    value = str(value).strip()

    if not value or value.lower() in {"n/a", "not applicable", "nan"}:
        return None

    return value


def parse_float(value: Any) -> float | None:
    value = parse_optional_string(value)
    return None if value is None else float(value.replace(",", "."))


def parse_int(value: Any) -> int | None:
    value = parse_optional_string(value)
    return None if value is None else int(value)


def parse_yes_no(value: Any) -> bool | None:
    value = parse_optional_string(value)

    if value is None:
        return None

    normalized = value.strip().casefold()

    if "yes" in normalized:
        return True
    if "no" in normalized:
        return False

    raise ValueError(f"Expected Yes/No value, got {value!r}")


def parse_date(value: Any) -> date | None:
    value = parse_optional_string(value)

    if value is None:
        return None

    return datetime.fromisoformat(value).date()


def parse_datetime(value: Any) -> datetime | None:
    value = parse_optional_string(value)

    if value is None:
        return None

    value = re.sub(r"\s*\([^)]*\)\s*$", "", value)

    return datetime.strptime(
        value,
        "%a %b %d %Y %H:%M:%S GMT%z",
    )


DEFAULT_CONVERTERS = {
    "BOOLEAN": parse_yes_no,
    "REAL": parse_float,
    "INTEGER": parse_int,
    "DATE": parse_date,
    "TIMESTAMP": parse_datetime,
}


def normalize_vocabulary_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value).strip()).casefold()


def parse_controlled_vocabulary(value: Any, vocabulary_code: str) -> str | None:
    value = parse_optional_string(value)
    if value is None:
        return None

    normalized_value = normalize_vocabulary_text(value)

    for vocabulary_class in vars(vocabularies).values():
        defs = getattr(vocabulary_class, "defs", None)

        if getattr(defs, "code", None) != vocabulary_code:
            continue

        for term in vars(vocabulary_class).values():
            term_code = getattr(term, "code", None)
            term_label = getattr(term, "label", None)

            if term_code is None:
                continue

            normalized_term_label = normalize_vocabulary_text(term_label)

            # Match either the vocabulary code itself...
            if (
                normalized_term_label == normalized_value
                or normalized_term_label in normalized_value
            ):
                return term_code

            # ...or its human-readable label.
            if term_label is not None and (
                normalized_term_label == normalized_value
                or normalized_term_label in normalized_value
            ):
                return term_code

        raise ValueError(
            f"{value!r} is not a valid term of vocabulary {vocabulary_code!r}"
        )

    raise ValueError(f"Unknown vocabulary {vocabulary_code!r}")


@dataclass(frozen=True)
class FieldMapping:
    object_type: type
    property_map: str
    converter: Callable[[Any], Any] | None = None
    merger: Callable[[Any, Any], Any] | None = None

    def convert(self, value: Any) -> Any:
        if self.converter is not None:
            return self.converter(value)

        property_def = getattr(self.object_type, self.property_map)

        if property_def.data_type.value == "CONTROLLEDVOCABULARY":
            return parse_controlled_vocabulary(
                value,
                property_def.vocabulary_code,
            )

        converter = DEFAULT_CONVERTERS.get(property_def.data_type.value)

        if converter is None:
            return value

        return converter(value)


def append_multiline(
    existing: str | None,
    value: str | None,
) -> str | None:
    value = parse_optional_string(value)

    if value is None:
        return existing

    if not existing:
        return value

    return f"{existing}\n{value}"


ANNOTATIONS = {
    "Metadata": {
        "Test info": {
            "Test job details": {
                "Date of test start": FieldMapping(CreepTest, "start_date"),
                "Data of test end": FieldMapping(CreepTest, "end_date"),
                "Test ID": FieldMapping(CreepTest, "creep_test_id"),
                "Project": FieldMapping(CreepTest, "creep_test_project_id"),
                "Test order": None,
            },
            "Test parameters": {
                "Was the test performed according to a test standard?": FieldMapping(
                    CreepTest, "creep_test_standard_applied"
                ),
                "Test standard": FieldMapping(CreepTest, "creep_test_standard"),
                "Specified temperature": FieldMapping(
                    CreepTest, "creep_test_specified_temperature"
                ),
                "Type of loading": FieldMapping(
                    CreepTest, "creep_test_type_of_loading"
                ),
                "Load control type": FieldMapping(
                    CreepTest, "creep_test_load_control_type"
                ),
                "Initial stress": FieldMapping(CreepTest, "creep_test_initial_stress"),
                "Test type": FieldMapping(CreepTest, "creep_test_test_type"),
                "End of test criterium": FieldMapping(
                    CreepTest, "creep_test_end_of_test_criterium"
                ),
                "End of test criterium - value (if not test piece break)": None,
                "Interruption course": FieldMapping(
                    CreepTest, "creep_test_interruption_course"
                ),
                "Test force": FieldMapping(CreepTest, "creep_test_test_force"),
                "Preload (Part of the test force)": FieldMapping(
                    CreepTest, "creep_test_preload"
                ),
                "Other additional information (e.g. if constant stress)": FieldMapping(
                    CreepTest, "notes"
                ),
            },
            "Related research outcome": {
                "Related article(s) available?": FieldMapping(
                    CreepTest, "creep_test_any_related_articles"
                ),
                "DOI Article 1": FieldMapping(
                    CreepTest, "creep_test_related_article", merger=append_multiline
                ),
                "Short description of content article 1": FieldMapping(
                    CreepTest, "creep_test_related_article", merger=append_multiline
                ),
                "DOI Article 2": FieldMapping(
                    CreepTest, "creep_test_related_article", merger=append_multiline
                ),
                "Short description of content article 2": FieldMapping(
                    CreepTest, "creep_test_related_article", merger=append_multiline
                ),
                "DOI Article n": FieldMapping(
                    CreepTest, "creep_test_related_article", merger=append_multiline
                ),
                "Short description of content article n": FieldMapping(
                    CreepTest, "creep_test_related_article", merger=append_multiline
                ),
            },
        },
        "Material related": {
            "History and condition of the material": {
                "(Digital) Material Identifier": FieldMapping(
                    CreepTestMaterialHistoryAndCondition,
                    "creep_test_material_identifier",
                ),
                "As-manufactured material": {
                    "Information on phase equilibrium": FieldMapping(
                        CreepTestMaterialHistoryAndCondition,
                        "creep_test_possible_phase_transformation",
                    ),
                    "Type of as-manufactured material\n(Cast / Ingot / Extrusion rod / …)": FieldMapping(
                        CreepTestMaterialHistoryAndCondition,
                        "creep_test_form_of_as_manufactured_material",
                    ),
                    "Description of the as-manufactured material (geometry and dimensions)": FieldMapping(
                        CreepTestMaterialHistoryAndCondition,
                        "creep_test_geometry_size_as_manufactured_material",
                    ),
                    "Description of the manufacturing process - as-manufactured material\n": FieldMapping(
                        CreepTestMaterialHistoryAndCondition,
                        "creep_test_manufacturing_process_description_as_manufactured_material",
                    ),
                    "Casting temperature": FieldMapping(
                        CreepTestMaterialHistoryAndCondition,
                        "creep_test_casting_temperature",
                    ),
                    "Casting speed": FieldMapping(
                        CreepTestMaterialHistoryAndCondition, "creep_test_casting_speed"
                    ),
                    "Single or polycrystal solidified": FieldMapping(
                        CreepTestMaterialHistoryAndCondition,
                        "creep_test_solidification",
                    ),
                    "Condition": FieldMapping(
                        CreepTestMaterialHistoryAndCondition, "creep_test_condition"
                    ),
                },
                "As-tested material": {
                    "Supplier": FieldMapping(
                        CreepTestMaterialHistoryAndCondition, "creep_test_supplier"
                    ),
                    "Description of the as-tested material (geometry and dimensions) - The test piece is manufactured from the tested material.": FieldMapping(
                        CreepTestMaterialHistoryAndCondition,
                        "creep_test_geometry_size_as_tested_material",
                    ),
                    "Description of the manufacturing process - as-tested material\n": FieldMapping(
                        CreepTestMaterialHistoryAndCondition,
                        "creep_test_manufacturing_process_description_as_tested_material",
                    ),
                    "Date of supply": FieldMapping(
                        CreepTestMaterialHistoryAndCondition, "creep_test_supply_date"
                    ),
                    "Order number": FieldMapping(
                        CreepTestMaterialHistoryAndCondition, "creep_test_order_number"
                    ),
                    "Supplier sample ID": None,
                },
                "Heat treatment": {
                    "Heat treatment - State": FieldMapping(
                        CreepTestMaterialHistoryAndCondition,
                        "creep_test_heat_treatment_state",
                    ),
                    "Multistage annealing?": FieldMapping(
                        CreepTestMaterialHistoryAndCondition,
                        "creep_test_multistage_annealing",
                    ),
                    "Multistage ageing?": FieldMapping(
                        CreepTestMaterialHistoryAndCondition,
                        "creep_test_multistage_ageing",
                    ),
                    "Atmosphere": None,
                    "Heat treatment - Annealing - Description": FieldMapping(
                        CreepTestMaterialHistoryAndCondition,
                        "creep_test_heat_treatment_annealing_description",
                    ),
                    "Heat treatment - Ageing - Description": FieldMapping(
                        CreepTestMaterialHistoryAndCondition,
                        "creep_test_heat_treatment_ageing_description",
                    ),
                    "Heat treatment - Protocol file": FieldMapping(
                        CreepTestMaterialHistoryAndCondition,
                        "creep_test_heat_treatment_protocol",
                    ),
                },
                "Chemical composition": {
                    "Chemical composition - nominal": FieldMapping(
                        CreepTestChemicalCompositionNominal,
                        "creep_test_chemical_composition_nominal",
                    ),
                    "Chemical composition - measured (including precision)": FieldMapping(
                        CreepTestChemicalCompositionMeasured,
                        "creep_test_chemical_composition_measured",
                    ),
                    "Measurement method": FieldMapping(
                        CreepTestChemicalCompositionMeasured,
                        "creep_test_measurement_method",
                    ),
                    "Measuring point": FieldMapping(
                        CreepTestChemicalCompositionMeasured,
                        "creep_test_measuring_position",
                    ),
                    "Partitioning of alloy elements in microstructure (dendrite cores and ID regions)": None,
                    "Chemical composition in gamma and gamma' regions (dendrite cores and ID regions)": None,
                },
                "Microstructure": {
                    "Type of investigation (characterization method)": FieldMapping(
                        CreepTestMaterialHistoryAndCondition,
                        "creep_test_characterization_method",
                    ),
                    "Grain size (if polycrystal)": FieldMapping(
                        CreepTestMaterialHistoryAndCondition, "creep_test_grain_size"
                    ),
                    "Grain size - Determination method, measuring point": FieldMapping(
                        CreepTestMaterialHistoryAndCondition,
                        "creep_test_grain_size_determination_method",
                    ),
                    "Grain size - documentation": FieldMapping(
                        CreepTestMaterialHistoryAndCondition,
                        "creep_test_microstructure_report",
                    ),
                    "Completely dissolved and re-precipitated gamma-gamma' regions": FieldMapping(
                        CreepTestMaterialHistoryAndCondition,
                        "creep_test_reprecipitated_gamma_gamma_prime_regions",
                    ),
                    "Gamma'-particles', average size": FieldMapping(
                        CreepTestMaterialHistoryAndCondition,
                        "creep_test_gamma_prime_particles_average_size",
                    ),
                    "Gamma'-particles', maximum size": FieldMapping(
                        CreepTestMaterialHistoryAndCondition,
                        "creep_test_gamma_prime_particles_maximum_size",
                    ),
                    "Dendrite spacings": FieldMapping(
                        CreepTestMaterialHistoryAndCondition,
                        "creep_test_dendrite_spacings",
                    ),
                    "Microstructure after test (SX/PX, gprime-Vol, gprime-size, dendrites)": FieldMapping(
                        CreepTestMaterialHistoryAndCondition,
                        "creep_test_microstructure_feature_information",
                    ),
                    "Images of the microstructure before testing": FieldMapping(
                        CreepTestMaterialHistoryAndCondition,
                        "creep_test_microstructure_image",
                    ),
                    "Images of the microstructure after testing": FieldMapping(
                        CreepTestMaterialHistoryAndCondition,
                        "creep_test_microstructure_image",
                    ),  # double with before
                    "Proof of single crystallinity": FieldMapping(
                        CreepTestMaterialHistoryAndCondition,
                        "creep_test_proof_of_single_crystallinity",
                    ),
                    "Single crystal orientation\n(Laue Crystal Verification. Must be documented for each test piece)": FieldMapping(
                        CreepTestMaterialHistoryAndCondition,
                        "creep_test_single_crystal_orientation",
                    ),
                    "Single crystal orientation - Determination method, measuring point": FieldMapping(
                        CreepTestMaterialHistoryAndCondition,
                        "creep_test_single_crystal_orientation_determination_method",
                    ),
                    "Accuracy of the determination of the single crystal orientation": FieldMapping(
                        CreepTestMaterialHistoryAndCondition,
                        "creep_test_orientation_determination_accuracy",
                    ),
                },
                "Results from NDT": {
                    "Crack inspection: e.g., Penetrant certification/Radiographic certification/XCT": FieldMapping(
                        CreepTestMaterialHistoryNDTResults,
                        "creep_test_crack_or_defect_inspection_method",
                    ),
                    "X-Ray film": FieldMapping(
                        CreepTestMaterialHistoryNDTResults,
                        "creep_test_crack_or_defect_inspection_result",
                    ),
                },
                "Results from other mech. tests": {
                    "0.2 % Proof strength at room temperature": FieldMapping(
                        CreepTestMaterialHistoryMechanicalTestsResults,
                        "creep_test_proof_strength_room_temperature",
                    ),
                    "0.2 % Proof strength at creep test temperature": FieldMapping(
                        CreepTestMaterialHistoryMechanicalTestsResults,
                        "creep_test_proof_strength_creep_test_temperature",
                    ),
                    "Hardness": FieldMapping(
                        CreepTestMaterialHistoryMechanicalTestsResults,
                        "creep_test_hardness",
                    ),
                },
            },
            "Test piece": {
                "Test piece ID": FieldMapping(
                    CreepTestTestPiece, "creep_test_test_piece_id"
                ),
                "Workshop order ID/ref.": FieldMapping(
                    CreepTestTestPiece, "creep_test_workshop_order_id"
                ),
                "Test piece history": FieldMapping(
                    CreepTestTestPiece, "creep_test_test_piece_history"
                ),
                "Type of test piece I": FieldMapping(
                    CreepTestTestPiece, "creep_test_test_piece_type_i"
                ),
                "Type of test piece II": FieldMapping(
                    CreepTestTestPiece, "creep_test_test_piece_type_ii"
                ),
                "Type of test piece III": FieldMapping(
                    CreepTestTestPiece, "creep_test_test_piece_type_iii"
                ),
                "Test piece technical drawing": FieldMapping(
                    CreepTestTestPiece, "creep_test_test_piece_technical_drawing"
                ),
                "Location of the test piece within the as-tested material": FieldMapping(
                    CreepTestTestPiece, "creep_test_test_piece_origin_and_orientation"
                ),
                "Positioning (Laue, precision)\n- Description whether  coordinate systems of as-tested material and test piece coincide, and of the alignment in the test machine": FieldMapping(
                    CreepTestTestPiece,
                    "creep_test_test_piece_orientation_in_test_machine",
                ),
                "Further information about sample(s)": FieldMapping(
                    CreepTestTestPiece, "creep_test_additional_information_test_piece"
                ),
            },
        },
        "Measuring and test equipment": {
            "Test machine": {
                "Test machine ID": FieldMapping(
                    CreepTestTestMachine, "creep_test_test_machine_id"
                ),
                "Type of test machine": FieldMapping(
                    CreepTestTestMachine, "creep_test_test_machine_type"
                ),
                "Min. applied force": FieldMapping(
                    CreepTestTestMachine, "creep_test_minimum_applicable_force"
                ),
                "Max. applied force": FieldMapping(
                    CreepTestTestMachine, "creep_test_maximum_applicable_force"
                ),
                "Verification of Test Frame and Specimen Alignment according to ASTM E1012?": FieldMapping(
                    CreepTestTestMachine, "creep_test_test_frame_and_specimen_alignment"
                ),
                "Please provide a description on the procedure followed for the Verification of Test Frame and Specimen Alignment if different from ASTM E1012": FieldMapping(
                    CreepTestTestMachine,
                    "creep_test_test_frame_and_specimen_alignment_description",
                ),
                "Calibration class (Alignment)": FieldMapping(
                    CreepTestTestMachine, "creep_test_calibration_class"
                ),
                "Data acquisition": {
                    "Data acquisition unit - Model information": FieldMapping(
                        CreepTestTestMachineDataAcquisition,
                        "creep_test_data_acquisition_unit_model_information",
                    ),
                    "Data acquisition unit - Laboratory ID": FieldMapping(
                        CreepTestTestMachineDataAcquisition,
                        "creep_test_data_acquisition_unit_id",
                    ),
                    "Data acquisition software and version": FieldMapping(
                        CreepTestTestMachineDataAcquisition,
                        "creep_test_data_acquisition_software_and_version",
                    ),
                    "Data acquisition - description": FieldMapping(
                        CreepTestTestMachineDataAcquisition,
                        "creep_test_data_acquisition_description",
                    ),
                    "Was the time checked during data acquisition?": FieldMapping(
                        CreepTestTestMachineDataAcquisition,
                        "creep_test_data_acquisition_time_check",
                    ),
                },
            },
            "Test force": {
                "Loading system": {
                    "Was the loading system calibrated/verified?": FieldMapping(
                        CreepTestTestMachineLoadingSystem,
                        "creep_test_verification_of_loading_system",
                    ),
                    "Calibration certificate": FieldMapping(
                        CreepTestTestMachineLoadingSystem,
                        "creep_test_calibration_certificate",
                    ),
                    "Calibration date ": FieldMapping(
                        CreepTestTestMachineLoadingSystem, "creep_test_calibration_date"
                    ),
                    "Calibration validity time period": FieldMapping(
                        CreepTestTestMachineLoadingSystem,
                        "creep_test_calibration_validity_time_period",
                    ),
                    "Calibration standard": FieldMapping(
                        CreepTestTestMachineLoadingSystem,
                        "creep_test_calibration_standard",
                    ),
                    "Calibration class": FieldMapping(
                        CreepTestTestMachineLoadingSystem,
                        "creep_test_calibration_class",
                    ),
                    "Range of calibration": FieldMapping(
                        CreepTestTestMachineLoadingSystem,
                        "creep_test_calibration_range",
                    ),
                    "Were calibrated weights used to apply the test force?": FieldMapping(
                        CreepTestTestMachineLoadingSystem,
                        "creep_test_use_of_calibrated_weights",
                    ),
                },
                "Load sensor": {
                    "Was a load sensor used during loading?": FieldMapping(
                        CreepTestLoadSensor, "creep_test_load_sensor_during_loading"
                    ),
                    "Was the load sensor calibrated?": FieldMapping(
                        CreepTestLoadSensor, "creep_test_load_sensor_calibration"
                    ),
                    "Calibration certificate": FieldMapping(
                        CreepTestLoadSensor, "creep_test_calibration_certificate"
                    ),
                    "Calibration date ": FieldMapping(
                        CreepTestLoadSensor, "creep_test_calibration_date"
                    ),
                    "Calibration validity time period": FieldMapping(
                        CreepTestLoadSensor,
                        "creep_test_calibration_validity_time_period",
                    ),
                    "Calibration standard": FieldMapping(
                        CreepTestLoadSensor, "creep_test_calibration_standard"
                    ),
                    "Calibration class": FieldMapping(
                        CreepTestLoadSensor, "creep_test_calibration_class"
                    ),
                    "Range of calibration": FieldMapping(
                        CreepTestLoadSensor, "creep_test_calibration_range"
                    ),
                },
                "Data acquisition": {
                    "Was the force recorded continuously or phase-wise (e.g. during loading)?": FieldMapping(
                        CreepTestLoadDataAcquisition, "creep_test_force_recording"
                    ),
                    "Has a calibration of the test force data acquisition been performed?": None,
                },
            },
            "Laboratory conditions": {
                "Was the room temperature recorded and checked?": FieldMapping(
                    CreepTestLaboratoryConditions, "creep_test_room_temperature"
                ),
                "Was the humidity recorded and checked?": FieldMapping(
                    CreepTestLaboratoryConditions, "creep_test_room_humidity"
                ),
            },
            "Temperature-measuring system": {
                "Control via thermocouples on sample/via furnace": FieldMapping(
                    CreepTestTemperatureMeasuringSystem, "creep_test_temperature_signal"
                ),
                "Furnace type": FieldMapping(
                    CreepTestTestMachineHeatingSystem, "creep_test_furnace_type"
                ),
                "Metrological traceability\n(Yes, if Sensor AND Data acquisition checked)": FieldMapping(
                    CreepTestTemperatureMeasuringSystem,
                    "creep_test_metrological_traceability",
                ),
                "Measuring instrument": {
                    "Sensor type": FieldMapping(
                        CreepTestTemperatureSensor, "creep_test_sensor_type"
                    ),
                    "Equipment ID": FieldMapping(
                        CreepTestTemperatureSensor, "creep_test_sensor_id"
                    ),
                    "Type of thermocouple": FieldMapping(
                        CreepTestTemperatureSensor, "creep_test_thermocouple_type"
                    ),
                    "Wire gauge": FieldMapping(
                        CreepTestTemperatureSensor, "creep_test_wire_gauge"
                    ),
                    "Layout": FieldMapping(
                        CreepTestTemperatureSensor, "creep_test_layout"
                    ),
                    "Is/are the thermocouples calibrated?": FieldMapping(
                        CreepTestTemperatureSensor, "creep_test_calibration_status"
                    ),
                    "Calibration method": FieldMapping(
                        CreepTestTemperatureSensor, "creep_test_calibration_method"
                    ),
                    "Calibration standard": FieldMapping(
                        CreepTestTemperatureSensor, "creep_test_calibration_standard"
                    ),
                    "Calibration certificate": FieldMapping(
                        CreepTestTemperatureSensor, "creep_test_calibration_certificate"
                    ),
                    "Calibration date": FieldMapping(
                        CreepTestTemperatureSensor, "creep_test_calibration_date"
                    ),
                    "Calibration validity time period": FieldMapping(
                        CreepTestTemperatureSensor,
                        "creep_test_calibration_validity_time_period",
                    ),
                    "Deviation detected during calibration": FieldMapping(
                        CreepTestTemperatureSensor, "creep_test_temperature_deviation"
                    ),
                    "Range of calibration": FieldMapping(
                        CreepTestTemperatureSensor, "creep_test_calibration_range"
                    ),
                    "Application: contact method": FieldMapping(
                        CreepTestTemperatureSensor, "creep_test_contact_method"
                    ),
                    "Application: number of thermocouples": FieldMapping(
                        CreepTestTemperatureSensor, "creep_test_number_of_thermocouples"
                    ),
                    "Application: location with respect to gauge section": FieldMapping(
                        CreepTestTemperatureSensor, "creep_test_thermocouple_location"
                    ),
                },
                "Data acquisition": {
                    "Is/are the data acquisition unit calibrated?": FieldMapping(
                        CreepTestTemperatureDataAcquisition,
                        "creep_test_calibration_status",
                    ),
                    "Reference junction": FieldMapping(
                        CreepTestTemperatureDataAcquisition,
                        "creep_test_reference_junction",
                    ),
                    "Calibration certificate": FieldMapping(
                        CreepTestTemperatureDataAcquisition,
                        "creep_test_calibration_certificate",
                    ),
                    "Calibration date": FieldMapping(
                        CreepTestTemperatureDataAcquisition,
                        "creep_test_calibration_date",
                    ),
                    "Calibration validity time period": FieldMapping(
                        CreepTestTemperatureDataAcquisition,
                        "creep_test_calibration_validity_time_period",
                    ),
                    "Calibration method": FieldMapping(
                        CreepTestTemperatureDataAcquisition,
                        "creep_test_calibration_method",
                    ),
                    "Calibration standard": FieldMapping(
                        CreepTestTemperatureDataAcquisition,
                        "creep_test_calibration_standard",
                    ),
                    "Deviation detected during calibration": FieldMapping(
                        CreepTestTemperatureDataAcquisition,
                        "creep_test_temperature_deviation",
                    ),
                    "Range of calibration": FieldMapping(
                        CreepTestTemperatureDataAcquisition,
                        "creep_test_calibration_range",
                    ),
                },
            },
            "Extensometer system": {
                "Type of strain measuring device": FieldMapping(
                    CreepTestExtensometerSystem,
                    "creep_test_displacement_measuring_method",
                ),
                "Sensor type - Contacting extensometer": FieldMapping(
                    CreepTestExtensometerSystem,
                    "creep_test_sensor_type_contacting_method",
                ),
                "Sensor type - Non-contacting extensometer": FieldMapping(
                    CreepTestExtensometerSystem,
                    "creep_test_sensor_type_non_contacting_method",
                ),
                "Contacting extensometer": {
                    "Measurement one-sided or two-sided?": FieldMapping(
                        CreepTestExtensionValuesContactingExtensometer,
                        "creep_test_measurement_setup",
                    ),
                    "Measurement: axial or diametrical action?": FieldMapping(
                        CreepTestExtensionValuesContactingExtensometer,
                        "creep_test_measurement_direction",
                    ),
                    "Mounting type": FieldMapping(
                        CreepTestExtensionValuesContactingExtensometer,
                        "creep_test_mounting_type",
                    ),
                    "Extensometer model information ": FieldMapping(
                        CreepTestExtensionValuesContactingExtensometer,
                        "creep_test_extensometer_model_information",
                    ),
                    "Equipment ID - Extensometer": FieldMapping(
                        CreepTestExtensionValuesContactingExtensometer,
                        "creep_test_extensometer_id",
                    ),
                    "Description of upper/lower legs (LVDT systems)": FieldMapping(
                        CreepTestExtensionValuesContactingExtensometer,
                        "creep_test_extensometer_leg_material",
                    ),
                    "Measuring amplifier": FieldMapping(
                        CreepTestExtensionValuesContactingExtensometer,
                        "creep_test_measuring_amplifier_model_information",
                    ),
                    "Extension range - Upper limit": FieldMapping(
                        CreepTestExtensionValuesContactingExtensometer,
                        "creep_test_extension_range_upper_limit",
                    ),
                    "Extension range - Lower limit": FieldMapping(
                        CreepTestExtensionValuesContactingExtensometer,
                        "creep_test_extension_range_lower_limit",
                    ),
                    "Nominal gauge length (if applicable)": FieldMapping(
                        CreepTestExtensionValuesContactingExtensometer,
                        "creep_test_nominal_gauge_length",
                    ),
                    "Is the extensometer incl. the data acquisition calibrated?": FieldMapping(
                        CreepTestExtensionValuesContactingExtensometer,
                        "creep_test_is_the_extensometer_incl_the_data_acquisition_calibrated",
                    ),
                    "Calibration certificate": FieldMapping(
                        CreepTestExtensionValuesContactingExtensometer,
                        "creep_test_calibration_certificate",
                    ),
                    "Calibration date": FieldMapping(
                        CreepTestExtensionValuesContactingExtensometer,
                        "creep_test_calibration_date",
                    ),
                    "Calibration validity time period": FieldMapping(
                        CreepTestExtensionValuesContactingExtensometer,
                        "creep_test_calibration_validity_time_period",
                    ),
                    "Calibration class": FieldMapping(
                        CreepTestExtensionValuesContactingExtensometer,
                        "creep_test_calibration_class",
                    ),
                    "Range of calibration  ": FieldMapping(
                        CreepTestExtensionValuesContactingExtensometer,
                        "creep_test_calibration_range",
                    ),
                    "Calibration standard": FieldMapping(
                        CreepTestExtensionValuesContactingExtensometer,
                        "creep_test_calibration_standard",
                    ),
                },
            },
        },
        "Data processing procedures": {
            "Description of primary and processed data series - Primary data is data that is directly acquired by sensors or measuring instruments during or after a test. Processed data is obtained as a result of using procedures (equations, algorithms, methods, unit conversions)  to transform data": FieldMapping(
                CreepTestDataProcessingProcedures, "creep_test_primary_data_series"
            ),
            "Description of primary data series processing (incl. averaging, smoothing)": FieldMapping(
                CreepTestDataProcessingProcedures, "creep_test_processed_data_series"
            ),
            "Description of the data processing and analysis procedures used to obtain specific test results, e.g. percentage elastic extension, ee": FieldMapping(
                CreepTestDataProcessingProcedures, "creep_test_data_analysis_procedures"
            ),
            "Were automated (user-independent) analysis workflows used?": FieldMapping(
                CreepTestDataProcessingProcedures, "creep_test_workflow_usage"
            ),
            "Software, if applicable, including product and version": FieldMapping(
                CreepTestDataProcessingProcedures, "creep_test_software"
            ),
            "Related publications, if applicable": FieldMapping(
                CreepTestDataProcessingProcedures, "creep_test_related_publications"
            ),
        },
    },
    "Primary data": {
        "Test result": {
            "Values recorded at test start": {
                "Min. test piece diameter at room temperature": FieldMapping(
                    CreepTestPrimaryValuesRecordedAtTestStart,
                    "creep_test_minimum_test_piece_diameter_at_room_temperature",
                ),
                "Original gauge length": FieldMapping(
                    CreepTestPrimaryValuesRecordedAtTestStart,
                    "creep_test_original_gauge_length",
                ),
                "Parallel length": FieldMapping(
                    CreepTestPrimaryValuesRecordedAtTestStart,
                    "creep_test_parallel_length",
                ),
                "Extensometer gauge length": FieldMapping(
                    CreepTestPrimaryValuesRecordedAtTestStart,
                    "creep_test_extensometer_gauge_length",
                ),
                "Reference length for calculation of percentage elongations": FieldMapping(
                    CreepTestPrimaryValuesRecordedAtTestStart,
                    "creep_test_reference_length_to_calculate_percentage_elongations",
                ),
                "Reference length for calculation of percentage elongations if Lo and/or extensometer Le are outside the parallel length.": FieldMapping(
                    CreepTestPrimaryValuesRecordedAtTestStart,
                    "creep_test_reference_length_to_calculate_percentage_elongations",
                ),
                "Reference length for calculation of percentage extensions": FieldMapping(
                    CreepTestPrimaryValuesRecordedAtTestStart,
                    "creep_test_reference_length_to_calculate_percentage_extensions",
                ),
                "Ratio Lr / D ; (if Lr = Lo)": FieldMapping(
                    CreepTestPrimaryValuesRecordedAtTestStart,
                    "creep_test_ratio_reference_length_to_diameter",
                ),
                "k-Value for Lr (if Lr = Lo)": FieldMapping(
                    CreepTestPrimaryValuesRecordedAtTestStart, "creep_test_k_value"
                ),
                "Ratio Lr / D ; (if Lr > Lc)": FieldMapping(
                    CreepTestPrimaryValuesRecordedAtTestStart,
                    "creep_test_ratio_reference_length_to_diameter",
                ),
                "k-Value for Lr (if Lr > Lc)": FieldMapping(
                    CreepTestPrimaryValuesRecordedAtTestStart, "creep_test_k_value"
                ),
                "Ratio Lr / D ; (if Lr = Le)": FieldMapping(
                    CreepTestPrimaryValuesRecordedAtTestStart,
                    "creep_test_ratio_reference_length_to_diameter",
                ),
                "k-Value for Lr  (if Lr = Le)": FieldMapping(
                    CreepTestPrimaryValuesRecordedAtTestStart, "creep_test_k_value"
                ),
            },
            "Values recorded during test run": {
                "Elapsed time from end of loading": FieldMapping(
                    CreepTestPrimaryValuesRecordedDuringTestRun,
                    "creep_test_elapsed_time_from_end_of_loading",
                ),
                "Extension": FieldMapping(
                    CreepTestPrimaryValuesRecordedDuringTestRun, "creep_test_extension"
                ),
                "Elongation": FieldMapping(
                    CreepTestPrimaryValuesRecordedDuringTestRun, "creep_test_elongation"
                ),
                "Heating time": FieldMapping(
                    CreepTestPrimaryValuesRecordedDuringTestRun,
                    "creep_test_heating_time",
                ),
                "Soak time before the test": FieldMapping(
                    CreepTestPrimaryValuesRecordedDuringTestRun, "creep_test_soak_time"
                ),
                "Test duration": FieldMapping(
                    CreepTestPrimaryValuesRecordedDuringTestRun,
                    "creep_test_test_duration",
                ),
            },
            "Values recorded after end of test ": {
                "Creep rupture time": FieldMapping(
                    CreepTestPrimaryValuesRecordedAfterEndOfTest,
                    "creep_test_creep_rupture_time",
                ),
                "Position of the fracture": FieldMapping(
                    CreepTestPrimaryValuesRecordedAfterEndOfTest,
                    "creep_test_fracture_position",
                ),
                "Final gauge length after fracture": FieldMapping(
                    CreepTestPrimaryValuesRecordedAfterEndOfTest,
                    "creep_test_final_gauge_length_after_fracture",
                ),
            },
        }
    },
    "Secondary data": {
        "Test result": {
            "Values recorded during test run": {
                "Corrected measured temperature": None,
                "Force": None,
                "Loading rate": FieldMapping(
                    CreepTestSecondaryValuesRecordedDuringTestRun,
                    "creep_test_loading_rate",
                ),
                "Unloading rate": FieldMapping(
                    CreepTestSecondaryValuesRecordedDuringTestRun,
                    "creep_test_unloading_rate",
                ),
                "Heating speed": FieldMapping(
                    CreepTestSecondaryValuesRecordedDuringTestRun,
                    "creep_test_heating_speed",
                ),
                "Cooling speed": FieldMapping(
                    CreepTestSecondaryValuesRecordedDuringTestRun,
                    "creep_test_cooling_speed",
                ),
                "Percentage plastic extension from end of loading": FieldMapping(
                    CreepTestSecondaryValuesRecordedDuringTestRun,
                    "creep_test_percentage_extension",
                ),
            },
            "Elongation values": {
                "Percentage permanent elongation": FieldMapping(
                    CreepTestSecondaryElongationValues,
                    "creep_test_percentage_permanent_elongation",
                ),
                "Percentage elongation after creep fracture": FieldMapping(
                    CreepTestSecondaryElongationValues,
                    "creep_test_percentage_elongation_after_creep_fracture",
                ),
                "percentage reduction of area after creep fracture": FieldMapping(
                    CreepTestSecondaryElongationValues,
                    "creep_test_percentage_reduction_of_area_after_creep_fracture",
                ),
            },
            "Extension values": {
                "Was there an averaging of the strain/distance values? (two-sided extensometer)": FieldMapping(
                    CreepTestExtensionValuesContactingExtensometer,
                    "creep_test_extension_averaging",
                ),
                "Percentage total extension": FieldMapping(
                    CreepTestSecondaryExtensionValues,
                    "creep_test_percentage_total_extension",
                ),
                "Percentage initial total extension": FieldMapping(
                    CreepTestSecondaryExtensionValues,
                    "creep_test_percentage_initial_total_extension",
                ),
                "Percentage elastic extension": FieldMapping(
                    CreepTestSecondaryExtensionValues,
                    "creep_test_percentage_elastic_extension",
                ),
                "Percentage initial plastic extension": FieldMapping(
                    CreepTestSecondaryExtensionValues,
                    "creep_test_percentage_initial_plastic_extension",
                ),
                "Percentage plastic extension": FieldMapping(
                    CreepTestSecondaryExtensionValues,
                    "creep_test_percentage_plastic_extension",
                ),
                "Percentage creep extension": FieldMapping(
                    CreepTestSecondaryExtensionValues,
                    "creep_test_percentage_creep_extension",
                ),
            },
        }
    },
}
