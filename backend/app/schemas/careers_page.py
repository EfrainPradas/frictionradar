from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator
from datetime import datetime


class VisibleJobCard(BaseModel):
    title: Optional[str] = None
    location: Optional[str] = None
    area: Optional[str] = None
    job_url: Optional[str] = None

    @validator("title", "location", "area", "job_url")
    def not_empty(cls, v):
        if v is not None and not isinstance(v, str):
            return v
        return v


class CareersPageExtraction(BaseModel):
    page_type: str = Field(
        default="unknown",
        description="Type of page: careers_listing, jobs_search, ats_platform, unknown",
    )
    open_positions_count: Optional[int] = Field(
        default=None, description="Total number of open positions visible on the page"
    )
    visible_hiring_areas: List[str] = Field(
        default_factory=list, description="Visible hiring categories/areas/tabs"
    )
    visible_role_cards: List[VisibleJobCard] = Field(
        default_factory=list, description="Up to 20 visible job cards"
    )
    visible_locations: List[str] = Field(
        default_factory=list, description="Unique locations visible in job listings"
    )
    evidence_quality: str = Field(
        default="unknown",
        description="Quality of evidence: high, moderate, limited, none",
    )
    what_is_clearly_visible: List[str] = Field(
        default_factory=list,
        description="What is clearly visible in the rendered content",
    )
    what_is_still_unclear: List[str] = Field(
        default_factory=list,
        description="What information is not visible/not extractable",
    )

    source_url: Optional[str] = None
    captured_at: Optional[datetime] = None
    extraction_method: str = Field(
        default="unknown", description="Method used: ai, deterministic, fallback"
    )

    class Config:
        extra = "forbid"


class CareersPageSignals(BaseModel):
    open_positions_count_detected: bool = False
    high_open_positions_count_detected: bool = False
    job_cards_visible_detected: bool = False
    visible_hiring_area_detected: bool = False
    job_links_extracted: bool = False

    retail_hiring_detected: bool = False
    distribution_hiring_detected: bool = False
    manufacturing_hiring_detected: bool = False
    technology_hiring_detected: bool = False
    finance_hiring_detected: bool = False
    operations_hiring_detected: bool = False
    marketing_hiring_detected: bool = False
    sales_hiring_detected: bool = False
    customer_success_hiring_detected: bool = False
    supply_chain_hiring_detected: bool = False
    hr_people_hiring_detected: bool = False

    def to_signal_list(self) -> List[Dict[str, Any]]:
        signals = []

        if self.open_positions_count_detected:
            signals.append(
                {
                    "type": "open_positions_count_detected",
                    "text": "Open positions count visible on page",
                }
            )
        if self.high_open_positions_count_detected:
            signals.append(
                {
                    "type": "high_open_positions_count_detected",
                    "text": "High volume of open positions detected",
                }
            )
        if self.job_cards_visible_detected:
            signals.append(
                {
                    "type": "job_cards_visible_detected",
                    "text": "Job cards are visible on page",
                }
            )
        if self.visible_hiring_area_detected:
            signals.append(
                {
                    "type": "visible_hiring_area_detected",
                    "text": "Visible hiring areas/categories detected",
                }
            )
        if self.job_links_extracted:
            signals.append(
                {"type": "job_links_extracted", "text": "Job links extracted from page"}
            )

        area_signals = [
            ("retail_hiring_detected", "Retail"),
            ("distribution_hiring_detected", "Distribution"),
            ("manufacturing_hiring_detected", "Manufacturing"),
            ("technology_hiring_detected", "Technology"),
            ("finance_hiring_detected", "Finance"),
            ("operations_hiring_detected", "Operations"),
            ("marketing_hiring_detected", "Marketing"),
            ("sales_hiring_detected", "Sales"),
            ("customer_success_hiring_detected", "Customer Success"),
            ("supply_chain_hiring_detected", "Supply Chain"),
            ("hr_people_hiring_detected", "HR/People"),
        ]

        for signal_type, label in area_signals:
            if getattr(self, signal_type):
                signals.append(
                    {
                        "type": signal_type,
                        "text": f"{label} hiring detected on careers page",
                    }
                )

        return signals


AREA_KEYWORDS = {
    "retail": [
        "retail",
        "store",
        "cashier",
        "sales floor",
        "associate",
        "cashier",
        "stock",
        "merchandising",
    ],
    "distribution": [
        "distribution",
        "warehouse",
        "fulfillment",
        "logistics",
        "shipping",
        "supply chain",
    ],
    "manufacturing": [
        "manufacturing",
        "production",
        "factory",
        "assembly",
        "fabrication",
    ],
    "technology": [
        "technology",
        "tech",
        "engineering",
        "software",
        "it",
        "developer",
        "data",
        "security",
    ],
    "finance": ["finance", "accounting", "financial", "controller", "analyst"],
    "operations": ["operations", "ops", "program", "project", "program manager"],
    "marketing": ["marketing", "digital marketing", "brand", "content", "creative"],
    "sales": ["sales", "account executive", "business development", "representative"],
    "customer_success": ["customer success", "support", "service", "experience"],
    "supply_chain": ["supply chain", "procurement", "sourcing", "vendor"],
    "hr_people": ["hr", "human resources", "people", "talent", "recruiting"],
}

HIGH_VOLUME_THRESHOLD = 100
