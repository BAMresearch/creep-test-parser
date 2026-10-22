import getpass

from bam_masterdata.cli.run_parser import RunParsers
from bam_masterdata.logger import logger
from pybis import Openbis

from creep_test_parser.parser import CreepTestParser

URL = "https://your-openbis-instance.com"  # openBIS URL
print(f"Connecting to openBIS instance at {URL}...")
openbis = Openbis(URL)
username = input("Username: ")
password = getpass.getpass("Password: ")
openbis.login(username, password, save_token=True)


# Define which parser to use and which files to parse
files_parser = {
    CreepTestParser(): [
        "./tests/data/test.xlsx",
    ]
}

# Run the parser
parsing = RunParsers(
    openbis=openbis,
    space_name="<SPACE-NAME>",
    project_name="<PROJECT-NAME>",
    collection_name="<COLLECTION-NAME>",  # optional
    files_parser=files_parser,
    logger=logger,
)


print("Starting parsing...")
parsing.run()
print("Done!")
