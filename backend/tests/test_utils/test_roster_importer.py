"""Tests for the roster importer — fully offline, no network, no live API.

Uses a small in-memory .xlsx fixture (via openpyxl) and an SQLite DB
(inherited from conftest.py).
"""

import os
import tempfile

import openpyxl
import pytest

from utils.roster_importer import (
    ImportResult,
    RosterRow,
    _normalize_handle,
    _parse_agency_flag,
    parse_roster_xlsx,
    upsert_roster,
)
from models import Influencer
from database import SessionLocal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_roster_xlsx(rows, path):
    """Create a minimal .xlsx with the expected sheet/column structure."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "List"
    # Headers (10 columns)
    ws.append(["Niche", "Name", "Username", "Profile Link", "Contact Info",
               "Location", "Followers", "Average views", " Talent agency", "Approved "])
    for row in rows:
        ws.append(row)
    wb.save(path)
    wb.close()


@pytest.fixture
def roster_xlsx(tmp_path):
    """Create a temporary roster .xlsx with 3 test rows."""
    xlsx_path = str(tmp_path / "test_roster.xlsx")
    _make_roster_xlsx([
        ["Gaming", None, "@TestCreatorA", "https://youtube.com/@TestCreatorA/videos",
         "a@example.com", "United States", None, None, "YES", None],
        ["Tech", "Bob", "@TestCreatorB", "https://youtube.com/@TestCreatorB/videos",
         "b@example.com", "Germany", None, None, "NO", None],
        ["Gaming", None, "@TestCreatorC", "https://youtube.com/@TestCreatorC/videos",
         None, "United Kingdom", None, None, None, None],
    ], xlsx_path)
    return xlsx_path


@pytest.fixture
def roster_xlsx_with_empties(tmp_path):
    """Roster with some empty/blank rows that should be skipped."""
    xlsx_path = str(tmp_path / "test_roster_empties.xlsx")
    _make_roster_xlsx([
        ["Gaming", None, "@ValidCreator", "https://youtube.com/@ValidCreator",
         "v@example.com", "US", None, None, "YES", None],
        [None, None, None, None, None, None, None, None, None, None],  # empty row
        [None, None, "  ", None, None, None, None, None, None, None],  # blank handle
        ["Tech", None, "@AnotherValid", "https://youtube.com/@AnotherValid",
         None, None, None, None, "NO", None],
    ], xlsx_path)
    return xlsx_path


# ---------------------------------------------------------------------------
# Unit tests — pure functions
# ---------------------------------------------------------------------------

class TestNormalizeHandle:
    def test_strips_at_and_lowercases(self):
        assert _normalize_handle("@BananaSlamJamma") == "bananaslamjamma"

    def test_strips_whitespace(self):
        assert _normalize_handle("  @Hutts ") == "hutts"

    def test_no_at_prefix(self):
        assert _normalize_handle("robokast") == "robokast"

    def test_empty_string(self):
        assert _normalize_handle("") == ""


class TestParseAgencyFlag:
    def test_yes(self):
        assert _parse_agency_flag("YES") is True

    def test_no(self):
        assert _parse_agency_flag("NO") is False

    def test_none_returns_none(self):
        assert _parse_agency_flag(None) is None

    def test_case_insensitive(self):
        assert _parse_agency_flag("yes") is True
        assert _parse_agency_flag("No") is False

    def test_unknown_returns_none(self):
        assert _parse_agency_flag("maybe") is None


# ---------------------------------------------------------------------------
# Integration tests — parsing the .xlsx
# ---------------------------------------------------------------------------

class TestParseRosterXlsx:
    def test_parses_correct_row_count(self, roster_xlsx):
        rows = parse_roster_xlsx(roster_xlsx)
        assert len(rows) == 3

    def test_handle_normalized(self, roster_xlsx):
        rows = parse_roster_xlsx(roster_xlsx)
        assert rows[0].handle == "testcreatora"
        assert rows[0].raw_handle == "@TestCreatorA"

    def test_email_captured(self, roster_xlsx):
        rows = parse_roster_xlsx(roster_xlsx)
        assert rows[0].email == "a@example.com"
        assert rows[2].email is None

    def test_agency_flag_parsed(self, roster_xlsx):
        rows = parse_roster_xlsx(roster_xlsx)
        assert rows[0].talent_agency is True
        assert rows[1].talent_agency is False
        assert rows[2].talent_agency is None

    def test_niche_and_location(self, roster_xlsx):
        rows = parse_roster_xlsx(roster_xlsx)
        assert rows[0].niche == "Gaming"
        assert rows[1].location == "Germany"

    def test_skips_empty_rows(self, roster_xlsx_with_empties):
        rows = parse_roster_xlsx(roster_xlsx_with_empties)
        assert len(rows) == 2
        handles = [r.handle for r in rows]
        assert "validcreator" in handles
        assert "anothervalid" in handles

    def test_wrong_sheet_name_raises(self, tmp_path):
        xlsx_path = str(tmp_path / "bad_sheet.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "WrongName"
        wb.save(xlsx_path)
        wb.close()
        with pytest.raises(ValueError, match="Sheet.*not found"):
            parse_roster_xlsx(xlsx_path)

    def test_name_field_captured(self, roster_xlsx):
        rows = parse_roster_xlsx(roster_xlsx)
        assert rows[1].name == "Bob"
        assert rows[0].name is None


# ---------------------------------------------------------------------------
# Integration tests — upserting into the DB
# ---------------------------------------------------------------------------

class TestUpsertRoster:
    def test_creates_new_influencers(self, roster_xlsx):
        rows = parse_roster_xlsx(roster_xlsx)
        db = SessionLocal()
        try:
            result = upsert_roster(db, rows)
            assert result.created == 3
            assert result.updated == 0
            assert result.skipped == 0

            # Verify DB state.
            all_inf = db.query(Influencer).filter(Influencer.platform == "youtube").all()
            assert len(all_inf) == 3
            handles = {inf.source_handle for inf in all_inf}
            assert handles == {"testcreatora", "testcreatorb", "testcreatorc"}
        finally:
            db.close()

    def test_idempotent_reimport(self, roster_xlsx):
        rows = parse_roster_xlsx(roster_xlsx)
        db = SessionLocal()
        try:
            # First import
            result1 = upsert_roster(db, rows)
            assert result1.created == 3

            # Second import — should update, not duplicate.
            result2 = upsert_roster(db, rows)
            assert result2.created == 0
            assert result2.updated == 3

            all_inf = db.query(Influencer).filter(Influencer.platform == "youtube").all()
            assert len(all_inf) == 3
        finally:
            db.close()

    def test_unresolved_platform_id_prefix(self, roster_xlsx):
        rows = parse_roster_xlsx(roster_xlsx)
        db = SessionLocal()
        try:
            upsert_roster(db, rows)
            inf = db.query(Influencer).filter(
                Influencer.source_handle == "testcreatora"
            ).first()
            assert inf is not None
            assert inf.platform_id.startswith("unresolved:")
        finally:
            db.close()

    def test_email_and_agency_stored(self, roster_xlsx):
        rows = parse_roster_xlsx(roster_xlsx)
        db = SessionLocal()
        try:
            upsert_roster(db, rows)
            inf = db.query(Influencer).filter(
                Influencer.source_handle == "testcreatora"
            ).first()
            assert inf.business_email == "a@example.com"
            assert inf.talent_agency is True

            inf_b = db.query(Influencer).filter(
                Influencer.source_handle == "testcreatorb"
            ).first()
            assert inf_b.talent_agency is False
        finally:
            db.close()

    def test_display_name_from_name_field(self, roster_xlsx):
        rows = parse_roster_xlsx(roster_xlsx)
        db = SessionLocal()
        try:
            upsert_roster(db, rows)
            inf_b = db.query(Influencer).filter(
                Influencer.source_handle == "testcreatorb"
            ).first()
            assert inf_b.display_name == "Bob"
        finally:
            db.close()
