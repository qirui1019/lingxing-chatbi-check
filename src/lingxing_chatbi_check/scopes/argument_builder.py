from __future__ import annotations

from collections.abc import Iterable

from lingxing_chatbi_check.cases.models import DynamicArgumentsSpec
from lingxing_chatbi_check.scopes.shop_discovery import AuthorizedShop


def build_tool_argument_batches(
    base_arguments: dict[str, object],
    dynamic_arguments: DynamicArgumentsSpec,
    shops: list[AuthorizedShop],
) -> list[dict[str, object]]:
    if (
        dynamic_arguments.shop_batch_mode == "none"
        or dynamic_arguments.shop_argument is None
    ):
        return [dict(base_arguments)]

    values = [
        value
        for shop in shops
        if (value := shop.value_for(dynamic_arguments.source_field)) is not None
    ]

    if dynamic_arguments.shop_batch_mode == "single":
        return [
            {
                **base_arguments,
                dynamic_arguments.shop_argument: value,
            }
            for value in values
        ]

    if dynamic_arguments.shop_batch_mode == "list":
        return [
            {
                **base_arguments,
                dynamic_arguments.shop_argument: batch,
            }
            for batch in _chunks(values, dynamic_arguments.batch_size)
        ]

    raise ValueError(
        f"Unsupported shop_batch_mode: {dynamic_arguments.shop_batch_mode}"
    )


def database_scope_param(dynamic_arguments: DynamicArgumentsSpec) -> str:
    if dynamic_arguments.database_param:
        return dynamic_arguments.database_param
    return f"{dynamic_arguments.source_field}_values"


def values_for_database_scope(
    shops: list[AuthorizedShop],
    dynamic_arguments: DynamicArgumentsSpec,
) -> list[str]:
    return [
        value
        for shop in shops
        if (value := shop.value_for(dynamic_arguments.source_field)) is not None
    ]


def _chunks(values: Iterable[str], size: int) -> list[list[str]]:
    if size <= 0:
        raise ValueError("batch_size must be greater than 0")
    chunked: list[list[str]] = []
    current: list[str] = []
    for value in values:
        current.append(value)
        if len(current) >= size:
            chunked.append(current)
            current = []
    if current:
        chunked.append(current)
    return chunked
