function subject(id, testId, description) {
  return Object.freeze({ id, testId, description });
}

export const BOOKING_SUBJECTS = Object.freeze({
  page: Object.freeze({
    services: subject(
      "booking.page.services",
      "route-services",
      "Services route page and document title.",
    ),
    schedule: subject(
      "booking.page.schedule",
      "route-schedule",
      "Schedule route page and document title.",
    ),
    details: subject(
      "booking.page.details",
      "route-details",
      "Customer-details route page and document title.",
    ),
    review: subject(
      "booking.page.review",
      "route-review",
      "Appointment-review route page and document title.",
    ),
    confirmation: subject(
      "booking.page.confirmation",
      "route-confirmation",
      "Booking-confirmation route page and document title.",
    ),
    help: subject(
      "booking.page.help",
      "route-help",
      "Help and policies route page and document title.",
    ),
  }),
  navigation: Object.freeze({
    help: subject(
      "booking.navigation.help",
      null,
      "General navigation link to Help and policies.",
    ),
    scheduleBack: subject(
      "booking.navigation.scheduleBack",
      "back-to-services",
      "Schedule route link back to service selection.",
    ),
    detailsBack: subject(
      "booking.navigation.detailsBack",
      "back-to-schedule",
      "Details route link back to scheduling.",
    ),
  }),
  progress: Object.freeze({
    navigation: subject(
      "booking.progress.navigation",
      "booking-progress",
      "Booking workflow progress navigation.",
    ),
    services: subject(
      "booking.progress.services",
      "booking-progress-services",
      "Service-selection progress step.",
    ),
    schedule: subject(
      "booking.progress.schedule",
      "booking-progress-schedule",
      "Scheduling progress step.",
    ),
    details: subject(
      "booking.progress.details",
      "booking-progress-details",
      "Customer-details progress step.",
    ),
    review: subject(
      "booking.progress.review",
      "booking-progress-review",
      "Appointment-review progress step.",
    ),
    confirmation: subject(
      "booking.progress.confirmation",
      "booking-progress-confirmation",
      "Booking-confirmation progress step.",
    ),
  }),
  services: Object.freeze({
    heading: subject(
      "booking.services.heading",
      null,
      "Choose a service section heading.",
    ),
    provider: subject(
      "booking.services.provider",
      "service-provider-context",
      "Appointment provider and location context.",
    ),
    consultation: subject(
      "booking.services.consultation",
      "service-option-svc-consultation",
      "Consultation service option.",
    ),
    repairAssessment: subject(
      "booking.services.repairAssessment",
      "service-option-svc-repair-assessment",
      "Repair assessment service option.",
    ),
    followUpCall: subject(
      "booking.services.followUpCall",
      "service-option-svc-follow-up-call",
      "Follow-up call service option.",
    ),
    preparationLink: subject(
      "booking.services.preparationLink",
      "preparation-link",
      "Link to appointment preparation information.",
    ),
    continueButton: subject(
      "booking.services.continueButton",
      "continue-to-schedule",
      "Button that advances to scheduling.",
    ),
  }),
  schedule: Object.freeze({
    heading: subject(
      "booking.schedule.heading",
      null,
      "Choose a date and time section heading.",
    ),
    date: subject(
      "booking.schedule.date",
      "schedule-date-input",
      "Appointment date input.",
    ),
    slotList: subject(
      "booking.schedule.slotList",
      "slot-list",
      "Appointment time options for the selected fixture date.",
    ),
    slot0900: subject(
      "booking.schedule.slot.0900",
      "slot-button-0900",
      "09:00 appointment slot.",
    ),
    slot1030: subject(
      "booking.schedule.slot.1030",
      "slot-unavailable-1030",
      "10:30 unavailable appointment slot.",
    ),
    slot1300: subject(
      "booking.schedule.slot.1300",
      "slot-button-1300",
      "13:00 appointment slot.",
    ),
    slot1530: subject(
      "booking.schedule.slot.1530",
      "slot-button-1530",
      "15:30 appointment slot.",
    ),
    slot0830: subject(
      "booking.schedule.slot.0830",
      "slot-button-0830",
      "08:30 appointment slot.",
    ),
    slot1100: subject(
      "booking.schedule.slot.1100",
      "slot-unavailable-1100",
      "11:00 unavailable appointment slot.",
    ),
    slot1400: subject(
      "booking.schedule.slot.1400",
      "slot-button-1400",
      "14:00 appointment slot.",
    ),
    slot1600: subject(
      "booking.schedule.slot.1600",
      "slot-button-1600",
      "16:00 appointment slot.",
    ),
    emptyPrompt: subject(
      "booking.schedule.emptyPrompt",
      "slot-empty-prompt",
      "Prompt shown before a supported fixture date is selected.",
    ),
    continueButton: subject(
      "booking.schedule.continueButton",
      "continue-to-details",
      "Button that advances to customer details.",
    ),
  }),
  details: Object.freeze({
    heading: subject(
      "booking.details.heading",
      null,
      "Customer details section heading.",
    ),
    fullName: subject(
      "booking.details.fullName",
      "details-full-name",
      "Customer full-name field.",
    ),
    email: subject(
      "booking.details.email",
      "details-email",
      "Customer email field.",
    ),
    phone: subject(
      "booking.details.phone",
      "details-phone",
      "Customer phone field.",
    ),
    notes: subject(
      "booking.details.notes",
      "details-notes",
      "Optional customer notes field.",
    ),
    accessibilityNeeds: subject(
      "booking.details.accessibilityNeeds",
      "details-accessibility-needs",
      "Optional accessibility needs field.",
    ),
    validationStatus: subject(
      "booking.details.validationStatus",
      "details-validation-status",
      "Customer-details validation status message.",
    ),
    continueButton: subject(
      "booking.details.continueButton",
      "details-submit",
      "Button that validates details and advances to review.",
    ),
  }),
  review: Object.freeze({
    heading: subject(
      "booking.review.heading",
      null,
      "Review appointment details section heading.",
    ),
    serviceHeading: subject(
      "booking.review.serviceHeading",
      null,
      "Review service summary panel heading.",
    ),
    reviewNotice: subject(
      "booking.review.notice",
      "review-only-note",
      "Notice that the appointment has not yet been confirmed.",
    ),
    changeService: subject(
      "booking.review.changeService",
      "change-service",
      "Link for changing the selected service.",
    ),
    changeAppointment: subject(
      "booking.review.changeAppointment",
      "change-appointment",
      "Link for changing the appointment date or time.",
    ),
    editDetails: subject(
      "booking.review.editDetails",
      "edit-details",
      "Link for editing customer details.",
    ),
    cancellationLink: subject(
      "booking.review.cancellationLink",
      "cancellation-policy-link",
      "Link to the cancellation policy.",
    ),
    reschedulingLink: subject(
      "booking.review.reschedulingLink",
      "rescheduling-help-link",
      "Link to rescheduling help.",
    ),
    confirmButton: subject(
      "booking.review.confirmButton",
      "confirm-booking",
      "Button that confirms the reviewed booking.",
    ),
    provider: subject(
      "booking.review.provider",
      "review-provider-summary",
      "Review summary for the clinic and location.",
    ),
  }),
  confirmation: Object.freeze({
    heading: subject(
      "booking.confirmation.heading",
      null,
      "Confirmed appointment section heading.",
    ),
    successMessage: subject(
      "booking.confirmation.successMessage",
      "confirmation-message",
      "Booking completion message.",
    ),
    reference: subject(
      "booking.confirmation.reference",
      "confirmation-reference",
      "Immutable confirmed booking reference.",
    ),
    provider: subject(
      "booking.confirmation.provider",
      "confirmation-provider-summary",
      "Confirmed booking clinic and location summary.",
    ),
    directionsLink: subject(
      "booking.confirmation.directionsLink",
      "directions-link",
      "Link to clinic directions.",
    ),
    contactLink: subject(
      "booking.confirmation.contactLink",
      "contact-clinic-link",
      "Link to clinic contact information.",
    ),
    bookAnother: subject(
      "booking.confirmation.bookAnother",
      "book-another-appointment",
      "Button that resets the flow for another appointment.",
    ),
  }),
  help: Object.freeze({
    content: subject(
      "booking.help.content",
      "help-content",
      "Help and policies content.",
    ),
    clinicHeading: subject(
      "booking.help.clinicHeading",
      null,
      "Clinic information heading.",
    ),
    cancellationHeading: subject(
      "booking.help.cancellationHeading",
      null,
      "Cancellation policy heading.",
    ),
    cancellationPolicy: subject(
      "booking.help.cancellationPolicy",
      "cancellation-policy-text",
      "Cancellation policy guidance paragraph.",
    ),
    reschedulingHeading: subject(
      "booking.help.reschedulingHeading",
      null,
      "Rescheduling guidance heading.",
    ),
    preparationHeading: subject(
      "booking.help.preparationHeading",
      null,
      "Appointment preparation heading.",
    ),
    preparationInstructions: subject(
      "booking.help.preparationInstructions",
      "preparation-instructions-text",
      "Appointment preparation guidance paragraph.",
    ),
    contactHeading: subject(
      "booking.help.contactHeading",
      null,
      "Clinic contact heading.",
    ),
    directionsHeading: subject(
      "booking.help.directionsHeading",
      null,
      "Clinic directions heading.",
    ),
    arrivalInstructions: subject(
      "booking.help.arrivalInstructions",
      "arrival-instructions-text",
      "Clinic arrival guidance paragraph.",
    ),
  }),
  status: Object.freeze({
    message: subject(
      "booking.status.message",
      "status-region",
      "Application workflow status message.",
    ),
  }),
});

export const BOOKING_SUBJECT_LIST = Object.freeze(
  collectSubjects(BOOKING_SUBJECTS),
);

const subjectIds = BOOKING_SUBJECT_LIST.map((item) => item.id);
if (new Set(subjectIds).size !== subjectIds.length) {
  throw new Error("Booking subject IDs must be unique.");
}

export const BOOKING_SUBJECT_BY_ID = Object.freeze(
  Object.fromEntries(BOOKING_SUBJECT_LIST.map((item) => [item.id, item])),
);

export const BOOKING_SUBJECT_BY_TEST_ID = Object.freeze(
  Object.fromEntries(
    BOOKING_SUBJECT_LIST.filter((item) => item.testId).map((item) => [
      item.testId,
      item,
    ]),
  ),
);

export function getBookingSubject(subjectId) {
  return BOOKING_SUBJECT_BY_ID[subjectId] ?? null;
}

export function getBookingSubjectByTestId(testId) {
  return BOOKING_SUBJECT_BY_TEST_ID[testId] ?? null;
}

function collectSubjects(group) {
  return Object.values(group).flatMap((value) =>
    typeof value?.id === "string" ? [value] : collectSubjects(value),
  );
}
