import { getBookingEffect } from "../benchmark/effects.js";
import { BOOKING_SUBJECTS } from "../benchmark/subjects.js";
import { formatFixtureDate } from "../state/bookingStore.js";
import { BOOKING_ROUTES } from "../utils/routes.js";
import { ProviderDetails } from "./ProviderDetails.jsx";
import { StepProgress } from "./StepProgress.jsx";
import { WorkflowLink } from "./WorkflowLink.jsx";

export function ConfirmationPage({
  benchmarkEffects,
  confirmedBooking,
  stepStates,
  onNavigate,
  onBookAnother,
}) {
  const successMessageLang = getBookingEffect(
    benchmarkEffects,
    BOOKING_SUBJECTS.confirmation.successMessage.id,
    "lang",
  );

  return (
    <div className="route-layout">
      <section
        className="confirmation-section"
        aria-labelledby="confirmation-heading"
      >
        <StepProgress
          currentStep="confirmation"
          stepStates={stepStates}
          allowNavigation={false}
        />

        <div className="section-heading confirmation-heading">
          <h2 id="confirmation-heading">Your appointment is confirmed</h2>
          <p
            className="confirmation-message"
            data-testid="confirmation-message"
            lang={successMessageLang}
          >
            Your booking is complete. A confirmation has been prepared for the
            contact details below.
          </p>
        </div>

        <div className="confirmation-summary-grid">
          <section
            className="review-summary-panel"
            aria-labelledby="confirmed-booking-heading"
          >
            <h3 id="confirmed-booking-heading">Confirmed booking</h3>
            <dl>
              <div>
                <dt>Reference</dt>
                <dd data-testid="confirmation-reference">
                  {confirmedBooking.reference}
                </dd>
              </div>
              <div>
                <dt>Service</dt>
                <dd data-testid="confirmation-service">
                  {confirmedBooking.service.name}
                </dd>
              </div>
              <div>
                <dt>Duration</dt>
                <dd>{confirmedBooking.service.duration}</dd>
              </div>
              <div>
                <dt>Date</dt>
                <dd data-testid="confirmation-date">
                  <time dateTime={confirmedBooking.date}>
                    {formatFixtureDate(confirmedBooking.date)}
                  </time>
                </dd>
              </div>
              <div>
                <dt>Time</dt>
                <dd data-testid="confirmation-time">{confirmedBooking.time}</dd>
              </div>
            </dl>
          </section>

          <section
            className="review-summary-panel"
            aria-labelledby="confirmed-customer-heading"
          >
            <h3 id="confirmed-customer-heading">Contact details</h3>
            <dl>
              <div>
                <dt>Full name</dt>
                <dd data-testid="confirmation-customer-name">
                  {confirmedBooking.customer.fullName}
                </dd>
              </div>
              <div>
                <dt>Email</dt>
                <dd data-testid="confirmation-customer-email">
                  {confirmedBooking.customer.email}
                </dd>
              </div>
              <div>
                <dt>Phone</dt>
                <dd data-testid="confirmation-customer-phone">
                  {confirmedBooking.customer.phone}
                </dd>
              </div>
            </dl>
          </section>

          <section
            className="review-summary-panel"
            aria-labelledby="confirmation-provider-heading"
            data-testid="confirmation-provider-summary"
          >
            <h3 id="confirmation-provider-heading">Clinic and location</h3>
            <ProviderDetails testIdPrefix="confirmation" />
            <ul className="context-link-list">
              <li>
                <WorkflowLink
                  data-testid="directions-link"
                  to={`${BOOKING_ROUTES.help}#directions`}
                  onNavigate={onNavigate}
                >
                  Directions
                </WorkflowLink>
              </li>
              <li>
                <WorkflowLink
                  data-testid="contact-clinic-link"
                  to={`${BOOKING_ROUTES.help}#contact`}
                  onNavigate={onNavigate}
                >
                  Contact clinic
                </WorkflowLink>
              </li>
            </ul>
          </section>
        </div>

        <button
          type="button"
          className="primary-action confirmation-reset-action"
          data-testid="book-another-appointment"
          onClick={onBookAnother}
        >
          Book another appointment
        </button>
      </section>
    </div>
  );
}
