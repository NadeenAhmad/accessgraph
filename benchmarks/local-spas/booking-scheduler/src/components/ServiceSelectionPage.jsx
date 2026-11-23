import { getBookingEffect } from "../benchmark/effects.js";
import { getBookingSubjectByTestId } from "../benchmark/subjects.js";
import { BOOKING_ROUTES } from "../utils/routes.js";
import { BookingSummary } from "./BookingSummary.jsx";
import { ProviderDetails } from "./ProviderDetails.jsx";
import { StepProgress } from "./StepProgress.jsx";
import { WorkflowLink } from "./WorkflowLink.jsx";

export function ServiceSelectionPage({
  benchmarkEffects = {},
  services,
  selectedService,
  selectedServiceId,
  selectedDate,
  selectedSlotTime,
  stepStates,
  onNavigate,
  onSelectService,
  onContinue,
}) {
  return (
    <div className="route-layout route-layout-with-aside">
      <section
        className="service-section"
        aria-labelledby="service-selection-heading"
      >
        <StepProgress
          currentStep="services"
          stepStates={stepStates}
          onNavigate={onNavigate}
        />

        <div className="section-heading">
          <h2 id="service-selection-heading">Choose a service</h2>
          <p>Select one deterministic fixture service before scheduling.</p>
        </div>

        <div className="provider-context" data-testid="service-provider-context">
          <h3>Appointment location</h3>
          <ProviderDetails testIdPrefix="service" />
          <WorkflowLink
            className="context-link"
            data-testid="preparation-link"
            to={`${BOOKING_ROUTES.help}#preparation`}
            onNavigate={onNavigate}
          >
            Preparation information
          </WorkflowLink>
        </div>

        <fieldset className="service-fieldset" data-testid="service-radio-group">
          <legend>Available services</legend>
          <ul className="service-list" data-testid="service-list">
            {services.map((service) => {
              const inputId = `service-${service.id}`;
              const isSelected = selectedServiceId === service.id;
              const optionTestId = `service-option-${service.id}`;
              const serviceSubject = getBookingSubjectByTestId(optionTestId);
              const serviceName = getBookingEffect(
                benchmarkEffects,
                serviceSubject?.id,
                "serviceName",
                service.name,
              );

              return (
                <li
                  className={isSelected ? "service-card is-selected" : "service-card"}
                  key={service.id}
                  data-testid={optionTestId}
                >
                  <input
                    id={inputId}
                    type="radio"
                    name="service"
                    value={service.id}
                    checked={isSelected}
                    data-testid={`service-radio-${service.id}`}
                    onChange={() => onSelectService(service.id)}
                  />
                  <label htmlFor={inputId}>
                    <span className="service-name">{serviceName}</span>
                    <span className="service-duration">{service.duration}</span>
                    <span className="service-description">
                      {service.description}
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
        </fieldset>

        <button
          type="button"
          className="primary-action"
          disabled={!selectedServiceId}
          data-testid="continue-to-schedule"
          onClick={onContinue}
        >
          Continue to schedule
        </button>
      </section>

      <aside className="route-aside" aria-label="Current booking summary">
        <BookingSummary
          selectedService={selectedService}
          selectedDate={selectedDate}
          selectedSlotTime={selectedSlotTime}
        />
      </aside>
    </div>
  );
}
