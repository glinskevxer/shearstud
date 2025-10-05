"""Reading and writing what was measured: gauges, campaigns and spectra.

Raw samples never reach the book of record. A week of one channel at 100 Hz is
sixty million numbers, and none of them is needed again once the cycles have
been counted. What is stored is the spectrum, plus the two fractions that say
how much of the record was not usable, because a spectrum with a third of its
record dropped out is a different piece of evidence from a clean one and nothing
downstream can tell them apart otherwise.

That is the one irreversible decision in this package. The samples are gone
after the count, so the counting parameters, the gate and the bin width, are
stored with the spectrum rather than assumed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from shearstud.errors import StorageError
from shearstud.signals.spectrum import Spectrum, SpectrumBin
from shearstud.store import db
from shearstud.structure.gauge import GaugeInstall


@dataclass(frozen=True, slots=True)
class CampaignRecord:
    """One measurement campaign on one structure."""

    campaign_id: str
    structure_number: str
    started_on: date
    ended_on: date
    seasonal_factor: float = 1.0
    note: str = ""

    def __post_init__(self) -> None:
        if not self.campaign_id.strip():
            raise StorageError("a campaign needs an id")
        if self.ended_on < self.started_on:
            raise StorageError(f"{self.campaign_id}: it ended before it started")
        if self.seasonal_factor <= 0.0:
            raise StorageError(f"{self.campaign_id}: seasonal factor is not a factor")

    @property
    def days(self) -> float:
        """How long the campaign ran, counting both end days."""
        return float((self.ended_on - self.started_on).days + 1)


@dataclass(frozen=True, slots=True)
class SpectrumQuality:
    """How much of a record was not usable."""

    dropout_frac: float = 0.0
    railed_frac: float = 0.0

    def __post_init__(self) -> None:
        for name, value in (("dropout", self.dropout_frac), ("railed", self.railed_frac)):
            if not 0.0 <= value <= 1.0:
                raise StorageError(f"{name} fraction {value} is outside zero to one")

    @property
    def usable_frac(self) -> float:
        """Share of the record that carried real strain."""
        return max(0.0, 1.0 - self.dropout_frac - self.railed_frac)

    @property
    def is_trustworthy(self) -> bool:
        """True when enough of the record survived to count cycles in.

        A rail hit is worse than a dropout: the dropout carries nothing and the
        rail hit carries an understatement, so any railing at all is a finding.
        """
        return self.railed_frac == 0.0 and self.dropout_frac < 0.10


def save_gauge(path: Path | str, install: GaugeInstall) -> None:
    """Write a gauge installation, replacing any earlier record of it."""
    with db.transaction(path) as connection:
        connection.execute("DELETE FROM gauges WHERE gauge_id = ?", (install.gauge_id,))
        connection.execute(
            "INSERT INTO gauges (gauge_id, detail_id, orientation, gauge_factor, "
            "installed_on, removed_on, channel_limit_ue) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                install.gauge_id,
                install.detail_id,
                install.orientation,
                install.gauge_factor,
                install.installed_on.isoformat(),
                None if install.removed_on is None else install.removed_on.isoformat(),
                install.channel_limit_ue,
            ),
        )


def load_gauges(path: Path | str, detail_id: str | None = None) -> list[GaugeInstall]:
    """Gauges on the structure, optionally narrowed to one detail."""
    if detail_id is None:
        rows = db.fetch_all(
            path,
            "SELECT gauge_id, detail_id, orientation, gauge_factor, installed_on, "
            "removed_on, channel_limit_ue FROM gauges ORDER BY gauge_id",
        )
    else:
        rows = db.fetch_all(
            path,
            "SELECT gauge_id, detail_id, orientation, gauge_factor, installed_on, "
            "removed_on, channel_limit_ue FROM gauges WHERE detail_id = ? ORDER BY gauge_id",
            (detail_id,),
        )
    return [
        GaugeInstall(
            gauge_id=str(row["gauge_id"]),
            detail_id=str(row["detail_id"]),
            orientation=str(row["orientation"]),
            gauge_factor=float(row["gauge_factor"]),
            installed_on=date.fromisoformat(str(row["installed_on"])),
            channel_limit_ue=float(row["channel_limit_ue"]),
            removed_on=(
                None if row["removed_on"] is None else date.fromisoformat(str(row["removed_on"]))
            ),
        )
        for row in rows
    ]


def save_campaign(path: Path | str, campaign: CampaignRecord) -> None:
    """Write a campaign, replacing any earlier record of it."""
    with db.transaction(path) as connection:
        connection.execute("DELETE FROM campaigns WHERE campaign_id = ?", (campaign.campaign_id,))
        connection.execute(
            "INSERT INTO campaigns (campaign_id, structure_number, started_on, "
            "ended_on, seasonal_factor, note) VALUES (?, ?, ?, ?, ?, ?)",
            (
                campaign.campaign_id,
                campaign.structure_number,
                campaign.started_on.isoformat(),
                campaign.ended_on.isoformat(),
                campaign.seasonal_factor,
                campaign.note,
            ),
        )


def load_campaigns(path: Path | str, structure_number: str) -> list[CampaignRecord]:
    """Campaigns on one structure, oldest first."""
    rows = db.fetch_all(
        path,
        "SELECT campaign_id, structure_number, started_on, ended_on, seasonal_factor, "
        "note FROM campaigns WHERE structure_number = ? ORDER BY started_on, campaign_id",
        (structure_number,),
    )
    return [
        CampaignRecord(
            campaign_id=str(row["campaign_id"]),
            structure_number=str(row["structure_number"]),
            started_on=date.fromisoformat(str(row["started_on"])),
            ended_on=date.fromisoformat(str(row["ended_on"])),
            seasonal_factor=float(row["seasonal_factor"]),
            note=str(row["note"]),
        )
        for row in rows
    ]


def save_spectrum(
    path: Path | str,
    campaign_id: str,
    spectrum: Spectrum,
    quality: SpectrumQuality | None = None,
) -> None:
    """Write one gauge's spectrum for one campaign, replacing what was there."""
    measured = quality or SpectrumQuality()
    with db.transaction(path) as connection:
        connection.execute(
            "DELETE FROM spectra WHERE campaign_id = ? AND gauge_id = ?",
            (campaign_id, spectrum.gauge_id),
        )
        connection.execute(
            "INSERT INTO spectra (campaign_id, gauge_id, bin_width_ue, dropout_frac, "
            "railed_frac) VALUES (?, ?, ?, ?, ?)",
            (
                campaign_id,
                spectrum.gauge_id,
                spectrum.bin_width_ue,
                measured.dropout_frac,
                measured.railed_frac,
            ),
        )
        connection.executemany(
            "INSERT INTO spectrum_bins (campaign_id, gauge_id, low_ue, count, "
            "representative_ue) VALUES (?, ?, ?, ?, ?)",
            [
                (campaign_id, spectrum.gauge_id, b.low_ue, b.count, b.representative_ue)
                for b in spectrum.bins
            ],
        )


def load_spectrum(path: Path | str, campaign_id: str, gauge_id: str) -> Spectrum:
    """Read one gauge's spectrum back."""
    head = db.fetch_one(
        path,
        "SELECT bin_width_ue FROM spectra WHERE campaign_id = ? AND gauge_id = ?",
        (campaign_id, gauge_id),
    )
    if head is None:
        raise StorageError(f"no spectrum for {gauge_id!r} in campaign {campaign_id!r}")
    width_ue = float(head["bin_width_ue"])
    rows = db.fetch_all(
        path,
        "SELECT low_ue, count, representative_ue FROM spectrum_bins "
        "WHERE campaign_id = ? AND gauge_id = ? ORDER BY low_ue",
        (campaign_id, gauge_id),
    )
    bins = tuple(
        SpectrumBin(
            low_ue=float(row["low_ue"]),
            width_ue=width_ue,
            count=float(row["count"]),
            representative_ue=float(row["representative_ue"]),
        )
        for row in rows
    )
    return Spectrum(gauge_id=gauge_id, bin_width_ue=width_ue, bins=bins)


def load_quality(path: Path | str, campaign_id: str, gauge_id: str) -> SpectrumQuality:
    """Read the two unusable fractions back."""
    row = db.fetch_one(
        path,
        "SELECT dropout_frac, railed_frac FROM spectra WHERE campaign_id = ? AND gauge_id = ?",
        (campaign_id, gauge_id),
    )
    if row is None:
        raise StorageError(f"no spectrum for {gauge_id!r} in campaign {campaign_id!r}")
    return SpectrumQuality(
        dropout_frac=float(row["dropout_frac"]), railed_frac=float(row["railed_frac"])
    )


def gauges_in_campaign(path: Path | str, campaign_id: str) -> list[str]:
    """Which gauges reported in one campaign, in id order."""
    rows = db.fetch_all(
        path,
        "SELECT gauge_id FROM spectra WHERE campaign_id = ? ORDER BY gauge_id",
        (campaign_id,),
    )
    return [str(row["gauge_id"]) for row in rows]
