from __future__ import annotations

import json
import subprocess
from functools import lru_cache
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BOOKING_SRC = (
  REPO_ROOT / "benchmarks" / "local-spas" / "booking-scheduler" / "src"
)
BOOKING_BENCHMARK_SRC = BOOKING_SRC / "benchmark"


def test_booking_subject_catalogue_is_unique_and_app_local():
  runtime = _scaffolding_runtime()

  assert runtime["subjectCount"] > 0
  assert runtime["subjectCount"] == runtime["uniqueSubjectCount"]
  assert runtime["allSubjectsBookingLocal"] is True
  assert runtime["subjectLookups"] == {
    "detailsEmail": "booking.details.email",
    "reviewCancellation": "booking.review.cancellationLink",
    "reviewServiceHeading": "booking.review.serviceHeading",
    "helpCancellationPolicy": "booking.help.cancellationPolicy",
    "helpPreparationInstructions": "booking.help.preparationInstructions",
    "helpArrivalInstructions": "booking.help.arrivalInstructions",
    "schedule0900": "booking.schedule.slot.0900",
    "schedule1400ByTestId": "booking.schedule.slot.1400",
    "unknown": None,
  }


def test_booking_production_catalogues_contain_implemented_profiles():
  runtime = _scaffolding_runtime()

  assert runtime["production"] == {
    "caseProfiles": [
      "booking-bs-sem-112",
      "booking-bs-sem-113",
      "booking-bs-sem-114",
      "booking-bs-sem-115",
      "booking-bs-sem-116",
      "booking-bs-sem-117",
      "booking-bs-sem-118",
      "booking-bs-sem-119",
      "booking-bs-sem-128",
      "booking-bs-sem-129",
      "booking-bs-sem-130",
      "booking-bs-sem-135",
      "booking-bs-sem-138",
      "booking-bs-sem-139",
      "booking-bs-sem-140",
      "booking-bs-sem-151",
      "booking-bs-sem-152",
      "booking-bs-sem-153",
      "booking-bs-sem-154",
      "booking-bs-sem-155",
      "booking-bs-sem-156",
      "booking-bs-sem-157",
      "booking-bs-sem-158",
      "booking-bs-sem-159",
      "booking-bs-sem-160",
      "booking-bs-sem-161",
      "booking-bs-sem-162",
    ],
    "cleanProfile": "booking-clean",
    "effectCount": 27,
    "mutationProfileCount": 27,
    "profileCount": 28,
    "seedCount": 27,
  }


def test_booking_baseline_and_clean_profiles_resolve_no_effects():
  runtime = _scaffolding_runtime()

  assert runtime["baseline"] == {
    "clean": {"effects": {}, "seedIds": []},
    "empty": {"effects": {}, "seedIds": []},
    "null": {"effects": {}, "seedIds": []},
    "undefined": {"effects": {}, "seedIds": []},
  }


def test_booking_bs_sem_112_profile_targets_only_0900_accessible_name():
  runtime = _scaffolding_runtime()

  assert runtime["bsSem112"] == {
    "effects": {
      "booking.schedule.slot.0900": {
        "accessibleName": "13:00 Available",
      },
    },
    "seedIds": ["bs-sem-112"],
  }


def test_booking_bs_sem_113_profile_targets_only_1400_accessible_name():
  runtime = _scaffolding_runtime()

  assert runtime["bsSem113"] == {
    "effects": {
      "booking.schedule.slot.1400": {
        "accessibleName": "14:00 Available on June 16, 2026",
      },
    },
    "seedIds": ["bs-sem-113"],
  }


def test_booking_bs_sem_114_profile_targets_only_change_service_text():
  runtime = _scaffolding_runtime()

  assert runtime["bsSem114"] == {
    "effects": {
      "booking.review.changeService": {
        "text": "Change appointment",
      },
    },
    "seedIds": ["bs-sem-114"],
  }


def test_booking_bs_sem_115_profile_targets_only_change_appointment_activation():
  runtime = _scaffolding_runtime()

  assert runtime["bsSem115"] == {
    "effects": {
      "booking.review.changeAppointment": {
        "activationTargetRoute": "/services",
      },
    },
    "seedIds": ["bs-sem-115"],
  }


def test_booking_bs_sem_116_profile_targets_only_consultation_service_name():
  runtime = _scaffolding_runtime()

  assert runtime["bsSem116"] == {
    "effects": {
      "booking.services.consultation": {
        "serviceName": "Repair assessment",
      },
    },
    "seedIds": ["bs-sem-116"],
  }


def test_booking_bs_sem_117_profile_targets_only_0900_pressed_state():
  runtime = _scaffolding_runtime()

  assert runtime["bsSem117"] == {
    "effects": {
      "booking.schedule.slot.0900": {
        "ariaPressed": False,
      },
    },
    "seedIds": ["bs-sem-117"],
  }


def test_booking_bs_sem_118_profile_targets_only_review_service_heading_text():
  runtime = _scaffolding_runtime()

  assert runtime["bsSem118"] == {
    "effects": {
      "booking.review.serviceHeading": {
        "text": "Date and time",
      },
    },
    "seedIds": ["bs-sem-118"],
  }


def test_booking_bs_sem_119_profile_targets_only_phone_validation_message():
  runtime = _scaffolding_runtime()

  assert runtime["bsSem119"] == {
    "effects": {
      "booking.details.phone": {
        "validationMessage": (
          "Choose a date and available time before entering booking details."
        ),
      },
    },
    "seedIds": ["bs-sem-119"],
  }


def test_booking_bs_sem_128_profile_targets_only_appointment_date_label_text():
  runtime = _scaffolding_runtime()

  assert runtime["bsSem128"] == {
    "effects": {
      "booking.schedule.date": {
        "labelText": "Appointment time",
      },
    },
    "seedIds": ["bs-sem-128"],
  }


def test_booking_bs_sem_129_profile_targets_only_phone_label_text():
  runtime = _scaffolding_runtime()

  assert runtime["bsSem129"] == {
    "effects": {
      "booking.details.phone": {
        "labelText": "Email",
      },
    },
    "seedIds": ["bs-sem-129"],
  }


def test_booking_bs_sem_130_profile_targets_only_accessibility_needs_label_text():
  runtime = _scaffolding_runtime()

  assert runtime["bsSem130"] == {
    "effects": {
      "booking.details.accessibilityNeeds": {
        "labelText": "Phone",
      },
    },
    "seedIds": ["bs-sem-130"],
  }


def test_booking_bs_sem_135_profile_targets_only_1300_pressed_state():
  runtime = _scaffolding_runtime()

  assert runtime["bsSem135"] == {
    "effects": {
      "booking.schedule.slot.1300": {
        "ariaPressed": True,
      },
    },
    "seedIds": ["bs-sem-135"],
  }


def test_booking_bs_sem_138_profile_targets_only_full_name_validation_message():
  runtime = _scaffolding_runtime()

  assert runtime["bsSem138"] == {
    "effects": {
      "booking.details.fullName": {
        "validationMessage": "Email is required.",
      },
    },
    "seedIds": ["bs-sem-138"],
  }


def test_booking_bs_sem_139_profile_targets_only_email_validation_message():
  runtime = _scaffolding_runtime()

  assert runtime["bsSem139"] == {
    "effects": {
      "booking.details.email": {
        "validationMessage": "Email format is invalid.",
      },
    },
    "seedIds": ["bs-sem-139"],
  }


def test_booking_bs_sem_140_profile_targets_only_phone_validation_message():
  runtime = _scaffolding_runtime()

  assert runtime["bsSem140"] == {
    "effects": {
      "booking.details.phone": {
        "validationMessage": "Phone is optional.",
      },
    },
    "seedIds": ["bs-sem-140"],
  }


def test_booking_bs_sem_151_profile_targets_only_email_autocomplete():
  runtime = _scaffolding_runtime()

  assert runtime["bsSem151"] == {
    "effects": {
      "booking.details.email": {
        "autocomplete": "tel",
      },
    },
    "seedIds": ["bs-sem-151"],
  }


def test_booking_bs_sem_152_profile_targets_only_phone_autocomplete():
  runtime = _scaffolding_runtime()

  assert runtime["bsSem152"] == {
    "effects": {
      "booking.details.phone": {
        "autocomplete": "email",
      },
    },
    "seedIds": ["bs-sem-152"],
  }


def test_booking_bs_sem_153_profile_targets_only_full_name_autocomplete():
  runtime = _scaffolding_runtime()

  assert runtime["bsSem153"] == {
    "effects": {
      "booking.details.fullName": {
        "autocomplete": "organization-title",
      },
    },
    "seedIds": ["bs-sem-153"],
  }


def test_booking_bs_sem_154_profile_targets_only_full_name_autocomplete():
  runtime = _scaffolding_runtime()

  assert runtime["bsSem154"] == {
    "effects": {
      "booking.details.fullName": {
        "autocomplete": "given-name",
      },
    },
    "seedIds": ["bs-sem-154"],
  }


def test_booking_bs_sem_155_profile_targets_only_cancellation_policy_language():
  runtime = _scaffolding_runtime()

  assert runtime["bsSem155"] == {
    "effects": {
      "booking.help.cancellationPolicy": {
        "lang": "fr",
      },
    },
    "seedIds": ["bs-sem-155"],
  }


def test_booking_bs_sem_156_profile_targets_only_confirmation_message_language():
  runtime = _scaffolding_runtime()

  assert runtime["bsSem156"] == {
    "effects": {
      "booking.confirmation.successMessage": {
        "lang": "es",
      },
    },
    "seedIds": ["bs-sem-156"],
  }


def test_booking_bs_sem_157_profile_targets_only_preparation_instructions_language():
  runtime = _scaffolding_runtime()

  assert runtime["bsSem157"] == {
    "effects": {
      "booking.help.preparationInstructions": {
        "lang": "de",
      },
    },
    "seedIds": ["bs-sem-157"],
  }


def test_booking_bs_sem_158_profile_targets_only_arrival_instructions_language():
  runtime = _scaffolding_runtime()

  assert runtime["bsSem158"] == {
    "effects": {
      "booking.help.arrivalInstructions": {
        "lang": "it",
      },
    },
    "seedIds": ["bs-sem-158"],
  }


def test_booking_bs_sem_159_profile_targets_only_help_page_language():
  runtime = _scaffolding_runtime()

  assert runtime["bsSem159"] == {
    "effects": {
      "booking.page.help": {
        "lang": "de",
      },
    },
    "seedIds": ["bs-sem-159"],
  }


def test_booking_bs_sem_160_profile_targets_only_confirmation_page_language():
  runtime = _scaffolding_runtime()

  assert runtime["bsSem160"] == {
    "effects": {
      "booking.page.confirmation": {
        "lang": "es",
      },
    },
    "seedIds": ["bs-sem-160"],
  }


def test_booking_bs_sem_161_profile_targets_only_details_page_language():
  runtime = _scaffolding_runtime()

  assert runtime["bsSem161"] == {
    "effects": {
      "booking.page.details": {
        "lang": "de",
      },
    },
    "seedIds": ["bs-sem-161"],
  }


def test_booking_bs_sem_162_profile_targets_only_review_page_language():
  runtime = _scaffolding_runtime()

  assert runtime["bsSem162"] == {
    "effects": {
      "booking.page.review": {
        "lang": "fr",
      },
    },
    "seedIds": ["bs-sem-162"],
  }


def test_booking_profile_global_resolves_clean_and_rejects_unknown_values():
  configured = _scaffolding_runtime()["configuredGlobal"]

  assert configured["clean"] == []
  assert configured["unknown"]["ok"] is False
  assert "booking-does-not-exist" in configured["unknown"]["message"]


def test_booking_synthetic_label_profile_targets_one_subject_property():
  runtime = _scaffolding_runtime()

  assert runtime["label"] == {
    "effects": {
      "booking.review.cancellationLink": {
        "visibleText": "Synthetic replacement",
      },
    },
    "exactValue": "Synthetic replacement",
    "seedIds": ["booking-test-seed-label"],
    "unrelatedValue": None,
  }


def test_booking_synthetic_profiles_are_isolated():
  runtime = _scaffolding_runtime()

  assert runtime["state"] == {
    "effects": {
      "booking.progress.review": {
        "ariaCurrent": "step",
      },
    },
    "labelValue": None,
    "seedIds": ["booking-test-seed-state"],
    "stateValue": "step",
  }
  assert runtime["label"]["effects"].get("booking.progress.review") is None


def test_booking_synthetic_multiple_seed_profile_combines_only_its_effects():
  runtime = _scaffolding_runtime()

  assert runtime["multiple"] == {
    "effects": {
      "booking.details.email": {
        "accessibleName": "Synthetic email",
      },
      "booking.review.cancellationLink": {
        "visibleText": "Synthetic replacement",
      },
    },
    "seedIds": [
      "booking-test-seed-label",
      "booking-test-seed-secondary",
    ],
    "stateValue": None,
  }


def test_booking_unknown_profile_and_seed_fail_explicitly():
  failures = _scaffolding_runtime()["failures"]

  assert failures["unknownProfile"]["ok"] is False
  assert "booking-does-not-exist" in failures["unknownProfile"]["message"]
  assert failures["unknownSeed"]["ok"] is False
  assert "booking-test-seed-missing" in failures["unknownSeed"]["message"]


def test_booking_unknown_subject_and_malformed_effect_fail_explicitly():
  failures = _scaffolding_runtime()["failures"]

  assert failures["unknownSubject"]["ok"] is False
  assert "booking.subject.doesNotExist" in failures["unknownSubject"]["message"]
  assert failures["malformedEffect"]["ok"] is False
  assert "property" in failures["malformedEffect"]["message"]


def test_booking_duplicate_subject_property_ownership_fails_explicitly():
  duplicate = _scaffolding_runtime()["failures"]["duplicateEffect"]

  assert duplicate["ok"] is False
  assert "booking.review.cancellationLink.visibleText" in duplicate["message"]


def test_booking_app_resolves_profile_and_effects_once_at_startup():
  app_source = (BOOKING_SRC / "App.jsx").read_text(encoding="utf-8")

  assert "resolveBookingProfile()" in app_source
  assert "resolveBookingEffects(resolveBookingProfile())" in app_source
  assert "const benchmarkEffects = useMemo" in app_source
  assert "window.location.pathname" not in (
    BOOKING_BENCHMARK_SRC / "effects.js"
  ).read_text(encoding="utf-8")
  assert "window.location.pathname" not in (
    BOOKING_BENCHMARK_SRC / "profiles.js"
  ).read_text(encoding="utf-8")


def test_booking_production_rendering_has_no_case_or_taxonomy_coupling():
  source_paths = [
    BOOKING_SRC / "App.jsx",
    *BOOKING_SRC.joinpath("components").glob("*.jsx"),
  ]
  source_text = "\n".join(
    path.read_text(encoding="utf-8")
    for path in source_paths
  )
  blocked_tokens = (
    "bs-sem-",
    "co-sem-",
    "tm-sem-",
    "image-alt-not-descriptive",
    "video-captions-inaccurate",
    "lang-mismatch",
    "language-of-parts-mismatch",
    "link-text-mismatch",
    "button-label-mismatch",
    "form-label-mismatch",
    "widget-label-purpose-mismatch",
    "heading-not-descriptive",
    "landmark-purpose-mismatch",
    "page-title-not-descriptive",
    "autocomplete-purpose-mismatch",
    "aria-state-mismatch",
    "table-header-association-mismatch",
    "error-message-mismatch",
    "candidate",
    "violation",
    "taxonomy",
    "expectedViolation",
    "checkout",
    "task-manager",
    "taskManager",
    "__ACCESSGRAPH_CHECKOUT_PROFILE__",
  )

  for token in blocked_tokens:
    assert token not in source_text


@lru_cache(maxsize=1)
def _scaffolding_runtime() -> dict[str, object]:
  script = r"""
    import {
      BOOKING_EFFECTS,
      getBookingEffect,
      resolveBookingEffects,
    } from "./benchmarks/local-spas/booking-scheduler/src/benchmark/effects.js";
    import {
      BOOKING_BS_SEM_112_PROFILE,
      BOOKING_BS_SEM_113_PROFILE,
      BOOKING_BS_SEM_114_PROFILE,
      BOOKING_BS_SEM_115_PROFILE,
      BOOKING_BS_SEM_116_PROFILE,
      BOOKING_BS_SEM_117_PROFILE,
      BOOKING_BS_SEM_118_PROFILE,
      BOOKING_BS_SEM_119_PROFILE,
      BOOKING_BS_SEM_128_PROFILE,
      BOOKING_BS_SEM_129_PROFILE,
      BOOKING_BS_SEM_130_PROFILE,
      BOOKING_BS_SEM_135_PROFILE,
      BOOKING_BS_SEM_138_PROFILE,
      BOOKING_BS_SEM_139_PROFILE,
      BOOKING_BS_SEM_140_PROFILE,
      BOOKING_BS_SEM_151_PROFILE,
      BOOKING_BS_SEM_152_PROFILE,
      BOOKING_BS_SEM_153_PROFILE,
      BOOKING_BS_SEM_154_PROFILE,
      BOOKING_BS_SEM_155_PROFILE,
      BOOKING_BS_SEM_156_PROFILE,
      BOOKING_BS_SEM_157_PROFILE,
      BOOKING_BS_SEM_158_PROFILE,
      BOOKING_BS_SEM_159_PROFILE,
      BOOKING_BS_SEM_160_PROFILE,
      BOOKING_BS_SEM_161_PROFILE,
      BOOKING_BS_SEM_162_PROFILE,
      BOOKING_CLEAN_PROFILE,
      BOOKING_PROFILE_GLOBAL,
      BOOKING_PROFILES,
      resolveBookingProfile,
    } from "./benchmarks/local-spas/booking-scheduler/src/benchmark/profiles.js";
    import {
      BOOKING_BENCHMARK_SEED_IDS,
    } from "./benchmarks/local-spas/booking-scheduler/src/benchmark/seeds.js";
    import {
      BOOKING_SUBJECT_LIST,
      BOOKING_SUBJECTS,
      getBookingSubject,
      getBookingSubjectByTestId,
    } from "./benchmarks/local-spas/booking-scheduler/src/benchmark/subjects.js";

    const syntheticSeedIds = Object.freeze([
      "booking-test-seed-label",
      "booking-test-seed-state",
      "booking-test-seed-secondary",
    ]);
    const syntheticProfiles = Object.freeze({
      "booking-test-profile-label": Object.freeze([
        "booking-test-seed-label",
      ]),
      "booking-test-profile-state": Object.freeze([
        "booking-test-seed-state",
      ]),
      "booking-test-profile-multiple": Object.freeze([
        "booking-test-seed-label",
        "booking-test-seed-secondary",
      ]),
    });
    const syntheticEffects = Object.freeze([
      Object.freeze({
        seedId: "booking-test-seed-label",
        subjectId: BOOKING_SUBJECTS.review.cancellationLink.id,
        property: "visibleText",
        value: "Synthetic replacement",
      }),
      Object.freeze({
        seedId: "booking-test-seed-state",
        subjectId: BOOKING_SUBJECTS.progress.review.id,
        property: "ariaCurrent",
        value: "step",
      }),
      Object.freeze({
        seedId: "booking-test-seed-secondary",
        subjectId: BOOKING_SUBJECTS.details.email.id,
        property: "accessibleName",
        value: "Synthetic email",
      }),
    ]);

    function resolveSynthetic(profileId) {
      const seedIds = resolveBookingProfile(
        profileId,
        syntheticProfiles,
        syntheticSeedIds,
      );
      return {
        seedIds,
        effects: resolveBookingEffects(
          seedIds,
          syntheticEffects,
          BOOKING_SUBJECT_LIST,
          syntheticSeedIds,
        ),
      };
    }

    function resolveProduction(profileId) {
      const seedIds = resolveBookingProfile(profileId);
      return {
        seedIds,
        effects: resolveBookingEffects(seedIds),
      };
    }

    function attempt(callback) {
      try {
        return { ok: true, value: callback() };
      } catch (error) {
        return { ok: false, message: error.message };
      }
    }

    const label = resolveSynthetic("booking-test-profile-label");
    const state = resolveSynthetic("booking-test-profile-state");
    const multiple = resolveSynthetic("booking-test-profile-multiple");
    const duplicateEffects = [
      syntheticEffects[0],
      {
        seedId: "booking-test-seed-secondary",
        subjectId: BOOKING_SUBJECTS.review.cancellationLink.id,
        property: "visibleText",
        value: "Conflicting replacement",
      },
    ];
    globalThis.window = {
      [BOOKING_PROFILE_GLOBAL]: BOOKING_CLEAN_PROFILE,
    };
    const configuredClean = resolveBookingProfile();
    globalThis.window = {
      [BOOKING_PROFILE_GLOBAL]: "booking-does-not-exist",
    };
    const configuredUnknown = attempt(() => resolveBookingProfile());
    delete globalThis.window;

    const output = {
      subjectCount: BOOKING_SUBJECT_LIST.length,
      uniqueSubjectCount: new Set(
        BOOKING_SUBJECT_LIST.map((subject) => subject.id),
      ).size,
      allSubjectsBookingLocal: BOOKING_SUBJECT_LIST.every((subject) =>
        subject.id.startsWith("booking.")
      ),
      subjectLookups: {
        detailsEmail: getBookingSubject("booking.details.email")?.id ?? null,
        reviewCancellation:
          getBookingSubject("booking.review.cancellationLink")?.id ?? null,
        reviewServiceHeading:
          getBookingSubject("booking.review.serviceHeading")?.id ?? null,
        helpCancellationPolicy:
          getBookingSubject("booking.help.cancellationPolicy")?.id ?? null,
        helpPreparationInstructions:
          getBookingSubject("booking.help.preparationInstructions")?.id ?? null,
        helpArrivalInstructions:
          getBookingSubject("booking.help.arrivalInstructions")?.id ?? null,
        schedule0900:
          getBookingSubject("booking.schedule.slot.0900")?.id ?? null,
        schedule1400ByTestId:
          getBookingSubjectByTestId("slot-button-1400")?.id ?? null,
        unknown: getBookingSubject("booking.unknown")?.id ?? null,
      },
      production: {
        caseProfiles: [
          BOOKING_BS_SEM_112_PROFILE,
          BOOKING_BS_SEM_113_PROFILE,
          BOOKING_BS_SEM_114_PROFILE,
          BOOKING_BS_SEM_115_PROFILE,
          BOOKING_BS_SEM_116_PROFILE,
          BOOKING_BS_SEM_117_PROFILE,
          BOOKING_BS_SEM_118_PROFILE,
          BOOKING_BS_SEM_119_PROFILE,
          BOOKING_BS_SEM_128_PROFILE,
          BOOKING_BS_SEM_129_PROFILE,
          BOOKING_BS_SEM_130_PROFILE,
          BOOKING_BS_SEM_135_PROFILE,
          BOOKING_BS_SEM_138_PROFILE,
          BOOKING_BS_SEM_139_PROFILE,
          BOOKING_BS_SEM_140_PROFILE,
          BOOKING_BS_SEM_151_PROFILE,
          BOOKING_BS_SEM_152_PROFILE,
          BOOKING_BS_SEM_153_PROFILE,
          BOOKING_BS_SEM_154_PROFILE,
          BOOKING_BS_SEM_155_PROFILE,
          BOOKING_BS_SEM_156_PROFILE,
          BOOKING_BS_SEM_157_PROFILE,
          BOOKING_BS_SEM_158_PROFILE,
          BOOKING_BS_SEM_159_PROFILE,
          BOOKING_BS_SEM_160_PROFILE,
          BOOKING_BS_SEM_161_PROFILE,
          BOOKING_BS_SEM_162_PROFILE,
        ],
        cleanProfile: BOOKING_CLEAN_PROFILE,
        profileCount: Object.keys(BOOKING_PROFILES).length,
        mutationProfileCount: Object.keys(BOOKING_PROFILES).filter(
          (profileId) => profileId !== BOOKING_CLEAN_PROFILE,
        ).length,
        seedCount: BOOKING_BENCHMARK_SEED_IDS.length,
        effectCount: BOOKING_EFFECTS.length,
      },
      bsSem112: resolveProduction(BOOKING_BS_SEM_112_PROFILE),
      bsSem113: resolveProduction(BOOKING_BS_SEM_113_PROFILE),
      bsSem114: resolveProduction(BOOKING_BS_SEM_114_PROFILE),
      bsSem115: resolveProduction(BOOKING_BS_SEM_115_PROFILE),
      bsSem116: resolveProduction(BOOKING_BS_SEM_116_PROFILE),
      bsSem117: resolveProduction(BOOKING_BS_SEM_117_PROFILE),
      bsSem118: resolveProduction(BOOKING_BS_SEM_118_PROFILE),
      bsSem119: resolveProduction(BOOKING_BS_SEM_119_PROFILE),
      bsSem128: resolveProduction(BOOKING_BS_SEM_128_PROFILE),
      bsSem129: resolveProduction(BOOKING_BS_SEM_129_PROFILE),
      bsSem130: resolveProduction(BOOKING_BS_SEM_130_PROFILE),
      bsSem135: resolveProduction(BOOKING_BS_SEM_135_PROFILE),
      bsSem138: resolveProduction(BOOKING_BS_SEM_138_PROFILE),
      bsSem139: resolveProduction(BOOKING_BS_SEM_139_PROFILE),
      bsSem140: resolveProduction(BOOKING_BS_SEM_140_PROFILE),
      bsSem151: resolveProduction(BOOKING_BS_SEM_151_PROFILE),
      bsSem152: resolveProduction(BOOKING_BS_SEM_152_PROFILE),
      bsSem153: resolveProduction(BOOKING_BS_SEM_153_PROFILE),
      bsSem154: resolveProduction(BOOKING_BS_SEM_154_PROFILE),
      bsSem155: resolveProduction(BOOKING_BS_SEM_155_PROFILE),
      bsSem156: resolveProduction(BOOKING_BS_SEM_156_PROFILE),
      bsSem157: resolveProduction(BOOKING_BS_SEM_157_PROFILE),
      bsSem158: resolveProduction(BOOKING_BS_SEM_158_PROFILE),
      bsSem159: resolveProduction(BOOKING_BS_SEM_159_PROFILE),
      bsSem160: resolveProduction(BOOKING_BS_SEM_160_PROFILE),
      bsSem161: resolveProduction(BOOKING_BS_SEM_161_PROFILE),
      bsSem162: resolveProduction(BOOKING_BS_SEM_162_PROFILE),
      baseline: {
        undefined: resolveProduction(undefined),
        null: resolveProduction(null),
        empty: resolveProduction(""),
        clean: resolveProduction(BOOKING_CLEAN_PROFILE),
      },
      configuredGlobal: {
        clean: configuredClean,
        unknown: configuredUnknown,
      },
      label: {
        ...label,
        exactValue: getBookingEffect(
          label.effects,
          BOOKING_SUBJECTS.review.cancellationLink.id,
          "visibleText",
        ) ?? null,
        unrelatedValue: getBookingEffect(
          label.effects,
          BOOKING_SUBJECTS.details.email.id,
          "accessibleName",
        ) ?? null,
      },
      state: {
        ...state,
        stateValue: getBookingEffect(
          state.effects,
          BOOKING_SUBJECTS.progress.review.id,
          "ariaCurrent",
        ) ?? null,
        labelValue: getBookingEffect(
          state.effects,
          BOOKING_SUBJECTS.review.cancellationLink.id,
          "visibleText",
        ) ?? null,
      },
      multiple: {
        ...multiple,
        stateValue: getBookingEffect(
          multiple.effects,
          BOOKING_SUBJECTS.progress.review.id,
          "ariaCurrent",
        ) ?? null,
      },
      failures: {
        unknownProfile: attempt(() =>
          resolveBookingProfile(
            "booking-does-not-exist",
            syntheticProfiles,
            syntheticSeedIds,
          )
        ),
        unknownSeed: attempt(() =>
          resolveBookingProfile(
            "booking-test-profile-unknown-seed",
            {
              "booking-test-profile-unknown-seed": [
                "booking-test-seed-missing",
              ],
            },
            syntheticSeedIds,
          )
        ),
        unknownSubject: attempt(() =>
          resolveBookingEffects(
            ["booking-test-seed-label"],
            [{
              seedId: "booking-test-seed-label",
              subjectId: "booking.subject.doesNotExist",
              property: "visibleText",
              value: "Synthetic replacement",
            }],
            BOOKING_SUBJECT_LIST,
            syntheticSeedIds,
          )
        ),
        malformedEffect: attempt(() =>
          resolveBookingEffects(
            ["booking-test-seed-label"],
            [{
              seedId: "booking-test-seed-label",
              subjectId: BOOKING_SUBJECTS.review.cancellationLink.id,
              value: "Synthetic replacement",
            }],
            BOOKING_SUBJECT_LIST,
            syntheticSeedIds,
          )
        ),
        duplicateEffect: attempt(() =>
          resolveBookingEffects(
            [
              "booking-test-seed-label",
              "booking-test-seed-secondary",
            ],
            duplicateEffects,
            BOOKING_SUBJECT_LIST,
            syntheticSeedIds,
          )
        ),
      },
    };

    console.log(JSON.stringify(output));
  """
  completed = subprocess.run(
    ["node", "--input-type=module", "-e", script],
    cwd=REPO_ROOT,
    text=True,
    capture_output=True,
    check=False,
  )
  assert completed.returncode == 0, completed.stderr
  return json.loads(completed.stdout)
