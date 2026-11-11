"""
Application configuration — CORS, sessions, paths, file handling, feature flags.

Changes when: deployment environment changes, new origins added, limits adjusted.
"""

import os
import tempfile

# ============================================================================
# FASTAPI / CORS
# ============================================================================

cors_origins = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:3000",
    "https://hammerhead-app-bqr7z.ondigitalocean.app",
    "https://api.pace-af-tool.com",
    "https://pace-af-tool.com",
    "https://www.api.pace-af-tool.com",
    "https://www.pace-af-tool.com",
    "http://pacetool.app",
    "https://pacetool.app",
    "http://www.pacetool.app",
    "https://www.pacetool.app",
    "http://test.pacetool.app",
    "https://test.pacetool.app",
]

allowed_types = [
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
]

# ============================================================================
# SESSION
# ============================================================================

session_ttl = 1800

SESSION_REQUIRED_KEYS = ['eligible_df', 'cycle', 'year', 'pascode_map']
SESSION_ID_LENGTH = 36
SESSION_CLEANUP_INTERVAL = 3600

# ============================================================================
# PATHS
# ============================================================================

TEMP_DIR = os.getenv("PACE_TEMP_DIR", tempfile.gettempdir())

images_dir = 'images'
default_logo = 'fiftyonefss.jpeg'
afpc_logo = 'afpc.png'

# ============================================================================
# FILE PROCESSING
# ============================================================================

MAX_FILE_SIZE_MB = 50
ALLOWED_FILE_EXTENSIONS = ['.csv', '.xlsx']

# ============================================================================
# UTILITY
# ============================================================================

small_unit_threshold = 10
max_name_length = 30
max_unit_length = 25

date_input_format = "%d-%b-%Y"
date_display_format = "%d %B %Y"

ACCOUNTING_DATE_OFFSET_DAYS = 119

# ============================================================================
# ERROR / RESPONSE CONSTANTS
# ============================================================================

DATA_VALIDATION_ERRORS = {
    'MISSING_COLUMNS': 'Missing required columns',
    'EMPTY_DATAFRAME': 'Uploaded file contains no data',
    'DUPLICATE_ENTRIES': 'Duplicate personnel entries detected',
    'INVALID_DATE_FORMAT': 'Invalid date format detected',
    'INVALID_GRADE': 'Invalid military grade detected',
    'MISSING_REQUIRED_DATA': 'Missing required data',
}

API_RESPONSES = {
    'UPLOAD_SUCCESS': 'Upload successful.',
    'PDF_GENERATION_FAILED': 'PDF generation failed',
    'SESSION_NOT_FOUND': 'Session not found',
    'INVALID_FILE_TYPE': 'Invalid file type. Only CSV or Excel files are allowed.',
    'PROCESSING_ERROR': 'Error processing data',
}

# ============================================================================
# LOGGING
# ============================================================================

LOG_LEVELS = {
    'DEBUG': 10,
    'INFO': 20,
    'WARNING': 30,
    'ERROR': 40,
    'CRITICAL': 50,
}

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# ============================================================================
# PERFORMANCE
# ============================================================================

MAX_RECORDS_PER_PDF = 10000
MAX_PASCODES_PER_SESSION = 100
PDF_GENERATION_TIMEOUT = 300
MAX_DATAFRAME_MEMORY_MB = 100
CHUNK_SIZE_FOR_LARGE_FILES = 1000

