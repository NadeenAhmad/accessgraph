export const BOOKING_ROUTES = {
  services: "/services",
  schedule: "/schedule",
  details: "/details",
  review: "/review",
  confirmation: "/confirmation",
  help: "/help",
};

export function normalizeRoute(pathname) {
  if (
    pathname === BOOKING_ROUTES.schedule ||
    pathname === BOOKING_ROUTES.details ||
    pathname === BOOKING_ROUTES.review ||
    pathname === BOOKING_ROUTES.confirmation ||
    pathname === BOOKING_ROUTES.help
  ) {
    return pathname;
  }

  return BOOKING_ROUTES.services;
}

export function getRouteId(pathname) {
  const route = normalizeRoute(pathname);

  if (route === BOOKING_ROUTES.schedule) {
    return "schedule";
  }

  if (route === BOOKING_ROUTES.details) {
    return "details";
  }

  if (route === BOOKING_ROUTES.review) {
    return "review";
  }

  if (route === BOOKING_ROUTES.confirmation) {
    return "confirmation";
  }

  if (route === BOOKING_ROUTES.help) {
    return "help";
  }

  return "services";
}
