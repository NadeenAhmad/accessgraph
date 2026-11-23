import { getBookingEffect } from "../benchmark/effects.js";
import { BOOKING_SUBJECTS } from "../benchmark/subjects.js";
import { ALTERNATE_FIXTURE_DATE, FIXTURE_DATE } from "../data/fixtures.js";
import { formatFixtureDate } from "../state/bookingStore.js";
import { BOOKING_ROUTES } from "../utils/routes.js";
import { BookingSummary } from "./BookingSummary.jsx";
import { SlotList } from "./SlotList.jsx";
import { StepProgress } from "./StepProgress.jsx";
import { WorkflowLink } from "./WorkflowLink.jsx";

export function SchedulePage({
  benchmarkEffects = {},
  selectedService,
  selectedDate,
  selectedSlotTime,
  slots,
  stepStates,
  onNavigate,
  onDateChange,
  onSelectSlot,
  onContinueToDetails,
}) {
  const showSlots = slots.length > 0;
  const dateLabel = getBookingEffect(
    benchmarkEffects,
    BOOKING_SUBJECTS.schedule.date.id,
    "labelText",
    "Appointment date",
  );
  const continueButton = selectedSlotTime ? (
    <button
      type="button"
      className="primary-action schedule-continue"
      data-testid="continue-to-details"
      onClick={onContinueToDetails}
    >
      Continue to details
    </button>
  ) : null;

  return (
    <div className="route-layout route-layout-with-aside">
      <section className="schedule-section" aria-labelledby="schedule-heading">
        <StepProgress
          currentStep="schedule"
          stepStates={stepStates}
          onNavigate={onNavigate}
        />

        <WorkflowLink
          className="workflow-back-link"
          data-testid="back-to-services"
          to={BOOKING_ROUTES.services}
          onNavigate={onNavigate}
        >
          Back to services
        </WorkflowLink>

        <div className="section-heading">
          <h2 id="schedule-heading">Choose a date and time</h2>
          <p>
            This baseline slice exposes deterministic fixture dates with mixed
            slot availability.
          </p>
        </div>

        <div className="date-field">
          <label htmlFor="booking-date">{dateLabel}</label>
          <input
            id="booking-date"
            type="date"
            min={FIXTURE_DATE}
            max={ALTERNATE_FIXTURE_DATE}
            step="2"
            value={selectedDate}
            aria-describedby="booking-date-help"
            data-testid="schedule-date-input"
            onChange={(event) => onDateChange(event.target.value)}
          />
          <p id="booking-date-help" className="field-help">
            Supported fixture dates: {formatFixtureDate(FIXTURE_DATE)} and{" "}
            {formatFixtureDate(ALTERNATE_FIXTURE_DATE)}.
          </p>
        </div>

        {showSlots ? (
          <SlotList
            benchmarkEffects={benchmarkEffects}
            selectedDate={selectedDate}
            headingDate={selectedDate}
            slots={slots}
            selectedSlotTime={selectedSlotTime}
            onSelectSlot={onSelectSlot}
          />
        ) : (
          <p className="empty-slot-prompt" data-testid="slot-empty-prompt">
            Choose a supported fixture date to show appointment times.
          </p>
        )}

        {continueButton}
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
