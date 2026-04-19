#!/usr/bin/env python
import sys

sys.path.insert(0, ".")
import urllib3

urllib3.disable_warnings()
from app.collectors import ACTIVE_COLLECTORS

print("_active_collectors=" + str([c.collector_type for c in ACTIVE_COLLECTORS]))
