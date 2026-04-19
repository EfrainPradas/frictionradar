"""Sanity tests for FunctionInferenceEngine after Fix C/D/E/F.

Covers:
  - Fix D: "Inside Sales Representative" no longer junk.
  - Fix C: substring false positives no longer classify.
  - Fix E: coverage gaps (coordinator, facilities, tech lead, maintenance).
  - Fix F: reason_code is always set on the return dict.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.services.function_inference_engine import function_inference_engine as fie


# ── Fix D: Inside Sales must classify, not be junk ──────────────────────

def test_inside_sales_is_sales_not_junk():
    r = fie.infer_functional_area("Inside Sales Representative")
    assert r["area"] == "sales", r
    assert r["reason_code"] == "matched"


def test_inside_sales_manager():
    r = fie.infer_functional_area("Inside Sales Manager")
    assert r["area"] == "sales"


# ── Fix C: substring false positives no longer classify as finance ──────

def test_field_and_area_leader_is_not_finance():
    # Before: "ar" substring -> finance. Now: word boundary blocks it.
    r = fie.infer_functional_area("Field & Area Leader")
    assert r["area"] != "finance", r


def test_associate_portal_is_not_recruiting():
    # Before: "ta" substring in "portal" -> recruiting. Now: blocked.
    r = fie.infer_functional_area("Associate Portal")
    assert r["area"] != "recruiting_talent", r


def test_apparel_designer_is_not_finance():
    # Before: "ap" matched anything with "ap". Now: blocked.
    r = fie.infer_functional_area("Apparel Designer")
    assert r["area"] != "finance"


# ── Fix E: coverage gaps ────────────────────────────────────────────────

def test_tech_lead_is_engineering():
    r = fie.infer_functional_area("Tech Lead")
    assert r["area"] == "engineering", r


def test_technical_lead_is_engineering():
    r = fie.infer_functional_area("Technical Lead")
    assert r["area"] == "engineering", r


def test_administrative_coordinator_is_operations():
    r = fie.infer_functional_area("Administrative Coordinator")
    assert r["area"] == "operations", r


def test_facilities_manager_is_operations():
    r = fie.infer_functional_area("Facilities Manager")
    assert r["area"] == "operations", r


def test_maintenance_mechanic_is_operations():
    r = fie.infer_functional_area("Maintenance Mechanic - Nights")
    assert r["area"] == "operations", r


def test_general_manager_is_operations():
    r = fie.infer_functional_area("General Manager")
    assert r["area"] == "operations"


# ── Positive cases that must keep working ───────────────────────────────

@pytest.mark.parametrize(
    "title,expected",
    [
        ("Senior Data Analyst", "data_analytics"),
        ("Software Engineer", "engineering"),
        ("Backend Engineer", "engineering"),
        ("Product Manager", "product"),
        ("Accounts Payable Specialist", "finance"),
        ("Accounts Receivable Clerk", "finance"),
        ("Financial Analyst", "finance"),
        ("Customer Success Manager", "customer_success"),
        ("Talent Acquisition Partner", "recruiting_talent"),
        ("Recruiting Coordinator", "recruiting_talent"),
        ("Marketing Manager", "marketing"),
        ("Content Marketing Specialist", "marketing"),
        ("Supply Chain Analyst", "supply_chain"),
        ("Demand Planner", "supply_chain"),
        ("Machine Operator", "manufacturing"),
        ("Store Manager", "retail"),
        ("IT Support Technician", "it"),
        ("HR Business Partner", "hr_people"),
        ("General Counsel", "legal_compliance"),
    ],
)
def test_positive_classifications(title, expected):
    r = fie.infer_functional_area(title)
    assert r["area"] == expected, f"{title} -> {r}"
    assert r["reason_code"] == "matched"


# ── Junk/unknown paths: all must emit a reason_code ─────────────────────

@pytest.mark.parametrize(
    "title,expected_area",
    [
        ("About Us", "junk"),
        ("What you'll do", "junk"),
        ("Post Date: 12-19-25", "junk"),
        ("Apr 13, 2026", "junk"),  # invalid_title:contains_date
        ("Marketing", "junk"),  # too_short_no_role (1 word, no role indicator)
        ("Join our Talent Community to get alerts", "junk"),  # sentence_fragment
    ],
)
def test_junk_paths_have_reason_code(title, expected_area):
    r = fie.infer_functional_area(title)
    assert r["area"] == expected_area
    assert "reason_code" in r
    assert r["reason_code"] != ""
    assert r["reason_code"] != "matched"


def test_unknown_has_reason_code():
    # Title that passes validation but matches no keyword family.
    r = fie.infer_functional_area("Goode XTR Pro Athlete Advisor")
    # Either unknown or a family; either way, reason_code must be set.
    assert "reason_code" in r
    assert r["reason_code"] != ""


# ── Word-boundary invariants ────────────────────────────────────────────

def test_word_boundary_finance_ar_not_matched():
    """'area' should not trigger finance via 'ar' substring."""
    r = fie.infer_functional_area("Operations Area Lead")
    assert r["area"] != "finance"


def test_word_boundary_product_pm_not_matched():
    """'pmi' must not match product via 'pm'."""
    r = fie.infer_functional_area("PMI Program Operations")
    assert r["area"] != "product"


def test_ap_clerk_still_finance_via_full_phrase():
    """Accounts Payable Clerk still classifies as finance."""
    r = fie.infer_functional_area("Accounts Payable Clerk")
    assert r["area"] == "finance"


# ── Fix G1: new junk patterns and department labels ────────────────────

@pytest.mark.parametrize(
    "title",
    [
        # Product/pricing listings
        "Visa Debit Card",
        "Fundz Visa Debit Card",
        "LIMITED EDITION: STARS AND STRIPES - PRO SERIES",
        "Goode XTR Pro Regular price $2,190",
        # Corporate PR / announcements
        "7-Eleven, Inc. Supports Local Communities on 7Cares Day",
        "7-Eleven, Inc. Celebrates 7Cares Day",
        "Fortune ® World's Most Admired Companies",
        "Forbes' America's Best Professional Recruiting Firms",
        "Deloitte: A recognized leader for top talent",
        # Site navigation
        "Saved Jobs (0)",
        "Search by job title, location, department",
        "All Departments All Locations",
        "Job Search Filter",
        "Tips & Tricks",
        "Who We Are",
        "Meet our people",
        "Meet our sustainability program leader",
        "Partner Directory",
        "Channel Partner Directory",
        "Developers for Hire",
        "Customer StoriesLearn how leading brands grow their business",
        # Department labels
        "Engineering",
        "Leadership",
        "Software Engineering",
        "Hardware Engineering",
        "Internships",
        "Internship Program",
        "Our Culture",
    ],
)
def test_g1_junk_titles_caught(title):
    r = fie.infer_functional_area(title)
    assert r["area"] == "junk", f"{title!r} -> {r}"
    assert r["reason_code"] in {"junk_title", "invalid_title:navigation_element",
                                "invalid_title:marketing_copy",
                                "invalid_title:too_short_no_role",
                                "invalid_title:sentence_fragment"}, r


def test_g1_testimonial_prefix_is_junk():
    r = fie.infer_functional_area("– Emily, Senior Associate of Team and Culture")
    assert r["area"] == "junk", r


# ── Fix G2: new operations/engineering/marketing/supply_chain keywords ──

def test_g2_administrative_assistant_is_operations():
    r = fie.infer_functional_area("Administrative Assistant II")
    assert r["area"] == "operations", r


def test_g2_assistant_manager_is_operations():
    r = fie.infer_functional_area("Assistant Manager")
    assert r["area"] == "operations", r


def test_g2_executive_assistant_is_operations():
    r = fie.infer_functional_area("Executive Personal Assistant C-level")
    assert r["area"] == "operations", r


def test_g2_solution_architect_is_engineering():
    r = fie.infer_functional_area("Solution Architect (.NET, Cloud, AI)")
    assert r["area"] == "engineering", r


def test_g2_data_architect_is_engineering():
    r = fie.infer_functional_area("Data Warehousing Architect")
    assert r["area"] == "engineering", r


def test_g2_motion_designer_is_marketing():
    r = fie.infer_functional_area("Senior Motion Designer")
    assert r["area"] == "marketing", r


def test_g2_graphic_designer_is_marketing():
    r = fie.infer_functional_area("Graphic Designer")
    assert r["area"] == "marketing", r


def test_g2_driver_is_supply_chain():
    r = fie.infer_functional_area("OTR Driver")
    assert r["area"] == "supply_chain", r


def test_g2_cdl_driver_is_supply_chain():
    r = fie.infer_functional_area("CDL Driver - Regional Routes")
    assert r["area"] == "supply_chain", r


# ── Fix G3: healthcare family ──────────────────────────────────────────

def test_g3_nurse_is_healthcare():
    r = fie.infer_functional_area("Licensed Practical Nurse - Evening Shift")
    assert r["area"] == "healthcare", r


def test_g3_registered_nurse_is_healthcare():
    r = fie.infer_functional_area("Registered Nurse")
    assert r["area"] == "healthcare", r


def test_g3_physician_is_healthcare():
    r = fie.infer_functional_area("Physician - Internal Medicine")
    assert r["area"] == "healthcare", r


def test_g3_pharmacist_is_healthcare():
    r = fie.infer_functional_area("Community Pharmacist")
    assert r["area"] == "healthcare", r


def test_g3_medical_assistant_is_healthcare():
    r = fie.infer_functional_area("Medical Assistant")
    assert r["area"] == "healthcare", r


def test_g3_therapist_is_healthcare():
    r = fie.infer_functional_area("Physical Therapist")
    assert r["area"] == "healthcare", r


def test_g3_phlebotomist_is_healthcare():
    r = fie.infer_functional_area("Phlebotomist II")
    assert r["area"] == "healthcare", r


def test_g3_healthcare_has_signal_type():
    r = fie.infer_functional_area("Registered Nurse")
    assert r["signal"] == "healthcare_hiring"
