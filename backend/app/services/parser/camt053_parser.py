from app.services.parser.camt053 import (
    CAMT053Parser,
    CAMT053ParserError,
    CAMT053ValidationError,
    CAMT053RowParsingError,
)

# Alias for standard import compatibility and standalone naming conventions
class CAMT053XMLParser(CAMT053Parser):
    """
    High-fidelity CAMT.053 XML Parser alias.
    Inherits all production-grade namespace resolution and batch decoupling capabilities.
    """
    pass
