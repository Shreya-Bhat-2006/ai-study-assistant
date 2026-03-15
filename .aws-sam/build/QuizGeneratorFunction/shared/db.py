"""DynamoDB client wrapper with single-table key pattern helpers."""
import os
import boto3
from boto3.dynamodb.conditions import Key


def get_table():
    """Return a DynamoDB Table resource using TABLE_NAME env var."""
    table_name = os.environ.get("TABLE_NAME", "study-assistant")
    dynamodb = boto3.resource("dynamodb")
    return dynamodb.Table(table_name)


def get_item(pk: str, sk: str) -> dict | None:
    """Retrieve a single item by composite key. Returns None if not found."""
    table = get_table()
    response = table.get_item(Key={"pk": pk, "sk": sk})
    return response.get("Item")


def put_item(item: dict) -> None:
    """Write an item to the table. Item must include 'pk' and 'sk'."""
    table = get_table()
    table.put_item(Item=item)


def update_item(pk: str, sk: str, updates: dict) -> dict:
    """Update specific attributes on an existing item.

    `updates` is a mapping of attribute name -> new value.
    Returns the updated item attributes.
    """
    table = get_table()
    set_expressions = []
    expr_names = {}
    expr_values = {}

    for i, (attr, value) in enumerate(updates.items()):
        placeholder = f"#attr{i}"
        value_key = f":val{i}"
        set_expressions.append(f"{placeholder} = {value_key}")
        expr_names[placeholder] = attr
        expr_values[value_key] = value

    update_expr = "SET " + ", ".join(set_expressions)
    response = table.update_item(
        Key={"pk": pk, "sk": sk},
        UpdateExpression=update_expr,
        ExpressionAttributeNames=expr_names,
        ExpressionAttributeValues=expr_values,
        ReturnValues="ALL_NEW",
    )
    return response.get("Attributes", {})


def query_by_pk(pk: str) -> list[dict]:
    """Return all items for a given partition key."""
    table = get_table()
    response = table.query(KeyConditionExpression=Key("pk").eq(pk))
    return response.get("Items", [])
