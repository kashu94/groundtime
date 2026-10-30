"""The data store: one DynamoDB table.

On-demand billing, so an idle table costs nothing beyond a few cents of storage. TTL clears
Qloo's cached answers after a day.

Development stages are disposable: deleting the stack deletes the table. Any other stage
keeps the table, turns on point-in-time recovery and blocks accidental deletion.
"""

from __future__ import annotations

from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as dynamodb
from constructs import Construct

from crewops.config import Settings
from crewops.store import schema

DISPOSABLE_STAGES = frozenset({"dev", "test"})


class DataStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, settings: Settings, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        disposable = settings.stage in DISPOSABLE_STAGES

        def key(name: str) -> dynamodb.Attribute:
            return dynamodb.Attribute(name=name, type=dynamodb.AttributeType.STRING)

        self.table = dynamodb.TableV2(
            self,
            "OpsTable",
            table_name=settings.table_name,
            partition_key=key(schema.PK),
            sort_key=key(schema.SK),
            billing=dynamodb.Billing.on_demand(),
            time_to_live_attribute=schema.TTL,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=not disposable
            ),
            deletion_protection=not disposable,
            removal_policy=RemovalPolicy.DESTROY if disposable else RemovalPolicy.RETAIN,
        )

        CfnOutput(self, "TableName", value=self.table.table_name)
