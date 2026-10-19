from decouple import config as environ
from pybis import Openbis

# Connect to openBIS
# Take the file `.env.example` in this repo, and rename it as `.env`. Change the
# variables there for your own parameters
openbis = Openbis(environ("OPENBIS_URL"))
openbis.login(environ("OPENBIS_USERNAME"), environ("OPENBIS_PASSWORD"), save_token=True)


from bam_masterdata.cli.run_parser import run_parser

from creep_test_parser.parser import CreepTestParser

# Define which parser to use and which files to parse
files_parser = {
    CreepTestParser(): [
        "./tests/data/data_schema_creep_test.xlsx",
    ]
}

# Run the parser
run_parser(
    openbis=openbis,
    space_name="VP.1_JPIZARRO",  # define your Space name
    project_name="CREEPTEST_PROJECT",  # define your Project name
    collection_name="CREEPTEST_TEST_COLLECTION",  # optional, define your Collection name
    files_parser=files_parser,
)
print("Parsing completed.")
