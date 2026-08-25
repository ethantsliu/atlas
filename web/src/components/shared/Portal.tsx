import { type ReactNode } from "react";
import { createPortal } from "react-dom";

type DialogPortalProps = {
  children: ReactNode;
};

/** Keep dialogs outside the application shell so the background can be inert. */
export function DialogPortal({ children }: DialogPortalProps) {
  return createPortal(children, document.body);
}
