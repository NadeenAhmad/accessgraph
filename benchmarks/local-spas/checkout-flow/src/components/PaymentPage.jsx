import { useRef, useState } from "react";
import { getAutocompleteValueOverride } from "../benchmark/effects/autocompleteEffects.js";
import { getErrorMessageTextOverride } from "../benchmark/effects/errorMessageEffects.js";
import {
  CHECKOUT_FORM_LABEL_TARGETS,
  getFormAccessibleNameOverride,
  getFormLabelTextOverride,
} from "../benchmark/effects/formLabelEffects.js";
import {
  CHECKOUT_HEADING_TARGETS,
  getHeadingTextOverride,
} from "../benchmark/effects/headingEffects.js";
import { CartSummary } from "./CartSummary.jsx";
import { CheckoutProgress } from "./CheckoutProgress.jsx";

export const PAYMENT_FIELDS = [
  {
    name: "cardholder",
    label: "Cardholder name",
    testId: "payment-cardholder",
    targetId: CHECKOUT_FORM_LABEL_TARGETS.paymentCardholder,
    autoComplete: "cc-name",
    type: "text",
  },
  {
    name: "cardNumber",
    label: "Card number",
    testId: "payment-card-number",
    targetId: CHECKOUT_FORM_LABEL_TARGETS.paymentCardNumber,
    autoComplete: "cc-number",
    inputMode: "numeric",
    type: "text",
  },
  {
    name: "expiry",
    label: "Expiry",
    testId: "payment-expiry",
    targetId: "checkout.payment.expiry",
    autoComplete: "cc-exp",
    inputMode: "numeric",
    type: "text",
  },
  {
    name: "securityCode",
    label: "Security code",
    testId: "payment-security-code",
    targetId: CHECKOUT_FORM_LABEL_TARGETS.paymentSecurityCode,
    autoComplete: "cc-csc",
    inputMode: "numeric",
    type: "text",
    pattern: "\\d{3,4}",
    formatPattern: /^\d{3,4}$/,
    formatError: "Enter a 3 or 4 digit security code.",
  },
];

const INITIAL_PAYMENT_VALUES = PAYMENT_FIELDS.reduce((values, field) => {
  values[field.name] = "";
  return values;
}, {});

const REQUIRED_PAYMENT_STATUS = "Enter the required payment fields.";
const INVALID_PAYMENT_STATUS = "Correct the highlighted payment fields.";

export function PaymentPage({
  autocompleteEffects,
  cartItems,
  errorMessageEffects,
  formLabelEffects,
  headingEffects,
  submittedAddress,
  onReturnToAddress,
  onStatus,
  onValidPayment,
}) {
  const [values, setValues] = useState(INITIAL_PAYMENT_VALUES);
  const [errors, setErrors] = useState({});
  const [hasSubmitted, setHasSubmitted] = useState(false);
  const fieldRefs = useRef({});

  if (!submittedAddress) {
    return (
      <div className="checkout-step-route">
        <CheckoutProgress currentStep="payment" />
        <div className="route-layout route-layout-with-aside">
          <section className="form-section" aria-labelledby="payment-missing-heading">
            <div className="section-heading">
              <h2 id="payment-missing-heading">Shipping address needed</h2>
              <p>Enter a shipping address before adding payment details.</p>
            </div>
            <button
              type="button"
              className="primary-action"
              data-testid="payment-return-to-address"
              onClick={onReturnToAddress}
            >
              Enter shipping address
            </button>
          </section>
          <aside className="route-aside" aria-label="Order totals">
            <CartSummary cartItems={cartItems} />
          </aside>
        </div>
      </div>
    );
  }

  function handleChange(event) {
    const { name, value } = event.target;
    const nextValues = {
      ...values,
      [name]: value,
    };

    setValues(nextValues);

    if (hasSubmitted) {
      const nextErrors = validatePaymentFields(nextValues);
      setErrors(nextErrors);
      onStatus(getPaymentValidationStatus(nextErrors));
    }
  }

  function handleSubmit(event) {
    event.preventDefault();

    const nextErrors = validatePaymentFields(values);
    const firstInvalidField = PAYMENT_FIELDS.find((field) => nextErrors[field.name]);

    setHasSubmitted(true);

    if (firstInvalidField) {
      setErrors(nextErrors);
      onStatus(getPaymentValidationStatus(nextErrors));
      focusField(firstInvalidField.name);
      return;
    }

    setErrors({});
    onStatus("");
    onValidPayment(getSubmittedPayment(values));
  }

  function focusField(fieldName) {
    window.setTimeout(() => {
      fieldRefs.current[fieldName]?.focus({ preventScroll: false });
    }, 0);
  }

  return (
    <div className="checkout-step-route">
      <CheckoutProgress currentStep="payment" />

      <div className="route-layout route-layout-with-aside">
        <section className="form-section" aria-labelledby="payment-form-heading">
          <div className="section-heading">
            <h2 id="payment-form-heading">
              {getHeadingTextOverride(
                headingEffects,
                CHECKOUT_HEADING_TARGETS.paymentMethodHeading,
              ) ?? "Payment method"}
            </h2>
            <p>Add card details before reviewing the order.</p>
          </div>

          <form
            className="stacked-form"
            noValidate
            data-testid="payment-form"
            onSubmit={handleSubmit}
          >
            {hasSubmitted && Object.keys(errors).length ? (
              <p className="form-status is-error" aria-live="polite">
                {REQUIRED_PAYMENT_STATUS}
              </p>
            ) : null}

            <fieldset className="payment-fieldset">
              <legend>Card details</legend>
              <div className="field-grid">
                {PAYMENT_FIELDS.map((field) => {
                  const fieldId = `payment-${field.name}`;
                  const errorId = `${fieldId}-error`;
                  const hasFieldError = hasSubmitted && Boolean(errors[field.name]);
                  const errorText =
                    getErrorMessageTextOverride(
                      errorMessageEffects,
                      field.targetId,
                    ) ?? errors[field.name];
                  const labelText =
                    getFormLabelTextOverride(formLabelEffects, field.targetId) ??
                    field.label;
                  const accessibleName = getFormAccessibleNameOverride(
                    formLabelEffects,
                    field.targetId,
                  );

                  return (
                    <div
                      className="form-field"
                      key={field.name}
                    >
                      <label htmlFor={fieldId}>
                        <span>{labelText}</span>
                        <span className="required-marker">Required</span>
                      </label>
                      <input
                        id={fieldId}
                        ref={(node) => {
                          fieldRefs.current[field.name] = node;
                        }}
                        name={field.name}
                        type={field.type}
                        pattern={field.pattern}
                        inputMode={field.inputMode}
                        autoComplete={
                          getAutocompleteValueOverride(
                            autocompleteEffects,
                            field.targetId,
                          ) ?? field.autoComplete
                        }
                        value={values[field.name]}
                        required
                        aria-label={accessibleName}
                        aria-invalid={hasFieldError ? "true" : undefined}
                        aria-describedby={hasFieldError ? errorId : undefined}
                        data-testid={field.testId}
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
            </fieldset>

            <button
              type="submit"
              className="primary-action form-submit"
              data-testid="continue-to-review"
            >
              Continue to review
            </button>
          </form>
        </section>

        <aside className="route-aside" aria-label="Order totals">
          <CartSummary cartItems={cartItems} />
        </aside>
      </div>
    </div>
  );
}

function validatePaymentFields(values) {
  return PAYMENT_FIELDS.reduce((nextErrors, field) => {
    const value = values[field.name].trim();

    if (!value) {
      nextErrors[field.name] = `${field.label} is required.`;
    } else if (field.formatPattern && !field.formatPattern.test(value)) {
      nextErrors[field.name] = field.formatError;
    }

    return nextErrors;
  }, {});
}

function getPaymentValidationStatus(errors) {
  const messages = Object.values(errors);
  if (!messages.length) return "";
  return messages.every((message) => message.endsWith(" is required."))
    ? REQUIRED_PAYMENT_STATUS
    : INVALID_PAYMENT_STATUS;
}

function getSubmittedPayment(values) {
  const cardNumber = values.cardNumber.replace(/\D/g, "");
  const cardLastFour = cardNumber.slice(-4);

  return {
    cardholder: values.cardholder.trim(),
    cardLastFour,
    expiry: values.expiry.trim(),
  };
}
