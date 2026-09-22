"""Image preparation: turning an upload into something a card box can hold."""

from .crop import crop_to_fill, prepare_for_box

__all__ = ["crop_to_fill", "prepare_for_box"]
