import {
  CHECKOUT_ARIA_STATE_TARGETS,
  getAriaCurrentOverride,
} from "../benchmark/effects/ariaStateEffects.js";
import {
  CHECKOUT_LANDMARK_TARGETS,
  getLandmarkAccessibleNameOverride,
} from "../benchmark/effects/landmarkEffects.js";

const CHECKOUT_PROGRESS_ARIA_TARGETS = Object.freeze({
  cart: CHECKOUT_ARIA_STATE_TARGETS.checkoutProgressCart,
  address: CHECKOUT_ARIA_STATE_TARGETS.checkoutProgressAddress,
});

const CHECKOUT_STEPS = [
  {
    id: "cart",
    label: "Cart",
  },
  {
    id: "address",
    label: "Shipping address",
  },
  {
    id: "payment",
    label: "Payment",
  },
  {
    id: "review",
    label: "Review",
  },
];

export function CheckoutProgress({
  ariaStateEffects = {},
  currentStep,
  copy = {},
  landmarkEffects = {},
}) {
  const currentIndex = CHECKOUT_STEPS.findIndex((step) => step.id === currentStep);
  const stepCopy = copy.steps ?? {};
  const stateLabels = copy.stateLabels ?? {};
  const accessibleNameOverride = getLandmarkAccessibleNameOverride(
    landmarkEffects,
    CHECKOUT_LANDMARK_TARGETS.checkoutProgress,
  );

  return (
    <section
      className="checkout-progress"
      aria-label={accessibleNameOverride}
      aria-labelledby={
        accessibleNameOverride ? undefined : "checkout-progress-heading"
      }
      data-testid="checkout-progress"
    >
      <h2 id="checkout-progress-heading">
        {copy.heading ?? "Checkout progress"}
      </h2>
      <ol>
        {CHECKOUT_STEPS.map((step, index) => {
          const isCurrent = step.id === currentStep;
          const ariaStateTarget = CHECKOUT_PROGRESS_ARIA_TARGETS[step.id];
          const currentOverride = ariaStateTarget
            ? getAriaCurrentOverride(
                ariaStateEffects,
                ariaStateTarget,
                currentStep,
              )
            : undefined;
          const declaredCurrent =
            currentOverride !== undefined
              ? currentOverride
              : isCurrent
                ? "step"
                : null;
          const stateLabel = isCurrent
            ? stateLabels.current ?? "Current step"
            : index < currentIndex
              ? stateLabels.previous ?? "Previous step"
              : stateLabels.notStarted ?? "Not started";

          return (
            <li
              key={step.id}
              className={isCurrent ? "progress-step is-current" : "progress-step"}
              aria-current={declaredCurrent ?? undefined}
              data-testid={`checkout-progress-${step.id}`}
            >
              <span className="progress-label">
                {stepCopy[step.id] ?? step.label}
              </span>
              <span className="progress-state">{stateLabel}</span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
