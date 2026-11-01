"""Normalize native database revisions before internal model contracts/JSON.

HTTP contracts continue to require strict Python integers. Call this helper
only for values read from the authoritative native model-runtime records.
"""
from decimal import Decimal


def native_revision(value):
    if type(value) is int:
        revision=value
    elif isinstance(value,Decimal) and value.is_finite() and value==value.to_integral_value():
        revision=int(value)
    else:
        raise ValueError('A native database revision must be a positive integer')
    if revision<1:raise ValueError('A native database revision must be a positive integer')
    return revision
