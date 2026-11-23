import { useEffect, useRef, useState } from "react";
import {
  CHECKOUT_CART_RESULTS,
  CHECKOUT_CART_TARGETS,
  getCartResultOverride,
} from "../benchmark/effects/cartEffects.js";
import {
  CHECKOUT_ARIA_STATE_TARGETS,
  getAriaCheckedOverride,
  getAriaExpandedOverride,
  getAriaPressedOverride,
} from "../benchmark/effects/ariaStateEffects.js";
import {
  CHECKOUT_LOCAL_LANGUAGE_TARGETS,
  getLocalLangOverride,
} from "../benchmark/effects/localLanguageEffects.js";
import {
  CHECKOUT_LANDMARK_TARGETS,
  getLandmarkRoleOverride,
} from "../benchmark/effects/landmarkEffects.js";
import { getCartLineItems } from "../state/cartStore.js";
import { CartItem } from "./CartItem.jsx";
import { CartSummary } from "./CartSummary.jsx";
import { CheckoutProgress } from "./CheckoutProgress.jsx";
import { EmptyCart } from "./EmptyCart.jsx";

export function CartPage({
  ariaStateEffects = {},
  buttonEffects = {},
  cartItems,
  cartEffects = {},
  headingEffects = {},
  landmarkEffects = {},
  localLanguageEffects = {},
  onIncrement,
  onDecrement,
  onContinueShopping,
  onContinueToAddress,
}) {
  const lineItems = getCartLineItems(cartItems);
  const cartContent = cartEffects.cartContentOverrides ?? {};
  const cartSectionCopy = cartContent.cartSection ?? {};
  const cartSummaryCopy = cartContent.cartSummary ?? {};
  const preferencesCopy = cartContent.preferences ?? {};
  const deliveryEstimateCopy = cartContent.deliveryEstimate ?? {};
  const shippingInformationCopy = cartContent.shippingInformation ?? {};
  const actionsCopy = cartContent.actions ?? {};
  const orderTotalsRole = getLandmarkRoleOverride(
    landmarkEffects,
    CHECKOUT_LANDMARK_TARGETS.cartOrderTotals,
  );
  const cartDescriptionLang = getLocalLangOverride(
    localLanguageEffects,
    CHECKOUT_LOCAL_LANGUAGE_TARGETS.cartDescription,
  );
  const shippingInformationBodyLang = getLocalLangOverride(
    localLanguageEffects,
    CHECKOUT_LOCAL_LANGUAGE_TARGETS.cartShippingInformationBody,
  );
  const [isShippingDialogOpen, setIsShippingDialogOpen] = useState(false);
  const [isDeliveryEstimateOpen, setIsDeliveryEstimateOpen] = useState(false);
  const [isGiftReceiptEnabled, setIsGiftReceiptEnabled] = useState(false);
  const [isCartSaved, setIsCartSaved] = useState(false);
  const dialogRef = useRef(null);
  const deliveryEstimateTriggerRef = useRef(null);
  const shippingInfoTriggerRef = useRef(null);
  const dialogReturnFocusRef = useRef(null);
  const closeButtonRef = useRef(null);
  const deliveryEstimateResult = getCartResultOverride(
    cartEffects,
    CHECKOUT_CART_TARGETS.deliveryEstimate,
  );
  const deliveryEstimateExpandedOverride = getAriaExpandedOverride(
    ariaStateEffects,
    CHECKOUT_ARIA_STATE_TARGETS.cartDeliveryEstimate,
  );
  const giftReceiptCheckedOverride = getAriaCheckedOverride(
    ariaStateEffects,
    CHECKOUT_ARIA_STATE_TARGETS.cartGiftReceipt,
  );
  const saveCartPressedOverride = getAriaPressedOverride(
    ariaStateEffects,
    CHECKOUT_ARIA_STATE_TARGETS.cartSaveCart,
  );

  useEffect(() => {
    if (!isShippingDialogOpen) {
      return;
    }

    closeButtonRef.current?.focus({ preventScroll: true });
  }, [isShippingDialogOpen]);

  function openShippingDialog(returnFocusRef = shippingInfoTriggerRef) {
    dialogReturnFocusRef.current = returnFocusRef;
    setIsShippingDialogOpen(true);
  }

  function closeShippingDialog() {
    setIsShippingDialogOpen(false);
    window.setTimeout(() => {
      const focusRef = dialogReturnFocusRef.current ?? shippingInfoTriggerRef;
      focusRef.current?.focus({ preventScroll: true });
    }, 0);
  }

  function toggleDeliveryEstimate() {
    setIsDeliveryEstimateOpen((currentState) => !currentState);
  }

  function handleDeliveryEstimateActivation() {
    if (
      deliveryEstimateResult === CHECKOUT_CART_RESULTS.shippingInformationDialog
    ) {
      setIsDeliveryEstimateOpen(false);
      openShippingDialog(deliveryEstimateTriggerRef);
      return;
    }

    toggleDeliveryEstimate();
  }

  function toggleGiftReceipt() {
    setIsGiftReceiptEnabled((currentState) => !currentState);
  }

  function toggleCartSaved() {
    setIsCartSaved((currentState) => !currentState);
  }

  function handleDialogKeyDown(event) {
    if (event.key === "Escape") {
      event.preventDefault();
      closeShippingDialog();
      return;
    }

    if (event.key !== "Tab") {
      return;
    }

    const focusableElements = getFocusableDialogElements(dialogRef.current);

    if (focusableElements.length === 0) {
      event.preventDefault();
      dialogRef.current?.focus({ preventScroll: true });
      return;
    }

    const firstFocusable = focusableElements[0];
    const lastFocusable = focusableElements[focusableElements.length - 1];

    if (event.shiftKey && document.activeElement === firstFocusable) {
      event.preventDefault();
      lastFocusable.focus();
      return;
    }

    if (!event.shiftKey && document.activeElement === lastFocusable) {
      event.preventDefault();
      firstFocusable.focus();
    }
  }

  if (lineItems.length === 0) {
    return (
      <EmptyCart
        copy={cartContent.emptyCart ?? {}}
        headingEffects={headingEffects}
        onContinueShopping={onContinueShopping}
      />
    );
  }

  const declaredDeliveryEstimateExpanded =
    deliveryEstimateExpandedOverride !== undefined
      ? deliveryEstimateExpandedOverride
      : isDeliveryEstimateOpen;
  const declaredGiftReceiptChecked =
    giftReceiptCheckedOverride !== undefined
      ? giftReceiptCheckedOverride
      : isGiftReceiptEnabled;
  const declaredCartSavedPressed =
    saveCartPressedOverride !== undefined
      ? saveCartPressedOverride
      : isCartSaved;
  const deliveryEstimateState = {
    ["aria-" + "expand" + "ed"]: declaredDeliveryEstimateExpanded
      ? "true"
      : "false",
  };
  return (
    <div className="checkout-step-route">
      <CheckoutProgress
        ariaStateEffects={ariaStateEffects}
        currentStep="cart"
        copy={cartContent.progress ?? {}}
        landmarkEffects={landmarkEffects}
      />

      <div className="route-layout route-layout-with-aside">
        <section className="cart-section" aria-labelledby="cart-items-heading">
          <div className="section-heading">
            <h2 id="cart-items-heading">
              {cartSectionCopy.heading ?? "Cart items"}
            </h2>
            <p
              id="cart-description"
              data-testid="cart-description"
              lang={cartDescriptionLang}
            >
              {cartSectionCopy.description ??
                "Review selected products before entering checkout details."}
            </p>
          </div>
          <ul className="cart-list" data-testid="cart-list">
            {lineItems.map((item) => (
              <CartItem
                key={item.id}
                item={item}
                buttonEffects={buttonEffects}
                copy={cartContent.cartItem ?? {}}
                onIncrement={onIncrement}
                onDecrement={onDecrement}
              />
            ))}
          </ul>
        </section>
        <aside
          className="route-aside"
          role={orderTotalsRole}
          aria-label={cartSummaryCopy.ariaLabel ?? "Order totals"}
          data-testid="cart-totals-region"
        >
          <CartSummary cartItems={cartItems} copy={cartSummaryCopy} />
          <div className="cart-preferences" data-testid="cart-preferences">
            <div className="cart-preference">
              <button
                type="button"
                className={
                  isGiftReceiptEnabled
                    ? "cart-switch is-on"
                    : "cart-switch"
                }
                role="switch"
                aria-checked={declaredGiftReceiptChecked ? "true" : "false"}
                data-testid="gift-receipt-switch"
                onClick={toggleGiftReceipt}
              >
                <span className="cart-switch-track" aria-hidden="true">
                  <span className="cart-switch-thumb" />
                </span>
                <span>{preferencesCopy.giftReceipt ?? "Gift receipt"}</span>
              </button>
              {isGiftReceiptEnabled ? (
                <p className="cart-preference-note" data-testid="gift-receipt-note">
                  {preferencesCopy.giftReceiptNote ??
                    "A gift receipt will be included."}
                </p>
              ) : null}
            </div>

            <div className="cart-preference">
              <button
                type="button"
                className={
                  isCartSaved
                    ? "secondary-action checkout-action cart-save-toggle is-saved"
                    : "secondary-action checkout-action cart-save-toggle"
                }
                aria-pressed={declaredCartSavedPressed ? "true" : "false"}
                data-testid="save-cart-toggle"
                onClick={toggleCartSaved}
              >
                {preferencesCopy.saveCart ?? "Save cart"}
              </button>
              {isCartSaved ? (
                <p className="cart-preference-note" data-testid="save-cart-note">
                  {preferencesCopy.saveCartNote ?? "Cart saved for later."}
                </p>
              ) : null}
            </div>
          </div>
          <button
            ref={deliveryEstimateTriggerRef}
            type="button"
            className="secondary-action checkout-action"
            aria-controls="delivery-estimate-panel"
            data-testid="delivery-estimate-trigger"
            onClick={handleDeliveryEstimateActivation}
            {...deliveryEstimateState}
          >
            {deliveryEstimateCopy.trigger ?? "Delivery estimate"}
          </button>
          <div
            className="delivery-estimate-panel"
            id="delivery-estimate-panel"
            data-testid="delivery-estimate-panel"
            hidden={!isDeliveryEstimateOpen}
          >
            <p>
              {deliveryEstimateCopy.panel ??
                "Standard delivery usually arrives in 3-5 business days after dispatch."}
            </p>
          </div>
          <button
            ref={shippingInfoTriggerRef}
            type="button"
            className="secondary-action checkout-action"
            data-testid="shipping-information-trigger"
            onClick={() => openShippingDialog(shippingInfoTriggerRef)}
          >
            {shippingInformationCopy.trigger ?? "Shipping information"}
          </button>
          <button
            type="button"
            className="primary-action checkout-action"
            data-testid="continue-to-address"
            onClick={onContinueToAddress}
          >
            {actionsCopy.continueToAddress ?? "Continue to address"}
          </button>
        </aside>
      </div>

      {isShippingDialogOpen ? (
        <div className="modal-backdrop">
          <div
            ref={dialogRef}
            className="shipping-information-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="shipping-information-title"
            tabIndex="-1"
            data-testid="shipping-information-dialog"
            onKeyDown={handleDialogKeyDown}
          >
            <h2 id="shipping-information-title">
              {shippingInformationCopy.heading ?? "Shipping information"}
            </h2>
            <p
              data-testid="shipping-information-body"
              lang={shippingInformationBodyLang}
            >
              {shippingInformationCopy.body ??
                "Standard shipping is calculated during checkout. Delivery details are confirmed after you enter the shipping address."}
            </p>
            <div className="dialog-actions">
              <button
                ref={closeButtonRef}
                type="button"
                className="primary-action"
                data-testid="shipping-information-close"
                onClick={closeShippingDialog}
              >
                {shippingInformationCopy.close ?? "Close"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function getFocusableDialogElements(dialog) {
  if (!dialog) {
    return [];
  }

  return Array.from(
    dialog.querySelectorAll(
      [
        "button:not([disabled])",
        "a[href]",
        "input:not([disabled]):not([type='hidden'])",
        "textarea:not([disabled])",
        "select:not([disabled])",
        "[tabindex]:not([tabindex='-1'])",
      ].join(","),
    ),
  ).filter((element) => element.offsetParent !== null);
}
