import { formatFixtureDate } from "../state/bookingStore.js";

export function BookingSummary({
  selectedService,
  selectedDate,
  selectedSlotTime,
}) {
  const slotText = selectedSlotTime ?? "No time selected";

  return (
    <section
      className="booking-summary"
      aria-labelledby="booking-summary-heading"
      data-testid="booking-summary"
    >
      <h2 id="booking-summary-heading">Booking summary</h2>
      <dl>
        <div>
          <dt>Service</dt>
          <dd data-testid="summary-service">
            {selectedService ? selectedService.name : "No service selected"}
          </dd>
        </div>
        <div>
          <dt>Duration</dt>
          <dd data-testid="summary-duration">
            {selectedService ? selectedService.duration : "Not selected"}
          </dd>
        </div>
        <div>
          <dt>Date</dt>
          <dd data-testid="summary-date">
            {selectedDate ? (
              <time dateTime={selectedDate}>{formatFixtureDate(selectedDate)}</time>
            ) : (
              "No date selected"
            )}
          </dd>
        </div>
        <div>
          <dt>Time</dt>
          <dd data-testid="summary-slot">{slotText}</dd>
        </div>
      </dl>
    </section>
  );
}
