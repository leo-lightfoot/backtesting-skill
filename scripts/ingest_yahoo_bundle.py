import argparse
import asyncio
import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo


def parse_date(date_str: str, tz_name: str) -> dt.datetime:
    y, m, d = [int(x) for x in date_str.split("-")]
    return dt.datetime(y, m, d, tzinfo=ZoneInfo(tz_name))


async def main_async(args):
    from ziplime.core.ingest_data import get_asset_service, ingest_market_data
    from ziplime.data.data_sources.yahoo_finance_data_source import (
        YahooFinanceDataSource,
    )

    start = parse_date(args.start, args.timezone)
    end = parse_date(args.end, args.timezone)

    asset_service = get_asset_service(
        db_path=str(Path(args.data_dir, "assets.sqlite")),
        clear_asset_db=False,
    )

    await ingest_market_data(
        start_date=start,
        end_date=end,
        trading_calendar="NYSE",
        bundle_name=args.bundle,
        symbols=args.symbols,
        data_frequency=dt.timedelta(minutes=args.frequency_minutes),
        data_bundle_source=YahooFinanceDataSource(maximum_threads=1),
        asset_service=asset_service,
        bundle_storage_path=args.data_dir,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--frequency-minutes", type=int, default=5)
    parser.add_argument("--timezone", default="America/New_York")
    parser.add_argument(
        "--data-dir", default=str(Path(Path.home(), ".ziplime", "data"))
    )
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
