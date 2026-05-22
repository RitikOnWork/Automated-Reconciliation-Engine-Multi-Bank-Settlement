import re
from typing import Any

def mask_pan(
    value: str,
    visible_prefix: int = 4,
    visible_suffix: int = 4,
    mask_char: str = "*"
) -> str:
    """
    PCI-DSS compliant Primary Account Number (PAN) & bank account masking utility.
    Obfuscates sensitive digits while preserving space/dash layout structures.
    
    Example:
      "1234-5678-9012-3456" -> "1234-****-****-3456"
      "ACC-987654321-OPS"   -> "ACC-*****4321-OPS" or similar depending on visible indices.
    """
    if not value:
        return ""
        
    val_str = str(value).strip()
    
    # If the string length is very short, keep only last 2 digits visible
    if len(val_str) <= (visible_prefix + visible_suffix):
        if len(val_str) <= 2:
            return mask_char * len(val_str)
        return (mask_char * (len(val_str) - 2)) + val_str[-2:]

    # Separate digits/letters from space/dashes, mask only alphanumeric components
    chars = list(val_str)
    
    # We want to identify the alphanumeric indices
    alpha_indices = [i for i, c in enumerate(chars) if c.isalnum()]
    
    if len(alpha_indices) <= (visible_prefix + visible_suffix):
        # Fallback if there are too few alphanumeric characters
        for idx in alpha_indices[:-2]:
            chars[idx] = mask_char
        return "".join(chars)
        
    # Mask indices between the prefix boundary and suffix boundary
    mask_indices = alpha_indices[visible_prefix : -visible_suffix]
    for idx in mask_indices:
        chars[idx] = mask_char
        
    return "".join(chars)
