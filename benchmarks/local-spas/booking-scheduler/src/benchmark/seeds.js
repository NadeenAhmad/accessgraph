export const BOOKING_BENCHMARK_SEEDS = Object.freeze({
  slot0900AccessibleName1300: "bs-sem-112",
  slot1400AccessibleNameJune16: "bs-sem-113",
  reviewChangeServiceTextChangeAppointment: "bs-sem-114",
  reviewChangeAppointmentActivationServices: "bs-sem-115",
  consultationServiceNameRepairAssessment: "bs-sem-116",
  slot0900AriaPressedFalse: "bs-sem-117",
  reviewServiceHeadingDateAndTime: "bs-sem-118",
  phoneValidationMessageSchedulePrerequisite: "bs-sem-119",
  appointmentDateLabelTextAppointmentTime: "bs-sem-128",
  phoneLabelTextEmail: "bs-sem-129",
  accessibilityNeedsLabelTextPhone: "bs-sem-130",
  slot1300AriaPressedTrue: "bs-sem-135",
  fullNameValidationMessageEmailRequired: "bs-sem-138",
  emailValidationMessageFormatInvalid: "bs-sem-139",
  phoneValidationMessageOptional: "bs-sem-140",
  emailAutocompleteTel: "bs-sem-151",
  phoneAutocompleteEmail: "bs-sem-152",
  fullNameAutocompleteOrganizationTitle: "bs-sem-153",
  fullNameAutocompleteGivenName: "bs-sem-154",
  cancellationPolicyLangFrench: "bs-sem-155",
  confirmationSuccessMessageLangSpanish: "bs-sem-156",
  preparationInstructionsLangGerman: "bs-sem-157",
  arrivalInstructionsLangItalian: "bs-sem-158",
  helpPageLangGerman: "bs-sem-159",
  confirmationPageLangSpanish: "bs-sem-160",
  detailsPageLangGerman: "bs-sem-161",
  reviewPageLangFrench: "bs-sem-162",
});

export const BOOKING_BENCHMARK_SEED_IDS = Object.freeze(
  Object.values(BOOKING_BENCHMARK_SEEDS),
);

export function resolveBookingSeedIds(
  requestedSeedIds,
  knownSeedIds = BOOKING_BENCHMARK_SEED_IDS,
) {
  validateSeedIdList(knownSeedIds, "Booking seed catalogue");
  validateSeedIdList(requestedSeedIds, "Booking profile seed list");

  const knownSeeds = new Set(knownSeedIds);
  for (const seedId of requestedSeedIds) {
    if (!knownSeeds.has(seedId)) {
      throw new Error(`Unknown Booking benchmark seed: ${seedId}`);
    }
  }

  return Object.freeze([...requestedSeedIds]);
}

function validateSeedIdList(seedIds, label) {
  if (!Array.isArray(seedIds)) {
    throw new Error(`${label} must be an array.`);
  }

  const seenSeedIds = new Set();
  for (const seedId of seedIds) {
    if (typeof seedId !== "string" || seedId.length === 0) {
      throw new Error(`${label} contains an invalid seed ID.`);
    }

    if (seenSeedIds.has(seedId)) {
      throw new Error(`${label} contains duplicate seed ID: ${seedId}`);
    }

    seenSeedIds.add(seedId);
  }
}
