export const CHECKOUT_SUPPORT_ORIGIN_GLOBAL =
  "__ACCESSGRAPH_CHECKOUT_SUPPORT_ORIGIN__";

export const RETURNS_SUPPORT_LABEL = "Returns and refunds";
export const RETURNS_SUPPORT_PATH = "/returns-and-refunds.html";
export const SHIPPING_INFORMATION_SUPPORT_LABEL = "Shipping information";
export const SHIPPING_INFORMATION_SUPPORT_PATH = "/shipping-information.html";

const DEFAULT_SUPPORT_ORIGIN = "http://127.0.0.1:8771";

export function getSupportHref(path) {
  const configuredOrigin =
    typeof window !== "undefined" &&
    typeof window[CHECKOUT_SUPPORT_ORIGIN_GLOBAL] === "string"
      ? window[CHECKOUT_SUPPORT_ORIGIN_GLOBAL]
      : DEFAULT_SUPPORT_ORIGIN;

  try {
    return new URL(path, configuredOrigin).href;
  } catch {
    return new URL(path, DEFAULT_SUPPORT_ORIGIN).href;
  }
}

export function getReturnsSupportHref() {
  return getSupportHref(RETURNS_SUPPORT_PATH);
}

export function getShippingInformationSupportHref() {
  return getSupportHref(SHIPPING_INFORMATION_SUPPORT_PATH);
}
