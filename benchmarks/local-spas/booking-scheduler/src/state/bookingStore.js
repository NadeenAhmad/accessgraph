import { AVAILABILITY, SERVICES } from "../data/fixtures.js";
import { areCustomerDetailsValid } from "./customerDetails.js";

const BOOKING_STEP_IDS = [
  "services",
  "schedule",
  "details",
  "review",
  "confirmation",
];

export function getServiceById(serviceId) {
  return SERVICES.find((service) => service.id === serviceId) ?? null;
}

export function getAvailabilityForDate(date) {
  return AVAILABILITY[date] ?? [];
}

export function isSupportedFixtureDate(date) {
  return Boolean(AVAILABILITY[date]);
}

export function getSlotByTime(date, time) {
  return getAvailabilityForDate(date).find((slot) => slot.time === time) ?? null;
}

export function isAvailableSlot(date, time) {
  return Boolean(getSlotByTime(date, time)?.available);
}

export function hasCompleteBookingSelection(state) {
  return Boolean(
    state.selectedServiceId &&
      isSupportedFixtureDate(state.selectedDate) &&
      isAvailableSlot(state.selectedDate, state.selectedSlotTime),
  );
}

export function canReachReview(state) {
  return Boolean(
    hasCompleteBookingSelection(state) &&
      state.customerDetailsSubmitted &&
      areCustomerDetailsValid(state.customerDetailsDraft),
  );
}

export function createConfirmedBooking(state) {
  if (!canReachReview(state)) {
    return null;
  }

  const service = getServiceById(state.selectedServiceId);

  if (!service) {
    return null;
  }

  return Object.freeze({
    reference: createBookingReference(state),
    service: Object.freeze({
      id: service.id,
      name: service.name,
      duration: service.duration,
    }),
    date: state.selectedDate,
    time: state.selectedSlotTime,
    customer: Object.freeze({
      fullName: state.customerDetailsDraft.fullName,
      email: state.customerDetailsDraft.email,
      phone: state.customerDetailsDraft.phone,
    }),
  });
}

export function getBookingRouteAvailability(state) {
  const isConfirmed = Boolean(state.confirmedBooking);
  const hasService = Boolean(state.selectedServiceId);
  const hasAppointment = hasCompleteBookingSelection(state);

  return {
    services: !isConfirmed,
    schedule: !isConfirmed && hasService,
    details: !isConfirmed && hasAppointment,
    review: !isConfirmed && canReachReview(state),
    confirmation: isConfirmed,
  };
}

export function getBookingProgressSteps(state, currentStep) {
  const availability = getBookingRouteAvailability(state);
  const isConfirmed = Boolean(state.confirmedBooking);
  const completed = {
    services: isConfirmed || Boolean(state.selectedServiceId),
    schedule: isConfirmed || hasCompleteBookingSelection(state),
    details: isConfirmed || canReachReview(state),
    review: isConfirmed,
    confirmation: false,
  };

  return BOOKING_STEP_IDS.reduce((stepStates, stepId) => {
    if (stepId === currentStep) {
      stepStates[stepId] = "current";
    } else if (completed[stepId]) {
      stepStates[stepId] = "completed";
    } else if (availability[stepId]) {
      stepStates[stepId] = "available";
    } else {
      stepStates[stepId] = "unavailable";
    }

    return stepStates;
  }, {});
}

export function formatFixtureDate(date) {
  if (!date) {
    return "No date selected";
  }

  if (date === "2026-06-16") {
    return "June 16, 2026";
  }

  if (date === "2026-06-18") {
    return "June 18, 2026";
  }

  return date;
}

export function formatSlotForTestId(time) {
  return time.replace(":", "");
}

function createBookingReference(state) {
  const date = state.selectedDate.replaceAll("-", "");
  const time = state.selectedSlotTime.replace(":", "");
  const service = state.selectedServiceId.replace(/^svc-/, "").toUpperCase();

  return `BKG-${date}-${time}-${service}`;
}
