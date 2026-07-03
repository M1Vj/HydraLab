import React from "react";

type WithChildren = {
  children: React.ReactNode;
  className?: string;
};

export function Dialog({ open, title, children, onClose }: WithChildren & { open: boolean; title: string; onClose: () => void }) {
  if (!open) return null;
  return (
    <div className="ui-overlay" role="presentation">
      <section className="ui-dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title">
        <header className="ui-dialog-header">
          <h2 id="dialog-title">{title}</h2>
          <button className="icon-button" onClick={onClose} aria-label="Close dialog">
            x
          </button>
        </header>
        {children}
      </section>
    </div>
  );
}

export function Popover({ label, children }: WithChildren & { label: string }) {
  return (
    <details className="ui-popover">
      <summary className="ui-button">{label}</summary>
      <div className="ui-popover-content">{children}</div>
    </details>
  );
}

export function DropdownMenu({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Array<{ value: string; label: string; disabled?: boolean }>;
  onChange: (value: string) => void;
}) {
  return (
    <label className="ui-field">
      <span>{label}</span>
      <select className="ui-select" value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option.value} value={option.value} disabled={option.disabled}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function ContextMenu({ children }: WithChildren) {
  return (
    <div className="ui-context-menu" role="menu">
      {children}
    </div>
  );
}

/**
 * Resolve the tab index a keyboard event should move focus to, or null when the
 * key is not a tablist navigation key. Arrows wrap around the ends; Home/End
 * jump to the first/last tab. Pure so it can be unit-tested without a DOM.
 */
export function nextTabIndex(current: number, key: string, count: number): number | null {
  if (count === 0) return null;
  let target: number;
  switch (key) {
    case "ArrowRight":
    case "ArrowDown":
      target = current + 1;
      break;
    case "ArrowLeft":
    case "ArrowUp":
      target = current - 1;
      break;
    case "Home":
      target = 0;
      break;
    case "End":
      target = count - 1;
      break;
    default:
      return null;
  }
  return (target + count) % count;
}

export function Tabs({
  tabs,
  value,
  onChange,
}: {
  tabs: Array<{ id: string; label: string }>;
  value: string;
  onChange: (id: string) => void;
}) {
  const listRef = React.useRef<HTMLDivElement>(null);

  // WAI-ARIA tabs pattern: the tablist is a single tab stop (roving tabindex),
  // and Arrow/Home/End move between tabs with selection following focus.
  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    const current = tabs.findIndex((tab) => tab.id === value);
    const target = nextTabIndex(current, event.key, tabs.length);
    if (target === null) return;
    event.preventDefault();
    onChange(tabs[target].id);
    const buttons = listRef.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]');
    buttons?.[target]?.focus();
  }

  return (
    <div className="ui-tabs" role="tablist" ref={listRef} onKeyDown={onKeyDown}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          className={`ui-tab ${value === tab.id ? "active" : ""}`}
          role="tab"
          aria-selected={value === tab.id}
          tabIndex={value === tab.id ? 0 : -1}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

export function Tooltip({ label, children }: WithChildren & { label: string }) {
  return (
    <span className="ui-tooltip" data-tooltip={label}>
      {children}
    </span>
  );
}

export function Switch({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
}) {
  return (
    <label className="ui-switch">
      <span>{label}</span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        className={`ui-switch-control ${checked ? "checked" : ""}`}
        onClick={() => onChange(!checked)}
      >
        <span />
      </button>
    </label>
  );
}

export function Checkbox({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
}) {
  return (
    <label className="ui-check">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span>{label}</span>
    </label>
  );
}

export function RadioGroup({
  value,
  options,
  onChange,
  label,
}: {
  value: string;
  label: string;
  options: Array<{ value: string; label: string; disabled?: boolean }>;
  onChange: (value: string) => void;
}) {
  return (
    <fieldset className="ui-radio-group">
      <legend>{label}</legend>
      {options.map((option) => (
        <label key={option.value} className="ui-check">
          <input
            type="radio"
            checked={value === option.value}
            disabled={option.disabled}
            onChange={() => onChange(option.value)}
          />
          <span>{option.label}</span>
        </label>
      ))}
    </fieldset>
  );
}

export function Select(props: React.ComponentProps<typeof DropdownMenu>) {
  return <DropdownMenu {...props} />;
}
