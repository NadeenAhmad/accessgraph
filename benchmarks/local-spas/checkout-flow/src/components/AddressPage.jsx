import { useRef, useState } from "react";
import { getAutocompleteValueOverride } from "../benchmark/effects/autocompleteEffects.js";
import { getErrorMessageTextOverride } from "../benchmark/effects/errorMessageEffects.js";
import {
  CHECKOUT_FORM_LABEL_TARGETS,
  getFormLabelTextOverride,
} from "../benchmark/effects/formLabelEffects.js";
import {
  CHECKOUT_LANDMARK_TARGETS,
  getLandmarkAccessibleNameOverride,
} from "../benchmark/effects/landmarkEffects.js";
import { CartSummary } from "./CartSummary.jsx";
import { CheckoutProgress } from "./CheckoutProgress.jsx";

export const ADDRESS_FIELDS = [
  {
    name: "fullName",
    label: "Full name",
    testId: "address-full-name",
    targetId: "checkout.address.fullName",
    autoComplete: "name",
    type: "text",
  },
  {
    name: "email",
    label: "Email",
    testId: "address-email",
    targetId: CHECKOUT_FORM_LABEL_TARGETS.addressEmail,
    autoComplete: "email",
    type: "email",
    pattern: "[^\\s@]+@[^\\s@]+\\.[^\\s@]+",
    formatPattern: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
    formatError: "Enter a valid email address.",
  },
  {
    name: "streetAddress",
    label: "Street address",
    testId: "address-street",
    targetId: "checkout.address.street",
    autoComplete: "street-address",
    type: "text",
  },
  {
    name: "city",
    label: "City",
    testId: "address-city",
    targetId: CHECKOUT_FORM_LABEL_TARGETS.addressCity,
    autoComplete: "address-level2",
    type: "text",
  },
  {
    name: "state",
    label: "State",
    testId: "address-state",
    targetId: "checkout.address.state",
    autoComplete: "address-level1",
    type: "text",
  },
  {
    name: "country",
    label: "Country/region",
    testId: "address-country",
    targetId: CHECKOUT_FORM_LABEL_TARGETS.addressCountry,
    autoComplete: "country-name",
    control: "select",
    defaultValue: "United States",
    options: ["United States", "Canada", "Germany"],
  },
  {
    name: "postalCode",
    label: "ZIP code",
    testId: "address-postal-code",
    targetId: "checkout.address.postalCode",
    autoComplete: "postal-code",
    inputMode: "numeric",
    type: "text",
    pattern: "\\d{5}",
    formatPattern: /^\d{5}$/,
    formatError: "Enter a valid 5-digit ZIP code.",
  },
  {
    name: "deliveryInstructions",
    label: "Delivery instructions",
    testId: "address-delivery-instructions",
    targetId: CHECKOUT_FORM_LABEL_TARGETS.addressDeliveryInstructions,
    control: "textarea",
    rows: 3,
    required: false,
    fullWidth: true,
    description:
      "Optional. Add gate codes, safe-place details, or delivery notes.",
  },
];

const INITIAL_ADDRESS_VALUES = ADDRESS_FIELDS.reduce((values, field) => {
  values[field.name] = field.defaultValue ?? "";
  return values;
}, {});

const REQUIRED_FIELD_STATUS = "Enter the required shipping address fields.";
const INVALID_ADDRESS_STATUS = "Correct the highlighted shipping address fields.";

export function AddressPage({
  ariaStateEffects,
  cartItems,
  autocompleteEffects,
  errorMessageEffects,
  formLabelEffects,
  initialAddress,
  landmarkEffects,
  onStatus,
  onValidAddress,
}) {
  const [values, setValues] = useState(() =>
    getInitialAddressValues(initialAddress),
  );
  const [errors, setErrors] = useState({});
  const [hasSubmitted, setHasSubmitted] = useState(false);
  const fieldRefs = useRef({});
  const hasErrors = hasSubmitted && Object.keys(errors).length > 0;
  const showFormStatus = hasErrors;
  const orderTotalsAccessibleName =
    getLandmarkAccessibleNameOverride(
      landmarkEffects,
      CHECKOUT_LANDMARK_TARGETS.addressOrderTotals,
    ) ?? "Order totals";

  function handleChange(event) {
    const { name, value } = event.target;
    const nextValues = {
      ...values,
      [name]: value,
    };

    setValues(nextValues);

    if (hasSubmitted) {
      const nextErrors = validateAddressFields(nextValues);
      setErrors(nextErrors);
      syncValidationStatus(nextErrors);
    }
  }

  function handleSubmit(event) {
    event.preventDefault();

    const nextErrors = validateAddressFields(values);
    const firstInvalidField = ADDRESS_FIELDS.find((field) => nextErrors[field.name]);

    setHasSubmitted(true);

    if (firstInvalidField) {
      setErrors(nextErrors);
      syncValidationStatus(nextErrors);
      focusField(firstInvalidField.name);
      return;
    }

    setErrors({});
    onStatus("");
    onValidAddress(getSubmittedAddress(values));
  }

  function focusField(fieldName) {
    window.setTimeout(() => {
      fieldRefs.current[fieldName]?.focus({ preventScroll: false });
    }, 0);
  }

  function syncValidationStatus(nextErrors) {
    onStatus(getAddressValidationStatus(nextErrors));
  }

  return (
    <div className="checkout-step-route">
      <CheckoutProgress
        ariaStateEffects={ariaStateEffects}
        currentStep="address"
      />

      <div className="route-layout route-layout-with-aside">
        <section className="form-section" aria-labelledby="address-form-heading">
          <div className="section-heading">
            <h2 id="address-form-heading">Shipping details</h2>
            <p>Enter the shipping address for this order.</p>
          </div>

          <form
            className="stacked-form"
            noValidate
            data-testid="address-form"
            onSubmit={handleSubmit}
          >
            {showFormStatus ? (
              <p className="form-status is-error" aria-live="polite">
                {REQUIRED_FIELD_STATUS}
              </p>
            ) : null}

            <div className="field-grid">
              {ADDRESS_FIELDS.map((field) => {
                const fieldId = `address-${field.name}`;
                const errorId = `${fieldId}-error`;
                const descriptionId = field.description
                  ? `${fieldId}-description`
                  : undefined;
                const hasFieldError = hasSubmitted && Boolean(errors[field.name]);
                const errorText =
                  getErrorMessageTextOverride(
                    errorMessageEffects,
                    field.targetId,
                  ) ?? errors[field.name];
                const labelText =
                  getFormLabelTextOverride(formLabelEffects, field.targetId) ??
                  field.label;
                const autoComplete =
                  getAutocompleteValueOverride(
                    autocompleteEffects,
                    field.targetId,
                  ) ?? field.autoComplete;

                return (
                  <div
                    className={
                      field.fullWidth
                        ? "form-field form-field-full-width"
                        : "form-field"
                    }
                    key={field.name}
                  >
                    <label htmlFor={fieldId}>
                      <span>{labelText}</span>
                      {field.required === false ? null : (
                        <span className="required-marker">Required</span>
                      )}
                    </label>
                    {field.description ? (
                      <p className="field-description" id={descriptionId}>
                        {field.description}
                      </p>
                    ) : null}
                    <AddressFieldControl
                      field={field}
                      fieldId={fieldId}
                      inputRef={(node) => {
                        fieldRefs.current[field.name] = node;
                      }}
                      autoComplete={autoComplete}
                      value={values[field.name]}
                      hasFieldError={hasFieldError}
                      descriptionId={descriptionId}
                      errorId={errorId}
                      onChange={handleChange}
                    />
                    {hasFieldError ? (
                      <p className="field-error" id={errorId}>
                        {errorText}
                      </p>
                    ) : null}
                  </div>
                );
              })}
            </div>

            <button
              type="submit"
              className="primary-action form-submit"
              data-testid="continue-to-payment"
            >
              Continue to payment
            </button>
          </form>
        </section>

        <aside
          className="route-aside"
          aria-label={orderTotalsAccessibleName}
          data-testid="address-totals-region"
        >
          <CartSummary cartItems={cartItems} />
        </aside>
      </div>
    </div>
  );
}

function AddressFieldControl({
  field,
  fieldId,
  inputRef,
  autoComplete,
  value,
  hasFieldError,
  descriptionId,
  errorId,
  onChange,
}) {
  const describedBy = [descriptionId, hasFieldError ? errorId : null]
    .filter(Boolean)
    .join(" ");
  const sharedProps = {
    id: fieldId,
    ref: inputRef,
    name: field.name,
    autoComplete,
    value,
    required: field.required === false ? undefined : true,
    "aria-invalid": hasFieldError ? "true" : undefined,
    "aria-describedby": describedBy || undefined,
    "data-testid": field.testId,
    onChange,
  };

  if (field.control === "select") {
    return (
      <select {...sharedProps}>
        {field.options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    );
  }

  if (field.control === "textarea") {
    return <textarea {...sharedProps} rows={field.rows} />;
  }

  return (
    <input
      {...sharedProps}
      type={field.type}
      inputMode={field.inputMode}
      pattern={field.pattern}
    />
  );
}

function validateAddressFields(values) {
  return ADDRESS_FIELDS.reduce((nextErrors, field) => {
    const value = values[field.name].trim();

    if (!value && field.required !== false) {
      nextErrors[field.name] = `${field.label} is required.`;
    } else if (field.formatPattern && !field.formatPattern.test(value)) {
      nextErrors[field.name] = field.formatError;
    }

    return nextErrors;
  }, {});
}

function getInitialAddressValues(initialAddress) {
  return ADDRESS_FIELDS.reduce((values, field) => {
    values[field.name] = initialAddress?.[field.name] ?? values[field.name];
    return values;
  }, { ...INITIAL_ADDRESS_VALUES });
}

function getAddressValidationStatus(errors) {
  const messages = Object.values(errors);
  if (!messages.length) return "";
  return messages.every((message) => message.endsWith(" is required."))
    ? REQUIRED_FIELD_STATUS
    : INVALID_ADDRESS_STATUS;
}

function getSubmittedAddress(values) {
  return ADDRESS_FIELDS.reduce((submittedAddress, field) => {
    submittedAddress[field.name] = values[field.name].trim();
    return submittedAddress;
  }, {});
}
