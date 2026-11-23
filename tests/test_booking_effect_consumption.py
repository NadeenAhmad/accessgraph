from __future__ import annotations

import json
import subprocess
from functools import lru_cache
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BOOKING_DIR = REPO_ROOT / "benchmarks" / "local-spas" / "booking-scheduler"
BOOKING_SRC = BOOKING_DIR / "src"


def test_slot_effects_preserve_visible_behavior_and_support_false_state():
  runtime = _effect_runtime()

  assert runtime["slot"] == {
    "clean": {
      "accessibleName": None,
      "ariaPressed": True,
      "selectedTime": "09:00",
      "text": "09:00Selected",
      "unselectedAriaPressed": None,
    },
    "effect": {
      "accessibleName": "Synthetic slot name",
      "ariaPressed": False,
      "selectedTime": "09:00",
      "text": "09:00Selected",
    },
  }


def test_service_review_link_and_heading_effects_are_isolated():
  runtime = _effect_runtime()

  assert runtime["service"] == {
    "cleanName": "Consultation",
    "description": "Initial planning appointment for the benchmark fixture.",
    "duration": "30 minutes",
    "effectName": "Synthetic service name",
    "inputId": "service-svc-consultation",
    "inputName": "service",
    "inputValue": "svc-consultation",
    "labelFor": "service-svc-consultation",
  }
  assert runtime["review"] == {
    "cleanHeading": "Service",
    "cleanLinkTarget": "/services",
    "cleanLinkText": "Change service",
    "routeEffectHref": "/services",
    "routeEffectTarget": "/synthetic-route",
    "routeEffectText": "Change service",
    "serviceContent": "Consultation",
    "textEffectHeading": "Synthetic heading",
    "textEffectHref": "/services",
    "textEffectTarget": "/services",
    "textEffectText": "Synthetic link text",
  }
  assert runtime["workflowLink"] == {
    "activatedRoute": "/synthetic-route",
    "href": "/clean-route",
    "prevented": True,
    "text": "Clean link text",
  }


def test_validation_message_effect_uses_clean_fallback_and_component_consumes_it():
  runtime = _effect_runtime()
  source = (BOOKING_SRC / "components" / "DetailsPage.jsx").read_text(
    encoding="utf-8"
  )

  assert runtime["validation"] == {
    "clean": "Phone is required.",
    "effect": "Synthetic field message",
  }
  assert '"validationMessage"' in source
  assert "fieldSubject?.id" in source
  assert "{validationMessage}" in source
  assert "validateRequiredCustomerDetails(customerDetails)" in source
  assert "focusField(firstInvalidField.name)" in source


def test_booking_effect_consumption_has_no_case_or_taxonomy_coupling():
  production_files = (
    BOOKING_SRC / "App.jsx",
    BOOKING_SRC / "benchmark" / "effects.js",
    BOOKING_SRC / "benchmark" / "subjects.js",
    BOOKING_SRC / "components" / "DetailsPage.jsx",
    BOOKING_SRC / "components" / "ReviewPage.jsx",
    BOOKING_SRC / "components" / "SchedulePage.jsx",
    BOOKING_SRC / "components" / "ServiceSelectionPage.jsx",
    BOOKING_SRC / "components" / "SlotList.jsx",
    BOOKING_SRC / "components" / "WorkflowLink.jsx",
  )
  source_text = "\n".join(path.read_text(encoding="utf-8") for path in production_files)

  for token in (
    "bs-sem-",
    "bs-ctrl-",
    "button-label-mismatch",
    "link-text-mismatch",
    "form-label-mismatch",
    "aria-state-mismatch",
    "heading-not-descriptive",
    "error-message-mismatch",
    "caseId",
    "violationType",
  ):
    assert token not in source_text


@lru_cache(maxsize=1)
def _effect_runtime() -> dict[str, object]:
  script = r"""
    import { createServer } from "vite";
    import react from "@vitejs/plugin-react";

    const server = await createServer({
      root: process.cwd(),
      configFile: false,
      cacheDir: `${process.env.TEMP}/accessgraph-booking-vite-test`,
      logLevel: "silent",
      appType: "custom",
      plugins: [react()],
      server: { middlewareMode: true },
    });

    try {
      const { resolveBookingEffects, getBookingEffect } =
        await server.ssrLoadModule("/src/benchmark/effects.js");
      const { BOOKING_SUBJECT_LIST, BOOKING_SUBJECTS } =
        await server.ssrLoadModule("/src/benchmark/subjects.js");
      const { SERVICES } = await server.ssrLoadModule("/src/data/fixtures.js");
      const { SlotList } =
        await server.ssrLoadModule("/src/components/SlotList.jsx");
      const { ServiceSelectionPage } =
        await server.ssrLoadModule("/src/components/ServiceSelectionPage.jsx");
      const { ReviewPage } =
        await server.ssrLoadModule("/src/components/ReviewPage.jsx");
      const { WorkflowLink } =
        await server.ssrLoadModule("/src/components/WorkflowLink.jsx");

      const seedId = "booking-test-effect";
      const resolve = (effectEntries) => resolveBookingEffects(
        [seedId],
        effectEntries.map((entry) => ({ seedId, ...entry })),
        BOOKING_SUBJECT_LIST,
        [seedId],
      );
      const emptyEffects = Object.freeze({});
      const slotEffects = resolve([
        {
          subjectId: BOOKING_SUBJECTS.schedule.slot0900.id,
          property: "accessibleName",
          value: "Synthetic slot name",
        },
        {
          subjectId: BOOKING_SUBJECTS.schedule.slot0900.id,
          property: "ariaPressed",
          value: false,
        },
      ]);
      const serviceEffects = resolve([{
        subjectId: BOOKING_SUBJECTS.services.consultation.id,
        property: "serviceName",
        value: "Synthetic service name",
      }]);
      const reviewTextEffects = resolve([
        {
          subjectId: BOOKING_SUBJECTS.review.changeService.id,
          property: "text",
          value: "Synthetic link text",
        },
        {
          subjectId: BOOKING_SUBJECTS.review.serviceHeading.id,
          property: "text",
          value: "Synthetic heading",
        },
      ]);
      const reviewRouteEffects = resolve([{
        subjectId: BOOKING_SUBJECTS.review.changeService.id,
        property: "activationTargetRoute",
        value: "/synthetic-route",
      }]);
      const validationEffects = resolve([{
        subjectId: BOOKING_SUBJECTS.details.phone.id,
        property: "validationMessage",
        value: "Synthetic field message",
      }]);

      let selectedTime = null;
      const slotProps = {
        selectedDate: "2026-06-16",
        slots: [
          { time: "09:00", available: true },
          { time: "13:00", available: true },
        ],
        selectedSlotTime: "09:00",
        onSelectSlot: (time) => { selectedTime = time; },
      };
      const cleanSlotTree = SlotList({
        ...slotProps,
        benchmarkEffects: emptyEffects,
      });
      const cleanSlot = findByTestId(cleanSlotTree, "slot-button-0900");
      const cleanUnselectedSlot = findByTestId(cleanSlotTree, "slot-button-1300");
      cleanSlot.props.onClick();
      const cleanSelectedTime = selectedTime;
      selectedTime = null;
      const effectSlotTree = SlotList({
        ...slotProps,
        benchmarkEffects: slotEffects,
      });
      const effectSlot = findByTestId(effectSlotTree, "slot-button-0900");
      effectSlot.props.onClick();

      const serviceProps = {
        services: SERVICES,
        selectedService: SERVICES[0],
        selectedServiceId: SERVICES[0].id,
        selectedDate: "",
        selectedSlotTime: null,
        stepStates: [],
        onNavigate: () => {},
        onSelectService: () => {},
        onContinue: () => {},
      };
      const cleanServiceTree = ServiceSelectionPage({
        ...serviceProps,
        benchmarkEffects: emptyEffects,
      });
      const effectServiceTree = ServiceSelectionPage({
        ...serviceProps,
        benchmarkEffects: serviceEffects,
      });
      const cleanOption = findByTestId(
        cleanServiceTree,
        "service-option-svc-consultation",
      );
      const effectOption = findByTestId(
        effectServiceTree,
        "service-option-svc-consultation",
      );
      const serviceInput = findByTestId(
        cleanOption,
        "service-radio-svc-consultation",
      );
      const serviceLabel = find(cleanOption, (node) => node.type === "label");

      const reviewProps = {
        selectedService: SERVICES[0],
        selectedDate: "2026-06-16",
        selectedSlotTime: "09:00",
        customerDetails: {
          fullName: "Jordan Lee",
          email: "jordan@example.test",
          phone: "555-0134",
          notes: "",
        },
        stepStates: [],
        onNavigate: () => {},
        onConfirmBooking: () => {},
      };
      const cleanReview = ReviewPage({
        ...reviewProps,
        benchmarkEffects: emptyEffects,
      });
      const textReview = ReviewPage({
        ...reviewProps,
        benchmarkEffects: reviewTextEffects,
      });
      const routeReview = ReviewPage({
        ...reviewProps,
        benchmarkEffects: reviewRouteEffects,
      });
      const cleanLink = findByTestId(cleanReview, "change-service");
      const textLink = findByTestId(textReview, "change-service");
      const routeLink = findByTestId(routeReview, "change-service");

      let activatedRoute = null;
      let prevented = false;
      const workflowAnchor = WorkflowLink({
        to: "/clean-route",
        activationTargetRoute: "/synthetic-route",
        onNavigate: (route) => { activatedRoute = route; },
        children: "Clean link text",
      });
      workflowAnchor.props.onClick({
        defaultPrevented: false,
        button: 0,
        metaKey: false,
        ctrlKey: false,
        shiftKey: false,
        altKey: false,
        preventDefault: () => { prevented = true; },
      });

      const output = {
        slot: {
          clean: {
            accessibleName: cleanSlot.props["aria-label"] ?? null,
            ariaPressed: cleanSlot.props["aria-pressed"] ?? null,
            selectedTime: cleanSelectedTime,
            text: textContent(cleanSlot),
            unselectedAriaPressed:
              cleanUnselectedSlot.props["aria-pressed"] ?? null,
          },
          effect: {
            accessibleName: effectSlot.props["aria-label"] ?? null,
            ariaPressed: effectSlot.props["aria-pressed"] ?? null,
            selectedTime,
            text: textContent(effectSlot),
          },
        },
        service: {
          cleanName: textContent(findByClass(cleanOption, "service-name")),
          effectName: textContent(findByClass(effectOption, "service-name")),
          duration: textContent(findByClass(effectOption, "service-duration")),
          description: textContent(
            findByClass(effectOption, "service-description"),
          ),
          inputId: serviceInput.props.id,
          inputName: serviceInput.props.name,
          inputValue: serviceInput.props.value,
          labelFor: serviceLabel.props.htmlFor,
        },
        review: {
          cleanHeading: textContent(findById(cleanReview, "review-service-heading")),
          cleanLinkText: textContent(cleanLink),
          cleanLinkTarget: cleanLink.props.activationTargetRoute,
          textEffectHeading:
            textContent(findById(textReview, "review-service-heading")),
          textEffectText: textContent(textLink),
          textEffectHref: textLink.props.to,
          textEffectTarget: textLink.props.activationTargetRoute,
          routeEffectText: textContent(routeLink),
          routeEffectHref: routeLink.props.to,
          routeEffectTarget: routeLink.props.activationTargetRoute,
          serviceContent: textContent(
            findByTestId(textReview, "review-service-name"),
          ),
        },
        workflowLink: {
          href: workflowAnchor.props.href,
          text: textContent(workflowAnchor),
          activatedRoute,
          prevented,
        },
        validation: {
          clean: getBookingEffect(
            emptyEffects,
            BOOKING_SUBJECTS.details.phone.id,
            "validationMessage",
            "Phone is required.",
          ),
          effect: getBookingEffect(
            validationEffects,
            BOOKING_SUBJECTS.details.phone.id,
            "validationMessage",
            "Phone is required.",
          ),
        },
      };

      console.log(JSON.stringify(output));
    } finally {
      await server.close();
    }

    function childNodes(node) {
      if (!node || typeof node !== "object") {
        return [];
      }
      const children = node.props?.children;
      return Array.isArray(children) ? children.flat(Infinity) : [children];
    }

    function find(node, predicate) {
      if (!node || typeof node !== "object") {
        return null;
      }
      if (predicate(node)) {
        return node;
      }
      for (const child of childNodes(node)) {
        const match = find(child, predicate);
        if (match) {
          return match;
        }
      }
      return null;
    }

    function findByTestId(node, testId) {
      return find(node, (item) => item.props?.["data-testid"] === testId);
    }

    function findById(node, id) {
      return find(node, (item) => item.props?.id === id);
    }

    function findByClass(node, className) {
      return find(node, (item) => item.props?.className === className);
    }

    function textContent(node) {
      if (node === null || node === undefined || typeof node === "boolean") {
        return "";
      }
      if (typeof node === "string" || typeof node === "number") {
        return String(node);
      }
      if (Array.isArray(node)) {
        return node.map(textContent).join("");
      }
      return textContent(node.props?.children);
    }
  """
  completed = subprocess.run(
    ["node", "--input-type=module", "-e", script],
    cwd=BOOKING_DIR,
    text=True,
    capture_output=True,
    check=False,
  )
  assert completed.returncode == 0, completed.stderr
  return json.loads(completed.stdout)
