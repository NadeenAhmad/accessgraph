import { getBookingEffect } from "../benchmark/effects.js";
import { BOOKING_SUBJECTS } from "../benchmark/subjects.js";
import { formatFixtureDate } from "../state/bookingStore.js";
import { BOOKING_ROUTES } from "../utils/routes.js";
import { BookingSummary } from "./BookingSummary.jsx";
import { ProviderDetails } from "./ProviderDetails.jsx";
import { StepProgress } from "./StepProgress.jsx";
import { WorkflowLink } from "./WorkflowLink.jsx";

export function ReviewPage({
  benchmarkEffects = {},
  selectedService,
  selectedDate,
  selectedSlotTime,
  customerDetails,
  stepStates,
  onNavigate,
  onConfirmBooking,
}) {
  const hasNotes = Boolean(customerDetails.notes);
  const serviceHeading = getBookingEffect(
    benchmarkEffects,
    BOOKING_SUBJECTS.review.serviceHeading.id,
    "text",
    "Service",
  );
  const changeServiceText = getBookingEffect(
    benchmarkEffects,
    BOOKING_SUBJECTS.review.changeService.id,
    "text",
    "Change service",
  );
  const changeServiceTarget = getBookingEffect(
    benchmarkEffects,
    BOOKING_SUBJECTS.review.changeService.id,
    "activationTargetRoute",
    BOOKING_ROUTES.services,
  );
  const changeAppointmentText = getBookingEffect(
    benchmarkEffects,
    BOOKING_SUBJECTS.review.changeAppointment.id,
    "text",
    "Change appointment",
  );
  const changeAppointmentTarget = getBookingEffect(
    benchmarkEffects,
    BOOKING_SUBJECTS.review.changeAppointment.id,
    "activationTargetRoute",
    BOOKING_ROUTES.schedule,
  );
  const editDetailsText = getBookingEffect(
    benchmarkEffects,
    BOOKING_SUBJECTS.review.editDetails.id,
    "text",
    "Edit details",
  );
  const editDetailsTarget = getBookingEffect(
    benchmarkEffects,
    BOOKING_SUBJECTS.review.editDetails.id,
    "activationTargetRoute",
    BOOKING_ROUTES.details,
  );

  return (
    <div className="route-layout route-layout-with-aside">
      <section className="review-section" aria-labelledby="review-heading">
        <StepProgress
          currentStep="review"
          stepStates={stepStates}
          onNavigate={onNavigate}
        />

        <div className="section-heading">
          <h2 id="review-heading">Review appointment details</h2>
          <p data-testid="review-only-note">
            Review only. No appointment has been confirmed yet.
          </p>
        </div>

        <div className="review-summary-grid" data-testid="review-summary">
          <section
            className="review-summary-panel"
            aria-labelledby="review-service-heading"
            data-testid="review-service-summary"
          >
            <h3 id="review-service-heading">{serviceHeading}</h3>
            <dl>
              <div>
                <dt>Name</dt>
                <dd data-testid="review-service-name">{selectedService.name}</dd>
              </div>
              <div>
                <dt>Duration</dt>
                <dd data-testid="review-service-duration">
                  {selectedService.duration}
                </dd>
              </div>
            </dl>
            <WorkflowLink
              className="review-edit-link"
              data-testid="change-service"
              to={BOOKING_ROUTES.services}
              activationTargetRoute={changeServiceTarget}
              onNavigate={onNavigate}
            >
              {changeServiceText}
            </WorkflowLink>
          </section>

          <section
            className="review-summary-panel"
            aria-labelledby="review-schedule-heading"
            data-testid="review-schedule-summary"
          >
            <h3 id="review-schedule-heading">Date and time</h3>
            <dl>
              <div>
                <dt>Date</dt>
                <dd data-testid="review-date">
                  <time dateTime={selectedDate}>{formatFixtureDate(selectedDate)}</time>
                </dd>
              </div>
              <div>
                <dt>Time</dt>
                <dd data-testid="review-slot">{selectedSlotTime}</dd>
              </div>
            </dl>
            <WorkflowLink
              className="review-edit-link"
              data-testid="change-appointment"
              to={BOOKING_ROUTES.schedule}
              activationTargetRoute={changeAppointmentTarget}
              onNavigate={onNavigate}
            >
              {changeAppointmentText}
            </WorkflowLink>
          </section>

          <section
            className="review-summary-panel"
            aria-labelledby="review-customer-heading"
            data-testid="review-customer-summary"
          >
            <h3 id="review-customer-heading">Customer details</h3>
            <dl>
              <div>
                <dt>Full name</dt>
                <dd data-testid="review-customer-full-name">
                  {customerDetails.fullName}
                </dd>
              </div>
              <div>
                <dt>Email</dt>
                <dd data-testid="review-customer-email">
                  {customerDetails.email}
                </dd>
              </div>
              <div>
                <dt>Phone</dt>
                <dd data-testid="review-customer-phone">
                  {customerDetails.phone}
                </dd>
              </div>
              {hasNotes ? (
                <div>
                  <dt>Notes</dt>
                  <dd data-testid="review-customer-notes">
                    {customerDetails.notes}
                  </dd>
                </div>
              ) : null}
            </dl>
            <WorkflowLink
              className="review-edit-link"
              data-testid="edit-details"
              to={BOOKING_ROUTES.details}
              activationTargetRoute={editDetailsTarget}
              onNavigate={onNavigate}
            >
              {editDetailsText}
            </WorkflowLink>
          </section>

          <section
            className="review-summary-panel"
            aria-labelledby="review-provider-heading"
            data-testid="review-provider-summary"
          >
            <h3 id="review-provider-heading">Clinic and location</h3>
            <ProviderDetails testIdPrefix="review" />
            <ul className="context-link-list">
              <li>
                <WorkflowLink
                  data-testid="cancellation-policy-link"
                  to={`${BOOKING_ROUTES.help}#cancellation`}
                  onNavigate={onNavigate}
                >
                  Cancellation policy
                </WorkflowLink>
              </li>
              <li>
                <WorkflowLink
                  data-testid="rescheduling-help-link"
                  to={`${BOOKING_ROUTES.help}#rescheduling`}
                  onNavigate={onNavigate}
                >
                  Rescheduling help
                </WorkflowLink>
              </li>
            </ul>
          </section>
        </div>

        <button
          type="button"
          className="primary-action review-confirm-action"
          data-testid="confirm-booking"
          onClick={onConfirmBooking}
        >
          Confirm booking
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
