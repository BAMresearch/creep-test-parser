from pathlib import Path

from bam_masterdata.logger import logger
from bam_masterdata.metadata.entities import CollectionType

from src.creep_test_parser.parser import CreepTestParser


class TestCreepTestParser:
    def test_parse(self):
        parser = CreepTestParser()
        collection = CollectionType()
        test_file = Path(__file__).parent / "data" / "test.xlsx"
        parser.parse([str(test_file)], collection, logger)
        assert collection is not None
        assert len(collection.attached_objects) == 1
        assert len(collection.relationships) == 0
        objects = list(collection.attached_objects.values())
        assert objects[0].name == "CreepTest"
        assert objects[0].creep_test_id == "Ab1234"
        assert objects[0].start_date == "2022-05-01 02:00:00"
        assert objects[0].end_date == "2022-05-02 02:00:00"
