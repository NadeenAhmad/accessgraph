import { getBookingEffect } from "../benchmark/effects.js";
import { BOOKING_SUBJECTS } from "../benchmark/subjects.js";
import { BOOKING_PROVIDER } from "../data/fixtures.js";
import { ProviderDetails } from "./ProviderDetails.jsx";

export function HelpPage({ benchmarkEffects }) {
  const cancellationPolicyLang = getBookingEffect(
    benchmarkEffects,
    BOOKING_SUBJECTS.help.cancellationPolicy.id,
    "lang",
  );
  const preparationInstructionsLang = getBookingEffect(
    benchmarkEffects,
    BOOKING_SUBJECTS.help.preparationInstructions.id,
    "lang",
  );
  const arrivalInstructionsLang = getBookingEffect(
    benchmarkEffects,
    BOOKING_SUBJECTS.help.arrivalInstructions.id,
    "lang",
  );

  return (
    <div className="route-layout help-layout" data-testid="help-content">
      <section className="help-section">
        <h2>Clinic information</h2>
        <ProviderDetails testIdPrefix="help" />
      </section>

      <section className="help-section" id="cancellation">
        <h2>Cancellation policy</h2>
        <p
          data-testid="cancellation-policy-text"
          lang={cancellationPolicyLang}
        >
          Contact the clinic at least 24 hours before your appointment if you
          need to cancel. Late cancellations may require a new booking.
        </p>
      </section>

      <section className="help-section" id="rescheduling">
        <h2>Rescheduling</h2>
        <p>
          Contact the clinic before your appointment. Staff will help you choose
          another available date and time.
        </p>
      </section>

      <section className="help-section" id="preparation">
        <h2>Preparing for your appointment</h2>
        <p
          data-testid="preparation-instructions-text"
          lang={preparationInstructionsLang}
        >
          Arrive 10 minutes early and bring any documents or notes relevant to
          the service you selected.
        </p>
      </section>

      <section className="help-section" id="contact">
        <h2>Contact</h2>
        <dl className="contact-details">
          <div>
            <dt>Email</dt>
            <dd>{BOOKING_PROVIDER.email}</dd>
          </div>
          <div>
            <dt>Phone</dt>
            <dd>{BOOKING_PROVIDER.phone}</dd>
          </div>
        </dl>
      </section>

      <section className="help-section" id="directions">
        <h2>Directions</h2>
        <p>
          <strong>{BOOKING_PROVIDER.name}</strong>
          <br />
          {BOOKING_PROVIDER.address}
        </p>
        <p
          data-testid="arrival-instructions-text"
          lang={arrivalInstructionsLang}
        >
          {BOOKING_PROVIDER.arrivalNote}
        </p>
      </section>
    </div>
  );
}
