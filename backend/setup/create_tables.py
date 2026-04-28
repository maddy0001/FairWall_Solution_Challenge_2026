"""
backend/setup/create_tables.py
Creates BigQuery dataset + tables for FairWall.
Run once before first deployment.

Usage:
    cd fairwall
    python -m backend.setup.create_tables
"""

import os
import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

PROJECT = os.getenv("GCP_PROJECT", "fairwall-2026")
DATASET = os.getenv("BQ_DATASET", "fairwall_logs")

try:
    from google.cloud import bigquery
except ImportError:
    print("ERROR: google-cloud-bigquery not installed.")
    print("Run: pip install google-cloud-bigquery")
    sys.exit(1)


def create_dataset(client: bigquery.Client) -> None:
    dataset_ref = bigquery.Dataset(f"{PROJECT}.{DATASET}")
    dataset_ref.location = "US"
    try:
        client.create_dataset(dataset_ref, exists_ok=True)
        print(f"Dataset ready: {PROJECT}.{DATASET}")
    except Exception as e:
        print(f"Failed to create dataset: {e}")
        raise


PREDICTIONS_SCHEMA = [
    bigquery.SchemaField("prediction_id",    "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("tenant_id",        "STRING",    mode="REQUIRED"),  # scopes all queries
    bigquery.SchemaField("domain",           "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("features",         "STRING",    mode="REQUIRED"),  # JSON — replay engine reads this
    bigquery.SchemaField("sensitive_attrs",  "STRING",    mode="REQUIRED"),  # JSON
    bigquery.SchemaField("prediction",       "INTEGER",   mode="REQUIRED"),  # 0 or 1
    bigquery.SchemaField("confidence",       "FLOAT64",   mode="NULLABLE"),
    bigquery.SchemaField("flagged",          "BOOL",      mode="NULLABLE"),
    bigquery.SchemaField("intervention_type","STRING",    mode="NULLABLE"),
    bigquery.SchemaField("trust_score",      "FLOAT64",   mode="NULLABLE"),
    bigquery.SchemaField("created_at",       "TIMESTAMP", mode="REQUIRED"),
]

INTERVENTIONS_SCHEMA = [
    bigquery.SchemaField("intervention_id",  "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("prediction_id",    "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("tenant_id",        "STRING",    mode="REQUIRED"),  # scopes all queries
    bigquery.SchemaField("domain",           "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("severity",         "STRING",    mode="REQUIRED"),  # low | medium | high
    bigquery.SchemaField("action",           "STRING",    mode="REQUIRED"),  # flag_only | adjust_threshold | block_and_review
    bigquery.SchemaField("trust_score",      "FLOAT64",   mode="NULLABLE"),
    bigquery.SchemaField("explanation",      "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("created_at",       "TIMESTAMP", mode="REQUIRED"),
]


def create_table(client: bigquery.Client, table_name: str, schema: list) -> None:
    table_ref = f"{PROJECT}.{DATASET}.{table_name}"
    table = bigquery.Table(table_ref, schema=schema)
    table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        field="created_at",
    )
    try:
        client.create_table(table, exists_ok=True)
        print(f"Table ready: {table_ref}")
    except Exception as e:
        print(f"Failed to create table {table_name}: {e}")
        raise


def main():
    print(f"Setting up BigQuery for project: {PROJECT}, dataset: {DATASET}")
    client = bigquery.Client(project=PROJECT)
    create_dataset(client)
    create_table(client, "predictions", PREDICTIONS_SCHEMA)
    create_table(client, "interventions", INTERVENTIONS_SCHEMA)
    print("\nBigQuery setup complete.")
    print(f"  Predictions table : {PROJECT}.{DATASET}.predictions")
    print(f"  Interventions table: {PROJECT}.{DATASET}.interventions")


if __name__ == "__main__":
    main()
