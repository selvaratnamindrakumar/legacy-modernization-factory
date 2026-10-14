"""Centralized runtime configuration for local and AWS-backed demos."""

from __future__ import annotations

import os
from dataclasses import dataclass


# Change defaults here for a local demonstration; environment variables override them.
DEFAULT_AWS_REGION = "us-east-1"
DEFAULT_DYNAMODB_TABLE = "legacy-modernization-demo"
DEFAULT_DYNAMODB_INDEX = "tacs-index"
DEFAULT_S3_KEY = "legacy-records.json"
DEFAULT_RDS_DATABASE = "legacydb"
DEFAULT_RDS_TABLE = "legacy_records"
DEFAULT_RDS_HANDSET_TABLE = "handset_details"
DEFAULT_RDS_CELL_TABLE = "cells"
DEFAULT_QUERY_LIMIT = 100


@dataclass(frozen=True)
class AppConfig:
    aws_profile: str | None
    aws_region: str
    data_mode: str
    dynamodb_table: str
    dynamodb_index: str
    s3_bucket: str | None
    s3_key: str
    rds_resource_arn: str | None
    rds_secret_arn: str | None
    rds_database: str
    rds_table: str
    rds_handset_table: str
    rds_cell_table: str
    query_limit: int

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            aws_profile=os.getenv("AWS_PROFILE") or None,
            aws_region=os.getenv("AWS_REGION", DEFAULT_AWS_REGION),
            data_mode=os.getenv("MODERNIZATION_DATA_MODE", "local"),
            dynamodb_table=os.getenv("DYNAMODB_TABLE", DEFAULT_DYNAMODB_TABLE),
            dynamodb_index=os.getenv("DYNAMODB_INDEX", DEFAULT_DYNAMODB_INDEX),
            s3_bucket=os.getenv("S3_BUCKET") or None,
            s3_key=os.getenv("S3_KEY", DEFAULT_S3_KEY),
            rds_resource_arn=os.getenv("RDS_RESOURCE_ARN") or None,
            rds_secret_arn=os.getenv("RDS_SECRET_ARN") or None,
            rds_database=os.getenv("RDS_DATABASE", DEFAULT_RDS_DATABASE),
            rds_table=os.getenv("RDS_TABLE", DEFAULT_RDS_TABLE),
            rds_handset_table=os.getenv("RDS_HANDSET_TABLE", DEFAULT_RDS_HANDSET_TABLE),
            rds_cell_table=os.getenv("RDS_CELL_TABLE", DEFAULT_RDS_CELL_TABLE),
            query_limit=max(1, int(os.getenv("QUERY_LIMIT", str(DEFAULT_QUERY_LIMIT)))),
        )
