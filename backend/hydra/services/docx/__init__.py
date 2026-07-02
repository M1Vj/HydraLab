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
from hydra.services.docx.reader import (
    DocxNode,
    StructuralModel,
    read_structural_model,
)
from hydra.services.docx.planner import (
    DocxPlanError,
    EditPlan,
    EditProposal,
    OP_TYPES,
    PlannedOperation,
    build_plan,
)
from hydra.services.docx.applier import (
    ApplyResult,
    DocxApplyError,
    OperationOutcome,
    apply_operations,
    create_checkpoint,
    resolve_working_docx,
    rollback,
    validate_docx_package,
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
    "DocxNode",
    "StructuralModel",
    "read_structural_model",
    "DocxPlanError",
    "EditPlan",
    "EditProposal",
    "OP_TYPES",
    "PlannedOperation",
    "build_plan",
    "ApplyResult",
    "DocxApplyError",
    "OperationOutcome",
    "apply_operations",
    "create_checkpoint",
    "resolve_working_docx",
    "rollback",
    "validate_docx_package",
]
