import { getBookingEffect } from "../benchmark/effects.js";
import { getBookingSubjectByTestId } from "../benchmark/subjects.js";
import {
  formatFixtureDate,
  formatSlotForTestId,
} from "../state/bookingStore.js";

export function SlotList({
  benchmarkEffects = {},
  selectedDate,
  headingDate = selectedDate,
  slots,
  selectedSlotTime,
  onSelectSlot,
}) {
  return (
    <section
      className="slot-section"
      aria-labelledby="slot-list-heading"
      data-testid="slot-list"
    >
      <div className="section-heading compact">
        <h2 id="slot-list-heading">
          Available times for {formatFixtureDate(headingDate)}
        </h2>
        <p>Choose one available appointment time.</p>
      </div>

      <ul className="slot-list">
        {slots.map((slot) => {
          const testIdTime = formatSlotForTestId(slot.time);
          const slotTestId = `slot-button-${testIdTime}`;

          if (!slot.available) {
            return (
              <li key={slot.time}>
                <div
                  className="slot-unavailable"
                  data-testid={`slot-unavailable-${testIdTime}`}
                >
                  <span className="slot-time">{slot.time}</span>
                  <span className="slot-state">Unavailable</span>
                </div>
              </li>
            );
          }

          const isSelected = selectedSlotTime === slot.time;
          const slotSubject = getBookingSubjectByTestId(slotTestId);
          const accessibleName = getBookingEffect(
            benchmarkEffects,
            slotSubject?.id,
            "accessibleName",
          );
          const ariaPressed = getBookingEffect(
            benchmarkEffects,
            slotSubject?.id,
            "ariaPressed",
            isSelected ? true : undefined,
          );

          return (
            <li key={slot.time}>
              <button
                type="button"
                className={isSelected ? "slot-button is-selected" : "slot-button"}
                aria-label={accessibleName}
                aria-pressed={ariaPressed}
                data-testid={slotTestId}
                onClick={() => onSelectSlot(slot.time)}
              >
                <span className="slot-time">{slot.time}</span>
                {isSelected ? (
                  <span className="slot-state">Selected</span>
                ) : (
                  <span className="slot-state">Available</span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
