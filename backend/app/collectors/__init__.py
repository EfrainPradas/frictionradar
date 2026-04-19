from .base import BaseCollector
from .company_site import CompanySiteCollector
from .careers import CareersCollector
from .ats_public import AtsPublicCollector
from .newsroom import NewsroomCollector
from .dynamic_careers import DynamicCareersCollector

# All active collectors — order matters: cheaper/faster collectors run first.
ACTIVE_COLLECTORS = [
    CompanySiteCollector(),       # Homepage scan: careers links, ATS embeds, friction keywords
    CareersCollector(),           # Multi-path careers finder + signal extraction
    AtsPublicCollector(),         # ATS platform detection (Greenhouse, Lever, Ashby, etc.)
    NewsroomCollector(),          # /news page for press releases / growth signals
    DynamicCareersCollector(),    # Fallback: category detection from careers pages
]
