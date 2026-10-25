import { memo, useCallback, useEffect, useId, useRef, useState } from "react";
import { Bell, ChevronDown, Contrast, Eye, FlaskConical, LayoutDashboard, Menu, Network, RefreshCw, SlidersHorizontal, Wallet, X } from "lucide-react";

const destinations = [
  ["Overview", LayoutDashboard],
  ["Transactions", Wallet],
  ["Alerts", Bell],
  ["Investigations", Network],
  ["Demo", SlidersHorizontal],
  ["Lab", FlaskConical],
] as const;

export type Page = (typeof destinations)[number][0];

interface NavigationShellProps {
  page: Page;
  alertCount: number;
  connection: string;
  onNavigate: (page: Page) => void;
  onRefresh: () => void;
}

// Only presentation state lives here. The monitoring controller stays mounted in App.
export const NavigationShell = memo(function NavigationShell({ page, alertCount, connection, onNavigate, onRefresh }: NavigationShellProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [opaque, setOpaque] = useState(false);
  const header = useRef<HTMLElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const mobileNav = useRef<HTMLElement>(null);
  const desktopNav = useRef<HTMLElement>(null);
  const compactFocus = useRef(false);
  const menuId = useId();
  const closeMenu = useCallback((restoreFocus = false) => {
    setMenuOpen(false);
    if (restoreFocus) trigger.current?.focus();
  }, []);

  useEffect(() => {
    if (!menuOpen) return;
    mobileNav.current?.querySelector<HTMLButtonElement>('[aria-current="page"]')?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeMenu(true);
      }
    };
    const onPointerDown = (event: PointerEvent) => {
      if (!header.current?.contains(event.target as Node)) closeMenu();
    };
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("pointerdown", onPointerDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("pointerdown", onPointerDown);
    };
  }, [menuOpen, closeMenu]);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const desktop = window.matchMedia("(min-width: 1120px)");
    const onChange = () => {
      if (!desktop.matches) return;
      // A CSS breakpoint may hide the focused disclosure before matchMedia fires.
      const focusInMenu = compactFocus.current || mobileNav.current?.contains(document.activeElement) || document.activeElement === trigger.current;
      closeMenu();
      if (focusInMenu) desktopNav.current?.querySelector<HTMLButtonElement>('[aria-current="page"]')?.focus();
    };
    desktop.addEventListener("change", onChange);
    return () => desktop.removeEventListener("change", onChange);
  }, [closeMenu]);

  const links = (mobile = false) => destinations.map(([name, Icon]) => (
    <button
      type="button"
      key={name}
      aria-current={page === name ? "page" : undefined}
      className={page === name ? "active" : undefined}
      onClick={() => {
        if (mobile) closeMenu(true);
        onNavigate(name);
      }}
    >
      <Icon size={16} aria-hidden="true" />
      <span>{name}</span>
      {name === "Alerts" && alertCount > 0 && <span className="m-nav-count" aria-label={`${alertCount} alerts`}>{alertCount}</span>}
    </button>
  ));

  return (
    <header
      className="m-header m-material-2"
      data-opaque={opaque ? "true" : undefined}
      ref={header}
      onFocusCapture={(event) => {
        compactFocus.current = event.target === trigger.current || Boolean(mobileNav.current?.contains(event.target as Node));
      }}
      onBlur={(event) => {
        // This is a nonmodal disclosure: Tab can leave it normally.
        if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget as Node)) {
          compactFocus.current = false;
          closeMenu();
        }
      }}
    >
      <div className="m-brand">
        <span className="m-brand-mark"><Eye size={23} aria-hidden="true" /></span>
        <strong>ARGUS</strong>
        <span className="m-brand-caption">Financial Fraud Intelligence</span>
      </div>
      <nav className="m-desktop-nav" aria-label="Primary navigation" ref={desktopNav}>{links()}</nav>
      <div className="m-header-actions">
        <span className={`m-connection ${connection === "Connected" ? "healthy" : "warning"}`} role="status">
          <i aria-hidden="true" />{connection}
        </span>
        <button type="button" className="m-icon-control" onClick={onRefresh} aria-label="Refresh detector health" title="Refresh detector health"><RefreshCw size={16} aria-hidden="true" /></button>
        <button type="button" className="m-icon-control" onClick={() => setOpaque(value => !value)} aria-label="Reduce transparency" aria-pressed={opaque} title="Reduce transparency"><Contrast size={16} aria-hidden="true" /></button>
        <span className="m-avatar" title="Local analyst workspace">AN</span>
      </div>
      <button type="button" className="m-menu-toggle" ref={trigger} aria-label={`Navigation menu · ${page}`} aria-expanded={menuOpen} aria-controls={menuOpen ? menuId : undefined} onClick={() => menuOpen ? closeMenu(true) : setMenuOpen(true)}>
        <span>{menuOpen ? <X size={17} aria-hidden="true" /> : <Menu size={17} aria-hidden="true" />} Menu</span>
        <span className="m-current-destination">{page}<ChevronDown size={15} aria-hidden="true" /></span>
      </button>
      {menuOpen && <nav id={menuId} className="m-mobile-nav m-material-3" aria-label="Mobile navigation" ref={mobileNav}>{links(true)}</nav>}
    </header>
  );
});
