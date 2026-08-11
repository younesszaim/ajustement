"""Print a local or S3 Parquet mapping in a readable table."""

import argparse
import json

import pyarrow.parquet as pq


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="Local path or s3:// URI to a Parquet mapping")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    table = pq.read_table(args.path)
    print(json.dumps(table.slice(0, args.limit).to_pylist(), indent=2, default=str))
    print(f"\nRows: {table.num_rows} · Columns: {', '.join(table.column_names)}")


if __name__ == "__main__":
    main()
