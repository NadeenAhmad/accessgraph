import { useEffect, useMemo, useRef, useState } from "react";
import {
  getBookingEffect,
  resolveBookingEffects,
} from "./benchmark/effects.js";
import { resolveBookingProfile } from "./benchmark/profiles.js";
import { BOOKING_SUBJECTS } from "./benchmark/subjects.js";
import { AppHeader } from "./components/AppHeader.jsx";
import { ConfirmationPage } from "./components/ConfirmationPage.jsx";
import { DetailsPage } from "./components/DetailsPage.jsx";
import { HelpPage } from "./components/HelpPage.jsx";
import { ReviewPage } from "./components/ReviewPage.jsx";
import { SchedulePage } from "./components/SchedulePage.jsx";
import { ServiceSelectionPage } from "./components/ServiceSelectionPage.jsx";
import { StatusRegion } from "./components/StatusRegion.jsx";
import {
  ALTERNATE_FIXTURE_DATE,
  FIXTURE_DATE,
  SERVICES,
} from "./data/fixtures.js";
import {
  canReachReview,
  createConfirmedBooking,
  getAvailabilityForDate,
  getBookingProgressSteps,
  getBookingRouteAvailability,
  getServiceById,
  hasCompleteBookingSelection,
  isAvailableSlot,
} from "./state/bookingStore.js";
import { createCustomerDetailsDraft } from "./state/customerDetails.js";
import { BOOKING_ROUTES, getRouteId, normalizeRoute } from "./utils/routes.js";

const SCHEDULE_GUARD_MESSAGE = "Select a service before choosing a schedule.";
const DETAILS_SERVICE_GUARD_MESSAGE =
  "Select a service before entering booking details.";
const DETAILS_SCHEDULE_GUARD_MESSAGE =
  "Choose a date and available time before entering booking details.";
const REVIEW_SERVICE_GUARD_MESSAGE =
  "Select a service before reviewing the appointment.";
const REVIEW_SCHEDULE_GUARD_MESSAGE =
  "Choose a date and available time before reviewing the appointment.";
const REVIEW_DETAILS_GUARD_MESSAGE =
  "Enter booking details before reviewing the appointment.";
const CONFIRMATION_GUARD_MESSAGE =
  "Complete and confirm a booking before viewing confirmation.";
const SLOT_CLEARED_STATUS = "Selected time cleared because the date changed.";

function createEmptyAppState(currentPath = BOOKING_ROUTES.services) {
  return {
    currentPath,
    selectedServiceId: null,
    selectedDate: "",
    selectedSlotTime: null,
    customerDetailsDraft: createCustomerDetailsDraft(),
    customerDetailsSubmitted: false,
    confirmedBooking: null,
    statusMessage: "",
  };
}

function getInitialAppState() {
  const normalizedPath = normalizeRoute(window.location.pathname);
  const isUnknownPath = window.location.pathname !== normalizedPath;
  const initialState = createEmptyAppState(normalizedPath);
  const initialGuard = getRouteGuard(normalizedPath, initialState);

  if (isUnknownPath || initialGuard) {
    window.history.replaceState(
      {},
      "",
      initialGuard?.path ?? BOOKING_ROUTES.services,
    );
  }

  return {
    ...initialState,
    currentPath: initialGuard?.path ?? normalizedPath,
    statusMessage: initialGuard?.message ?? "",
  };
}

export default function App() {
  const [appState, setAppState] = useState(getInitialAppState);
  const routeHeadingRef = useRef(null);
  const hasMountedRef = useRef(false);
  const benchmarkEffects = useMemo(
    () => resolveBookingEffects(resolveBookingProfile()),
    [],
  );

  const routeId = getRouteId(appState.currentPath);
  const pageTitle = getPageTitle(routeId);
  const documentTitle = `${pageTitle} | Booking Scheduler Benchmark`;
  const documentLanguage = getBookingEffect(
    benchmarkEffects,
    BOOKING_SUBJECTS.page[routeId].id,
    "lang",
    "en",
  );
  const selectedService = useMemo(
    () => getServiceById(appState.selectedServiceId),
    [appState.selectedServiceId],
  );
  const slots = useMemo(
    () => getAvailabilityForDate(appState.selectedDate),
    [appState.selectedDate],
  );
  const hasSelectedBooking = hasCompleteBookingSelection(appState);
  const stepStates = getBookingProgressSteps(appState, routeId);

  useEffect(() => {
    function handlePopState() {
      const nextPath = normalizeRoute(window.location.pathname);

      setAppState((currentState) => {
        const guard = getRouteGuard(nextPath, currentState);

        if (guard) {
          window.history.replaceState({}, "", guard.path);
          return {
            ...currentState,
            currentPath: guard.path,
            statusMessage: guard.message,
          };
        }

        if (window.location.pathname !== nextPath) {
          window.history.replaceState({}, "", nextPath);
        }

        return {
          ...currentState,
          currentPath: nextPath,
          statusMessage: "",
        };
      });
    }

    window.addEventListener("popstate", handlePopState);

    return () => {
      window.removeEventListener("popstate", handlePopState);
    };
  }, []);

  useEffect(() => {
    document.title = documentTitle;
    document.documentElement.lang = documentLanguage;

    if (!hasMountedRef.current) {
      hasMountedRef.current = true;
      return;
    }

    window.setTimeout(() => {
      routeHeadingRef.current?.focus({ preventScroll: true });
    }, 0);
  }, [documentLanguage, documentTitle]);

  function navigateTo(path, { replace = false, statusMessage = "" } = {}) {
    const { nextPath, historyPath, fragment } = getNavigationTarget(path);

    if (replace) {
      window.history.replaceState({}, "", historyPath);
    } else {
      window.history.pushState({}, "", historyPath);
    }

    setAppState((currentState) => ({
      ...currentState,
      currentPath: nextPath,
      statusMessage,
    }));

    if (fragment) {
      window.setTimeout(() => {
        document.getElementById(fragment)?.scrollIntoView({ block: "start" });
      }, 0);
    }
  }

  function handleWorkflowNavigation(path) {
    const { nextPath } = getNavigationTarget(path);
    const guard = getRouteGuard(nextPath, appState);

    if (guard) {
      navigateTo(guard.path, { statusMessage: guard.message });
      return;
    }

    navigateTo(path);
  }

  function handleSelectService(serviceId) {
    const service = getServiceById(serviceId);

    if (!service) {
      return;
    }

    setAppState((currentState) => {
      const serviceChanged = currentState.selectedServiceId !== serviceId;

      return {
        ...currentState,
        selectedServiceId: serviceId,
        selectedSlotTime: serviceChanged
          ? null
          : currentState.selectedSlotTime,
        statusMessage: `${service.name} selected.`,
      };
    });
  }

  function handleContinueToSchedule() {
    if (!appState.selectedServiceId) {
      return;
    }

    navigateTo(BOOKING_ROUTES.schedule, {
      statusMessage: "Choose a supported fixture date to view appointment times.",
    });
  }

  function handleDateChange(nextDate) {
    setAppState((currentState) => {
      const clearedSelectedSlot =
        Boolean(currentState.selectedSlotTime) &&
        currentState.selectedDate !== nextDate;

      return {
        ...currentState,
        selectedDate: nextDate,
        selectedSlotTime:
          currentState.selectedDate === nextDate
            ? currentState.selectedSlotTime
            : null,
        statusMessage: getDateChangeStatus(nextDate, { clearedSelectedSlot }),
      };
    });
  }

  function handleSelectSlot(slotTime) {
    if (!isAvailableSlot(appState.selectedDate, slotTime)) {
      return;
    }

    setAppState((currentState) => ({
      ...currentState,
      selectedSlotTime: slotTime,
      statusMessage: `${slotTime} selected for ${selectedService?.name ?? "the service"}.`,
    }));
  }

  function handleContinueToDetails() {
    if (!hasCompleteBookingSelection(appState)) {
      return;
    }

    navigateTo(BOOKING_ROUTES.details, {
      statusMessage: "Enter booking details for the selected appointment.",
    });
  }

  function handleCustomerDetailsChange(customerDetailsDraft) {
    setAppState((currentState) => ({
      ...currentState,
      customerDetailsDraft,
      customerDetailsSubmitted: false,
    }));
  }

  function handleValidDetails(customerDetailsDraft) {
    setAppState((currentState) => ({
      ...currentState,
      customerDetailsDraft,
      customerDetailsSubmitted: true,
      statusMessage: "",
    }));
    navigateTo(BOOKING_ROUTES.review);
  }

  function handleConfirmBooking() {
    if (appState.confirmedBooking || !canReachReview(appState)) {
      return;
    }

    const confirmedBooking = createConfirmedBooking(appState);

    if (!confirmedBooking) {
      return;
    }

    window.history.pushState({}, "", BOOKING_ROUTES.confirmation);
    setAppState((currentState) => ({
      ...currentState,
      currentPath: BOOKING_ROUTES.confirmation,
      confirmedBooking,
      statusMessage: "",
    }));
  }

  function handleBookAnother() {
    window.history.replaceState({}, "", BOOKING_ROUTES.services);
    setAppState(createEmptyAppState());
  }

  return (
    <div className="app-shell" data-testid="booking-scheduler-app">
      <AppHeader
        currentPath={appState.currentPath}
        onNavigate={handleWorkflowNavigation}
      />

      <main className="main-content" data-testid={`route-${routeId}`}>
        <div className="route-heading">
          <h1 ref={routeHeadingRef} tabIndex="-1">
            {pageTitle}
          </h1>
          <p>{getRouteSummary(routeId)}</p>
        </div>

        {routeId === "help" ? (
          <HelpPage benchmarkEffects={benchmarkEffects} />
        ) : routeId === "confirmation" && appState.confirmedBooking ? (
          <ConfirmationPage
            benchmarkEffects={benchmarkEffects}
            confirmedBooking={appState.confirmedBooking}
            stepStates={stepStates}
            onNavigate={handleWorkflowNavigation}
            onBookAnother={handleBookAnother}
          />
        ) : routeId === "review" &&
        selectedService &&
        hasSelectedBooking &&
        canReachReview(appState) ? (
          <ReviewPage
            benchmarkEffects={benchmarkEffects}
            selectedService={selectedService}
            selectedDate={appState.selectedDate}
            selectedSlotTime={appState.selectedSlotTime}
            customerDetails={appState.customerDetailsDraft}
            stepStates={stepStates}
            onNavigate={handleWorkflowNavigation}
            onConfirmBooking={handleConfirmBooking}
          />
        ) : routeId === "details" && selectedService && hasSelectedBooking ? (
          <DetailsPage
            benchmarkEffects={benchmarkEffects}
            selectedService={selectedService}
            selectedDate={appState.selectedDate}
            selectedSlotTime={appState.selectedSlotTime}
            customerDetails={appState.customerDetailsDraft}
            stepStates={stepStates}
            onNavigate={handleWorkflowNavigation}
            onCustomerDetailsChange={handleCustomerDetailsChange}
            onStatus={(statusMessage) =>
              setAppState((currentState) => ({
                ...currentState,
                statusMessage,
              }))
            }
            onValidDetails={handleValidDetails}
          />
        ) : routeId === "schedule" && selectedService ? (
          <SchedulePage
            benchmarkEffects={benchmarkEffects}
            selectedService={selectedService}
            selectedDate={appState.selectedDate}
            selectedSlotTime={appState.selectedSlotTime}
            slots={slots}
            stepStates={stepStates}
            onNavigate={handleWorkflowNavigation}
            onDateChange={handleDateChange}
            onSelectSlot={handleSelectSlot}
            onContinueToDetails={handleContinueToDetails}
          />
        ) : (
          <ServiceSelectionPage
            benchmarkEffects={benchmarkEffects}
            services={SERVICES}
            selectedService={selectedService}
            selectedServiceId={appState.selectedServiceId}
            selectedDate={appState.selectedDate}
            selectedSlotTime={appState.selectedSlotTime}
            stepStates={stepStates}
            onNavigate={handleWorkflowNavigation}
            onSelectService={handleSelectService}
            onContinue={handleContinueToSchedule}
          />
        )}
      </main>

      <StatusRegion message={appState.statusMessage} />
    </div>
  );
}

function getPageTitle(routeId) {
  if (routeId === "help") {
    return "Help & policies";
  }

  if (routeId === "confirmation") {
    return "Booking confirmed";
  }

  if (routeId === "review") {
    return "Review appointment";
  }

  if (routeId === "details") {
    return "Booking details";
  }

  if (routeId === "schedule") {
    return "Schedule appointment";
  }

  return "Select service";
}

function getRouteSummary(routeId) {
  if (routeId === "help") {
    return "Find clinic details, appointment policies, preparation guidance, and directions.";
  }

  if (routeId === "confirmation") {
    return "View the completed appointment and booking reference.";
  }

  if (routeId === "review") {
    return "Review the selected appointment and submitted customer details.";
  }

  if (routeId === "details") {
    return "Enter required customer details for the selected appointment.";
  }

  if (routeId === "schedule") {
    return "Choose a supported fixture date and one available appointment time.";
  }

  return "Choose one deterministic service fixture before scheduling.";
}

function getDateChangeStatus(date, { clearedSelectedSlot }) {
  if (clearedSelectedSlot) {
    return SLOT_CLEARED_STATUS;
  }

  if (date === FIXTURE_DATE) {
    return "Availability loaded for June 16, 2026.";
  }

  if (date === ALTERNATE_FIXTURE_DATE) {
    return "Availability loaded for June 18, 2026.";
  }

  return "Choose a supported fixture date to show appointment times.";
}

function getRouteGuard(path, state) {
  if (path === BOOKING_ROUTES.help) {
    return null;
  }

  if (state.confirmedBooking) {
    if (path !== BOOKING_ROUTES.confirmation) {
      return {
        path: BOOKING_ROUTES.confirmation,
        message: "",
      };
    }

    return null;
  }

  if (path === BOOKING_ROUTES.confirmation) {
    return {
      path: BOOKING_ROUTES.services,
      message: CONFIRMATION_GUARD_MESSAGE,
    };
  }

  const availability = getBookingRouteAvailability(state);

  if (path === BOOKING_ROUTES.schedule && !availability.schedule) {
    return {
      path: BOOKING_ROUTES.services,
      message: SCHEDULE_GUARD_MESSAGE,
    };
  }

  if (path === BOOKING_ROUTES.details) {
    if (!availability.schedule) {
      return {
        path: BOOKING_ROUTES.services,
        message: DETAILS_SERVICE_GUARD_MESSAGE,
      };
    }

    if (!availability.details) {
      return {
        path: BOOKING_ROUTES.schedule,
        message: DETAILS_SCHEDULE_GUARD_MESSAGE,
      };
    }
  }

  if (path === BOOKING_ROUTES.review) {
    if (!availability.schedule) {
      return {
        path: BOOKING_ROUTES.services,
        message: REVIEW_SERVICE_GUARD_MESSAGE,
      };
    }

    if (!availability.details) {
      return {
        path: BOOKING_ROUTES.schedule,
        message: REVIEW_SCHEDULE_GUARD_MESSAGE,
      };
    }

    if (!availability.review) {
      return {
        path: BOOKING_ROUTES.details,
        message: REVIEW_DETAILS_GUARD_MESSAGE,
      };
    }
  }

  return null;
}

function getNavigationTarget(path) {
  const hashIndex = path.indexOf("#");
  const requestedPath = hashIndex === -1 ? path : path.slice(0, hashIndex);
  const nextPath = normalizeRoute(requestedPath);
  const fragment =
    hashIndex === -1 || requestedPath !== nextPath
      ? ""
      : path.slice(hashIndex + 1);

  return {
    nextPath,
    historyPath: fragment ? `${nextPath}#${fragment}` : nextPath,
    fragment,
  };
}
