import type { ReactNode } from "react";

type BrandProps = {
  compact?: boolean;
};

export function Brand({ compact = false }: BrandProps) {
  return (
    <div className={`brand ${compact ? "brand--compact" : ""}`}>
      <span className="brand-logo-frame">
        <img
          className="brand-logo"
          src="/header_logo_new.png"
          alt="Научно-технологический университет «Сириус»"
        />
      </span>
      {!compact && <span className="brand-product">Gate</span>}
    </div>
  );
}

export function ArrowIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 12h13M13 6l6 6-6 6" />
    </svg>
  );
}

export function ExitIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M10 5H5v14h5M14 8l4 4-4 4M8 12h10" />
    </svg>
  );
}

export function PlusIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

export function OrbitGlyph({ small = false }: { small?: boolean }) {
  return (
    <span className={`orbit-glyph ${small ? "orbit-glyph--small" : ""}`} aria-hidden="true">
      <i className="orbit-glyph__ring orbit-glyph__ring--one" />
      <i className="orbit-glyph__ring orbit-glyph__ring--two" />
      <i className="orbit-glyph__core" />
      <i className="orbit-glyph__satellite orbit-glyph__satellite--one" />
      <i className="orbit-glyph__satellite orbit-glyph__satellite--two" />
    </span>
  );
}

export function AppHeader({
  role,
  meta,
  onLogout,
}: {
  role: "Организатор" | "Участник";
  meta?: ReactNode;
  onLogout: () => void;
}) {
  return (
    <header className="app-header">
      <Brand />
      <div className="app-header__right">
        {meta}
        <span className="role-pill">{role}</span>
        <button className="icon-action" type="button" onClick={onLogout} aria-label="Выйти">
          <ExitIcon />
        </button>
      </div>
    </header>
  );
}
