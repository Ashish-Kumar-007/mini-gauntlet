class InventoryLoadError(Exception):
    """The inventory file cannot be loaded as a usable snapshot."""


class InvalidResource(Exception):
    """A resource does not contain valid data for a particular check."""


class UnknownAccountError(ValueError):
    """A requested account ID is not present in the inventory."""
