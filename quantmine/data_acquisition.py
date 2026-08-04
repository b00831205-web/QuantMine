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

def data_acquisition(
    tickers: list,
    start_date: str,
    end_date: str,
    batch_size: int,
    max_retries: int = 3,
    wait: int = 60,
    checkpoint_dir: str = "tmp/checkpoint",
    batch_wait: float = 1.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Download historical price and volume data in batches with checkpoints.

    Args:
        tickers: List of tickers to download.
        start_date: Start date in ``YYYY-MM-DD`` format.
        end_date: End date in ``YYYY-MM-DD`` format.
        batch_size: Number of tickers per download batch.
        max_retries: Maximum retries for each batch download.
        wait: Seconds to wait between retry attempts.
        checkpoint_dir: Directory used to store batch checkpoints and logs.

    Returns:
        A tuple of ``(close_dataframe, volume_dataframe)``.

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
    

    def download_batch_with_retry(batch: list, start_date: str, end_date:str, batch_index:int  ,max_retries:int =3, wait: int =60) ->pd.DataFrame | None :
        checkpoint_path = os.path.join(task_checkpoint_dir, f"batch_{batch_index}.parquet")
        if os.path.exists(checkpoint_path):
            print(f"{batch_index} already exist")
            return pd.read_parquet(checkpoint_path)

        for attempt in range(max_retries):
            try:
                #threads=False: 串行请求, 避免并发触发Yahoo限流(429被误报成"possibly delisted")
                #timeout=30: 单请求超时, 卡住快速失败而非无限挂起
                data = yf.download(batch, start=start_date, end=end_date,
                                auto_adjust=True, progress=False,
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
    
    all_close = []
    all_volume = []
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i: i+batch_size]
        batch_index= i//batch_size+1
        print(f"downloading batch{batch_index} ... \ntickers {i} - {min(len(tickers), (i+batch_size))}")
        data = download_batch_with_retry(batch=batch, start_date=start_date, end_date=end_date, max_retries=max_retries, wait=wait, batch_index=batch_index)
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
    return close, volume

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
    

def merge_checkpoints(checkpoint_dir: str = "tmp/checkpoint") -> tuple:
    """Merge all batch checkpoint files into full close and volume tables.

    Args:
        checkpoint_dir: Directory containing ``batch_*.parquet`` checkpoint
            files.

    Returns:
        A tuple of ``(close_dataframe, volume_dataframe)``.

    Notes:
        Only parquet files with a MultiIndex column layout are merged.
    """
    files = sorted(glob.glob(os.path.join(checkpoint_dir, "**", "batch_*.parquet"), recursive=True),
                   key=lambda x: int(x.split("batch_")[1].split(".")[0]))
    
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
