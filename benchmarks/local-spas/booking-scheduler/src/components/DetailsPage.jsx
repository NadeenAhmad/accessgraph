import { useRef, useState } from "react";
import { getBookingEffect } from "../benchmark/effects.js";
import { getBookingSubjectByTestId } from "../benchmark/subjects.js";
import {
  CUSTOMER_FIELDS,
  normalizeCustomerDetails,
  validateRequiredCustomerDetails,
} from "../state/customerDetails.js";
import { BOOKING_ROUTES } from "../utils/routes.js";
import { BookingSummary } from "./BookingSummary.jsx";
import { StepProgress } from "./StepProgress.jsx";
import { WorkflowLink } from "./WorkflowLink.jsx";

const REQUIRED_FIELD_STATUS = "Enter the required booking details.";

export function DetailsPage({
  benchmarkEffects = {},
  selectedService,
  selectedDate,
  selectedSlotTime,
  customerDetails,
  stepStates,
  onNavigate,
  onCustomerDetailsChange,
  onStatus,
  onValidDetails,
}) {
  const [errors, setErrors] = useState({});
  const [hasSubmitted, setHasSubmitted] = useState(false);
  const fieldRefs = useRef({});

  function handleChange(event) {
    const { name, value } = event.target;
    const nextValues = {
      ...customerDetails,
      [name]: value,
    };

    onCustomerDetailsChange(nextValues);

    if (hasSubmitted) {
      const nextErrors = validateRequiredCustomerDetails(nextValues);
      setErrors(nextErrors);
      onStatus(hasErrors(nextErrors) ? REQUIRED_FIELD_STATUS : "");
    }
  }

  function handleSubmit(event) {
    event.preventDefault();

    const nextErrors = validateRequiredCustomerDetails(customerDetails);
    const firstInvalidField = getFirstInvalidField(nextErrors);

    setHasSubmitted(true);

    if (firstInvalidField) {
      setErrors(nextErrors);
      onStatus(REQUIRED_FIELD_STATUS);
      focusField(firstInvalidField.name);
      return;
    }

    setErrors({});
    onStatus("");
    onValidDetails(normalizeCustomerDetails(customerDetails));
  }

  function focusField(fieldName) {
    window.setTimeout(() => {
      fieldRefs.current[fieldName]?.focus({ preventScroll: false });
    }, 0);
  }

  return (
    <div className="route-layout route-layout-with-aside">
      <section className="details-section" aria-labelledby="details-form-heading">
        <StepProgress
          currentStep="details"
          stepStates={stepStates}
          onNavigate={onNavigate}
        />

        <WorkflowLink
          className="workflow-back-link"
          data-testid="back-to-schedule"
          to={BOOKING_ROUTES.schedule}
          onNavigate={onNavigate}
        >
          Back to schedule
        </WorkflowLink>

        <div className="section-heading">
          <h2 id="details-form-heading">Customer details</h2>
          <p>Enter local fixture customer details for this benchmark booking.</p>
        </div>

        <form
          className="details-form"
          noValidate
          data-testid="details-form"
          onSubmit={handleSubmit}
        >
          {hasSubmitted && hasErrors(errors) ? (
            <p
              className="form-status is-error"
              aria-live="polite"
              data-testid="details-validation-status"
            >
              {REQUIRED_FIELD_STATUS}
            </p>
          ) : null}

          <div className="details-field-grid">
            {CUSTOMER_FIELDS.map((field) => {
              const fieldId = `details-${field.name}`;
              const errorId = `${fieldId}-error`;
              const hasFieldError = hasSubmitted && Boolean(errors[field.name]);
              const fieldSubject = getBookingSubjectByTestId(field.testId);
              const labelText = getBookingEffect(
                benchmarkEffects,
                fieldSubject?.id,
                "labelText",
                field.label,
              );
              const validationMessage = getBookingEffect(
                benchmarkEffects,
                fieldSubject?.id,
                "validationMessage",
                errors[field.name],
              );
              const autocomplete = getBookingEffect(
                benchmarkEffects,
                fieldSubject?.id,
                "autocomplete",
                field.autoComplete,
              );

              return (
                <div className="form-field" key={field.name}>
                  <label htmlFor={fieldId}>
                    <span>{labelText}</span>
                    {field.required ? (
                      <span className="required-marker">Required</span>
                    ) : (
                      <span className="optional-marker">Optional</span>
                    )}
                  </label>

                  {isTextareaField(field) ? (
                    <textarea
                      id={fieldId}
                      ref={(node) => {
                        fieldRefs.current[field.name] = node;
                      }}
                      name={field.name}
                      rows="4"
                      value={customerDetails[field.name]}
                      placeholder={field.placeholder}
                      aria-describedby={
                        field.description ? `${fieldId}-hint` : undefined
                      }
                      data-testid={field.testId}
                      onChange={handleChange}
                    />
                  ) : (
                    <input
                      id={fieldId}
                      ref={(node) => {
                        fieldRefs.current[field.name] = node;
                      }}
                      name={field.name}
                      type={field.type}
                      autoComplete={autocomplete}
                      value={customerDetails[field.name]}
                      required={field.required}
                      aria-invalid={hasFieldError ? "true" : undefined}
                      aria-describedby={hasFieldError ? errorId : undefined}
                      data-testid={field.testId}
                      onChange={handleChange}
                    />
                  )}

                  {field.description ? (
                    <p className="field-hint" id={`${fieldId}-hint`}>
                      {field.description}
                    </p>
                  ) : null}

                  {hasFieldError ? (
                    <p
                      className="field-error"
                      id={errorId}
                      data-testid={`${field.testId}-error`}
                    >
                      {validationMessage}
                    </p>
                  ) : null}
                </div>
              );
            })}
          </div>

          <button
            type="submit"
            className="primary-action details-submit"
            data-testid="details-submit"
          >
            Continue to review
          </button>
        </form>
      </section>

      <aside className="route-aside" aria-label="Current booking summary">
        <BookingSummary
          selectedService={selectedService}
          selectedDate={selectedDate}
          selectedSlotTime={selectedSlotTime}
        />
      </aside>
    </div>
  );
}

function isTextareaField(field) {
  return field.name === "notes" || field.name === "accessibilityNeeds";
}

function getFirstInvalidField(errors) {
  return CUSTOMER_FIELDS.find((field) => errors[field.name]);
}

function hasErrors(errors) {
  return Object.keys(errors).length > 0;
}
