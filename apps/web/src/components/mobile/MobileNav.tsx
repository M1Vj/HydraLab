import type React from "react";
import type { CapabilityFlow, Surface } from "../../lib/responsive";

export type NavItem = {
  flow: CapabilityFlow;
  label: string;
  icon: React.ComponentType<{ size?: number; "aria-hidden"?: boolean }>;
};

/**
 * Adaptive primary navigation exposing ONLY the matrix-supported companion flows.
 * Phone renders a bottom tab bar; tablet renders a side rail. Every control is an
 * icon+label button >=44x44px with an accessible name and a visible focus outline,
 * in the same DOM/tab order as it reads visually (HL-UX-38).
 */
export function MobileNav({
  items,
  active,
  onSelect,
  surface,
}: {
  items: readonly NavItem[];
  active: CapabilityFlow;
  onSelect: (flow: CapabilityFlow) => void;
  surface: Surface;
}) {
  return (
    <nav className={`mobile-nav mobile-nav-${surface === "tablet" ? "rail" : "tabs"}`} aria-label="Mobile navigation">
      {items.map((item) => {
        const Icon = item.icon;
        const isActive = item.flow === active;
        return (
          <button
            key={item.flow}
            type="button"
            className={`mobile-nav-item ${isActive ? "active" : ""}`}
            aria-current={isActive ? "page" : undefined}
            aria-label={item.label}
            onClick={() => onSelect(item.flow)}
          >
            <Icon size={20} aria-hidden />
            <span className="mobile-nav-label">{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
