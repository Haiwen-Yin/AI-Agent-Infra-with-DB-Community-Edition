"""Authoritative product and acceptance matrix for v5 and later releases."""

from __future__ import annotations

from dataclasses import asdict, dataclass


DATABASES = ("oracle", "pg", "yashandb")


@dataclass(frozen=True)
class Product:
    key: str
    package: str
    name_zh: str
    name_en: str
    databases: tuple[str, ...]
    edition: str
    license: str
    brand: str = "chuanxu"

    def manifest(self) -> dict:
        return asdict(self)


PRODUCTS = (
    Product("unified-community", "AI-Agent-Infra-with-DB-Community-Edition",
            "川序社区版", "Chuanxu Community Edition", DATABASES,
            "Community", "Apache-2.0"),
    Product("agentx-community", "OpenTenBase-AgentX", "OpenTenBase AgentX",
            "OpenTenBase AgentX", ("pg",), "Community", "Apache-2.0", "agentx"),
    Product("oracle-enterprise", "AI-Agent-Infra-with-OracleDB-Enterprise-Edition",
            "川序 Oracle 企业版", "Chuanxu Oracle Enterprise Edition", ("oracle",),
            "Enterprise", "BSL-1.1"),
    Product("pg-enterprise", "AI-Agent-Infra-with-PG-Enterprise-Edition",
            "川序 PostgreSQL 企业版", "Chuanxu PostgreSQL Enterprise Edition", ("pg",),
            "Enterprise", "BSL-1.1"),
    Product("yashandb-enterprise", "AI-Agent-Infra-with-YashanDB-Enterprise-Edition",
            "川序 YashanDB 企业版", "Chuanxu YashanDB Enterprise Edition", ("yashandb",),
            "Enterprise", "BSL-1.1"),
)


def product_for(key: str) -> Product:
    for product in PRODUCTS:
        if product.key == key:
            return product
    raise ValueError(f"Unknown product: {key}")


def acceptance_targets() -> tuple[dict[str, str], ...]:
    return tuple(
        {"key": f"{product.key}-{database}", "product": product.key,
         "package": product.package, "database": database, "edition": product.edition}
        for product in PRODUCTS for database in product.databases
    )
