from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import asyncpg
import boto3
from botocore.config import Config


async def register(stage_bucket: str, stage_database: str, archive_sha256: str) -> UUID:
    attempt_id = uuid4()
    connection = await asyncpg.connect(os.environ["TEST_DATABASE_URL"])
    try:
        await connection.execute(
            """INSERT INTO plotlot.restore_attempts
            (attempt_id, stage_bucket, stage_database, archive_sha256, state, cleanup_after)
            VALUES ($1, $2, $3, $4, 'REGISTERED', $5)""",
            attempt_id,
            stage_bucket,
            stage_database,
            archive_sha256,
            datetime.now(UTC) + timedelta(days=1),
        )
    finally:
        await connection.close()
    return attempt_id


async def prepare_stage(
    stage_url: str,
    attempt_id: UUID,
    stage_bucket: str,
    stage_database: str,
    archive_sha256: str,
) -> None:
    connection = await asyncpg.connect(stage_url)
    try:
        async with connection.transaction():
            await connection.execute(
                """CREATE TABLE IF NOT EXISTS plotlot.restore_attempts (
                attempt_id uuid PRIMARY KEY, stage_bucket varchar(255) NOT NULL UNIQUE,
                stage_database varchar(255) NOT NULL, archive_sha256 char(64) NOT NULL,
                state varchar(24) NOT NULL, cleanup_after timestamptz NOT NULL,
                last_error text, updated_at timestamptz NOT NULL DEFAULT now())"""
            )
            await connection.execute(
                """CREATE TABLE IF NOT EXISTS plotlot.storage_generation (
                singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
                bucket varchar(255) NOT NULL,
                restore_attempt_id uuid NOT NULL UNIQUE
                  REFERENCES plotlot.restore_attempts(attempt_id),
                updated_at timestamptz NOT NULL DEFAULT now())"""
            )
            await connection.execute(
                """INSERT INTO plotlot.restore_attempts
                (attempt_id, stage_bucket, stage_database, archive_sha256, state, cleanup_after)
                VALUES ($1, $2, $3, $4, 'PROMOTED', $5)""",
                attempt_id,
                stage_bucket,
                stage_database,
                archive_sha256,
                datetime.now(UTC) + timedelta(days=1),
            )
            await connection.execute("DELETE FROM plotlot.storage_generation")
            await connection.execute(
                """INSERT INTO plotlot.storage_generation
                (singleton, bucket, restore_attempt_id)
                VALUES (true, $1, $2)""",
                stage_bucket,
                attempt_id,
            )
    finally:
        await connection.close()


async def set_state(attempt_id: UUID, state: str, error: str | None = None) -> None:
    connection = await asyncpg.connect(os.environ["TEST_DATABASE_URL"])
    try:
        await connection.execute(
            """UPDATE plotlot.restore_attempts
            SET state=$1, last_error=$2, updated_at=now() WHERE attempt_id=$3""",
            state,
            error,
            attempt_id,
        )
    finally:
        await connection.close()


async def list_recovery() -> list[dict[str, object]]:
    connection = await asyncpg.connect(os.environ["TEST_DATABASE_URL"])
    try:
        rows = await connection.fetch(
            """SELECT attempt_id, stage_bucket, stage_database, archive_sha256,
            state, cleanup_after, last_error FROM plotlot.restore_attempts
            WHERE state IN ('OBJECTS_RESTORED', 'RECOVERY_REQUIRED') ORDER BY updated_at"""
        )
        return [dict(row) for row in rows]
    finally:
        await connection.close()


async def clean_ready(attempt_id: UUID) -> None:
    connection = await asyncpg.connect(os.environ["TEST_DATABASE_URL"])
    try:
        row = await connection.fetchrow(
            """SELECT stage_bucket FROM plotlot.restore_attempts
            WHERE attempt_id=$1
              AND state IN ('OBJECTS_RESTORED', 'RECOVERY_REQUIRED')
              AND cleanup_after <= now()""",
            attempt_id,
        )
        if row is None:
            raise RuntimeError("restore attempt is not eligible for cleanup")
        client = boto3.client(
            "s3",
            endpoint_url=os.environ["PLOTLOT_OBJECT_STORE_ENDPOINT"],
            aws_access_key_id=os.environ["PLOTLOT_OBJECT_STORE_ACCESS_KEY"],
            aws_secret_access_key=os.environ["PLOTLOT_OBJECT_STORE_SECRET_KEY"],
            config=Config(s3={"addressing_style": "path"}),
        )
        bucket = row["stage_bucket"]
        versions = client.list_object_versions(Bucket=bucket).get("Versions", [])
        for version in versions:
            client.delete_object(
                Bucket=bucket,
                Key=version["Key"],
                VersionId=version["VersionId"],
            )
        client.delete_bucket(Bucket=bucket)
        await connection.execute(
            """UPDATE plotlot.restore_attempts SET state='CLEANED', updated_at=now()
            WHERE attempt_id=$1""",
            attempt_id,
        )
    finally:
        await connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=("register", "objects-restored", "prepare", "failed", "list", "clean"),
    )
    parser.add_argument("--attempt")
    parser.add_argument("--stage-bucket")
    parser.add_argument("--stage-database")
    parser.add_argument("--stage-url")
    parser.add_argument("--archive-sha")
    parser.add_argument("--error")
    arguments = parser.parse_args()
    if arguments.command == "register":
        result = asyncio.run(
            register(arguments.stage_bucket, arguments.stage_database, arguments.archive_sha)
        )
        print(result)
    elif arguments.command == "prepare":
        asyncio.run(
            prepare_stage(
                arguments.stage_url,
                UUID(arguments.attempt),
                arguments.stage_bucket,
                arguments.stage_database,
                arguments.archive_sha,
            )
        )
    elif arguments.command == "list":
        print(json.dumps(asyncio.run(list_recovery()), default=str, sort_keys=True))
    elif arguments.command == "clean":
        asyncio.run(clean_ready(UUID(arguments.attempt)))
    else:
        state = "RECOVERY_REQUIRED" if arguments.command == "failed" else "OBJECTS_RESTORED"
        asyncio.run(set_state(UUID(arguments.attempt), state, arguments.error))


if __name__ == "__main__":
    main()
