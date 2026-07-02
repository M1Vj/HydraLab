import React from "react";

import { type PdfAnnotationRecord, viewportRectFromQuad } from "../../../lib/annotations/store";

export function AnnotationLayer({
  annotations,
  page,
  pageWidth,
  pageHeight,
  scale,
  selectedId,
  onSelect,
}: {
  annotations: PdfAnnotationRecord[];
  page: number;
  pageWidth: number;
  pageHeight: number;
  scale: number;
  selectedId: string | null;
  onSelect: (annotation: PdfAnnotationRecord) => void;
}) {
  return (
    <div className="pdf-annotation-layer" aria-label="PDF annotations">
      {annotations
        .filter((annotation) => annotation.page === page)
        .map((annotation) => {
          const rect = viewportRectFromQuad(annotation.quad_points, pageWidth, pageHeight, scale);
          return (
            <button
              key={annotation.sidecar_record_id}
              className={`pdf-annotation-mark ${selectedId === annotation.sidecar_record_id ? "selected" : ""}`}
              style={{
                left: rect.left,
                top: rect.top,
                width: rect.width,
                height: Math.max(rect.height, 10),
              }}
              title={annotation.text}
              aria-label={`Annotation: ${annotation.text}`}
              onClick={() => onSelect(annotation)}
            />
          );
        })}
    </div>
  );
}
