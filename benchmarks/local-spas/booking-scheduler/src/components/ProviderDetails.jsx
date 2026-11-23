import { BOOKING_PROVIDER } from "../data/fixtures.js";

export function ProviderDetails({ testIdPrefix }) {
  return (
    <dl className="provider-details">
      <div>
        <dt>Clinic</dt>
        <dd data-testid={`${testIdPrefix}-provider-name`}>
          {BOOKING_PROVIDER.name}
        </dd>
      </div>
      <div>
        <dt>Location</dt>
        <dd data-testid={`${testIdPrefix}-provider-location`}>
          <address>{BOOKING_PROVIDER.address}</address>
        </dd>
      </div>
    </dl>
  );
}
