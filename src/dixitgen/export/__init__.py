"""Print output.  Every file this project writes for a printer comes from here.

Two writers, one framing: ``sheet_pdf`` lays cards out on paper, ``card_images``
writes them one file each.  Both crop to the same trim rectangle -- see
``card_images`` for why that matters and what the alternative cost.
"""

from .card_images import export_card_images
from .formats import OUTPUTS, OutputFormat, OutputOption, option_for
from .formats import as_dicts as output_formats_json
from .sheet_pdf import CardArt, ExportResult, export_batch

__all__ = [
    "CardArt",
    "ExportResult",
    "export_batch",
    "export_card_images",
    "OutputFormat",
    "OutputOption",
    "OUTPUTS",
    "option_for",
    "output_formats_json",
]
