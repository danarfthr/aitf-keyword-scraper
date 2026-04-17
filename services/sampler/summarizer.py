from typing import Optional, Tuple
from shared.shared.constants import SUMMARY_CHAR_THRESHOLD

def summarize_body(body: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (body_to_store, summary_to_store).

    If len(body) > SUMMARY_CHAR_THRESHOLD:
        body_to_store   = None          (do not store — saves column space)
        summary_to_store = body[:SUMMARY_CHAR_THRESHOLD] + "... [truncated]"
    Else:
        body_to_store   = body
        summary_to_store = None
    """
    if not body:
        return None, None
        
    if len(body) > SUMMARY_CHAR_THRESHOLD:
        return None, body[:SUMMARY_CHAR_THRESHOLD] + "... [truncated]"
    
    return body, None
