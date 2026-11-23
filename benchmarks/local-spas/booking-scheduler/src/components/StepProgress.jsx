import { BOOKING_ROUTES } from "../utils/routes.js";
import { WorkflowLink } from "./WorkflowLink.jsx";

const BOOKING_STEPS = [
  {
    id: "services",
    label: "Service",
    path: BOOKING_ROUTES.services,
  },
  {
    id: "schedule",
    label: "Schedule",
    path: BOOKING_ROUTES.schedule,
  },
  {
    id: "details",
    label: "Details",
    path: BOOKING_ROUTES.details,
  },
  {
    id: "review",
    label: "Review",
    path: BOOKING_ROUTES.review,
  },
  {
    id: "confirmation",
    label: "Confirmation",
    path: BOOKING_ROUTES.confirmation,
  },
];

export function StepProgress({
  currentStep,
  stepStates,
  onNavigate,
  allowNavigation = true,
}) {
  return (
    <nav
      className="step-progress"
      aria-label="Booking progress"
      data-testid="booking-progress"
    >
      <h2>Booking progress</h2>
      <ol>
        {BOOKING_STEPS.map((step) => {
          const isCurrent = step.id === currentStep;
          const stepState = stepStates[step.id];
          const stateLabel = getStateLabel(stepState);
          const isReachable =
            allowNavigation &&
            (stepState === "completed" || stepState === "available");

          return (
            <li
              key={step.id}
              className={`progress-step is-${stepState}`}
              aria-current={isCurrent ? "step" : undefined}
              data-state={stepState}
              data-testid={`booking-progress-${step.id}`}
            >
              {isReachable ? (
                <WorkflowLink
                  className="progress-link"
                  to={step.path}
                  onNavigate={onNavigate}
                >
                  <span className="progress-label">{step.label}</span>
                </WorkflowLink>
              ) : (
                <span className="progress-label">{step.label}</span>
              )}
              <span className="progress-state">{stateLabel}</span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

function getStateLabel(stepState) {
  if (stepState === "current") {
    return "Current step";
  }

  if (stepState === "completed") {
    return "Completed";
  }

  if (stepState === "available") {
    return "Available";
  }

  return "Not available";
}
