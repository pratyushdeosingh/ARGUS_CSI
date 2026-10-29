import { useLayoutEffect, useRef, type RefObject } from "react";

const focusable = 'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
const available = (element: HTMLElement) => {
  if (element.tabIndex < 0 || element.closest("[hidden], [inert]")) return false;
  for (let node: HTMLElement | null = element; node; node = node.parentElement) {
    const style = getComputedStyle(node);
    if (style.display === "none" || style.visibility === "hidden") return false;
  }
  return true;
};

// Presentation-only modal behavior. No requests, analysis state, or timers.
export function useDialogFocus(open: boolean, dialog: RefObject<HTMLElement | null>, onClose: () => void) {
  const close = useRef(onClose);
  close.current = onClose;
  useLayoutEffect(() => {
    if (!open || !dialog.current) return;
    const modal = dialog.current;
    const app = modal.closest(".m-app");
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const overflow = document.body.style.overflow;
    const siblings: Array<[HTMLElement, string | null]> = [];
    // Inert siblings up the ancestor chain also covers the Lab opened inside
    // Canonical Demo, without accidentally making that nested dialog inert.
    let branch = modal.parentElement;
    while (branch && branch !== document.body) {
      const parent = branch.parentElement;
      if (!parent) break;
      for (const sibling of parent.children) {
        if (sibling !== branch && sibling instanceof HTMLElement && !["SCRIPT", "STYLE", "LINK"].includes(sibling.tagName)) {
          siblings.push([sibling, sibling.getAttribute("inert")]);
          sibling.setAttribute("inert", "");
        }
      }
      branch = parent;
    }
    document.body.style.overflow = "hidden";
    const controls = () => Array.from(modal.querySelectorAll<HTMLElement>(focusable)).filter(available);
    const first = () => controls()[0] ?? modal;
    const keydown = (event: KeyboardEvent) => {
      // A nested native investigation dialog owns its keyboard/focus behavior.
      if (event.target instanceof Element && event.target.closest("dialog[open]")) return;
      if (event.key === "Escape" && !event.defaultPrevented && !event.isComposing) {
        event.preventDefault();
        event.stopPropagation();
        close.current();
      } else if (event.key === "Tab") {
        const items = controls();
        const active = document.activeElement;
        const outside = !items.includes(active as HTMLElement);
        if (!items.length || outside || (!event.shiftKey && active === items.at(-1)) || (event.shiftKey && active === items[0])) {
          event.preventDefault();
          (event.shiftKey ? items.at(-1) ?? modal : items[0] ?? modal).focus();
        }
      }
    };
    const focusin = (event: FocusEvent) => {
      if (!modal.contains(event.target as Node)) first().focus({ preventScroll: true });
    };
    document.addEventListener("keydown", keydown, true);
    document.addEventListener("focusin", focusin, true);
    first().focus({ preventScroll: true });
    return () => {
      document.removeEventListener("keydown", keydown, true);
      document.removeEventListener("focusin", focusin, true);
      for (const [element, original] of siblings) {
        if (original === null) element.removeAttribute("inert");
        else element.setAttribute("inert", original);
      }
      document.body.style.overflow = overflow;
      const fallback = app?.querySelector<HTMLElement>("[data-lab-launcher]");
      if (previous?.isConnected && available(previous)) previous.focus({ preventScroll: true });
      else if (fallback && available(fallback)) fallback.focus({ preventScroll: true });
    };
  }, [open, dialog]);
}
