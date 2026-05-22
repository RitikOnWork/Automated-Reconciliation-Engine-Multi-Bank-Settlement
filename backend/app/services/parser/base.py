from abc import ABC, abstractmethod
from typing import Dict, List


class BaseParser(ABC):
    @abstractmethod
    def parse(self, file_content: bytes, filename: str = "") -> List[Dict]:
        """
        Parses raw statement bytes and returns a list of standardized dictionaries representing transactions:
        [
            {
                "transaction_date": "YYYY-MM-DD",
                "value_date": "YYYY-MM-DD",
                "amount": float,
                "currency": "USD",
                "reference": "REF12345",
                "description": "WIRE FROM CLIENT",
                "bank_account": "ACC123"
            }
        ]
        """
        pass
