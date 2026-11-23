import { BOOKING_ROUTES } from "../utils/routes.js";
import { WorkflowLink } from "./WorkflowLink.jsx";

export function AppHeader({ currentPath, onNavigate }) {
  return (
    <header className="app-header">
      <div>
        <p className="eyebrow">AccessGraph local SPA benchmark</p>
        <p className="app-name">Booking Scheduler</p>
      </div>

      <nav className="global-nav" aria-label="General navigation">
        <WorkflowLink
          to={BOOKING_ROUTES.help}
          onNavigate={onNavigate}
          aria-current={currentPath === BOOKING_ROUTES.help ? "page" : undefined}
        >
          Help &amp; policies
        </WorkflowLink>
      </nav>
    </header>
  );
}
