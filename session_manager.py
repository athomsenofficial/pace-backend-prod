from io import BytesIO
import os
import json
import uuid
import logging
import redis
import pandas as pd
from dotenv import load_dotenv
import base64
from constants import session_ttl
from datetime import datetime
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    raise ValueError("REDIS_URL environment variable is required. Please set it in your .env file.")

_redis_client = None

def _get_redis():
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


# =============================================================================
# ENCRYPTION FOR CUI COMPLIANCE - Data at Rest Protection
# =============================================================================

def _get_encryption_key() -> bytes:
    """
    Get the encryption key for session data from environment.
    Generate a key with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    """
    key = os.getenv("SESSION_ENCRYPTION_KEY")
    if not key:
        raise ValueError(
            "SESSION_ENCRYPTION_KEY environment variable is required. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return key.encode()


_fernet_instance: Optional[Fernet] = None

def _get_fernet() -> Fernet:
    """Get cached Fernet instance for encryption/decryption."""
    global _fernet_instance
    if _fernet_instance is None:
        _fernet_instance = Fernet(_get_encryption_key())
    return _fernet_instance


def _encrypt_data(data: str) -> str:
    """Encrypt string data for storage."""
    fernet = _get_fernet()
    encrypted = fernet.encrypt(data.encode())
    return encrypted.decode()


def _decrypt_data(encrypted_data: str) -> str:
    """Decrypt string data from storage."""
    fernet = _get_fernet()
    decrypted = fernet.decrypt(encrypted_data.encode())
    return decrypted.decode()


def _is_encrypted(data: str) -> bool:
    """Check if data is a valid Fernet token."""
    try:
        decoded = base64.urlsafe_b64decode(data.encode())
        return len(decoded) >= 73 and decoded[0] == 0x80
    except Exception:
        return False


# =============================================================================
# SESSION MANAGEMENT FUNCTIONS
# =============================================================================

def create_session(processed_df: pd.DataFrame, pdf_df: pd.DataFrame, session_id: Optional[str] = None) -> str:
    if session_id is None:
        session_id = str(uuid.uuid4())

    def convert_datetime_columns(df):
        """Convert all datetime columns to strings before creating records"""
        df_copy = df.copy()
        for col in df_copy.columns:
            if pd.api.types.is_datetime64_any_dtype(df_copy[col]):
                df_copy[col] = df_copy[col].dt.strftime('%Y-%m-%d').fillna('')
            else:
                # Check for datetime objects in object columns
                if df_copy[col].dtype == 'object':
                    df_copy[col] = df_copy[col].apply(
                        lambda x: x.isoformat() if isinstance(x, (datetime, pd.Timestamp)) else x
                    )
        return df_copy

    # Convert datetime columns first
    processed_clean = convert_datetime_columns(processed_df)
    pdf_clean = convert_datetime_columns(pdf_df)

    def simple_sanitize(records):
        for record in records:
            for key, value in record.items():
                if pd.isna(value):
                    record[key] = None
        return records

    session_data = {
        "dataframe": simple_sanitize(processed_clean.to_dict(orient="records")),
        "pdf_dataframe": simple_sanitize(pdf_clean.to_dict(orient="records")),
    }

    # Encrypt session data before storing
    json_data = json.dumps(session_data)
    encrypted_data = _encrypt_data(json_data)

    _get_redis().set(session_id, encrypted_data, ex=session_ttl)
    return session_id


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    raw = _get_redis().get(session_id)
    if not raw:
        return None

    # Refresh TTL on access so active sessions don't expire
    _get_redis().expire(session_id, session_ttl)

    # Handle both encrypted and legacy unencrypted data
    if _is_encrypted(raw):
        try:
            decrypted = _decrypt_data(raw)
            return json.loads(decrypted)
        except Exception as e:
            logger.warning(f"Decryption failed for session {session_id}, trying as plain JSON: {e}")
            try:
                return json.loads(raw)
            except Exception as e2:
                logger.error(f"Failed to parse session data as JSON: {e2}")
                return None
    else:
        # Legacy unencrypted data
        return json.loads(raw)


def _comprehensive_sanitize(obj):
    """Recursively sanitize any datetime objects in nested structures."""
    if isinstance(obj, dict):
        return {k: _comprehensive_sanitize(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_comprehensive_sanitize(item) for item in obj]
    elif obj is None:
        return None
    elif isinstance(obj, float) and pd.isna(obj):
        return None
    elif isinstance(obj, (pd.Timestamp, datetime)):
        return obj.isoformat()
    elif hasattr(obj, 'isoformat'):
        try:
            return obj.isoformat()
        except Exception:
            return str(obj)
    else:
        return obj


def update_session(session_id: str, max_retries: int = 3, **kwargs) -> Optional[Dict[str, Any]]:
    """Update session with optimistic locking via Redis WATCH/MULTI/EXEC."""
    for attempt in range(max_retries):
        try:
            with _get_redis().pipeline() as pipe:
                pipe.watch(session_id)
                raw = pipe.get(session_id)
                if not raw:
                    return None

                # Decode session data
                if _is_encrypted(raw):
                    try:
                        decrypted = _decrypt_data(raw)
                        session = json.loads(decrypted)
                    except Exception as e:
                        logger.warning(f"Decryption failed in update_session for {session_id}, trying as plain JSON: {e}")
                        session = json.loads(raw)
                else:
                    session = json.loads(raw)

                # Apply updates
                for key, value in kwargs.items():
                    if isinstance(value, pd.DataFrame):
                        records = value.to_dict(orient="records")
                        session[key] = _comprehensive_sanitize(records)
                    else:
                        session[key] = _comprehensive_sanitize(value)

                # Atomic write
                json_data = json.dumps(session)
                encrypted_data = _encrypt_data(json_data)

                pipe.multi()
                pipe.set(session_id, encrypted_data, ex=session_ttl)
                pipe.execute()
                return session

        except redis.WatchError:
            if attempt < max_retries - 1:
                logger.info(f"Session {session_id[:8]} modified concurrently, retrying ({attempt + 1}/{max_retries})")
                continue
            logger.warning(f"Session {session_id[:8]} update failed after {max_retries} retries due to concurrent access")
            return None


def delete_session(session_id: str) -> None:
    _get_redis().delete(session_id)


def store_pdf_in_redis(session_id: str, pdf_buffer: BytesIO) -> None:
    """Store PDF in Redis with encryption."""
    pdf_bytes = pdf_buffer.getvalue()
    # Encrypt the PDF bytes
    encrypted = _encrypt_data(base64.b64encode(pdf_bytes).decode())
    _get_redis().set(f"{session_id}_pdf", encrypted, ex=session_ttl)


def get_pdf_from_redis(session_id: str) -> Optional[BytesIO]:
    """Retrieve and decrypt PDF from Redis."""
    encrypted = _get_redis().get(f"{session_id}_pdf")
    if not encrypted:
        return None

    # Handle both encrypted and legacy unencrypted data
    if _is_encrypted(encrypted):
        try:
            decrypted = _decrypt_data(encrypted)
            pdf_bytes = base64.b64decode(decrypted)
        except Exception as e:
            logger.warning(f"PDF decryption failed for {session_id}, trying as legacy unencrypted: {e}")
            pdf_bytes = base64.b64decode(encrypted)
    else:
        pdf_bytes = base64.b64decode(encrypted)

    return BytesIO(pdf_bytes)
