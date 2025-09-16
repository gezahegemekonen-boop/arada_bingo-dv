import re

def is_valid_phone(phone):
    """
    Validates Ethiopian phone numbers.
    Accepts formats like: 0912345678, +251912345678, 251912345678
    """
    pattern = r'^(?:\+251|251|0)?9\d{8}$'
    return bool(re.match(pattern, phone))
