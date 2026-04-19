"""ATS adapter registry.

Maps ATSPlatform → adapter instance. Used by the dispatcher to
route extraction to the correct vendor-specific implementation.
"""

from app.extraction.constants import ATSPlatform

from .greenhouse import GreenhouseAdapter
from .lever import LeverAdapter
from .ashby import AshbyAdapter

# Registry: platform enum → adapter instance
# Add new adapters here as they're implemented.
ATS_ADAPTERS = {
    ATSPlatform.GREENHOUSE: GreenhouseAdapter(),
    ATSPlatform.LEVER: LeverAdapter(),
    ATSPlatform.ASHBY: AshbyAdapter(),
}
