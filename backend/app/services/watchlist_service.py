from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import re

class WatchlistProvider(ABC):
    @abstractmethod
    def check_watchlist(self, full_name: Optional[str], document_number: Optional[str]) -> Optional[Dict[str, Any]]:
        """Queries watchlist database for matching identity records."""
        pass


class MockWatchlistProvider(WatchlistProvider):
    """
    Simulated Sandbox Watchlist Provider.
    
    IMPORTANT NOTICE:
    SIMULATED DATA — NOT CONNECTED TO GOVERNMENT SYSTEMS OR REAL LAW ENFORCEMENT.
    Contains solely fictional sample entries for demonstration purposes.
    """

    LABEL = "DEMO WATCHLIST — SIMULATED DATA — NOT CONNECTED TO GOVERNMENT SYSTEMS"

    # Fictional demonstration targets
    DEMO_WATCHLIST: List[Dict[str, Any]] = [
        {
            "watchlist_id": "WL-SIM-2026-081",
            "name": "VIKTOR KOROL",
            "document_number": "P8892144",
            "category": "Travel Alert (Simulated)",
            "reason": "Simulated stolen passport blank alert in demonstration scenario.",
            "severity": "CRITICAL"
        },
        {
            "watchlist_id": "WL-SIM-2026-094",
            "name": "ELENA ROSTOVA",
            "document_number": "A9938210",
            "category": "Document Revocation (Simulated)",
            "reason": "Simulated administrative document cancellation notice in test catalog.",
            "severity": "HIGH"
        },
        {
            "watchlist_id": "WL-SIM-2026-103",
            "name": "MARCUS VANCE",
            "document_number": "M7744112",
            "category": "Inquiry Flag (Simulated)",
            "reason": "Simulated secondary customs examination request.",
            "severity": "MEDIUM"
        }
    ]

    def check_watchlist(self, full_name: Optional[str], document_number: Optional[str]) -> Optional[Dict[str, Any]]:
        clean_doc = re.sub(r'[^A-Za-z0-9]', '', document_number or '').upper()
        clean_name = re.sub(r'[^A-Za-z\s]', '', full_name or '').upper().strip()

        for entry in self.DEMO_WATCHLIST:
            entry_doc = re.sub(r'[^A-Za-z0-9]', '', entry["document_number"]).upper()
            entry_name = entry["name"].upper()

            # Check document number match or name match
            if clean_doc and entry_doc == clean_doc:
                return {
                    "matched": True,
                    "provider": self.LABEL,
                    "entry": entry,
                    "match_field": "Document Number",
                    "explanation": f"Document ID matched simulated test record {entry['watchlist_id']} ({entry['category']})."
                }

            if clean_name and (entry_name == clean_name or entry_name in clean_name):
                return {
                    "matched": True,
                    "provider": self.LABEL,
                    "entry": entry,
                    "match_field": "Full Name",
                    "explanation": f"Identity matched simulated test record {entry['watchlist_id']} ({entry['category']})."
                }

        return None


def get_watchlist_provider() -> WatchlistProvider:
    return MockWatchlistProvider()
