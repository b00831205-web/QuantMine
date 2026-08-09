"""Market data download from Yahoo Finance.

Downloads run in batches with a checkpoint per batch, so a long run interrupted
by rate limiting resumes instead of restarting. Batches that exhaust their
retries are logged to ``failed_batches.json`` for ``retry_batches`` to pick up
later, and a blacklist file excludes names that should never be requested.

Empty columns are recorded but never auto-blacklisted: under rate limiting a
live ticker also comes back empty, and blacklisting it would silently shrink
the universe on every subsequent run. Genuine delistings are handled by the
point-in-time membership table instead.
"""
import yfinance as yf
import pandas as pd
import time
import json
import glob
import os
import hashlib
import pandas_datareader.data as web
from typing import Literal

def is_delisted_error(msg: str, ignore_json: json)-> bool:
    """Check whether an error message matches any delisting keyword.

    Args:
        msg: Error message to inspect.
        ignore_json: Iterable of keyword strings used to detect delisting.

    Returns:
        True if any keyword appears in the message, otherwise False.
    """
    msg = msg.lower()
    return any(kw in msg for kw in ignore_json)

def load_blacklist(checkpoint_dir:str)-> set :
    """Load the ticker blacklist from the checkpoint directory.

    Args:
        checkpoint_dir: Directory containing ``blacklist.json``.

    Returns:
        A set of blacklisted tickers. Returns an empty set if the file does not
        exist.
    """
    path = os.path.join(checkpoint_dir, "blacklist.json")
    if not os.path.exists(path):
        return set()
    with open(path) as f:
        return set(json.load(f))
    
def get_ff3(start_date: str, end_date: str, save_path: str, format: Literal['csv', 'parquet']):
    """Download Fama-French 3-factor data and save it under ``save_path``.

    Args:
        start_date: Start date in ``YYYY-MM-DD`` format.
        end_date: End date in ``YYYY-MM-DD`` format.
        save_path: Directory relative to the working directory; created if
            missing.
        format: Output format, ``csv`` or ``parquet``.

    Returns:
        The downloaded factor data as returned by pandas-datareader.

    Raises:
        ValueError: If ``format`` is neither csv nor parquet.
    """
    if format not in ('csv', 'parquet'):
        raise ValueError(f'{format} format error')
    start_date = pd.to_datetime(start_date)
    end_date = pd.to_datetime(end_date)
    output_path = os.path.join(os.getcwd(), save_path)
    
    if not os.path.exists(output_path):
        os.makedirs(output_path)

    ff3 = web.DataReader('F-F_Research_Data_Factors', 'famafrench', start_date, end_date)
    if format == 'csv':
        ff3.to_csv(os.path.join(output_path, 'F-F_Research_Data_Factors.csv'))
    if format == 'parquet':
        ff3.to_parquet(os.path.join(output_path, 'F-F_Research_Data_Factors.parquet'))
    return ff3
    
    
def set_blacklist(keyword: list | str, checkpoint_dir:list):
    """Add one or more keywords to the blacklist file.

    Args:
        keyword: A single keyword or a list of keywords to add.
        checkpoint_dir: Directory where the blacklist file is stored.

    Returns:
        None.

    Notes:
        The directory is created automatically if it does not already exist.
    """
    if isinstance(keyword, str):
        keyword = [keyword]
    os.makedirs(checkpoint_dir, exist_ok=True)
    existing = load_blacklist(checkpoint_dir)
    updated = list(existing | set(keyword))
    
    blacklist_path = os.path.join(checkpoint_dir, "blacklist.json")
    with open(blacklist_path, "w") as f:
        json.dump(updated, f, indent=2)
    print(f"Blacklist updated: added {keyword}, total {len(keyword)}")
    
def save_blacklist(tickers: list, checkpoint_dir:str):
    """Persist a list of tickers into the blacklist file.

    Args:
        tickers: Tickers to append to the blacklist.
        checkpoint_dir: Directory where ``blacklist.json`` is stored.

    Returns:
        None.
    """
    os.makedirs(checkpoint_dir, exist_ok=True)
    path = os.path.join(checkpoint_dir, "blacklist.json")
    existing = load_blacklist(checkpoint_dir)
    updated = list(existing | set(tickers))
    with open(path, "w") as f:
        json.dump(updated,f, indent=2)
    print(f"Blacklist updated: {updated}")

def download_batch_with_retry(batch: list, start_date: str, end_date:str, batch_index:int , task_checkpoint_dir: str,max_retries:int =3, wait: int =60, auto_adjust: bool = True, file_prefix: str = 'batch') ->pd.DataFrame | None :
        """Download one batch of tickers, resuming from its checkpoint if present.

        Args:
            batch: Tickers for this batch.
            start_date: Start date in ``YYYY-MM-DD`` format.
            end_date: End date in ``YYYY-MM-DD`` format.
            batch_index: 1-based batch number, used in the checkpoint filename.
            task_checkpoint_dir: Directory holding this task's checkpoints.
            max_retries: Attempts before giving up on the batch.
            wait: Seconds between attempts.
            auto_adjust: Whether to request adjusted prices. Market-cap callers
                pass False, since adjusted prices distort cross-sectional size.
            file_prefix: Checkpoint filename prefix. Callers writing a second
                kind of price data must change it, otherwise
                ``merge_checkpoints`` would glob those files as ordinary bars
                and silently mix adjusted with unadjusted closes.

        Returns:
            The downloaded frame, or None once retries are exhausted; in that
            case the batch is appended to ``failed_batches.json``.

        Notes:
            Requests are serialized (``threads=False``) because concurrent
            requests trigger Yahoo rate limiting, which surfaces misleadingly
            as "possibly delisted".
        """
        checkpoint_path = os.path.join(task_checkpoint_dir, f"{file_prefix}_{batch_index}.parquet")
        if os.path.exists(checkpoint_path):
            print(f"{batch_index} already exist")
            return pd.read_parquet(checkpoint_path)

        for attempt in range(max_retries):
            try:
                #threads=False: 串行请求, 避免并发触发Yahoo限流(429被误报成"possibly delisted")
                #timeout=30: 单请求超时, 卡住快速失败而非无限挂起
                data = yf.download(batch, start=start_date, end=end_date,
                                auto_adjust=auto_adjust, progress=False,
                                threads=False, timeout=30)
                if data.empty:
                    raise ValueError("Empty data returned")
                if isinstance(data.columns, pd.MultiIndex):
                    close = data["Close"]
                    empty_tickers = close.columns[close.isnull().all()].tolist()
                    #不再自动拉黑: 空列多为限流的真实票, 拉黑会永久排除它们, 越跑数据越少。
                    #真退市由历史成分股表(带end_date)判定; 这里只记录不排除。
                    if empty_tickers:
                        print(f"Empty columns (not blacklisted): {empty_tickers}")
                data.to_parquet(checkpoint_path)
                return data
            except Exception as e:
                print(f"Attempt {attempt+1} failed: {e}")
                if attempt < max_retries - 1:
                    print(f"Retrying after {wait} seconds...")
                    time.sleep(wait)
        failed_log = os.path.join(task_checkpoint_dir, "failed_batches.json")
        existing_failed = set()
        if os.path.exists(failed_log):
            with open(failed_log, encoding="utf-8") as failed_file:
                for line in failed_file:
                    if line.strip():
                        existing_failed.add(json.loads(line)["batch_index"])

        if batch_index not in existing_failed:
            with open(failed_log, mode="a", encoding="utf-8") as failed_file:
                json.dump(
                    {"batch_index": batch_index, "tickers": batch},
                    failed_file,
                )
                failed_file.write("\n")
        print(f"Batch {batch_index} failed, logging to {failed_log}")
        return None 

def data_acquisition(
    tickers: list,
    start_date: str,
    end_date: str,
    batch_size: int,
    max_retries: int = 3,
    wait: int = 60,
    checkpoint_dir: str = "tmp/checkpoint",
    batch_wait: float = 1.0,
    shares_start_date: str | None = None,
    auto_adjust: bool = True,
    file_prefix: str = 'batch',
    with_market_cap: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Download historical price, volume, and market-cap data in batches.

    Args:
        tickers: List of tickers to download.
        start_date: Start date in ``YYYY-MM-DD`` format.
        end_date: End date in ``YYYY-MM-DD`` format.
        batch_size: Number of tickers per download batch.
        max_retries: Maximum retries for each batch download.
        wait: Seconds to wait between retry attempts.
        checkpoint_dir: Directory used to store batch checkpoints and logs.
        batch_wait: Seconds to sleep between batches, to ease Yahoo rate limits.
        shares_start_date: Start date for the share-count history. Defaults to
            ``start_date``. Set it earlier than the price window so the sparse
            share series has a value to forward-fill from on day one.
        auto_adjust: Reserved for callers that need raw prices from the price
            leg; the market-cap leg always downloads unadjusted prices.
        file_prefix: Checkpoint filename prefix for the price leg.
        with_market_cap: When False, skip the market-cap leg entirely and
            return empty frames for it. Price-only consumers should pass False
            to avoid the per-ticker share-count requests.

    Returns:
        A tuple of ``(close, volume, shares, market_cap)``. All four are wide
        date-by-ticker frames. ``shares`` and ``market_cap`` are empty frames
        when ``with_market_cap`` is False.

    Notes:
        Each batch is cached to disk so repeated runs can resume from existing
        checkpoint files.
    """
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if max_retries <= 0:
        raise ValueError("max_retries must be positive")

    # A stable order is essential: checkpoint names are batch-number based.
    # Without this normalization, a resumed run could load another ticker's
    # checkpoint when the caller originally supplied a set.
    tickers = sorted(set(tickers))
    task_signature = hashlib.md5(f'{sorted(tickers)}_{start_date}_{end_date}'.encode()).hexdigest()[:8]
    task_checkpoint_dir = os.path.join(checkpoint_dir,task_signature)
    os.makedirs(task_checkpoint_dir,exist_ok=True)
      
    all_close = []
    all_volume = []
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i: i+batch_size]
        batch_index= i//batch_size+1
        print(f"downloading batch{batch_index} ... \ntickers {i} - {min(len(tickers), (i+batch_size))}")
        data = download_batch_with_retry(batch=batch, start_date=start_date, end_date=end_date, max_retries=max_retries, wait=wait, batch_index=batch_index, task_checkpoint_dir = task_checkpoint_dir)
        if data is not None:
            if isinstance(data.columns, pd.MultiIndex):
                all_close.append(data['Close'])
                all_volume.append(data['Volume'])
        if batch_wait > 0:
            time.sleep(batch_wait)
    
    if not all_close:
        raise RuntimeError(
            "No market-data batch succeeded; inspect "
            f"{os.path.join(task_checkpoint_dir, 'failed_batches.json')}"
        )
    close = pd.concat(all_close, axis=1)
    volume = pd.concat(all_volume, axis=1)
    # 价格-only 消费者(如 datareader)传 with_market_cap=False, 跳过逐票 get_shares_full 网络开销
    if not with_market_cap:
        return close, volume, pd.DataFrame(), pd.DataFrame()
    shares, market_cap = acquire_market_cap(
        tickers=tickers,
        start_date=start_date,
        end_date=end_date,
        batch_size=batch_size,
        max_retries=max_retries,
        wait=wait,
        checkpoint_dir=checkpoint_dir,
        batch_wait=batch_wait,
        shares_start_date=shares_start_date,
    )
    return close, volume, shares, market_cap



def retry_batches(start_date: str, end_date: str, max_retries: int, checkpoint_dir: str = "tmp/checkpoint", wait: int =60)->pd.DataFrame | None:
    """Retry batches that previously failed to download.

    Args:
        start_date: Start date in ``YYYY-MM-DD`` format.
        end_date: End date in ``YYYY-MM-DD`` format.
        max_retries: Maximum retries per failed batch.
        checkpoint_dir: Directory containing failure logs and checkpoints.
        wait: Seconds to wait between retry attempts.

    Returns:
        A tuple of ``(close_dataframe, volume_dataframe)`` if any batch is
        recovered, otherwise ``(None, None)``.

    Notes:
        The function reads ``failed_batches.json`` and retries only the batches
        recorded there.
    """
    black_list = load_blacklist(checkpoint_dir)
    failed_log = os.path.join(checkpoint_dir, "failed_batches.json") #failure log
    retry_log = os.path.join(checkpoint_dir, "retry_log.json") #retry log
    if not os.path.exists(failed_log):
        print("No failed batches need to be processed")
        return None, None
    failed = []
    with open(failed_log) as f:
        for line in f:
            failed.append(json.loads(line))

    retry_count = 1
    if os.path.exists(retry_log):
        with open(retry_log) as f: #read the retry log to find the last retry round number
            records = [json.loads(line) for line in f if line.strip()]
            if records:
                retry_count = records[-1]["retry_call"] +1
    print(f"Retry round {retry_count}, {len(failed)} batches failed in total")

    
    still_failed=[]
    retry_records = []
    success_close=[]
    success_volume=[]

    for record in failed:
        batch_index = record["batch_index"]
        batch = [
            ticker
            for ticker in record["tickers"]
            if ticker not in black_list
        ]

        if not batch:
            print(f"Batch {record['batch_index']} is fully blacklisted, skipping")
            retry_records.append({
                "retry_call": retry_count,
                "batch_index": record["batch_index"],
                "status": "skipped_blacklist",
                "attempts": 0,
            })
            continue
        
        checkpoint_path = os.path.join(checkpoint_dir, f"batch_{batch_index}.parquet")
        print(f"Retrying batch {batch_index}")
        success = False
        for attempt in range(max_retries):
            try:
                data = yf.download(batch, start=start_date, end=end_date,
                                auto_adjust=True, progress=False,
                                threads=False, timeout=30)
                if data.empty:
                    raise ValueError("Empty data returned")
                retry_records.append({
                    "retry_call":retry_count,
                    "batch_index": batch_index,
                    "status": "success",
                    "attempts": attempt + 1
                })
                data.to_parquet(checkpoint_path)
                if isinstance(data.columns, pd.MultiIndex):
                    success_close.append(data['Close'])
                    success_volume.append(data['Volume'])
                print(f"{batch} succeeded!")
                success = True
                break
            except Exception as e:
                print(f"Attempt {attempt+1} failed: {e}")
                if attempt < max_retries - 1:
                    print(f"Retrying after {wait} seconds...")
                    time.sleep(wait)
        if not success:
            print(f"Batch {batch} still failed to download")
            retry_records.append({
                    "retry_call":retry_count,
                    "batch_index": batch_index,
                    "status": "failed",
                    "attempts": max_retries
                })
            still_failed.append(record)
        
    with open(failed_log, "w") as f:
        for record in still_failed: #rewrite the failure log with the batches that still fail
            json.dump(record, f)
            f.write("\n")

    with open(retry_log, "a") as f: #append this round's attempts to the retry log
        for record in retry_records:
            json.dump(record, f)
            f.write("\n")
    if still_failed:
        print(f"Still {len(still_failed)} batches failed to download")
    else:
        print("All previously failed batches succeeded")
    if success_volume:
        volume = pd.concat(success_volume,axis=1)
        close = pd.concat(success_close,axis=1)
        return close, volume
    else:
        return None, None
    

def merge_checkpoints(checkpoint_dir: str = "tmp/checkpoint", file_prefix: str = 'batch') -> tuple:
    """Merge all batch checkpoint files into full close and volume tables.

    Args:
        checkpoint_dir: Directory containing ``batch_*.parquet`` checkpoint
            files.

    Returns:
        A tuple of ``(close_dataframe, volume_dataframe)``.

    Notes:
        Only parquet files with a MultiIndex column layout are merged.
    """
    files = sorted(glob.glob(os.path.join(checkpoint_dir, "**", f"{file_prefix}_*.parquet"), recursive=True),
                   key=lambda x: int(os.path.basename(x).split(f'{file_prefix}_')[1].split('x')[0]),)
    
    all_close, all_volume = [], []
    for f in files:
        data = pd.read_parquet(f)
        if isinstance(data.columns, pd.MultiIndex):
            all_close.append(data["Close"])
            all_volume.append(data["Volume"])
    
    if not all_close:
        return pd.DataFrame(), pd.DataFrame()

    close = pd.concat(all_close, axis=1)
    volume = pd.concat(all_volume, axis=1)
    return close, volume

def acquire_market_cap(
        tickers: list, start_date: str, end_date: str, batch_size,
        max_retries: int=3, wait: int=60, checkpoint_dir: str = 'tmp/checkpoint',
        batch_wait = 1.0, shares_start_date: str| None = None
)-> tuple[pd.DataFrame, pd.DataFrame]:
    """Download share counts and derive market capitalization.

    Market cap is ``unadjusted close * shares outstanding``. Adjusted prices
    must not be used here: the adjustment factor differs per ticker, which
    distorts the cross-sectional size ordering that market-cap weighting
    depends on.

    Args:
        tickers: Tickers to download. Blacklisted names are dropped.
        start_date: Price-window start in ``YYYY-MM-DD`` format.
        end_date: Price-window end in ``YYYY-MM-DD`` format.
        batch_size: Number of tickers per price-download batch.
        max_retries: Maximum retries per price batch and per share request.
        wait: Seconds to wait between retry attempts.
        checkpoint_dir: Directory used to store checkpoints.
        batch_wait: Seconds to sleep between price batches.
        shares_start_date: Start date for the share history. Defaults to
            ``start_date``.

    Returns:
        A tuple of ``(shares, market_cap)`` as wide date-by-ticker frames,
        aligned to the price index. Tickers whose share count cannot be
        fetched stay NaN and therefore drop out of any weighting downstream.

    Notes:
        Prices download in batches, but share counts have no batch endpoint and
        are fetched one ticker at a time, each with its own checkpoint file.
        ``get_shares_full`` is called without ``end``: passing it makes the
        request fail outright, and the trailing surplus is trimmed by the
        reindex onto the price index anyway.
    """
    tickers = sorted(set(tickers) - load_blacklist(checkpoint_dir))
    task_sig = hashlib.md5(
        f'{tickers}_{start_date}_{end_date}'.encode()).hexdigest()[:8]
    task_dir = os.path.join(checkpoint_dir, task_sig, 'mcap')
    os.makedirs(task_dir, exist_ok=True)

    px_batches = []
    for i in range(0, len(tickers), batch_size):
        data = download_batch_with_retry(
            batch =tickers[i: i+batch_size],
            start_date= start_date,
            end_date= end_date,
            batch_index= i//batch_size+1,
            task_checkpoint_dir=task_dir,
            max_retries = max_retries,
            wait = wait,
            auto_adjust=False,
            file_prefix='mcap_px'
        )
        if data is not None and isinstance(data.columns, pd.MultiIndex):
            px_batches.append(data['Close'])
        time.sleep(batch_wait)
    price = pd.concat(px_batches, axis=1)
    price.index = price.index.tz_localize(None)

    shares = {}
    for t in price.columns:
        # 单票 checkpoint: 股本端点易被 Yahoo 限流, 缓存避免重跑裸打 + 加剧限流
        cp = os.path.join(task_dir, f'shares_{t}.parquet')
        if os.path.exists(cp):
            shares[t] = pd.read_parquet(cp)['shares']
            continue
        # 和价格一致的重试: 一次性裸调遇到抖动会让整列归零
        s = None
        for attempt in range(max_retries):
            try:
                # 不传 end: yfinance 该端点带 end 常直接失败; 末端多抓无害, 后面 reindex 会裁到价格窗口
                s = yf.Ticker(t).get_shares_full(start=shares_start_date or start_date)
                if s is not None and not s.empty:
                    break
            except Exception as e:
                print(f'{t} shares attempt {attempt+1} failed: {e}')
            if attempt < max_retries - 1:
                time.sleep(wait)
        # 抓不到就留 NaN, 不用当前股本铺满历史(会系统性污染历史市值加权)
        if s is None or s.empty:
            print(f'{t} shares unavailable, leave NaN')
            continue
        s = s[~s.index.duplicated(keep='last')]
        if s.index.tz is not None:
            s.index = s.index.tz_localize(None)
        aligned = s.reindex(price.index, method='ffill')
        aligned.to_frame('shares').to_parquet(cp)
        shares[t] = aligned
    shares = pd.DataFrame(shares).reindex(columns = price.columns)
    market_cap = price* shares
    return shares, market_cap
