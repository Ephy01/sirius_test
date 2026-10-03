import type { ReactNode } from "react";

export const ENVIRONMENT_LABEL = "Смешанный контент";

export function Brand() {
  return (
    <div className="brand">
      <span className="brand-logo-frame">
        <img
          className="brand-logo"
          src="/header_logo_new.png"
          alt="Научно-технологический университет «Сириус»"
        />
      </span>
      <span className="brand-product">Gate</span>
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
