class BookingDomainError(Exception):
    """Base exception for booking domain errors."""
    pass


class RoomTypeNotFoundError(BookingDomainError):
    """Raised when a room type ID does not exist."""
    pass


class RoomUnavailableError(BookingDomainError):
    """Raised when requested room types are fully booked or held."""

    def __init__(self, details: list[str]):
        super().__init__("Selected rooms are no longer available.")
        self.details = details

class RedisUnavailable(Exception):
    """Raised when Redis is unavailable."""
    pass