"""Shared test fixtures for ics_append tests."""

import pandas as pd
import pytest

from ics_append.settings import Settings


@pytest.fixture
def base_dir(tmp_path):
    """Create a base directory structure with client folders."""
    base = tmp_path / "ics"
    base.mkdir()
    return base


@pytest.fixture
def sample_settings(base_dir):
    """Settings instance pointing at temp base_dir."""
    return Settings(base_dir=base_dir)


@pytest.fixture
def client_dir(base_dir):
    """Create a client folder with ID 1453."""
    d = base_dir / "1453"
    d.mkdir()
    return d


@pytest.fixture
def sample_ref_df():
    """Synthetic REF file data."""
    return pd.DataFrame(
        {
            "Account Number": ["ABC123", "DEF456", "GHI789", "JKL012", "MNO345"],
            "Name": ["Alice", "Bob", "Carol", "Dave", "Eve"],
        }
    )


@pytest.fixture
def sample_dm_df():
    """Synthetic DM file data."""
    return pd.DataFrame(
        {
            "Acct Hash": ["DEF456", "PQR678", "STU901", "VWX234"],
            "Status": ["Active", "Active", "Closed", "Active"],
        }
    )


@pytest.fixture
def sample_odd_df():
    """Synthetic ODD file with account numbers."""
    return pd.DataFrame(
        {
            "Acct Number": [
                "ABC123",
                "DEF456",
                "GHI789",
                "JKL012",
                "MNO345",
                "PQR678",
                "STU901",
                "VWX234",
                "YZA567",
                "BCD890",
            ],
            "Stat Code": ["O", "O", "O", "C", "O", "O", "C", "O", "O", "O"],
            "Debit?": ["Yes", "No", "Yes", "No", "Yes", "Yes", "No", "Yes", "No", "Yes"],
            "Business?": ["No", "No", "Yes", "No", "No", "No", "No", "Yes", "No", "No"],
            "Curr Bal": [1000, 2000, 500, 0, 15000, 3000, 0, 8000, 25000, 12000],
            "Date Opened": pd.to_datetime(
                [
                    "2024-01-15",
                    "2024-03-20",
                    "2023-06-01",
                    "2022-11-10",
                    "2025-01-05",
                    "2024-07-18",
                    "2023-09-22",
                    "2024-12-01",
                    "2025-02-14",
                    "2024-05-30",
                ]
            ),
            "Prod Code": ["100", "200", "100", "300", "200", "100", "400", "200", "100", "300"],
            "Branch": [
                "Main",
                "North",
                "South",
                "Main",
                "East",
                "North",
                "South",
                "West",
                "Main",
                "East",
            ],
            "Source": ["DM", "REF", "Blank", "Web", "DM", "REF", "Blank", "DM", "Web", "REF"],
        }
    )


@pytest.fixture
def sample_merged_df():
    """Merged ICS accounts (REF+DM combined)."""
    return pd.DataFrame(
        {
            "Acct Hash": [
                "ABC123",
                "DEF456",
                "GHI789",
                "JKL012",
                "MNO345",
                "PQR678",
                "STU901",
                "VWX234",
            ],
            "Source": ["REF", "REF", "REF", "REF", "REF", "DM", "DM", "DM"],
        }
    )


@pytest.fixture
def ref_excel(client_dir, sample_ref_df):
    """Write a REF Excel file to the client directory."""
    path = client_dir / "1453-ICS_Detailed Referral-2026.01.xlsx"
    sample_ref_df.to_excel(path, index=False)
    return path


@pytest.fixture
def dm_excel(client_dir, sample_dm_df):
    """Write a DM Excel file to the client directory."""
    path = client_dir / "1453-Direct Mail New Accounts-2026.01.xlsx"
    sample_dm_df.to_excel(path, index=False)
    return path


@pytest.fixture
def odd_excel(client_dir, sample_odd_df):
    """Write an ODD Excel file to the client directory."""
    path = client_dir / "1453_oddd.xlsx"
    sample_odd_df.to_excel(path, index=False)
    return path


@pytest.fixture
def merged_excel(client_dir, sample_merged_df):
    """Write a merged ICS accounts file."""
    path = client_dir / "1453-ICS Accounts-All-2026.01.xlsx"
    sample_merged_df.to_excel(path, index=False)
    return path
