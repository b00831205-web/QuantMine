from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import json
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

SpotLoader = Callable[[], pd.DataFrame]
SuspensionLoader = Callable[[str], pd.DataFrame]
Clock = Callable[[],datetime]

_REQUIRED_SPOT_COLUMNS = ("代码", "名称", "最新价", "成交量")
_REQUIRED_SUSPENSION_COLUMNS = ("代码", "名称", "停牌时间")
_A_SHARE_TIME_ZONE = ZoneInfo("Asia/Shanghai")


class LiveSnapshotDateMismatchError(RuntimeError):
    """Raised when live data would be stored under a different date."""

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

@dataclass(frozen = True)
class AStockRawSnapshot:
    output_dir: Path
    spot_path: Path
    suspension_path: Path
    manifest_path: Path
    spot_row_count: int
    suspension_row_count: int

@dataclass(frozen = True)
class AkShareAStockRawSnapshotCollector:
    """Collect and immutably persist one forward_only daily raw snapshot"""
    spot_loader: SpotLoader | None = field(
        default=None,
        repr=False,
        compare=False
    )

    suspension_loader: SuspensionLoader | None = field(
        default=None,
        repr= False,
        compare=False,
    )

    clock: Clock = field(
        default = _utc_now,
        repr = False,
        compare = False,
    )

    def collect(
            self,
            *,
            as_of_date: pd.Timestamp|str,
            root: Path
    ) -> AStockRawSnapshot:
        date = pd.Timestamp(as_of_date).normalize()

        _require_live_snapshot_date(
            date,
            observed_at = self.clock(),
        )

        date_text = date.date().isoformat()

        spot_loader = self.spot_loader or _default_spot_loader
        suspension_loader = (self.suspension_loader or _default_suspension_loader)

        spot = spot_loader()
        suspension = suspension_loader(date.strftime("%Y%m%d"))

        _validate_frame(
            spot,
            required_columns = _REQUIRED_SPOT_COLUMNS,
            label = "AkShare A-share spot snapshot",
            allow_empty = False
        )

        _validate_frame(
            suspension,
            required_columns = _REQUIRED_SUSPENSION_COLUMNS,
            label="Akshare suspension snapshot",
            allow_empty=True,
        )

        output_dir = root / "akshare_a_share_raw" / date_text
        spot_path = output_dir/"spot.parquet"
        suspension_path = output_dir / "suspension.parquet"
        manifest_path = output_dir / "manifest.json"

        if output_dir.exists():
            raise FileExistsError(
                f"raw AkShare snapshot already exists for {date_text}: {output_dir}"
            )

        output_dir.parent.mkdir(parents=True, exist_ok = True)
        staging_dir = output_dir.parent / f".{date_text}.staging-{uuid4().hex}"
        staging_dir.mkdir()

        try:
            spot.to_parquet(staging_dir / "spot.parquet", index = False)
            suspension.to_parquet(staging_dir / "suspension.parquet", index = False)

            manifest = {
                "as_of_date": date_text,
                "provider": "akshare",
                "spot_row_count": len(spot),
                "suspension_row_count": len(suspension),
            }
            (staging_dir / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii = False, sort_keys=True, indent = 2),
                encoding= "utf-8"

            )

            staging_dir.replace(output_dir)
        except Exception:
            if staging_dir.exists():
                for path in staging_dir.iterdir():
                    path.unlink()
                staging_dir.rmdir()
            raise

        return AStockRawSnapshot(
            output_dir= output_dir,
            spot_path = spot_path,
            suspension_path= suspension_path,
            manifest_path= manifest_path,
            spot_row_count= len(spot),
            suspension_row_count= len(suspension),
        )

def _require_live_snapshot_date(
        as_of_date: pd.Timestamp,
        *,
        observed_at: datetime,
) -> None:
    """Prevent a live response from being labelled as another market date."""

    if not isinstance(observed_at, datetime):
        raise TypeError(
            "snapshot clock must return a datetime"
        )

    if (
        observed_at.tzinfo is None
        or observed_at.utcoffset() is None
    ):
        raise ValueError(
            "snapshot clock must return a timezone-aware datetime."
        )
    current_market_date = pd.Timestamp(
        observed_at.astimezone(_A_SHARE_TIME_ZONE).date()
    )

    if as_of_date != current_market_date:
        raise LiveSnapshotDateMismatchError(
            "refusing to label live AkShare data as "
            f"{as_of_date.date().isoformat()}; "
            "the current Asia/Shanghai market date is "
            f"{current_market_date.date().isoformat()}. "
            "An existing immutable historical snapshot may be replayed, "
            "but a missing historical snapshot cannot be reconstructed "
            "from the live endpoint."
        )

def _validate_frame(
        frame: object,
        *,
        required_columns: tuple[str, ...],
        label:  str,
        allow_empty: bool,
) -> None:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{label} must be a pandas DataFrame")

    if frame.empty and not allow_empty:
        raise ValueError(f"{label} is empty")

    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(
            f"{label} is missing required columns: {', '.join(missing)}"
        )

def _default_spot_loader() -> pd.DataFrame:
    try:
        import akshare as ak
    except ImportError as error:
        raise RuntimeError(
            "AkShare support is not installed. "
            "Install quantmine with its 'data' extra"
        ) from error

    return ak.stock_zh_a_spot_em()

def _default_suspension_loader(date: str) -> pd.DataFrame:
    try:
        import akshare as ak

    except ImportError as error:
        raise RuntimeError(
            "AkShare support is not installed. "
            "Install quantmine with its 'data' extra"
        ) from error

    return ak.stock_tfp_em(date=date)
