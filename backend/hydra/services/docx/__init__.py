"""HydraLab DOCX converter services (branch 01-12).

Permissive-by-default DOCX import/view/export. The bundled path is python-docx
(MIT); Pandoc (GPL) and LibreOffice are optional, non-bundled, subprocess-only
adapters (HL-LIC-04). Untrusted-DOCX hardening lives in ``security``.
"""
from hydra.services.docx.adapters import (
    ConverterAvailability,
    ImportedDocx,
    LibreOfficeAdapter,
    PandocAdapter,
    PythonDocxAdapter,
    default_adapters,
)
from hydra.services.docx.security import (
    DocxPackageError,
    extract_docx_safely,
    has_active_content,
    validate_ooxml_package,
)
from hydra.services.docx.service import (
    DocxConverterError,
    DocxService,
    ExportResult,
    ImportResult,
    detect_latex_toolchain,
    scrub_secrets,
)

__all__ = [
    "ConverterAvailability",
    "ImportedDocx",
    "PythonDocxAdapter",
    "PandocAdapter",
    "LibreOfficeAdapter",
    "default_adapters",
    "DocxPackageError",
    "extract_docx_safely",
    "has_active_content",
    "validate_ooxml_package",
    "DocxConverterError",
    "DocxService",
    "ExportResult",
    "ImportResult",
    "detect_latex_toolchain",
    "scrub_secrets",
]
