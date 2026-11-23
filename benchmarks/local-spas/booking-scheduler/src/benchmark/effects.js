import {
  BOOKING_BENCHMARK_SEEDS,
  BOOKING_BENCHMARK_SEED_IDS,
  resolveBookingSeedIds,
} from "./seeds.js";
import { BOOKING_SUBJECT_LIST, BOOKING_SUBJECTS } from "./subjects.js";

export const BOOKING_EFFECTS = Object.freeze([
  Object.freeze({
    seedId: BOOKING_BENCHMARK_SEEDS.slot0900AccessibleName1300,
    subjectId: BOOKING_SUBJECTS.schedule.slot0900.id,
    property: "accessibleName",
    value: "13:00 Available",
  }),
  Object.freeze({
    seedId: BOOKING_BENCHMARK_SEEDS.slot1400AccessibleNameJune16,
    subjectId: BOOKING_SUBJECTS.schedule.slot1400.id,
    property: "accessibleName",
    value: "14:00 Available on June 16, 2026",
  }),
  Object.freeze({
    seedId: BOOKING_BENCHMARK_SEEDS.reviewChangeServiceTextChangeAppointment,
    subjectId: BOOKING_SUBJECTS.review.changeService.id,
    property: "text",
    value: "Change appointment",
  }),
  Object.freeze({
    seedId: BOOKING_BENCHMARK_SEEDS.reviewChangeAppointmentActivationServices,
    subjectId: BOOKING_SUBJECTS.review.changeAppointment.id,
    property: "activationTargetRoute",
    value: "/services",
  }),
  Object.freeze({
    seedId: BOOKING_BENCHMARK_SEEDS.consultationServiceNameRepairAssessment,
    subjectId: BOOKING_SUBJECTS.services.consultation.id,
    property: "serviceName",
    value: "Repair assessment",
  }),
  Object.freeze({
    seedId: BOOKING_BENCHMARK_SEEDS.slot0900AriaPressedFalse,
    subjectId: BOOKING_SUBJECTS.schedule.slot0900.id,
    property: "ariaPressed",
    value: false,
  }),
  Object.freeze({
    seedId: BOOKING_BENCHMARK_SEEDS.reviewServiceHeadingDateAndTime,
    subjectId: BOOKING_SUBJECTS.review.serviceHeading.id,
    property: "text",
    value: "Date and time",
  }),
  Object.freeze({
    seedId: BOOKING_BENCHMARK_SEEDS.phoneValidationMessageSchedulePrerequisite,
    subjectId: BOOKING_SUBJECTS.details.phone.id,
    property: "validationMessage",
    value: "Choose a date and available time before entering booking details.",
  }),
  Object.freeze({
    seedId: BOOKING_BENCHMARK_SEEDS.appointmentDateLabelTextAppointmentTime,
    subjectId: BOOKING_SUBJECTS.schedule.date.id,
    property: "labelText",
    value: "Appointment time",
  }),
  Object.freeze({
    seedId: BOOKING_BENCHMARK_SEEDS.phoneLabelTextEmail,
    subjectId: BOOKING_SUBJECTS.details.phone.id,
    property: "labelText",
    value: "Email",
  }),
  Object.freeze({
    seedId: BOOKING_BENCHMARK_SEEDS.accessibilityNeedsLabelTextPhone,
    subjectId: BOOKING_SUBJECTS.details.accessibilityNeeds.id,
    property: "labelText",
    value: "Phone",
  }),
  Object.freeze({
    seedId: BOOKING_BENCHMARK_SEEDS.slot1300AriaPressedTrue,
    subjectId: BOOKING_SUBJECTS.schedule.slot1300.id,
    property: "ariaPressed",
    value: true,
  }),
  Object.freeze({
    seedId: BOOKING_BENCHMARK_SEEDS.fullNameValidationMessageEmailRequired,
    subjectId: BOOKING_SUBJECTS.details.fullName.id,
    property: "validationMessage",
    value: "Email is required.",
  }),
  Object.freeze({
    seedId: BOOKING_BENCHMARK_SEEDS.emailValidationMessageFormatInvalid,
    subjectId: BOOKING_SUBJECTS.details.email.id,
    property: "validationMessage",
    value: "Email format is invalid.",
  }),
  Object.freeze({
    seedId: BOOKING_BENCHMARK_SEEDS.phoneValidationMessageOptional,
    subjectId: BOOKING_SUBJECTS.details.phone.id,
    property: "validationMessage",
    value: "Phone is optional.",
  }),
  Object.freeze({
    seedId: BOOKING_BENCHMARK_SEEDS.emailAutocompleteTel,
    subjectId: BOOKING_SUBJECTS.details.email.id,
    property: "autocomplete",
    value: "tel",
  }),
  Object.freeze({
    seedId: BOOKING_BENCHMARK_SEEDS.phoneAutocompleteEmail,
    subjectId: BOOKING_SUBJECTS.details.phone.id,
    property: "autocomplete",
    value: "email",
  }),
  Object.freeze({
    seedId: BOOKING_BENCHMARK_SEEDS.fullNameAutocompleteOrganizationTitle,
    subjectId: BOOKING_SUBJECTS.details.fullName.id,
    property: "autocomplete",
    value: "organization-title",
  }),
  Object.freeze({
    seedId: BOOKING_BENCHMARK_SEEDS.fullNameAutocompleteGivenName,
    subjectId: BOOKING_SUBJECTS.details.fullName.id,
    property: "autocomplete",
    value: "given-name",
  }),
  Object.freeze({
    seedId: BOOKING_BENCHMARK_SEEDS.cancellationPolicyLangFrench,
    subjectId: BOOKING_SUBJECTS.help.cancellationPolicy.id,
    property: "lang",
    value: "fr",
  }),
  Object.freeze({
    seedId: BOOKING_BENCHMARK_SEEDS.confirmationSuccessMessageLangSpanish,
    subjectId: BOOKING_SUBJECTS.confirmation.successMessage.id,
    property: "lang",
    value: "es",
  }),
  Object.freeze({
    seedId: BOOKING_BENCHMARK_SEEDS.preparationInstructionsLangGerman,
    subjectId: BOOKING_SUBJECTS.help.preparationInstructions.id,
    property: "lang",
    value: "de",
  }),
  Object.freeze({
    seedId: BOOKING_BENCHMARK_SEEDS.arrivalInstructionsLangItalian,
    subjectId: BOOKING_SUBJECTS.help.arrivalInstructions.id,
    property: "lang",
    value: "it",
  }),
  Object.freeze({
    seedId: BOOKING_BENCHMARK_SEEDS.helpPageLangGerman,
    subjectId: BOOKING_SUBJECTS.page.help.id,
    property: "lang",
    value: "de",
  }),
  Object.freeze({
    seedId: BOOKING_BENCHMARK_SEEDS.confirmationPageLangSpanish,
    subjectId: BOOKING_SUBJECTS.page.confirmation.id,
    property: "lang",
    value: "es",
  }),
  Object.freeze({
    seedId: BOOKING_BENCHMARK_SEEDS.detailsPageLangGerman,
    subjectId: BOOKING_SUBJECTS.page.details.id,
    property: "lang",
    value: "de",
  }),
  Object.freeze({
    seedId: BOOKING_BENCHMARK_SEEDS.reviewPageLangFrench,
    subjectId: BOOKING_SUBJECTS.page.review.id,
    property: "lang",
    value: "fr",
  }),
]);

export function resolveBookingEffects(
  seedIds,
  effects = BOOKING_EFFECTS,
  subjects = BOOKING_SUBJECT_LIST,
  knownSeedIds = BOOKING_BENCHMARK_SEED_IDS,
) {
  const activeSeedIds = resolveBookingSeedIds(seedIds, knownSeedIds);
  const knownSeeds = new Set(knownSeedIds);
  const knownSubjects = getKnownSubjectIds(subjects);

  if (!Array.isArray(effects)) {
    throw new Error("Booking effect catalogue must be an array.");
  }

  effects.forEach((effect, index) =>
    validateEffect(effect, index, knownSeeds, knownSubjects),
  );

  const activeSeeds = new Set(activeSeedIds);
  const resolvedEffects = {};
  const claimedProperties = new Set();

  for (const effect of effects) {
    if (!activeSeeds.has(effect.seedId)) {
      continue;
    }

    const claimKey = `${effect.subjectId}\u0000${effect.property}`;
    if (claimedProperties.has(claimKey)) {
      throw new Error(
        `Duplicate Booking effect for ${effect.subjectId}.${effect.property}`,
      );
    }

    claimedProperties.add(claimKey);
    resolvedEffects[effect.subjectId] ??= {};
    resolvedEffects[effect.subjectId][effect.property] = effect.value;
  }

  for (const subjectEffects of Object.values(resolvedEffects)) {
    Object.freeze(subjectEffects);
  }

  return Object.freeze(resolvedEffects);
}

export function getBookingEffect(
  resolvedEffects,
  subjectId,
  property,
  cleanValue = undefined,
) {
  const subjectEffects = resolvedEffects?.[subjectId];

  if (
    !subjectEffects ||
    !Object.prototype.hasOwnProperty.call(subjectEffects, property)
  ) {
    return cleanValue;
  }

  return subjectEffects[property];
}

function getKnownSubjectIds(subjects) {
  if (!Array.isArray(subjects)) {
    throw new Error("Booking subject catalogue must be an array.");
  }

  const subjectIds = new Set();
  for (const item of subjects) {
    if (
      !item ||
      typeof item !== "object" ||
      typeof item.id !== "string" ||
      item.id.length === 0
    ) {
      throw new Error("Booking subject catalogue contains an invalid subject.");
    }

    if (subjectIds.has(item.id)) {
      throw new Error(`Duplicate Booking subject ID: ${item.id}`);
    }

    subjectIds.add(item.id);
  }

  return subjectIds;
}

function validateEffect(effect, index, knownSeeds, knownSubjects) {
  if (!effect || typeof effect !== "object" || Array.isArray(effect)) {
    throw new Error(`Booking effect at index ${index} must be an object.`);
  }

  for (const field of ["seedId", "subjectId", "property"]) {
    if (typeof effect[field] !== "string" || effect[field].length === 0) {
      throw new Error(
        `Booking effect at index ${index} has invalid ${field}.`,
      );
    }
  }

  if (!Object.prototype.hasOwnProperty.call(effect, "value")) {
    throw new Error(`Booking effect at index ${index} is missing value.`);
  }

  if (effect.value === undefined) {
    throw new Error(`Booking effect at index ${index} has undefined value.`);
  }

  if (!knownSeeds.has(effect.seedId)) {
    throw new Error(`Unknown Booking benchmark seed: ${effect.seedId}`);
  }

  if (!knownSubjects.has(effect.subjectId)) {
    throw new Error(`Unknown Booking subject: ${effect.subjectId}`);
  }
}
