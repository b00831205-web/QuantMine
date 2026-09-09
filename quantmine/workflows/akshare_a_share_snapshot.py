from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import json
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import logging
from datetime import datetime, time, timezone

from ..http_resilience import (
    is_transient_http_error,
    retry_http_call,
)

import pandas as pd

SpotLoader = Callable[[str], pd.DataFrame]
SuspensionLoader = Callable[[str], pd.DataFrame]
Clock = Callable[[],datetime]

_REQUIRED_SPOT_COLUMNS = ("代码", "名称", "最新价", "成交量")
_REQUIRED_SUSPENSION_COLUMNS = ("代码", "名称", "停牌时间")
_A_SHARE_TIME_ZONE = ZoneInfo("Asia/Shanghai")
_LOGGER = logging.getLogger(__name__)
A_SHARE_RAW_SNAPSHOT_SCHEMA_VERSION = "a_share_raw_snapshot_v3"
_UPSTREAM_SOURCE_ATTR = "upstream_source"


class LiveSnapshotDateMismatchError(RuntimeError):
    """Raised when live data would be stored under a different date."""

class LiveSnapshotNotReadyError(RuntimeError):
    """Raised when the current market-day snapshot is requested too early"""

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

    snapshot_available_after: time = time(15,15)
    def __post_init__(self) -> None:
        if not isinstance(self.snapshot_available_after, time):
            raise TypeError("snapshot_available_after must be a time")

        if self.snapshot_available_after.tzinfo is not None:
            raise ValueError("snapshot_available_after must be a naive Asia/Shanghai local time")
    def collect(
            self,
            *,
            as_of_date: pd.Timestamp|str,
            root: Path
    ) -> AStockRawSnapshot:
        date = pd.Timestamp(as_of_date).normalize()

        observed_at = self.clock()

        _require_live_snapshot_date(
            date,
            observed_at = self.clock(),
        )

        _require_live_snapshot_available(
            date,
            observed_at = observed_at,
            available_after = self.snapshot_available_after,
        )

        date_text = date.date().isoformat()

        spot_loader = self.spot_loader or _default_spot_loader
        suspension_loader = (self.suspension_loader or _default_suspension_loader)

        spot = spot_loader(date.strftime("%Y%m%d"))
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
                "schema_version": A_SHARE_RAW_SNAPSHOT_SCHEMA_VERSION,
                "spot_source": spot.attrs.get(
                    _UPSTREAM_SOURCE_ATTR,
                    "custom",
                ),
                "spot_row_count": len(spot),
                "suspension_source": suspension.attrs.get(
                    _UPSTREAM_SOURCE_ATTR,
                    "custom",
                ),
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

def _default_spot_loader(date: str) -> pd.DataFrame:
    try:
        import akshare as ak
    except ImportError as error:
        raise RuntimeError(
            "AkShare support is not installed. "
            "Install quantmine with its 'data' extra"
        ) from error

    try:
        spot = retry_http_call(
            ak.stock_zh_a_spot_em,
            label = "AkShare Eastmoney A-share spot snapshot"
        )
        spot.attrs[_UPSTREAM_SOURCE_ATTR] = "eastmoney"
        return spot
    except Exception as error:
        if not is_transient_http_error(error):
            raise

        _LOGGER.warning(
            "Eastmoney A-share spot endpoint remained unavailable; "
            "falling back to the AkShare Sina endpoint"
        )
    spot = retry_http_call(
        ak.stock_zh_a_spot,
        label = "AkShare Sina A-share spot snapshot"
    )
    limit_up = retry_http_call(
        lambda: ak.stock_zt_pool_em(date= date),
        label = "AkShare A-share limit-up pool",
    )

    limit_down = retry_http_call(
        lambda: ak.stock_zt_pool_dtgc_em(date = date),
        label = "AkShare A-share limit-down pool",
    )

    result = _attach_limit_flags(
        spot,
        limit_up= limit_up,
        limit_down = limit_down,
    )
    result.attrs[_UPSTREAM_SOURCE_ATTR] = (
        "sina+eastmoney_limit_pools"
    )

    return result

def _default_suspension_loader(date: str) -> pd.DataFrame:
    try:
        import akshare as ak

    except ImportError as error:
        raise RuntimeError(
            "AkShare support is not installed. "
            "Install quantmine with its 'data' extra"
        ) from error


    suspension =  retry_http_call(
        lambda: ak.stock_tfp_em(date = date),
        label = "AkShare A-share suspension snapshot"
    )
    suspension.attrs[_UPSTREAM_SOURCE_ATTR] = "eastmoney"
    return suspension

def _attach_limit_flags(
        spot: pd.DataFrame,
        *,
        limit_up: pd.DataFrame,
        limit_down: pd.DataFrame
) -> pd.DataFrame:
    _validate_frame(
        spot,
        required_columns = _REQUIRED_SPOT_COLUMNS,
        label = "AkShare Sina A-share spot snapshot",
        allow_empty = False,
    )

    result = spot.copy()
    result["代码"] = _normalize_a_share_tickers(
        result["代码"],
        label = "AkShare Sina A-share spot snapshot"
    )

    result["is_limit_up"] = result["代码"].isin(
        _pool_tickers(limit_up, label = "limit-up pool")
    )
    result["is_limit_down"] = result["代码"].isin(
        _pool_tickers(limit_down, label = "limit-down pool")
    )
    return result


def _require_live_snapshot_available(
        as_of_date: pd.Timestamp,
        *,
        observed_at: datetime,
        available_after: time
) -> None:
    market_time = observed_at.astimezone(_A_SHARE_TIME_ZONE)

    if market_time.time() < available_after:
        raise LiveSnapshotNotReadyError(
            "live A-share snapshot for "
            f"{as_of_date.date().isoformat()} is not available before "
            f"{available_after.isoformat()} Asia/Shanghai; "
            f"observed at {market_time.isoformat()}"
        )

def _normalize_a_share_tickers(
        values: pd.Series,
        *,
        label: str
) -> pd.Series:
    tickers =(
        values.astype(str)
        .str.strip()
        .str.lower()
        .str.replace(r"^(?:sh|sz|bj)", "", regex = True)
        .str.zfill(6)
    )

    invalid = ~tickers.str.fullmatch(r"\d{6}")

    if invalid.any():
        samples = tickers.loc[invalid].head(5).tolist()
        raise ValueError(
            f"{label} contains invalid A-share ticker: {samples}"
        )
    return tickers

def _pool_tickers(frame: pd.DataFrame, *, label: str) -> set[str]:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{label} must be a pandas DataFrame")

    if frame.empty:
        return set()

    if "代码" not in frame.columns:
        raise ValueError(f"{label} is missing required columns: 代码")

    return set(
        _normalize_a_share_tickers(frame["代码"], label = label)
    )
