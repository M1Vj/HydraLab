import { MonitorSmartphone } from "lucide-react";

/**
 * Named unsupported-on-this-surface state (HL-UX-34). Renders a heading, a one-line
 * reason and a descriptive "Open on desktop" affordance. There is no real cross-device
 * deep link, so the affordance is descriptive copy, not a broken link. Layout stays
 * intact (single column, no clipped desktop panels).
 */
export function UnsupportedSurfaceState({ title, reason }: { title: string; reason: string }) {
  return (
    <section className="mobile-unsupported" role="status" aria-label={`${title} is not available on this surface`}>
      <MonitorSmartphone size={28} aria-hidden />
      <h2>{title} is a desktop feature</h2>
      <p>{reason}</p>
      <p className="mobile-unsupported-hint">Open this project in the desktop HydraLab workbench to use {title}.</p>
    </section>
  );
}
