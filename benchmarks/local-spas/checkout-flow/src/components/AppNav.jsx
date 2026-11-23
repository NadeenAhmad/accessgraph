import { NAV_ITEMS, getRouteId } from "../utils/routes.js";
import { getAriaCurrentOverride } from "../benchmark/effects/ariaStateEffects.js";
import {
  CHECKOUT_LANDMARK_TARGETS,
  getLandmarkAccessibleNameOverride,
} from "../benchmark/effects/landmarkEffects.js";
import {
  getLinkAccessibleNameOverride,
  getLinkDestinationOverride,
  getLinkTextOverride,
} from "../benchmark/effects/linkEffects.js";

export function AppNav({
  ariaStateEffects = {},
  currentPath,
  landmarkEffects = {},
  linkEffects = {},
  navCopy = {},
  onNavigate,
}) {
  const navAccessibleName =
    getLandmarkAccessibleNameOverride(
      landmarkEffects,
      CHECKOUT_LANDMARK_TARGETS.navigationRoutes,
    ) ??
    navCopy.ariaLabel ??
    "Checkout routes";
  const routeId = getRouteId(currentPath);

  return (
    <nav className="app-nav" aria-label={navAccessibleName}>
      <ul>
        {NAV_ITEMS.map((item) => {
          const isCurrent = currentPath === item.path;
          const accessibleName = getLinkAccessibleNameOverride(
            linkEffects,
            item.subjectId,
          );
          const destination =
            getLinkDestinationOverride(linkEffects, item.subjectId) ?? item.path;
          const label =
            getLinkTextOverride(linkEffects, item.subjectId) ??
            navCopy[item.id] ??
            item.label;
          const ariaCurrentOverride = getAriaCurrentOverride(
            ariaStateEffects,
            item.subjectId,
            routeId,
          );
          const ariaCurrent =
            ariaCurrentOverride !== undefined
              ? ariaCurrentOverride
              : isCurrent
                ? "page"
                : undefined;

          return (
            <li key={item.id}>
              <a
                className={isCurrent ? "nav-link active" : "nav-link"}
                href={destination}
                aria-current={ariaCurrent ?? undefined}
                aria-label={accessibleName}
                data-testid={item.testId}
                onClick={(event) => {
                  event.preventDefault();
                  onNavigate(destination);
                }}
              >
                {label}
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
