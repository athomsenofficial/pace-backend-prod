"""Shared file ingestion — parse, validate, and normalize uploaded roster files."""

import io
import pandas as pd
import openpyxl
from fastapi import HTTPException
from constants import (
    allowed_types, MAX_FILE_SIZE_MB,
    MIN_PROMOTION_CYCLE_YEAR, MAX_PROMOTION_CYCLE_YEAR,
    REQUIRED_COLUMNS, OPTIONAL_COLUMNS, PDF_COLUMNS,
    MAX_RECORDS_PER_PDF, MAX_DATAFRAME_MEMORY_MB,
)

VALID_CYCLES = ["SRA", "SSG", "TSG", "MSG", "SMS"]


def validate_cycle(cycle: str) -> str:
    if cycle not in VALID_CYCLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid cycle. Must be one of: {', '.join(VALID_CYCLES)}",
        )
    return cycle


def validate_year(year: int) -> int:
    try:
        year = int(year)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Year must be a valid integer")
    if year < MIN_PROMOTION_CYCLE_YEAR or year > MAX_PROMOTION_CYCLE_YEAR:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid year. Must be between {MIN_PROMOTION_CYCLE_YEAR} and {MAX_PROMOTION_CYCLE_YEAR}",
        )
    return year


def validate_file_type(content_type: str) -> None:
    if content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only CSV or Excel files are allowed.",
        )


def ingest_file(contents: bytes, filename: str, logger=None, required_columns=None) -> pd.DataFrame:
    """Parse, validate, and normalize a roster file upload. Raises HTTPException on failure.

    ``required_columns`` defaults to the promotion-roster REQUIRED_COLUMNS. Callers
    with a different column contract (e.g. recurring rosters, which resolve header
    aliases first) pass their own list, or ``[]`` to skip the check here.
    """
    if required_columns is None:
        required_columns = REQUIRED_COLUMNS
    def log(level, msg):
        if logger:
            getattr(logger, level)(msg)

    # Validate file size
    file_size_bytes = len(contents)
    log("info", f"  File size: {file_size_bytes} bytes")
    max_size_bytes = MAX_FILE_SIZE_MB * 1024 * 1024
    if file_size_bytes > max_size_bytes:
        log("error", f"  FAILED: File too large ({file_size_bytes / 1024 / 1024:.2f}MB)")
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE_MB}MB",
        )

    # Parse file based on extension
    if filename.endswith(".csv"):
        log("info", "  Parsing CSV file")
        df = _parse_csv(contents, logger)
    elif filename.endswith(".xlsx"):
        log("info", "  Parsing Excel file")
        df = _parse_xlsx(contents, logger)
    else:
        raise HTTPException(status_code=400, detail="Unsupported file extension.")

    log("info", f"  File parsed successfully: {len(df)} rows, {len(df.columns)} columns")

    # Filter empty rows first (so limits apply to real data only)
    initial_rows = len(df)
    df = df.dropna(how="all")
    if len(df) < initial_rows:
        log("info", f"  Filtered out {initial_rows - len(df)} empty rows")

    # Enforce record count limit
    if len(df) > MAX_RECORDS_PER_PDF:
        log("error", f"  FAILED: Too many records ({len(df)}). Maximum is {MAX_RECORDS_PER_PDF}")
        raise HTTPException(
            status_code=400,
            detail=f"File contains too many records ({len(df)}). Maximum is {MAX_RECORDS_PER_PDF}.",
        )

    # Enforce memory limit
    memory_mb = df.memory_usage(deep=True).sum() / (1024 * 1024)
    if memory_mb > MAX_DATAFRAME_MEMORY_MB:
        log("error", f"  FAILED: DataFrame too large ({memory_mb:.1f}MB). Maximum is {MAX_DATAFRAME_MEMORY_MB}MB")
        raise HTTPException(
            status_code=400,
            detail=f"File data exceeds memory limit ({memory_mb:.0f}MB). Maximum is {MAX_DATAFRAME_MEMORY_MB}MB.",
        )

    # Normalize columns
    df.columns = df.columns.astype(str).str.strip().str.upper()
    log("info", "  Normalized column names to uppercase")

    # Strip whitespace from string columns
    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].apply(lambda x: x.strip() if isinstance(x, str) else x)

    # Validate required columns
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        log("error", f"  FAILED: Missing required columns: {', '.join(missing)}")
        log("info", f"  Available columns: {', '.join(df.columns.tolist())}")
        raise HTTPException(
            status_code=400,
            detail=f"Missing required columns: {', '.join(missing)}",
        )

    return df


def prepare_session_dataframes(df: pd.DataFrame):
    """Produce (processed_df, pdf_df) for create_session(). Raises HTTPException if PDF columns missing."""
    available_optional = [col for col in OPTIONAL_COLUMNS if col in df.columns]
    # Per-member bookkeeping (stable `_uid`, editor flags) travels with the source roster
    # so a re-process keeps the reviewer's adds, deletes, edits and overrides.
    available_meta = [col for col in ('_uid', '_manual', '_override', '_override_reason', 'deleted', 'deletion_reason')
                      if col in df.columns]
    columns_to_keep = REQUIRED_COLUMNS + available_optional + available_meta
    processed_df = df[columns_to_keep].copy()

    missing_pdf = [col for col in PDF_COLUMNS if col not in processed_df.columns]
    if missing_pdf:
        raise HTTPException(
            status_code=400,
            detail=f"Missing PDF columns: {', '.join(missing_pdf)}",
        )

    pdf_df = processed_df[PDF_COLUMNS].copy()
    return processed_df, pdf_df


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_csv(contents: bytes, logger=None) -> pd.DataFrame:
    """Parse CSV with multi-encoding fallback."""
    for encoding in ("utf-8", "cp1252", "latin1"):
        try:
            return pd.read_csv(io.BytesIO(contents), encoding=encoding)
        except UnicodeDecodeError:
            if logger:
                logger.warning(f"  {encoding} decoding failed, trying next encoding")
    raise HTTPException(status_code=400, detail="Could not decode CSV file with any supported encoding.")


def _parse_xlsx(contents: bytes, logger=None) -> pd.DataFrame:
    """Parse XLSX, searching for first non-empty sheet if needed."""
    try:
        df = pd.read_excel(io.BytesIO(contents), sheet_name=0, engine="openpyxl")
    except TypeError:
        if logger:
            logger.warning("  openpyxl styling error, retrying with data_only workbook")
        wb = openpyxl.load_workbook(io.BytesIO(contents), data_only=True, read_only=True)
        ws = wb.active
        data = list(ws.values)
        wb.close()
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data[1:], columns=data[0])

    if not df.empty:
        return df

    if logger:
        logger.warning("  First sheet is empty, checking other sheets...")
    wb = openpyxl.load_workbook(io.BytesIO(contents), data_only=True, read_only=True)
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        data = list(ws.values)
        if data and len(data) > 1:
            test_df = pd.DataFrame(data[1:], columns=data[0])
            if not test_df.empty:
                if logger:
                    logger.info(f"  Using sheet '{sheet_name}' which contains data")
                wb.close()
                return test_df
    wb.close()

    return df
