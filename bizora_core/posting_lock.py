"""
Global Posting Lock to prevent recursive signal loops in voucher posting.

This module provides a singleton lock that ensures only one posting operation
can execute at a time across the entire application. This prevents recursive
signal loops where UI updates trigger multiple concurrent posting operations.
"""

import threading

# Global lock instance - shared across all posting operations
_lock = threading.Lock()


def is_busy() -> bool:
    """
    Check if the posting lock is currently held.
    
    Returns:
        True if the lock is held (posting is in progress), False otherwise
    """
    return _lock.locked()


def acquire(blocking: bool = False) -> bool:
    """
    Attempt to acquire the posting lock.
    
    Args:
        blocking: If True, block until lock is acquired. If False, return immediately.
    
    Returns:
        True if lock was acquired, False if lock is already held (when blocking=False)
    """
    return _lock.acquire(blocking=blocking)


def release() -> None:
    """
    Release the posting lock.
    
    This should only be called by the thread that currently holds the lock.
    """
    _lock.release()
