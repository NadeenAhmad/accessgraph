import { CHECKOUT_BENCHMARK_SEEDS } from "../seeds.js";

export const CHECKOUT_AUTOCOMPLETE_TARGETS = Object.freeze({
  addressCity: "checkout.address.city",
  addressCountry: "checkout.address.country",
  addressState: "checkout.address.state",
  addressFullName: "checkout.address.fullName",
  addressPostalCode: "checkout.address.postalCode",
  addressStreet: "checkout.address.street",
  paymentCardNumber: "checkout.payment.cardNumber",
  paymentExpiry: "checkout.payment.expiry",
  paymentSecurityCode: "checkout.payment.securityCode",
});

const AUTOCOMPLETE_VALUE_OVERRIDES_BY_SEED = Object.freeze({
  [CHECKOUT_BENCHMARK_SEEDS.addressCityAutocompleteState]: Object.freeze({
    [CHECKOUT_AUTOCOMPLETE_TARGETS.addressCity]: "address-level1",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.addressStateAutocompleteCity]: Object.freeze({
    [CHECKOUT_AUTOCOMPLETE_TARGETS.addressState]: "address-level2",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.addressCountryAutocompleteState]: Object.freeze({
    [CHECKOUT_AUTOCOMPLETE_TARGETS.addressCountry]: "address-level1",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.streetAutocompleteEmail]: Object.freeze({
    [CHECKOUT_AUTOCOMPLETE_TARGETS.addressStreet]: "email",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.addressStreetAutocompleteEmail]: Object.freeze({
    [CHECKOUT_AUTOCOMPLETE_TARGETS.addressStreet]: "email",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.addressStreetAutocompleteBillingContext]:
    Object.freeze({
      [CHECKOUT_AUTOCOMPLETE_TARGETS.addressStreet]: "billing street-address",
    }),
  [CHECKOUT_BENCHMARK_SEEDS.addressFullNameAutocompleteOrganizationTitle]:
    Object.freeze({
      [CHECKOUT_AUTOCOMPLETE_TARGETS.addressFullName]: "organization-title",
    }),
  [CHECKOUT_BENCHMARK_SEEDS.addressPostalCodeAutocompleteCity]: Object.freeze({
    [CHECKOUT_AUTOCOMPLETE_TARGETS.addressPostalCode]: "address-level2",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.paymentCardNumberAutocompleteCardholderName]:
    Object.freeze({
      [CHECKOUT_AUTOCOMPLETE_TARGETS.paymentCardNumber]: "cc-name",
    }),
  [CHECKOUT_BENCHMARK_SEEDS.paymentExpiryAutocompleteSecurityCode]:
    Object.freeze({
      [CHECKOUT_AUTOCOMPLETE_TARGETS.paymentExpiry]: "cc-csc",
    }),
  [CHECKOUT_BENCHMARK_SEEDS.paymentSecurityCodeAutocompleteExpiry]: Object.freeze({
    [CHECKOUT_AUTOCOMPLETE_TARGETS.paymentSecurityCode]: "cc-exp",
  }),
});

export function resolveAutocompleteEffects(activeSeeds = []) {
  const autocompleteValueOverrides = {};

  for (const seedId of activeSeeds) {
    const valueOverrides = AUTOCOMPLETE_VALUE_OVERRIDES_BY_SEED[seedId];
    if (valueOverrides) {
      Object.assign(autocompleteValueOverrides, valueOverrides);
    }
  }

  if (Object.keys(autocompleteValueOverrides).length === 0) {
    return Object.freeze({});
  }

  return Object.freeze({
    autocompleteValueOverrides: Object.freeze(autocompleteValueOverrides),
  });
}

export function getAutocompleteValueOverride(autocompleteEffects, targetId) {
  const autocompleteValueOverrides =
    autocompleteEffects?.autocompleteValueOverrides ?? {};
  return autocompleteValueOverrides[targetId] ?? undefined;
}
