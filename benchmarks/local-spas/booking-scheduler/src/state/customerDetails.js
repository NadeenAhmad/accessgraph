export const CUSTOMER_FIELDS = [
  {
    name: "fullName",
    label: "Full name",
    testId: "details-full-name",
    type: "text",
    autoComplete: "name",
    required: true,
  },
  {
    name: "email",
    label: "Email",
    testId: "details-email",
    type: "email",
    autoComplete: "email",
    required: true,
  },
  {
    name: "phone",
    label: "Phone",
    testId: "details-phone",
    type: "tel",
    autoComplete: "tel",
    required: true,
  },
  {
    name: "notes",
    label: "Notes",
    testId: "details-notes",
    required: false,
  },
  {
    name: "accessibilityNeeds",
    label: "Accessibility needs",
    testId: "details-accessibility-needs",
    placeholder: "Accessibility needs, preparation notes, or special requests",
    description:
      "Share accessibility needs, preparation notes, or special requests for this appointment.",
    required: false,
  },
];

export function createCustomerDetailsDraft() {
  return CUSTOMER_FIELDS.reduce((values, field) => {
    values[field.name] = "";
    return values;
  }, {});
}

export function validateRequiredCustomerDetails(values) {
  return CUSTOMER_FIELDS.reduce((errors, field) => {
    if (field.required && !values[field.name].trim()) {
      errors[field.name] = `${field.label} is required.`;
    }

    return errors;
  }, {});
}

export function normalizeCustomerDetails(values) {
  return CUSTOMER_FIELDS.reduce((details, field) => {
    details[field.name] = values[field.name].trim();
    return details;
  }, {});
}

export function areCustomerDetailsValid(values) {
  return Object.keys(validateRequiredCustomerDetails(values)).length === 0;
}
