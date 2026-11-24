import ipaddress
from collections.abc import Mapping

from app.domain.errors import InvalidResource


def require_object(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise InvalidResource(f"{field} must be an object")
    return value


def require_list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise InvalidResource(f"{field} must be an array")
    return value


def require_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidResource(f"{field} must be a non-empty string")
    return value


def require_boolean(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise InvalidResource(f"{field} must be a boolean")
    return value


def require_integer(value: object, field: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise InvalidResource(f"{field} must be an integer from {minimum} to {maximum}")
    return value


def parse_network(value: object, field: str) -> ipaddress.IPv4Network | ipaddress.IPv6Network:
    cidr = require_string(value, field)
    try:
        return ipaddress.ip_network(cidr, strict=False)
    except ValueError as error:
        raise InvalidResource(f"{field} must be a valid CIDR") from error


def is_internet_wide_source(value: object, field: str) -> bool:
    source = require_string(value, field)
    if source in {"*", "Internet"}:
        return True
    network = parse_network(source, field)
    return network.prefixlen == 0


def port_intersects_target(start: int, end: int) -> bool:
    return start <= 22 <= end or start <= 3389 <= end


def parse_port_expression(value: object, field: str) -> tuple[int, int] | None:
    expression = require_string(value, field)
    if expression == "*":
        return 0, 65535

    parts = expression.split("-")
    if len(parts) not in (1, 2):
        raise InvalidResource(f"{field} must be a port or port range")
    try:
        start = int(parts[0])
        end = int(parts[-1])
    except ValueError as error:
        raise InvalidResource(f"{field} must contain integer ports") from error
    if not 0 <= start <= 65535 or not 0 <= end <= 65535 or start > end:
        raise InvalidResource(f"{field} contains an invalid port range")
    return start, end
