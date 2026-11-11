"""Tests for file_ingestion module."""

import io
import pytest
import pandas as pd
from unittest.mock import patch
from fastapi import HTTPException
from file_ingestion import validate_cycle, validate_year, validate_file_type, ingest_file


class TestValidateCycle:
    def test_valid_cycles(self):
        for cycle in ["SRA", "SSG", "TSG", "MSG", "SMS"]:
            assert validate_cycle(cycle) == cycle

    def test_invalid_cycle_raises(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_cycle("INVALID")
        assert exc_info.value.status_code == 400


class TestValidateYear:
    def test_valid_year(self):
        assert validate_year(2025) == 2025

    def test_string_year_converted(self):
        assert validate_year("2025") == 2025

    def test_year_too_low_raises(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_year(1999)
        assert exc_info.value.status_code == 400

    def test_year_too_high_raises(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_year(9999)
        assert exc_info.value.status_code == 400

    def test_invalid_string_raises(self):
        with pytest.raises(HTTPException):
            validate_year("abc")


class TestValidateFileType:
    def test_csv_accepted(self):
        validate_file_type("text/csv")  # Should not raise

    def test_xlsx_accepted(self):
        validate_file_type("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    def test_pdf_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_file_type("application/pdf")
        assert exc_info.value.status_code == 400


class TestIngestFile:
    def test_csv_ingestion(self):
        csv_content = b"FULL_NAME,GRADE,DOR,TAFMSD,ASSIGNED_PAS,ASSIGNED_PAS_CLEARTEXT,DAFSC,PAFSC,DATE_ARRIVED_STATION,UIF_CODE,UIF_DISPOSITION_DATE,REENL_ELIG_STATUS,2AFSC,3AFSC,4AFSC,GRADE_PERM_PROJ\nDOE JOHN,SSG,01-Jan-2022,15-Jun-2016,ABCD,51 FSS,3F071,3F071,01-Mar-2020,0,,,,,,"
        df = ingest_file(csv_content, "test.csv")
        assert len(df) == 1
        assert "FULL_NAME" in df.columns

    def test_file_too_large_raises(self):
        # Create content larger than MAX_FILE_SIZE_MB
        with pytest.raises(HTTPException) as exc_info:
            huge_content = b"x" * (51 * 1024 * 1024)  # 51MB
            ingest_file(huge_content, "test.csv")
        assert exc_info.value.status_code == 400

    def test_unsupported_extension_raises(self):
        with pytest.raises(HTTPException) as exc_info:
            ingest_file(b"data", "test.pdf")
        assert exc_info.value.status_code == 400

    def test_missing_required_columns_raises(self):
        csv_content = b"COL_A,COL_B\n1,2"
        with pytest.raises(HTTPException) as exc_info:
            ingest_file(csv_content, "test.csv")
        assert exc_info.value.status_code == 400
        assert "Missing required columns" in str(exc_info.value.detail)

    def test_column_names_normalized_to_uppercase(self):
        csv_content = b"full_name,grade,dor,tafmsd,assigned_pas,assigned_pas_cleartext,dafsc,pafsc,date_arrived_station,uif_code,uif_disposition_date,reenl_elig_status,2afsc,3afsc,4afsc,grade_perm_proj\nDOE JOHN,SSG,01-Jan-2022,15-Jun-2016,ABCD,51 FSS,3F071,3F071,01-Mar-2020,0,,,,,,"
        df = ingest_file(csv_content, "test.csv")
        assert "FULL_NAME" in df.columns
