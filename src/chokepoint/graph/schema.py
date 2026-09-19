from enum import StrEnum


class NodeType(StrEnum):
    PORT = "port"
    ROUTE = "route"
    COMMODITY = "commodity"
    FACILITY = "facility"
    INDUSTRY = "industry"
    MARKET = "market"


class EdgeType(StrEnum):
    HANDLES = "handles"
    SUPPLIES = "supplies"
    TRANSITS = "transits"
    DEPENDS_ON = "depends_on"
