import {
  BOOKING_BENCHMARK_SEEDS,
  BOOKING_BENCHMARK_SEED_IDS,
  resolveBookingSeedIds,
} from "./seeds.js";

export const BOOKING_PROFILE_GLOBAL = "__ACCESSGRAPH_BOOKING_PROFILE__";
export const BOOKING_CLEAN_PROFILE = "booking-clean";
export const BOOKING_BS_SEM_112_PROFILE = "booking-bs-sem-112";
export const BOOKING_BS_SEM_113_PROFILE = "booking-bs-sem-113";
export const BOOKING_BS_SEM_114_PROFILE = "booking-bs-sem-114";
export const BOOKING_BS_SEM_115_PROFILE = "booking-bs-sem-115";
export const BOOKING_BS_SEM_116_PROFILE = "booking-bs-sem-116";
export const BOOKING_BS_SEM_117_PROFILE = "booking-bs-sem-117";
export const BOOKING_BS_SEM_118_PROFILE = "booking-bs-sem-118";
export const BOOKING_BS_SEM_119_PROFILE = "booking-bs-sem-119";
export const BOOKING_BS_SEM_128_PROFILE = "booking-bs-sem-128";
export const BOOKING_BS_SEM_129_PROFILE = "booking-bs-sem-129";
export const BOOKING_BS_SEM_130_PROFILE = "booking-bs-sem-130";
export const BOOKING_BS_SEM_135_PROFILE = "booking-bs-sem-135";
export const BOOKING_BS_SEM_138_PROFILE = "booking-bs-sem-138";
export const BOOKING_BS_SEM_139_PROFILE = "booking-bs-sem-139";
export const BOOKING_BS_SEM_140_PROFILE = "booking-bs-sem-140";
export const BOOKING_BS_SEM_151_PROFILE = "booking-bs-sem-151";
export const BOOKING_BS_SEM_152_PROFILE = "booking-bs-sem-152";
export const BOOKING_BS_SEM_153_PROFILE = "booking-bs-sem-153";
export const BOOKING_BS_SEM_154_PROFILE = "booking-bs-sem-154";
export const BOOKING_BS_SEM_155_PROFILE = "booking-bs-sem-155";
export const BOOKING_BS_SEM_156_PROFILE = "booking-bs-sem-156";
export const BOOKING_BS_SEM_157_PROFILE = "booking-bs-sem-157";
export const BOOKING_BS_SEM_158_PROFILE = "booking-bs-sem-158";
export const BOOKING_BS_SEM_159_PROFILE = "booking-bs-sem-159";
export const BOOKING_BS_SEM_160_PROFILE = "booking-bs-sem-160";
export const BOOKING_BS_SEM_161_PROFILE = "booking-bs-sem-161";
export const BOOKING_BS_SEM_162_PROFILE = "booking-bs-sem-162";

export const BOOKING_PROFILES = Object.freeze({
  [BOOKING_CLEAN_PROFILE]: Object.freeze([]),
  [BOOKING_BS_SEM_112_PROFILE]: Object.freeze([
    BOOKING_BENCHMARK_SEEDS.slot0900AccessibleName1300,
  ]),
  [BOOKING_BS_SEM_113_PROFILE]: Object.freeze([
    BOOKING_BENCHMARK_SEEDS.slot1400AccessibleNameJune16,
  ]),
  [BOOKING_BS_SEM_114_PROFILE]: Object.freeze([
    BOOKING_BENCHMARK_SEEDS.reviewChangeServiceTextChangeAppointment,
  ]),
  [BOOKING_BS_SEM_115_PROFILE]: Object.freeze([
    BOOKING_BENCHMARK_SEEDS.reviewChangeAppointmentActivationServices,
  ]),
  [BOOKING_BS_SEM_116_PROFILE]: Object.freeze([
    BOOKING_BENCHMARK_SEEDS.consultationServiceNameRepairAssessment,
  ]),
  [BOOKING_BS_SEM_117_PROFILE]: Object.freeze([
    BOOKING_BENCHMARK_SEEDS.slot0900AriaPressedFalse,
  ]),
  [BOOKING_BS_SEM_118_PROFILE]: Object.freeze([
    BOOKING_BENCHMARK_SEEDS.reviewServiceHeadingDateAndTime,
  ]),
  [BOOKING_BS_SEM_119_PROFILE]: Object.freeze([
    BOOKING_BENCHMARK_SEEDS.phoneValidationMessageSchedulePrerequisite,
  ]),
  [BOOKING_BS_SEM_128_PROFILE]: Object.freeze([
    BOOKING_BENCHMARK_SEEDS.appointmentDateLabelTextAppointmentTime,
  ]),
  [BOOKING_BS_SEM_129_PROFILE]: Object.freeze([
    BOOKING_BENCHMARK_SEEDS.phoneLabelTextEmail,
  ]),
  [BOOKING_BS_SEM_130_PROFILE]: Object.freeze([
    BOOKING_BENCHMARK_SEEDS.accessibilityNeedsLabelTextPhone,
  ]),
  [BOOKING_BS_SEM_135_PROFILE]: Object.freeze([
    BOOKING_BENCHMARK_SEEDS.slot1300AriaPressedTrue,
  ]),
  [BOOKING_BS_SEM_138_PROFILE]: Object.freeze([
    BOOKING_BENCHMARK_SEEDS.fullNameValidationMessageEmailRequired,
  ]),
  [BOOKING_BS_SEM_139_PROFILE]: Object.freeze([
    BOOKING_BENCHMARK_SEEDS.emailValidationMessageFormatInvalid,
  ]),
  [BOOKING_BS_SEM_140_PROFILE]: Object.freeze([
    BOOKING_BENCHMARK_SEEDS.phoneValidationMessageOptional,
  ]),
  [BOOKING_BS_SEM_151_PROFILE]: Object.freeze([
    BOOKING_BENCHMARK_SEEDS.emailAutocompleteTel,
  ]),
  [BOOKING_BS_SEM_152_PROFILE]: Object.freeze([
    BOOKING_BENCHMARK_SEEDS.phoneAutocompleteEmail,
  ]),
  [BOOKING_BS_SEM_153_PROFILE]: Object.freeze([
    BOOKING_BENCHMARK_SEEDS.fullNameAutocompleteOrganizationTitle,
  ]),
  [BOOKING_BS_SEM_154_PROFILE]: Object.freeze([
    BOOKING_BENCHMARK_SEEDS.fullNameAutocompleteGivenName,
  ]),
  [BOOKING_BS_SEM_155_PROFILE]: Object.freeze([
    BOOKING_BENCHMARK_SEEDS.cancellationPolicyLangFrench,
  ]),
  [BOOKING_BS_SEM_156_PROFILE]: Object.freeze([
    BOOKING_BENCHMARK_SEEDS.confirmationSuccessMessageLangSpanish,
  ]),
  [BOOKING_BS_SEM_157_PROFILE]: Object.freeze([
    BOOKING_BENCHMARK_SEEDS.preparationInstructionsLangGerman,
  ]),
  [BOOKING_BS_SEM_158_PROFILE]: Object.freeze([
    BOOKING_BENCHMARK_SEEDS.arrivalInstructionsLangItalian,
  ]),
  [BOOKING_BS_SEM_159_PROFILE]: Object.freeze([
    BOOKING_BENCHMARK_SEEDS.helpPageLangGerman,
  ]),
  [BOOKING_BS_SEM_160_PROFILE]: Object.freeze([
    BOOKING_BENCHMARK_SEEDS.confirmationPageLangSpanish,
  ]),
  [BOOKING_BS_SEM_161_PROFILE]: Object.freeze([
    BOOKING_BENCHMARK_SEEDS.detailsPageLangGerman,
  ]),
  [BOOKING_BS_SEM_162_PROFILE]: Object.freeze([
    BOOKING_BENCHMARK_SEEDS.reviewPageLangFrench,
  ]),
});

export function resolveBookingProfile(
  profileId = getConfiguredBookingProfileId(),
  profiles = BOOKING_PROFILES,
  knownSeedIds = BOOKING_BENCHMARK_SEED_IDS,
) {
  if (profileId === null || profileId === undefined || profileId === "") {
    return Object.freeze([]);
  }

  if (
    typeof profileId !== "string" ||
    !Object.prototype.hasOwnProperty.call(profiles, profileId)
  ) {
    throw new Error(`Unknown Booking benchmark profile: ${String(profileId)}`);
  }

  return resolveBookingSeedIds(profiles[profileId], knownSeedIds);
}

export function getConfiguredBookingProfileId() {
  if (
    typeof window === "undefined" ||
    typeof window[BOOKING_PROFILE_GLOBAL] !== "string"
  ) {
    return "";
  }

  return window[BOOKING_PROFILE_GLOBAL];
}
