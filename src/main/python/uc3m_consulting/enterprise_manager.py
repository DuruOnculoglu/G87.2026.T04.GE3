"""Module """
import re
import json

from datetime import datetime, timezone
from freezegun import freeze_time
from uc3m_consulting.enterprise_project import EnterpriseProject
from uc3m_consulting.enterprise_management_exception import EnterpriseManagementException
from uc3m_consulting.enterprise_manager_config import (PROJECTS_STORE_FILE,
                                                       TEST_DOCUMENTS_STORE_FILE,
                                                       TEST_NUMDOCS_STORE_FILE)
from uc3m_consulting.project_document import ProjectDocument

class EnterpriseManager(object):

    class __EnterpriseManager():
        """Manages enterprise projects and document validation operations"""

        def __init__(self):
            pass

        def register_project(self,
                             company_cif: str,
                             project_acronym: str,
                             project_description: str,
                             department: str,
                             date: str,
                             budget: str):
            """Creates and stores a validated enterprise project"""

            self.validate_cif(company_cif)
            self.validate_pattern(r"^[a-zA-Z0-9]{5,10}", project_acronym, "Invalid acronym")
            self.validate_pattern(r"^.{10,30}$", project_description, "Invalid description format")
            self.validate_pattern(r"(HR|FINANCE|LEGAL|LOGISTICS)", department, "Invalid department")

            self.validate_starting_date(date)
            self.validate_budget(budget)

            new_project = EnterpriseProject(company_cif=company_cif,
                                            project_acronym=project_acronym,
                                            project_description=project_description,
                                            department=department,
                                            starting_date=date,
                                            project_budget=budget)

            project_list = self.load_json_file(PROJECTS_STORE_FILE, [])

            for project_item in project_list:
                if project_item == new_project.to_json():
                    raise EnterpriseManagementException("Duplicated project in projects list")

            project_list.append(new_project.to_json())

            self.save_json_file(PROJECTS_STORE_FILE, project_list)

            return new_project.project_id

        def find_docs(self, date_str):
            """
            Counts valid documents for a given date and generates a report.
            Ensures document integrity using signature verification.
            """
            self.validate_pattern(r"^(([0-2]\d|3[0-1])\/(0\d|1[0-2])\/\d\d\d\d)$",
                                  date_str, "Invalid date format")
            self.validate_date(date_str)
            documents = self.get_documents(TEST_DOCUMENTS_STORE_FILE)

            valid_counter = 0

            for document in documents:
                if self.validate_document(document, date_str):
                    valid_counter += 1

            if valid_counter == 0:
                raise EnterpriseManagementException("No documents found")

            self.write_report(date_str, valid_counter)

            return valid_counter

        @staticmethod
        def validate_cif(cif: str):
            """Validates Spanish CIF identification number format and control digit. """
            if not isinstance(cif, str):
                raise EnterpriseManagementException("CIF code must be a string")

            EnterpriseManager.__EnterpriseManager.validate_pattern(r"^[ABCDEFGHJKNPQRSUVW]\d{7}[0-9A-J]$", cif, "Invalid CIF format")

            cif_letter = cif[0]
            cif_digits = cif[1:8]
            control_char = cif[8]

            even_sum = 0
            odd_sum = 0

            for i in range(len(cif_digits)):
                if i % 2 == 0:
                    doubled = int(cif_digits[i]) * 2
                    if doubled > 9:
                        even_sum = even_sum + (doubled // 10) + (doubled % 10)
                    else:
                        even_sum = even_sum + doubled
                else:
                    odd_sum = odd_sum + int(cif_digits[i])

            total_sum = even_sum + odd_sum
            remainder_digit = total_sum % 10
            control_digit = 10 - remainder_digit

            if control_digit == 10:
                control_digit = 0

            control_letter_map = "JABCDEFGHI"

            if cif_letter in ('A', 'B', 'E', 'H'):
                if str(control_digit) != control_char:
                    raise EnterpriseManagementException("Invalid CIF character control number")
            elif cif_letter in ('P', 'Q', 'S', 'K'):
                if control_letter_map[control_digit] != control_char:
                    raise EnterpriseManagementException("Invalid CIF character control letter")
            else:
                raise EnterpriseManagementException("CIF type not supported")
            return True

        def validate_starting_date(self, date_str):
            """Validates the project start date format and constraints"""
            self.validate_pattern(r"^(([0-2]\d|3[0-1])\/(0\d|1[0-2])\/\d\d\d\d)$",
                                  date_str, "Invalid date format")

            my_date = self.validate_date(date_str)

            if my_date < datetime.now(timezone.utc).date():
                raise EnterpriseManagementException("Project's date must be today or later.")
            if my_date.year < 2025 or my_date.year > 2050:
                raise EnterpriseManagementException("Invalid date format")
            return date_str

        @staticmethod
        def validate_date(date_str):
            """Validates a date string to ensure it matches expected format"""
            try:
                return datetime.strptime(date_str, "%d/%m/%Y").date()
            except ValueError as ex:
                raise EnterpriseManagementException("Invalid date format") from ex

        @staticmethod
        def validate_pattern(pattern, value, message):
            """Validates whether a value matches a regular expression pattern."""
            if not re.compile(pattern).fullmatch(value):
                raise EnterpriseManagementException(message)

        @staticmethod
        def validate_budget(budget: str):
            """Validates budget format and range constraints."""
            try:
                budget_float = float(budget)
            except ValueError as exc:
                raise EnterpriseManagementException("Invalid budget amount") from exc

            budget_str = str(budget_float)
            if '.' in budget_str:
                decimals = len(budget_str.split('.')[1])
                if decimals > 2:
                    raise EnterpriseManagementException("Invalid budget amount")

            if budget_float < 50000 or budget_float > 1000000:
                raise EnterpriseManagementException("Invalid budget amount")

        def validate_document(self, document, date_str):
            """Checks whether a document matches the given date and validates its integrity."""

            time_val = document["register_date"]

            formatted_date = datetime.fromtimestamp(time_val).strftime("%d/%m/%Y")

            if formatted_date == date_str:
                date_object = datetime.fromtimestamp(time_val, tz=timezone.utc)
                with freeze_time(date_object):
                    self.validate_document_signature(document)
                return True
            return False

        @staticmethod
        def validate_document_signature(document):
            """Validates document signature integrity"""

            project_doc = ProjectDocument(document["project_id"], document["file_name"])

            if project_doc.document_signature != document["document_signature"]:
                raise EnterpriseManagementException("Inconsistent document signature")

        @staticmethod
        def load_json_file(path, default_value):
            """Reads a JSON file, returning the default value if the file does not exist"""
            try:
                with open(path, "r", encoding="utf-8", newline="") as file:
                    return json.load(file)
            except FileNotFoundError:
                return default_value
            except json.JSONDecodeError as ex:
                raise EnterpriseManagementException("JSON Decode Error - Wrong JSON Format") from ex

        @staticmethod
        def save_json_file(path, data):
            """Writes a JSON file, returning the default value if the file does not exist"""
            try:
                with open(path, "w", encoding="utf-8", newline="") as file:
                    json.dump(data, file, indent=2)
            except FileNotFoundError as ex:
                raise EnterpriseManagementException("Wrong file  or file path") from ex
            except json.JSONDecodeError as ex:
                raise EnterpriseManagementException("JSON Decode Error - Wrong JSON Format") from ex

        @staticmethod
        def get_documents(path):
            """Handles file loading with exception management"""
            try:
                with open(path, "r", encoding="utf-8", newline="") as file:
                    return json.load(file)

            except FileNotFoundError as ex:
                raise EnterpriseManagementException("Wrong file  or file path") from ex

        def write_report(self, date_str, valid_counter):
            """ Report entry created with query date, current timestamp, and number of valid
                files. Appends information to existing report file."""
            date_now = datetime.now(timezone.utc).timestamp()
            data_input = {"Querydate": date_str,
                          "ReportDate": date_now,
                          "Numfiles": valid_counter,
                          }

            store_report = self.load_json_file(TEST_NUMDOCS_STORE_FILE, [])
            store_report.append(data_input)

            self.save_json_file(TEST_NUMDOCS_STORE_FILE, store_report)

    instance = None

    def __new__(cls):
        if not EnterpriseManager.instance:
            EnterpriseManager.instance = EnterpriseManager.__EnterpriseManager()
        return EnterpriseManager.instance

    def __getattr__(self, name):
        return getattr(self.instance, name)

    def __setattr__(self, name, value):
        return setattr(self.instance, name, value)