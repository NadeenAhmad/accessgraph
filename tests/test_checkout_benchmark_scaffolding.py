from __future__ import annotations

import csv
import json
import re
import subprocess
from pathlib import Path

from src.analysis.candidates.taxonomy import SUPPORTED_CANDIDATE_TYPES
from src.analysis.evaluation.benchmark_registry import load_benchmark_registry


REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = REPO_ROOT / "benchmarks"
CHECKOUT_ROOT = BENCHMARK_ROOT / "local-spas" / "checkout-flow"
CHECKOUT_SRC_ROOT = CHECKOUT_ROOT / "src"
REGISTRY = BENCHMARK_ROOT / "registry" / "benchmark-case-registry.json"
MANIFEST = BENCHMARK_ROOT / "dataset-manifest.json"
CASE_TRACKER = BENCHMARK_ROOT / "case-tracker.csv"
RUNNER = REPO_ROOT / "scripts" / "benchmarks" / "checkout" / "runner.py"
PILOT_PROFILE_ID = "checkout-pilot-001"
PILOT_SEED_IDS = ["co-sem-001", "co-sem-002"]
IMPLEMENTED_DATASET_CASES = {
  "checkout-co-sem-006": {
    "seed_ids": ["co-sem-006"],
    "product_effects": {"imageAltOverrides": {"prod-desk-lamp": "A dog"}},
  },
  "checkout-co-sem-007": {
    "seed_ids": ["co-sem-007"],
    "product_effects": {"imageAltOverrides": {"prod-desk-lamp": "Floor lamp"}},
  },
  "checkout-co-sem-008": {
    "seed_ids": ["co-sem-008"],
    "product_effects": {"imageAltOverrides": {"prod-desk-lamp": "User profile avatar"}},
  },
  "checkout-co-sem-009": {
    "seed_ids": ["co-sem-009"],
    "product_effects": {"imageAltOverrides": {"prod-desk-lamp": "Purple desk lamp"}},
  },
  "checkout-co-sem-010": {
    "seed_ids": ["co-sem-010"],
    "product_effects": {"imageAltOverrides": {"prod-desk-lamp": "Two desk lamps"}},
  },
  "checkout-co-sem-011": {
    "seed_ids": ["co-sem-011"],
    "app_effects": {"rootLang": "en", "rootLangByRoute": {"products": "da"}},
    "product_effects": {},
  },
  "checkout-co-sem-012": {
    "seed_ids": ["co-sem-012"],
    "app_effects": {"rootLang": "en", "rootLangByRoute": {"products": "en"}},
    "product_effects": {},
  },
  "checkout-co-sem-013": {
    "seed_ids": ["co-sem-013"],
    "app_effects": {"rootLang": "en", "rootLangByRoute": {"cart": "da"}},
    "product_effects": {},
  },
  "checkout-co-sem-014": {
    "seed_ids": ["co-sem-014"],
    "app_effects": {"rootLang": "en", "rootLangByRoute": {"cart": "en"}},
    "cart_effects": {},
    "product_effects": {},
  },
  "checkout-co-sem-015": {
    "seed_ids": ["co-sem-015"],
    "app_effects": {"rootLang": "en", "rootLangByRoute": {"products": "en"}},
    "product_effects": {},
  },
  "checkout-co-sem-016": {
    "seed_ids": ["co-sem-016"],
    "local_language_effects": {
      "localLangOverrides": {"checkout.products.description": "fr"}
    },
    "product_effects": {},
  },
  "checkout-co-sem-017": {
    "seed_ids": ["co-sem-017"],
    "local_language_effects": {
      "localLangOverrides": {"checkout.products.cartSummary": "de"}
    },
    "product_effects": {},
  },
  "checkout-co-sem-018": {
    "seed_ids": ["co-sem-018"],
    "local_language_effects": {
      "localLangOverrides": {"checkout.cart.description": "fr"}
    },
    "product_effects": {},
  },
  "checkout-co-sem-019": {
    "seed_ids": ["co-sem-019"],
    "local_language_effects": {
      "localLangOverrides": {"checkout.products.description": "en"}
    },
    "product_effects": {},
  },
  "checkout-co-sem-020": {
    "seed_ids": ["co-sem-020"],
    "link_effects": {
      "linkTextOverrides": {"checkout.navigation.cart": "Weather forecast"}
    },
    "product_effects": {},
  },
  "checkout-co-sem-021": {
    "seed_ids": ["co-sem-021"],
    "link_effects": {
      "linkAccessibleNameOverrides": {
        "checkout.navigation.cart": "Weather forecast"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-023": {
    "seed_ids": ["co-sem-023"],
    "link_effects": {
      "linkTextOverrides": {"checkout.navigation.cart": "Shipping address"}
    },
    "product_effects": {},
  },
  "checkout-co-sem-024": {
    "seed_ids": ["co-sem-024"],
    "link_effects": {
      "linkAccessibleNameOverrides": {
        "checkout.navigation.cart": "Shipping address"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-027": {
    "seed_ids": ["co-sem-027"],
    "link_effects": {
      "linkTextOverrides": {
        "checkout.support.returns": "Shipping information"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-028": {
    "seed_ids": ["co-sem-028"],
    "button_effects": {
      "buttonTextOverrides": {
        "checkout.products.notebookSet.addButton": "Weather forecast"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-029": {
    "seed_ids": ["co-sem-029"],
    "button_effects": {
      "buttonAccessibleNameOverrides": {
        "checkout.products.notebookSet.addButton": "Weather forecast"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-031": {
    "seed_ids": ["co-sem-031"],
    "button_effects": {
      "buttonTextOverrides": {
        "checkout.products.notebookSet.addButton": "Remove Notebook set"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-032": {
    "seed_ids": ["co-sem-032"],
    "button_effects": {
      "buttonAccessibleNameOverrides": {
        "checkout.products.notebookSet.addButton": "Remove Notebook set"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-035": {
    "seed_ids": ["co-sem-035"],
    "button_effects": {
      "buttonTextOverrides": {
        "checkout.products.notebookSet.addButton": "Add Cable organizer"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-036": {
    "seed_ids": ["co-sem-036"],
    "product_effects": {},
    "widget_effects": {
      "widgetTextOverrides": {
        "checkout.products.categoryTabs.deskAccessories": "Fishing supplies"
      }
    },
  },
  "checkout-co-sem-037": {
    "seed_ids": ["co-sem-037"],
    "product_effects": {},
    "widget_effects": {
      "widgetTextOverrides": {
        "checkout.products.categoryTabs.deskAccessories": "Stationery"
      }
    },
  },
  "checkout-co-sem-038": {
    "seed_ids": ["co-sem-038"],
    "product_effects": {},
    "widget_effects": {
      "widgetAccessibleNameOverrides": {
        "checkout.products.categoryTabs.deskAccessories": "Fishing supplies"
      }
    },
  },
  "checkout-co-sem-041": {
    "seed_ids": ["co-sem-041"],
    "heading_effects": {
      "headingTextOverrides": {
        "checkout.products.pageHeading": "Payment details"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-042": {
    "seed_ids": ["co-sem-042"],
    "heading_effects": {
      "headingTextOverrides": {
        "checkout.products.pageHeading": "Fishing techniques"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-044": {
    "seed_ids": ["co-sem-044"],
    "heading_effects": {
      "headingTextOverrides": {
        "checkout.products.featuredProductsHeading": "Order summary"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-045": {
    "seed_ids": ["co-sem-045"],
    "heading_effects": {
      "headingTextOverrides": {
        "checkout.products.featuredProductsHeading": "Weather forecast"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-047": {
    "seed_ids": ["co-sem-047"],
    "heading_effects": {
      "headingTextOverrides": {
        "checkout.cart.pageHeading": "Products"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-052": {
    "seed_ids": ["co-sem-052"],
    "landmark_effects": {
      "landmarkAccessibleNameOverrides": {
        "checkout.navigation.routes": "Order totals"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-053": {
    "seed_ids": ["co-sem-053"],
    "landmark_effects": {
      "landmarkAccessibleNameOverrides": {
        "checkout.products.featuredRegion": "Checkout routes"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-054": {
    "seed_ids": ["co-sem-054"],
    "landmark_effects": {
      "landmarkRoleOverrides": {
        "checkout.cart.orderTotals": "search"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-055": {
    "seed_ids": ["co-sem-055"],
    "landmark_effects": {
      "landmarkRoleOverrides": {
        "checkout.footer.site": "search"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-056": {
    "seed_ids": ["co-sem-056"],
    "landmark_effects": {
      "landmarkAccessibleNameOverrides": {
        "checkout.footer.site": "Checkout routes"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-058": {
    "seed_ids": ["co-sem-058"],
    "page_title_effects": {
      "pageTitleTextOverrides": {
        "checkout.page.products": "Payment"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-059": {
    "seed_ids": ["co-sem-059"],
    "page_title_effects": {
      "pageTitleTextOverrides": {
        "checkout.page.products": "Weather Forecast"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-060": {
    "seed_ids": ["co-sem-060"],
    "page_title_effects": {
      "pageTitleTextOverrides": {
        "checkout.page.payment": "Shipping address"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-061": {
    "seed_ids": ["co-sem-061"],
    "autocomplete_effects": {
      "autocompleteValueOverrides": {"checkout.address.fullName": "organization-title"}
    },
    "product_effects": {},
  },
  "checkout-co-sem-062": {
    "seed_ids": ["co-sem-062"],
    "autocomplete_effects": {
      "autocompleteValueOverrides": {"checkout.address.street": "email"}
    },
    "product_effects": {},
  },
  "checkout-co-sem-063": {
    "seed_ids": ["co-sem-063"],
    "autocomplete_effects": {
      "autocompleteValueOverrides": {"checkout.address.postalCode": "address-level2"}
    },
    "product_effects": {},
  },
  "checkout-co-sem-064": {
    "seed_ids": ["co-sem-064"],
    "autocomplete_effects": {
      "autocompleteValueOverrides": {"checkout.payment.cardNumber": "cc-name"}
    },
    "product_effects": {},
  },
  "checkout-co-sem-065": {
    "seed_ids": ["co-sem-065"],
    "autocomplete_effects": {
      "autocompleteValueOverrides": {"checkout.payment.securityCode": "cc-exp"}
    },
    "product_effects": {},
  },
  "checkout-co-sem-066": {
    "seed_ids": ["co-sem-066"],
    "aria_state_effects": {
      "ariaSelectedOverrides": {
        "checkout.products.categoryTabs.deskAccessories": False,
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-067": {
    "seed_ids": ["co-sem-067"],
    "aria_state_effects": {
      "ariaSelectedOverrides": {
        "checkout.products.categoryTabs.deskAccessories": True,
        "checkout.products.categoryTabs.officeSupplies": False,
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-068": {
    "seed_ids": ["co-sem-068"],
    "aria_state_effects": {
      "ariaExpandedOverrides": {
        "checkout.cart.deliveryEstimate": False,
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-069": {
    "seed_ids": ["co-sem-069"],
    "aria_state_effects": {
      "ariaExpandedOverrides": {
        "checkout.cart.deliveryEstimate": True,
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-070": {
    "seed_ids": ["co-sem-070"],
    "aria_state_effects": {
      "ariaCheckedOverrides": {
        "checkout.cart.giftReceipt": False,
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-071": {
    "seed_ids": ["co-sem-071"],
    "aria_state_effects": {
      "ariaCheckedOverrides": {
        "checkout.cart.giftReceipt": True,
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-072": {
    "seed_ids": ["co-sem-072"],
    "aria_state_effects": {
      "ariaPressedOverrides": {
        "checkout.cart.saveCart": False,
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-073": {
    "seed_ids": ["co-sem-073"],
    "aria_state_effects": {
      "ariaPressedOverrides": {
        "checkout.cart.saveCart": True,
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-074": {
    "seed_ids": ["co-sem-074"],
    "review_effects": {
      "tableHeaderAssociationOverrides": {
        "checkout.review.orderItems.deskLamp.lineTotalCell": [
          "review-item-header-prod-desk-lamp",
          "review-quantity-header",
        ]
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-075": {
    "seed_ids": ["co-sem-075"],
    "review_effects": {
      "tableHeaderAssociationOverrides": {
        "checkout.review.orderItems.deskLamp.quantityCell": [
          "review-item-header-prod-desk-lamp",
          "review-line-total-header",
        ]
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-076": {
    "seed_ids": ["co-sem-076"],
    "error_message_effects": {
      "errorTextOverrides": {"checkout.address.email": "ZIP code is required."}
    },
    "product_effects": {},
  },
  "checkout-co-sem-077": {
    "seed_ids": ["co-sem-077"],
    "error_message_effects": {
      "errorTextOverrides": {"checkout.address.postalCode": "Email is required."}
    },
    "product_effects": {},
  },
  "checkout-co-sem-078": {
    "seed_ids": ["co-sem-078"],
    "error_message_effects": {
      "errorTextOverrides": {"checkout.address.fullName": "Street address is required."}
    },
    "product_effects": {},
  },
  "checkout-co-sem-079": {
    "seed_ids": ["co-sem-079"],
    "error_message_effects": {
      "errorTextOverrides": {"checkout.payment.cardNumber": "Security code is required."}
    },
    "product_effects": {},
  },
  "checkout-co-sem-080": {
    "seed_ids": ["co-sem-080"],
    "error_message_effects": {
      "errorTextOverrides": {"checkout.payment.securityCode": "Card number is required."}
    },
    "product_effects": {},
  },
  "checkout-co-sem-081": {
    "seed_ids": ["co-sem-081"],
    "error_message_effects": {
      "errorTextOverrides": {"checkout.payment.expiry": "Cardholder name is required."}
    },
    "product_effects": {},
  },
  "checkout-co-sem-086": {
    "seed_ids": ["co-sem-086"],
    "form_label_effects": {
      "formLabelTextOverrides": {
        "checkout.payment.cardNumber": "Security code",
        "checkout.payment.securityCode": "Card number",
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-087": {
    "seed_ids": ["co-sem-087"],
    "form_label_effects": {
      "formLabelTextOverrides": {
        "checkout.address.email": "Full name",
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-088": {
    "seed_ids": ["co-sem-088"],
    "form_label_effects": {
      "formLabelTextOverrides": {
        "checkout.payment.cardNumber": "Street address",
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-089": {
    "seed_ids": ["co-sem-089"],
    "cart_effects": {
      "cartResultOverrides": {
        "checkout.cart.deliveryEstimate": "shipping_information_dialog"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-090": {
    "seed_ids": ["co-sem-090"],
    "aria_state_effects": {
      "ariaCurrentOverrides": {
        "checkout.navigation.products": {"cart": "page"},
        "checkout.navigation.cart": {"cart": None},
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-091": {
    "seed_ids": ["co-sem-091"],
    "heading_effects": {
      "headingTextOverrides": {
        "checkout.cart.pageHeading": "Shipping address"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-092": {
    "seed_ids": ["co-sem-092"],
    "heading_effects": {
      "headingTextOverrides": {
        "checkout.cart.emptyHeading": "Cart items"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-093": {
    "seed_ids": ["co-sem-093"],
    "heading_effects": {
      "headingTextOverrides": {
        "checkout.payment.methodHeading": "Card number"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-094": {
    "seed_ids": ["co-sem-094"],
    "heading_effects": {
      "headingTextOverrides": {
        "checkout.cart.pageHeading": "Products",
        "checkout.cart.pageSummary": (
          "Browse featured products and update the cart summary."
        ),
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-095": {
    "seed_ids": ["co-sem-095"],
    "product_effects": {"imageAltOverrides": {"prod-desk-lamp": "Image"}},
  },
  "checkout-co-sem-097": {
    "seed_ids": ["co-sem-097"],
    "product_effects": {
      "imageAltOverrides": {
        "prod-desk-lamp": "Three notebooks with blue, teal, and coral covers",
        "prod-notebook-set": "Desk lamp with adjustable brass shade",
      }
    },
  },
  "checkout-co-sem-100": {
    "seed_ids": ["co-sem-100"],
    "link_effects": {
      "linkDestinationOverrides": {"checkout.navigation.products": "/cart"}
    },
    "product_effects": {},
  },
  "checkout-co-sem-101": {
    "seed_ids": ["co-sem-101"],
    "link_effects": {
      "linkDestinationOverrides": {
        "checkout.support.shippingInformation": "/returns-and-refunds.html"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-102": {
    "seed_ids": ["co-sem-102"],
    "link_effects": {
      "linkDestinationOverrides": {
        "checkout.support.shippingInformation": "/resource.html"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-103": {
    "seed_ids": ["co-sem-103"],
    "button_effects": {
      "buttonDestinationOverrides": {
        "checkout.address.continueToPayment": "/cart"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-104": {
    "seed_ids": ["co-sem-104"],
    "button_effects": {
      "buttonActionTargetOverrides": {
        "checkout.cart.deskLamp.increment": "prod-notebook-set"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-107": {
    "seed_ids": ["co-sem-107"],
    "form_label_effects": {
      "formLabelTextOverrides": {
        "checkout.address.country": "State",
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-108": {
    "seed_ids": ["co-sem-108"],
    "form_label_effects": {
      "formLabelTextOverrides": {
        "checkout.address.deliveryInstructions": "Street address",
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-109": {
    "seed_ids": ["co-sem-109"],
    "form_label_effects": {
      "formLabelTextOverrides": {
        "checkout.address.city": "State",
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-110": {
    "seed_ids": ["co-sem-110"],
    "form_label_effects": {
      "formAccessibleNameOverrides": {
        "checkout.payment.cardholder": "Card number",
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-111": {
    "seed_ids": ["co-sem-111"],
    "form_label_effects": {
      "formLabelTextOverrides": {
        "checkout.payment.cardholder": "Card number",
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-112": {
    "seed_ids": ["co-sem-112"],
    "product_effects": {},
    "widget_effects": {
      "widgetTextOverrides": {
        "checkout.products.categoryTabs.deskAccessories": "Office supplies",
        "checkout.products.categoryTabs.officeSupplies": "Desk accessories",
      }
    },
  },
  "checkout-co-sem-113": {
    "seed_ids": ["co-sem-113"],
    "product_effects": {},
    "widget_effects": {
      "widgetContentBindingOverrides": {
        "checkout.products.categoryTabs.deskAccessories": "office-supplies"
      }
    },
  },
  "checkout-co-sem-114": {
    "seed_ids": ["co-sem-114"],
    "product_effects": {},
    "widget_effects": {
      "widgetAccessibleNameOverrides": {
        "checkout.products.categoryTablist": "Payment methods"
      }
    },
  },
  "checkout-co-sem-116": {
    "seed_ids": ["co-sem-116"],
    "landmark_effects": {
      "landmarkAccessibleNameOverrides": {
        "checkout.navigation.routes": "Checkout progress"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-117": {
    "seed_ids": ["co-sem-117"],
    "landmark_effects": {
      "landmarkAccessibleNameOverrides": {
        "checkout.progress": "Order totals"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-118": {
    "seed_ids": ["co-sem-118"],
    "landmark_effects": {
      "landmarkAccessibleNameOverrides": {
        "checkout.address.orderTotals": "Shipping details"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-119": {
    "seed_ids": ["co-sem-119"],
    "page_title_effects": {
      "pageTitleCarryoverTransitions": [
        {
          "fromTarget": "checkout.page.cart",
          "toTarget": "checkout.page.address",
        }
      ]
    },
    "product_effects": {},
  },
  "checkout-co-sem-120": {
    "seed_ids": ["co-sem-120"],
    "page_title_effects": {
      "pageTitleTextOverrides": {
        "checkout.page.address": "Billing address"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-121": {
    "seed_ids": ["co-sem-121"],
    "page_title_effects": {
      "pageTitleTextOverrides": {
        "checkout.page.payment": "Review"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-122": {
    "seed_ids": ["co-sem-122"],
    "autocomplete_effects": {
      "autocompleteValueOverrides": {
        "checkout.address.city": "address-level1"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-123": {
    "seed_ids": ["co-sem-123"],
    "autocomplete_effects": {
      "autocompleteValueOverrides": {
        "checkout.address.state": "address-level2"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-124": {
    "seed_ids": ["co-sem-124"],
    "autocomplete_effects": {
      "autocompleteValueOverrides": {
        "checkout.address.street": "billing street-address"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-125": {
    "seed_ids": ["co-sem-125"],
    "autocomplete_effects": {
      "autocompleteValueOverrides": {
        "checkout.payment.expiry": "cc-csc"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-126": {
    "seed_ids": ["co-sem-126"],
    "autocomplete_effects": {
      "autocompleteValueOverrides": {
        "checkout.address.country": "address-level1"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-127": {
    "seed_ids": ["co-sem-127"],
    "aria_state_effects": {
      "ariaCurrentOverrides": {
        "checkout.progress.cart": {"cart": None},
        "checkout.progress.address": {"cart": "step"},
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-128": {
    "seed_ids": ["co-sem-128"],
    "aria_state_effects": {
      "ariaCurrentOverrides": {
        "checkout.progress.cart": {"address": "step"},
        "checkout.progress.address": {"address": None},
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-129": {
    "seed_ids": ["co-sem-129"],
    "aria_state_effects": {
      "ariaPressedOverrides": {
        "checkout.products.language.en": False,
        "checkout.products.language.es": True,
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-130": {
    "seed_ids": ["co-sem-130"],
    "aria_state_effects": {
      "ariaPressedOverrides": {
        "checkout.products.language.en": True,
        "checkout.products.language.es": False,
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-131": {
    "seed_ids": ["co-sem-131"],
    "review_effects": {
      "tableHeaderAssociationOverrides": {
        "checkout.review.orderItems.deskLamp.lineTotalCell": [
          "review-item-header-prod-notebook-set",
          "review-line-total-header",
        ]
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-132": {
    "seed_ids": ["co-sem-132"],
    "review_effects": {
      "tableHeaderAssociationOverrides": {
        "checkout.review.orderItems.deskLamp.lineTotalCell": [
          "review-item-header-prod-notebook-set",
          "review-line-total-header",
        ],
        "checkout.review.orderItems.notebookSet.lineTotalCell": [
          "review-item-header-prod-desk-lamp",
          "review-line-total-header",
        ],
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-134": {
    "seed_ids": ["co-sem-134"],
    "error_message_effects": {
      "errorTextOverrides": {"checkout.address.postalCode": "ZIP code is required."}
    },
    "product_effects": {},
  },
  "checkout-co-sem-135": {
    "seed_ids": ["co-sem-135"],
    "error_message_effects": {
      "errorTextOverrides": {"checkout.address.email": "Email is required."}
    },
    "product_effects": {},
  },
  "checkout-co-sem-136": {
    "seed_ids": ["co-sem-136"],
    "error_message_effects": {
      "errorTextOverrides": {
        "checkout.payment.securityCode": "Security code is required."
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-137": {
    "seed_ids": ["co-sem-137"],
    "app_effects": {
      "rootLang": "en",
      "rootLangByRoute": {},
      "rootLangCarryoverTransitions": [
        {"fromLanguage": "es", "toLanguage": "en"}
      ],
    },
    "product_effects": {},
  },
  "checkout-co-sem-138": {
    "seed_ids": ["co-sem-138"],
    "local_language_effects": {
      "localLangOverrides": {
        "checkout.cart.shippingInformationBody": "en"
      }
    },
    "product_effects": {},
  },
  "checkout-co-sem-139": {
    "seed_ids": ["co-sem-139"],
    "product_effects": {
      "mediaSourceOverrides": {
        "checkout.products.walkthrough.captionTrack":
          "/media/brightlane-checkout-walkthrough.co-sem-139.en.vtt"
      }
    },
  },
}
IMPLEMENTED_DATASET_PROFILE_IDS = list(IMPLEMENTED_DATASET_CASES)
IMPLEMENTED_DATASET_SEED_IDS = [
  seed_id
  for case in IMPLEMENTED_DATASET_CASES.values()
  for seed_id in case["seed_ids"]
]
ALL_CHECKOUT_SEED_IDS = [
  *PILOT_SEED_IDS,
  *IMPLEMENTED_DATASET_SEED_IDS,
]
CASE_TRACKER_HEADER = [
  "case_id",
  "violation_type",
  "app",
  "short_description",
  "pattern",
  "tier",
  "baseline",
  "mutation",
  "why_unambiguous",
  "interaction_path",
  "evidence_state",
  "batch_id",
  "status",
  "notes",
]
FORBIDDEN_TRACKER_ID_FIELDS = {
  "dataset_no",
  "dataset_case_id",
  "ordinal",
  "display_id",
  "case_number",
}
CASE_TRACKER_STATUSES = {"planned", "implemented", "accepted", "rejected", "blocked"}
CASE_TRACKER_TIERS = {"easy", "hard"}
CASE_TRACKER_EVIDENCE_STATES = {"initial", "post_interaction"}


def _read_json(path: Path) -> dict:
  if path == REGISTRY:
    return load_benchmark_registry(path)
  return json.loads(path.read_text(encoding="utf-8"))


def _read_tracker_rows() -> tuple[list[str], list[dict[str, str]]]:
  with CASE_TRACKER.open(newline="", encoding="utf-8") as handle:
    reader = csv.DictReader(handle)
    return list(reader.fieldnames or []), list(reader)


def _node_payload() -> dict:
  script = f"""
    const subjects = await import({json.dumps((CHECKOUT_SRC_ROOT / "benchmark" / "subjects.js").as_uri())});
    const seeds = await import({json.dumps((CHECKOUT_SRC_ROOT / "benchmark" / "seeds.js").as_uri())});
    const profiles = await import({json.dumps((CHECKOUT_SRC_ROOT / "benchmark" / "profiles.js").as_uri())});
    const appEffects = await import({json.dumps((CHECKOUT_SRC_ROOT / "benchmark" / "effects" / "appEffects.js").as_uri())});
    const autocompleteEffects = await import({json.dumps((CHECKOUT_SRC_ROOT / "benchmark" / "effects" / "autocompleteEffects.js").as_uri())});
    const ariaStateEffects = await import({json.dumps((CHECKOUT_SRC_ROOT / "benchmark" / "effects" / "ariaStateEffects.js").as_uri())});
    const buttonEffects = await import({json.dumps((CHECKOUT_SRC_ROOT / "benchmark" / "effects" / "buttonEffects.js").as_uri())});
    const cartEffects = await import({json.dumps((CHECKOUT_SRC_ROOT / "benchmark" / "effects" / "cartEffects.js").as_uri())});
    const errorMessageEffects = await import({json.dumps((CHECKOUT_SRC_ROOT / "benchmark" / "effects" / "errorMessageEffects.js").as_uri())});
    const formLabelEffects = await import({json.dumps((CHECKOUT_SRC_ROOT / "benchmark" / "effects" / "formLabelEffects.js").as_uri())});
    const headingEffects = await import({json.dumps((CHECKOUT_SRC_ROOT / "benchmark" / "effects" / "headingEffects.js").as_uri())});
    const landmarkEffects = await import({json.dumps((CHECKOUT_SRC_ROOT / "benchmark" / "effects" / "landmarkEffects.js").as_uri())});
    const linkEffects = await import({json.dumps((CHECKOUT_SRC_ROOT / "benchmark" / "effects" / "linkEffects.js").as_uri())});
    const localLanguageEffects = await import({json.dumps((CHECKOUT_SRC_ROOT / "benchmark" / "effects" / "localLanguageEffects.js").as_uri())});
    const pageTitleEffects = await import({json.dumps((CHECKOUT_SRC_ROOT / "benchmark" / "effects" / "pageTitleEffects.js").as_uri())});
    const productsEffects = await import({json.dumps((CHECKOUT_SRC_ROOT / "benchmark" / "effects" / "productsEffects.js").as_uri())});
    const reviewEffects = await import({json.dumps((CHECKOUT_SRC_ROOT / "benchmark" / "effects" / "reviewEffects.js").as_uri())});
    const widgetEffects = await import({json.dumps((CHECKOUT_SRC_ROOT / "benchmark" / "effects" / "widgetEffects.js").as_uri())});
    const fixtures = await import({json.dumps((CHECKOUT_SRC_ROOT / "data" / "fixtures.js").as_uri())});
    const productsCopy = await import({json.dumps((CHECKOUT_SRC_ROOT / "content" / "productsCopy.js").as_uri())});

    const pilotActiveSeeds = profiles.getActiveSeeds(profiles.CHECKOUT_PILOT_PROFILE);
    const implementedProfileIds = {json.dumps(IMPLEMENTED_DATASET_PROFILE_IDS)};
    const effectsForSeeds = (activeSeeds) => ({{
      appEffects: appEffects.resolveAppEffects(activeSeeds),
      autocompleteEffects: autocompleteEffects.resolveAutocompleteEffects(activeSeeds),
      ariaStateEffects: ariaStateEffects.resolveAriaStateEffects(activeSeeds),
      buttonEffects: buttonEffects.resolveButtonEffects(activeSeeds),
      cartEffects: cartEffects.resolveCartEffects(activeSeeds),
      errorMessageEffects: errorMessageEffects.resolveErrorMessageEffects(activeSeeds),
      formLabelEffects: formLabelEffects.resolveFormLabelEffects(activeSeeds),
      headingEffects: headingEffects.resolveHeadingEffects(activeSeeds),
      landmarkEffects: landmarkEffects.resolveLandmarkEffects(activeSeeds),
      linkEffects: linkEffects.resolveLinkEffects(activeSeeds),
      localLanguageEffects: localLanguageEffects.resolveLocalLanguageEffects(activeSeeds),
      pageTitleEffects: pageTitleEffects.resolvePageTitleEffects(activeSeeds),
      productEffects: productsEffects.resolveProductsEffects(activeSeeds),
      reviewEffects: reviewEffects.resolveReviewEffects(activeSeeds),
      widgetEffects: widgetEffects.resolveWidgetEffects(activeSeeds),
    }});
    const implementedProfiles = Object.fromEntries(
      implementedProfileIds.map((profileId) => {{
        const activeSeeds = profiles.getActiveSeeds(profileId);
        return [profileId, {{
          activeSeeds,
          ...effectsForSeeds(activeSeeds),
        }}];
      }})
    );

    console.log(JSON.stringify({{
      subjectList: subjects.CHECKOUT_SUBJECT_LIST,
      notebookProduct: fixtures.PRODUCTS.find(
        (product) => product.id === "prod-notebook-set"
      ),
      notebookProductCopy: {{
        en: productsCopy.PRODUCTS_COPY_BY_LANGUAGE.en.products["prod-notebook-set"],
        es: productsCopy.PRODUCTS_COPY_BY_LANGUAGE.es.products["prod-notebook-set"],
      }},
      autocompleteTargets: autocompleteEffects.CHECKOUT_AUTOCOMPLETE_TARGETS,
      ariaStateTargets: ariaStateEffects.CHECKOUT_ARIA_STATE_TARGETS,
      buttonTargets: buttonEffects.CHECKOUT_BUTTON_TARGETS,
      formLabelTargets: formLabelEffects.CHECKOUT_FORM_LABEL_TARGETS,
      landmarkTargets: landmarkEffects.CHECKOUT_LANDMARK_TARGETS,
      linkTargets: linkEffects.CHECKOUT_LINK_TARGETS,
      localLanguageTargets: localLanguageEffects.CHECKOUT_LOCAL_LANGUAGE_TARGETS,
      widgetTargets: widgetEffects.CHECKOUT_WIDGET_TARGETS,
      seedIds: seeds.CHECKOUT_BENCHMARK_SEED_IDS,
      profileMap: Object.fromEntries(
        Object.entries(profiles.CHECKOUT_PROFILES).map(([key, value]) => [key, [...value]])
      ),
      cleanProfileId: profiles.CHECKOUT_CLEAN_PROFILE,
      pilotProfileId: profiles.CHECKOUT_PILOT_PROFILE,
      profileGlobal: profiles.CHECKOUT_PROFILE_GLOBAL,
      implementedProfiles,
      noProfileActiveSeeds: profiles.getActiveSeeds(),
      unknownProfileActiveSeeds: profiles.getActiveSeeds("checkout-unknown-profile"),
      cleanProfileActiveSeeds: profiles.getActiveSeeds(profiles.CHECKOUT_CLEAN_PROFILE),
      pilotProfileActiveSeeds: pilotActiveSeeds,
      noProfileAppEffects: appEffects.resolveAppEffects(profiles.getActiveSeeds()),
      cleanAppEffects: appEffects.resolveAppEffects(
        profiles.getActiveSeeds(profiles.CHECKOUT_CLEAN_PROFILE)
      ),
      unknownAppEffects: appEffects.resolveAppEffects(
        profiles.getActiveSeeds("checkout-unknown-profile")
      ),
      pilotAppEffects: appEffects.resolveAppEffects(pilotActiveSeeds),
      noProfileLocalLanguageEffects: localLanguageEffects.resolveLocalLanguageEffects(profiles.getActiveSeeds()),
      cleanLocalLanguageEffects: localLanguageEffects.resolveLocalLanguageEffects(
        profiles.getActiveSeeds(profiles.CHECKOUT_CLEAN_PROFILE)
      ),
      unknownLocalLanguageEffects: localLanguageEffects.resolveLocalLanguageEffects(
        profiles.getActiveSeeds("checkout-unknown-profile")
      ),
      pilotLocalLanguageEffects: localLanguageEffects.resolveLocalLanguageEffects(pilotActiveSeeds),
      noProfileAutocompleteEffects: autocompleteEffects.resolveAutocompleteEffects(profiles.getActiveSeeds()),
      noProfileAriaStateEffects: ariaStateEffects.resolveAriaStateEffects(profiles.getActiveSeeds()),
      noProfileButtonEffects: buttonEffects.resolveButtonEffects(profiles.getActiveSeeds()),
      noProfileCartEffects: cartEffects.resolveCartEffects(profiles.getActiveSeeds()),
      noProfileErrorMessageEffects: errorMessageEffects.resolveErrorMessageEffects(profiles.getActiveSeeds()),
      noProfileFormLabelEffects: formLabelEffects.resolveFormLabelEffects(profiles.getActiveSeeds()),
      noProfileHeadingEffects: headingEffects.resolveHeadingEffects(profiles.getActiveSeeds()),
      noProfileLandmarkEffects: landmarkEffects.resolveLandmarkEffects(profiles.getActiveSeeds()),
      noProfileLinkEffects: linkEffects.resolveLinkEffects(profiles.getActiveSeeds()),
      noProfilePageTitleEffects: pageTitleEffects.resolvePageTitleEffects(profiles.getActiveSeeds()),
      cleanAutocompleteEffects: autocompleteEffects.resolveAutocompleteEffects(
        profiles.getActiveSeeds(profiles.CHECKOUT_CLEAN_PROFILE)
      ),
      cleanAriaStateEffects: ariaStateEffects.resolveAriaStateEffects(
        profiles.getActiveSeeds(profiles.CHECKOUT_CLEAN_PROFILE)
      ),
      cleanButtonEffects: buttonEffects.resolveButtonEffects(
        profiles.getActiveSeeds(profiles.CHECKOUT_CLEAN_PROFILE)
      ),
      cleanCartEffects: cartEffects.resolveCartEffects(
        profiles.getActiveSeeds(profiles.CHECKOUT_CLEAN_PROFILE)
      ),
      cleanErrorMessageEffects: errorMessageEffects.resolveErrorMessageEffects(
        profiles.getActiveSeeds(profiles.CHECKOUT_CLEAN_PROFILE)
      ),
      cleanFormLabelEffects: formLabelEffects.resolveFormLabelEffects(
        profiles.getActiveSeeds(profiles.CHECKOUT_CLEAN_PROFILE)
      ),
      cleanHeadingEffects: headingEffects.resolveHeadingEffects(
        profiles.getActiveSeeds(profiles.CHECKOUT_CLEAN_PROFILE)
      ),
      cleanLandmarkEffects: landmarkEffects.resolveLandmarkEffects(
        profiles.getActiveSeeds(profiles.CHECKOUT_CLEAN_PROFILE)
      ),
      cleanLinkEffects: linkEffects.resolveLinkEffects(
        profiles.getActiveSeeds(profiles.CHECKOUT_CLEAN_PROFILE)
      ),
      cleanPageTitleEffects: pageTitleEffects.resolvePageTitleEffects(
        profiles.getActiveSeeds(profiles.CHECKOUT_CLEAN_PROFILE)
      ),
      unknownAutocompleteEffects: autocompleteEffects.resolveAutocompleteEffects(
        profiles.getActiveSeeds("checkout-unknown-profile")
      ),
      unknownAriaStateEffects: ariaStateEffects.resolveAriaStateEffects(
        profiles.getActiveSeeds("checkout-unknown-profile")
      ),
      unknownButtonEffects: buttonEffects.resolveButtonEffects(
        profiles.getActiveSeeds("checkout-unknown-profile")
      ),
      unknownCartEffects: cartEffects.resolveCartEffects(
        profiles.getActiveSeeds("checkout-unknown-profile")
      ),
      unknownErrorMessageEffects: errorMessageEffects.resolveErrorMessageEffects(
        profiles.getActiveSeeds("checkout-unknown-profile")
      ),
      unknownFormLabelEffects: formLabelEffects.resolveFormLabelEffects(
        profiles.getActiveSeeds("checkout-unknown-profile")
      ),
      unknownHeadingEffects: headingEffects.resolveHeadingEffects(
        profiles.getActiveSeeds("checkout-unknown-profile")
      ),
      unknownLandmarkEffects: landmarkEffects.resolveLandmarkEffects(
        profiles.getActiveSeeds("checkout-unknown-profile")
      ),
      unknownLinkEffects: linkEffects.resolveLinkEffects(
        profiles.getActiveSeeds("checkout-unknown-profile")
      ),
      unknownPageTitleEffects: pageTitleEffects.resolvePageTitleEffects(
        profiles.getActiveSeeds("checkout-unknown-profile")
      ),
      pilotAutocompleteEffects: autocompleteEffects.resolveAutocompleteEffects(pilotActiveSeeds),
      pilotAriaStateEffects: ariaStateEffects.resolveAriaStateEffects(pilotActiveSeeds),
      pilotButtonEffects: buttonEffects.resolveButtonEffects(pilotActiveSeeds),
      pilotCartEffects: cartEffects.resolveCartEffects(pilotActiveSeeds),
      pilotErrorMessageEffects: errorMessageEffects.resolveErrorMessageEffects(pilotActiveSeeds),
      pilotFormLabelEffects: formLabelEffects.resolveFormLabelEffects(pilotActiveSeeds),
      pilotHeadingEffects: headingEffects.resolveHeadingEffects(pilotActiveSeeds),
      pilotLandmarkEffects: landmarkEffects.resolveLandmarkEffects(pilotActiveSeeds),
      pilotLinkEffects: linkEffects.resolveLinkEffects(pilotActiveSeeds),
      pilotPageTitleEffects: pageTitleEffects.resolvePageTitleEffects(pilotActiveSeeds),
      noProfileProductEffects: productsEffects.resolveProductsEffects(profiles.getActiveSeeds()),
      cleanProductEffects: productsEffects.resolveProductsEffects(
        profiles.getActiveSeeds(profiles.CHECKOUT_CLEAN_PROFILE)
      ),
      unknownProductEffects: productsEffects.resolveProductsEffects(
        profiles.getActiveSeeds("checkout-unknown-profile")
      ),
      pilotProductEffects: productsEffects.resolveProductsEffects(pilotActiveSeeds),
      noProfileReviewEffects: reviewEffects.resolveReviewEffects(profiles.getActiveSeeds()),
      cleanReviewEffects: reviewEffects.resolveReviewEffects(
        profiles.getActiveSeeds(profiles.CHECKOUT_CLEAN_PROFILE)
      ),
      unknownReviewEffects: reviewEffects.resolveReviewEffects(
        profiles.getActiveSeeds("checkout-unknown-profile")
      ),
      pilotReviewEffects: reviewEffects.resolveReviewEffects(pilotActiveSeeds),
      noProfileWidgetEffects: widgetEffects.resolveWidgetEffects(profiles.getActiveSeeds()),
      cleanWidgetEffects: widgetEffects.resolveWidgetEffects(
        profiles.getActiveSeeds(profiles.CHECKOUT_CLEAN_PROFILE)
      ),
      unknownWidgetEffects: widgetEffects.resolveWidgetEffects(
        profiles.getActiveSeeds("checkout-unknown-profile")
      ),
      pilotWidgetEffects: widgetEffects.resolveWidgetEffects(pilotActiveSeeds),
    }}));
  """
  completed = subprocess.run(
    ["node", "--input-type=module", "-e", script],
    cwd=REPO_ROOT,
    text=True,
    capture_output=True,
    check=False,
  )
  assert completed.returncode == 0, completed.stderr
  return json.loads(completed.stdout)

def _runtime_source_text() -> str:
  paths = [*CHECKOUT_SRC_ROOT.rglob("*.js"), *CHECKOUT_SRC_ROOT.rglob("*.jsx")]
  return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def _component_source_text() -> str:
  paths = [
    path
    for path in CHECKOUT_SRC_ROOT.rglob("*")
    if path.suffix in {".js", ".jsx"} and "benchmark" not in path.parts
  ]
  return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def _assert_nested_subset(expected: object, actual: object) -> None:
  if isinstance(expected, dict):
    assert isinstance(actual, dict)
    for key, expected_value in expected.items():
      assert key in actual
      _assert_nested_subset(expected_value, actual[key])
    return

  assert actual == expected


def _testid_is_represented(test_id: str, source_text: str) -> bool:
  if test_id in source_text:
    return True
  dynamic_prefixes = {
    "cart-increment-": "cart-increment-" + "${item.id}",
    "product-add-": "product-add-${product.id}",
    "product-category-tab-": "product-category-tab-${category.id}",
    "product-image-": "product-image-${product.id}",
    "cart-quantity-": "cart-quantity-${item.id}",
    "review-order-quantity-": "review-order-quantity-${item.id}",
    "review-order-line-total-": "review-order-line-total-${item.id}",
    "checkout-progress-": "checkout-progress-${step.id}",
  }
  return any(
    test_id.startswith(prefix) and pattern in source_text
    for prefix, pattern in dynamic_prefixes.items()
  )


def test_checkout_benchmark_paths_are_standalone():
  assert CHECKOUT_ROOT.exists()
  assert REGISTRY.exists()
  assert MANIFEST.exists()
  assert CASE_TRACKER.exists()
  assert not (CHECKOUT_SRC_ROOT / "utils" / "semanticVariants.js").exists()


def test_checkout_profiles_activate_retained_fixtures_and_implemented_cases():
  payload = _node_payload()
  seed_ids = set(payload["seedIds"])

  assert payload["seedIds"] == ALL_CHECKOUT_SEED_IDS
  assert "co-sem-003" not in payload["seedIds"]
  assert all(seed_id.startswith("co-sem-") for seed_id in payload["seedIds"])
  assert payload["cleanProfileId"] == "checkout-clean-v1"
  assert payload["pilotProfileId"] == PILOT_PROFILE_ID
  assert set(payload["implementedProfiles"]) == set(IMPLEMENTED_DATASET_PROFILE_IDS)
  assert payload["noProfileActiveSeeds"] == []
  assert payload["unknownProfileActiveSeeds"] == []
  assert payload["cleanProfileActiveSeeds"] == []
  assert payload["pilotProfileActiveSeeds"] == PILOT_SEED_IDS
  assert payload["autocompleteTargets"]["addressCity"] == "checkout.address.city"
  assert payload["autocompleteTargets"]["addressCountry"] == (
    "checkout.address.country"
  )
  assert payload["autocompleteTargets"]["addressState"] == "checkout.address.state"
  assert payload["autocompleteTargets"]["paymentExpiry"] == "checkout.payment.expiry"
  assert payload["formLabelTargets"]["paymentCardholder"] == (
    "checkout.payment.cardholder"
  )
  assert payload["formLabelTargets"]["addressCountry"] == (
    "checkout.address.country"
  )
  assert payload["formLabelTargets"]["addressDeliveryInstructions"] == (
    "checkout.address.deliveryInstructions"
  )
  assert payload["ariaStateTargets"]["checkoutProgressCart"] == "checkout.progress.cart"
  assert payload["ariaStateTargets"]["checkoutProgressAddress"] == (
    "checkout.progress.address"
  )
  assert payload["ariaStateTargets"]["productsLanguageEnglish"] == (
    "checkout.products.language.en"
  )
  assert payload["ariaStateTargets"]["productsLanguageSpanish"] == (
    "checkout.products.language.es"
  )
  assert payload["buttonTargets"]["addressContinueToPayment"] == (
    "checkout.address.continueToPayment"
  )
  assert payload["buttonTargets"]["cartDeskLampIncrement"] == (
    "checkout.cart.deskLamp.increment"
  )
  assert payload["landmarkTargets"]["addressOrderTotals"] == (
    "checkout.address.orderTotals"
  )
  assert payload["linkTargets"]["navigationProducts"] == "checkout.navigation.products"
  assert payload["linkTargets"]["supportShippingInformation"] == (
    "checkout.support.shippingInformation"
  )
  assert payload["localLanguageTargets"]["cartShippingInformationBody"] == (
    "checkout.cart.shippingInformationBody"
  )

  for profile_id, expected_case in IMPLEMENTED_DATASET_CASES.items():
    assert payload["implementedProfiles"][profile_id]["activeSeeds"] == expected_case["seed_ids"]

  for profile_id, profile_seed_ids in payload["profileMap"].items():
    assert profile_id.startswith("checkout-")
    assert set(profile_seed_ids) <= seed_ids


def test_effect_resolvers_keep_clean_and_unknown_profiles_unmutated():
  payload = _node_payload()

  default_app_effects = {"rootLang": "en", "rootLangByRoute": {}}

  assert payload["noProfileAppEffects"] == default_app_effects
  assert payload["cleanAppEffects"] == default_app_effects
  assert payload["unknownAppEffects"] == default_app_effects
  assert payload["noProfileAutocompleteEffects"] == {}
  assert payload["noProfileButtonEffects"] == {}
  assert payload["noProfileCartEffects"] == {}
  assert payload["noProfileErrorMessageEffects"] == {}
  assert payload["noProfileFormLabelEffects"] == {}
  assert payload["noProfileHeadingEffects"] == {}
  assert payload["noProfileLandmarkEffects"] == {}
  assert payload["noProfileLinkEffects"] == {}
  assert payload["noProfilePageTitleEffects"] == {}
  assert payload["cleanAutocompleteEffects"] == {}
  assert payload["cleanButtonEffects"] == {}
  assert payload["cleanCartEffects"] == {}
  assert payload["cleanErrorMessageEffects"] == {}
  assert payload["cleanFormLabelEffects"] == {}
  assert payload["cleanHeadingEffects"] == {}
  assert payload["cleanLandmarkEffects"] == {}
  assert payload["cleanLinkEffects"] == {}
  assert payload["cleanPageTitleEffects"] == {}
  assert payload["unknownAutocompleteEffects"] == {}
  assert payload["unknownButtonEffects"] == {}
  assert payload["unknownCartEffects"] == {}
  assert payload["unknownErrorMessageEffects"] == {}
  assert payload["unknownFormLabelEffects"] == {}
  assert payload["unknownHeadingEffects"] == {}
  assert payload["unknownLandmarkEffects"] == {}
  assert payload["unknownLinkEffects"] == {}
  assert payload["unknownPageTitleEffects"] == {}
  assert payload["noProfileProductEffects"] == {}
  assert payload["cleanProductEffects"] == {}
  assert payload["unknownProductEffects"] == {}
  assert payload["noProfileReviewEffects"] == {}
  assert payload["cleanReviewEffects"] == {}
  assert payload["unknownReviewEffects"] == {}
  assert payload["noProfileWidgetEffects"] == {}
  assert payload["cleanWidgetEffects"] == {}
  assert payload["unknownWidgetEffects"] == {}
  assert payload["noProfileLocalLanguageEffects"] == {}
  assert payload["cleanLocalLanguageEffects"] == {}
  assert payload["unknownLocalLanguageEffects"] == {}
  assert payload["pilotAutocompleteEffects"] == {
    "autocompleteValueOverrides": {"checkout.address.street": "email"}
  }
  assert payload["noProfileAriaStateEffects"] == {}
  assert payload["cleanAriaStateEffects"] == {}
  assert payload["unknownAriaStateEffects"] == {}
  assert payload["pilotAriaStateEffects"] == {}
  assert payload["pilotButtonEffects"] == {}
  assert payload["pilotCartEffects"] == {}
  assert payload["pilotErrorMessageEffects"] == {}
  assert payload["pilotFormLabelEffects"] == {}
  assert payload["pilotHeadingEffects"] == {}
  assert payload["pilotLandmarkEffects"] == {}
  assert payload["pilotLinkEffects"] == {}
  assert payload["pilotPageTitleEffects"] == {}
  assert payload["pilotLocalLanguageEffects"] == {}
  assert payload["pilotProductEffects"] == {
    "deskLampAddButtonAccessibleName": "Remove Desk lamp"
  }
  assert payload["pilotAppEffects"] == default_app_effects
  assert payload["pilotReviewEffects"] == {}
  assert payload["pilotWidgetEffects"] == {}

  for profile_id, expected_case in IMPLEMENTED_DATASET_CASES.items():
    profile_payload = payload["implementedProfiles"][profile_id]
    assert profile_payload["appEffects"] == expected_case.get(
      "app_effects",
      default_app_effects,
    )
    assert profile_payload["autocompleteEffects"] == expected_case.get(
      "autocomplete_effects",
      {},
    )
    assert profile_payload["ariaStateEffects"] == expected_case.get(
      "aria_state_effects",
      {},
    )
    assert profile_payload["buttonEffects"] == expected_case.get(
      "button_effects",
      {},
    )
    assert profile_payload["errorMessageEffects"] == expected_case.get(
      "error_message_effects",
      {},
    )
    assert profile_payload["formLabelEffects"] == expected_case.get(
      "form_label_effects",
      {},
    )
    if "cart_effects_subset" in expected_case:
      _assert_nested_subset(
        expected_case["cart_effects_subset"],
        profile_payload["cartEffects"],
      )
    else:
      assert profile_payload["cartEffects"] == expected_case.get("cart_effects", {})
    assert profile_payload["headingEffects"] == expected_case.get(
      "heading_effects",
      {},
    )
    assert profile_payload["landmarkEffects"] == expected_case.get(
      "landmark_effects",
      {},
    )
    assert profile_payload["linkEffects"] == expected_case.get("link_effects", {})
    assert profile_payload["localLanguageEffects"] == expected_case.get(
      "local_language_effects",
      {},
    )
    assert profile_payload["pageTitleEffects"] == expected_case.get(
      "page_title_effects",
      {},
    )
    assert profile_payload["widgetEffects"] == expected_case.get(
      "widget_effects",
      {},
    )
    if "product_effects" in expected_case:
      assert profile_payload["productEffects"] == expected_case["product_effects"]
    else:
      _assert_nested_subset(
        expected_case["product_effects_subset"],
        profile_payload["productEffects"],
      )
    assert profile_payload["reviewEffects"] == expected_case.get(
      "review_effects", {}
    )


def test_checkout_subject_inventory_is_unique_and_maps_to_dom_testids():
  payload = _node_payload()
  subjects = payload["subjectList"]
  subject_ids = [subject["id"] for subject in subjects]
  test_ids = [subject["testId"] for subject in subjects if subject.get("testId")]
  component_text = _component_source_text()
  required_subject_ids = {
    "checkout.page.root",
    "checkout.page.products",
    "checkout.page.address",
    "checkout.page.payment",
    "checkout.navigation.routes",
    "checkout.progress",
    "checkout.cart.orderTotals",
    "checkout.cart.giftReceipt",
    "checkout.cart.saveCart",
    "checkout.footer.site",
    "checkout.products.featuredRegion",
    "checkout.products.pageHeading",
    "checkout.products.pageSummary",
    "checkout.products.featuredProductsHeading",
    "checkout.products.description",
    "checkout.products.language.en",
    "checkout.products.language.es",
    "checkout.products.cartSummary",
    "checkout.products.categoryTablist",
    "checkout.products.categoryTabs.deskAccessories",
    "checkout.products.categoryTabs.officeSupplies",
    "checkout.support.shippingInformation",
    "checkout.cart.pageHeading",
    "checkout.cart.pageSummary",
    "checkout.cart.emptyHeading",
    "checkout.payment.methodHeading",
    "checkout.cart.description",
    "checkout.cart.deliveryEstimate",
    "checkout.cart.shippingInformationDialog",
    "checkout.cart.shippingInformationBody",
    "checkout.products.deskLamp.image",
    "checkout.products.notebookSet.image",
    "checkout.products.deskLamp.addButton",
    "checkout.products.notebookSet.addButton",
    "checkout.address.street",
    "checkout.address.country",
    "checkout.address.deliveryInstructions",
    "checkout.payment.cardholder",
    "checkout.payment.cardNumber",
    "checkout.payment.securityCode",
    "checkout.review.content",
    "checkout.review.orderSummary",
    "checkout.review.orderItems.deskLamp.quantityCell",
    "checkout.review.orderItems.deskLamp.lineTotalCell",
    "checkout.review.orderItems.notebookSet.lineTotalCell",
  }

  assert subjects
  assert len(subject_ids) == len(set(subject_ids))
  assert len(test_ids) == len(set(test_ids))
  assert required_subject_ids <= set(subject_ids)
  assert all(subject_id.startswith("checkout.") for subject_id in subject_ids)
  assert all(_testid_is_represented(test_id, component_text) for test_id in test_ids)


def test_checkout_notebook_image_baseline_uses_fixture_copy_and_generic_subject():
  payload = _node_payload()
  subjects = {
    subject["id"]: subject
    for subject in payload["subjectList"]
  }

  assert payload["notebookProduct"] == {
    "id": "prod-notebook-set",
    "name": "Notebook set",
    "priceCents": 1800,
    "category": "Stationery",
    "imageSrc": "/notebook-set.svg",
    "imageAlt": "Three notebooks with blue, teal, and coral covers",
  }
  assert payload["notebookProductCopy"]["en"]["imageAlt"] == (
    "Three notebooks with blue, teal, and coral covers"
  )
  assert payload["notebookProductCopy"]["es"]["imageAlt"] == (
    "Tres cuadernos con cubiertas de color azul, verde azulado y coral"
  )
  assert subjects["checkout.products.notebookSet.image"] == {
    "id": "checkout.products.notebookSet.image",
    "testId": "product-image-prod-notebook-set",
    "description": "Notebook set product image in the browsing surface.",
  }

  asset = CHECKOUT_ROOT / "public" / "notebook-set.svg"
  assert asset.exists()
  asset_text = asset.read_text(encoding="utf-8")
  assert "<text" not in asset_text
  assert "co-sem" not in asset_text

def test_registry_registers_retained_fixtures_and_implemented_cases():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
    if configuration["app"] == "checkout-flow"
  }
  variants = {
    variant["variant_id"]: variant
    for variant in registry["variants"]
    if variant["app"] == "checkout-flow"
  }

  assert registry["schema_version"] == "benchmark-case-registry-v1"
  assert registry["benchmark_generation"] == "controlled-local-spas"
  assert list(variants) == ALL_CHECKOUT_SEED_IDS
  assert set(configurations) == {
    PILOT_PROFILE_ID,
    *IMPLEMENTED_DATASET_PROFILE_IDS,
  }
  assert configurations[PILOT_PROFILE_ID]["seed_ids"] == PILOT_SEED_IDS
  assert configurations[PILOT_PROFILE_ID]["planned_seed_count"] == 2
  for profile_id, expected_case in IMPLEMENTED_DATASET_CASES.items():
    assert configurations[profile_id]["seed_ids"] == expected_case["seed_ids"]
    assert configurations[profile_id]["planned_seed_count"] == 1
    assert configurations[profile_id]["status"] == "implemented"


def test_registry_profile_and_mutation_targets_are_consistent():
  payload = _node_payload()
  registry = _read_json(REGISTRY)
  subjects = {subject["id"] for subject in payload["subjectList"]}
  runtime_seed_ids = set(payload["seedIds"])
  variants = {
    variant["variant_id"]: variant
    for variant in registry["variants"]
    if variant["app"] == "checkout-flow"
  }
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
    if configuration["app"] == "checkout-flow"
  }

  assert set(variants) == runtime_seed_ids
  assert set(configurations) == (
    set(payload["profileMap"]) - {payload["cleanProfileId"]}
  )

  for profile_id, config in configurations.items():
    assert config["seed_ids"] == payload["profileMap"][profile_id]

    mutation_keys = []
    for seed_id in config["seed_ids"]:
      variant = variants[seed_id]
      assert variant["candidate_type"] in SUPPORTED_CANDIDATE_TYPES
      assert "legacy_reference_seed_id" not in variant
      assert variant["profile"] == profile_id
      assert variant["expected_human_judgment"] == "violation"
      assert variant["expected_state"]["benchmark_state_ids"]
      assert variant["expected_state"]["routes"]
      assert variant["expected_candidate"]["candidate_type"] == variant["candidate_type"]
      expected_evidence = variant["expected_evidence"]
      all_of = expected_evidence.get("all_of")
      if all_of:
        for evidence_item in all_of:
          assert evidence_item.get("bucket")
          assert any(
            (
              evidence_item.get("selector_hint"),
              evidence_item.get("attributes"),
              evidence_item.get("attribute_contains"),
              evidence_item.get("candidate_evidence"),
              evidence_item.get("primary_evidence_key"),
            )
          )
      elif expected_evidence.get("bucket") != "page":
        selector_hint = expected_evidence.get("selector_hint")
        if not selector_hint:
          attributes = expected_evidence.get("attributes")
          assert isinstance(attributes, dict) and attributes.get("tag")
          assert expected_evidence.get("candidate_evidence")

      for target in variant["mutation_targets"]:
        assert target["subject"] in subjects
        assert target["mutation_property"]
        mutation_keys.append((target["subject"], target["mutation_property"]))

    assert len(mutation_keys) == len(set(mutation_keys))


def test_registry_describes_stale_payment_form_label_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-088"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-088"]["status"] == "implemented"
  assert configurations["checkout-co-sem-088"]["seed_ids"] == ["co-sem-088"]
  assert variant["profile"] == "checkout-co-sem-088"
  assert variant["candidate_type"] == "form-label-mismatch"
  assert variant["expected_state"]["benchmark_state_ids"] == ["CO-S004"]
  assert variant["expected_state"]["routes"] == ["/checkout/payment"]
  assert "all_of" not in expected_evidence
  assert expected_evidence["selector_hint"] == '[data-testid="payment-card-number"]'
  assert expected_evidence["control"] == {
    "id": "payment-cardNumber",
    "name": "cardNumber",
  }
  assert expected_evidence["attributes"]["type"] == "text"
  assert expected_evidence["attributes"]["autocomplete"] == "cc-number"
  assert expected_evidence["attribute_contains"]["label"] == "Street address"


def test_registry_describes_city_labelled_as_state_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-109"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-109"]["status"] == "implemented"
  assert configurations["checkout-co-sem-109"]["seed_ids"] == ["co-sem-109"]
  assert variant["profile"] == "checkout-co-sem-109"
  assert variant["candidate_type"] == "form-label-mismatch"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S003"],
    "routes": ["/checkout/address"],
  }
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.address.city",
      "mutation_property": "label_text",
    }
  ]
  assert variant["expected_candidate"] == {
    "candidate_type": "form-label-mismatch",
    "selection_reason": "form_control_with_label_and_context_evidence",
    "type": "form-label-mismatch",
    "selector_hint": '[data-testid="address-city"]',
    "label": "State",
    "autocomplete": "address-level2",
  }
  assert expected_evidence["bucket"] == "form_controls"
  assert expected_evidence["selector_hint"] == '[data-testid="address-city"]'
  assert expected_evidence["control"] == {
    "id": "address-city",
    "name": "city",
  }
  assert expected_evidence["attributes"] == {
    "type": "text",
    "autocomplete": "address-level2",
  }
  assert expected_evidence["attribute_contains"] == {"label": "State"}
  assert "address-state" in expected_evidence["context"]["purpose_evidence"]


def test_registry_describes_country_select_labelled_as_state_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-107"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-107"]["status"] == "implemented"
  assert configurations["checkout-co-sem-107"]["seed_ids"] == ["co-sem-107"]
  assert variant["profile"] == "checkout-co-sem-107"
  assert variant["candidate_type"] == "form-label-mismatch"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S003"],
    "routes": ["/checkout/address"],
  }
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.address.country",
      "mutation_property": "label_text",
    }
  ]
  assert variant["expected_candidate"] == {
    "candidate_type": "form-label-mismatch",
    "selection_reason": "form_control_with_label_and_context_evidence",
    "type": "form-label-mismatch",
    "tag": "select",
    "label": "State",
    "autocomplete": "country-name",
  }
  assert "selector_hint" not in expected_evidence
  assert expected_evidence["bucket"] == "form_controls"
  assert expected_evidence["control"] == {"name": "country"}
  assert expected_evidence["attributes"] == {
    "tag": "select",
    "autocomplete": "country-name",
    "required": True,
    "has_value": True,
  }
  assert "attribute_contains" not in expected_evidence
  assert expected_evidence["candidate_evidence"] == {
    "supporting": {
      "form_label_context_v1": {
        "schema_version": "form_label_context_v1",
        "control": {
          "tag": "select",
          "name": "country",
          "autocomplete": "country-name",
          "required": True,
          "value_state": "filled",
        },
        "field_purpose_evidence": {
          "name": "country",
          "autocomplete": "country-name",
        },
        "labeling": {
          "label_sources": [
            {
              "relationship_type": "labels",
              "method": "for",
              "text_segments": ["State"],
            }
          ]
        },
      }
    }
  }
  assert "United States" in expected_evidence["context"]["purpose_evidence"]
  assert "address-level1" in expected_evidence["context"]["purpose_evidence"]


def test_registry_describes_delivery_instructions_labelled_as_street_address_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-108"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-108"]["status"] == "implemented"
  assert configurations["checkout-co-sem-108"]["seed_ids"] == ["co-sem-108"]
  assert variant["profile"] == "checkout-co-sem-108"
  assert variant["candidate_type"] == "form-label-mismatch"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S003"],
    "routes": ["/checkout/address"],
  }
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.address.deliveryInstructions",
      "mutation_property": "label_text",
    }
  ]
  assert variant["expected_candidate"] == {
    "candidate_type": "form-label-mismatch",
    "selection_reason": "form_control_with_label_and_context_evidence",
    "type": "form-label-mismatch",
    "tag": "textarea",
    "label": "Street address",
    "accessible_name": "Street address",
  }
  assert "selector_hint" not in expected_evidence
  assert expected_evidence["bucket"] == "form_controls"
  assert expected_evidence["control"] == {"name": "deliveryInstructions"}
  assert expected_evidence["attributes"] == {
    "tag": "textarea",
    "required": False,
    "accessible_name": "Street address",
  }
  assert "attribute_contains" not in expected_evidence
  context = expected_evidence["candidate_evidence"]["supporting"][
    "form_label_context_v1"
  ]
  assert context["control"] == {
    "tag": "textarea",
    "name": "deliveryInstructions",
    "required": False,
  }
  assert context["labeling"] == {
    "visible_label": "Street address",
    "computed_accessible_name": "Street address",
    "label_sources": [
      {
        "relationship_type": "labels",
        "method": "for",
        "text_segments": ["Street address"],
      }
    ],
  }
  descriptions = context["field_purpose_evidence"]["descriptions"]
  assert descriptions == [
    {
      "text": "Optional. Add gate codes, safe-place details, or delivery notes.",
      "relationship_type": "describes",
      "method": "aria-describedby",
    }
  ]
  assert "streetAddress" in expected_evidence["context"]["purpose_evidence"]


def test_registry_describes_cardholder_accessible_name_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-110"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-110"]["status"] == "implemented"
  assert configurations["checkout-co-sem-110"]["seed_ids"] == ["co-sem-110"]
  assert variant["profile"] == "checkout-co-sem-110"
  assert variant["candidate_type"] == "form-label-mismatch"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S004"],
    "routes": ["/checkout/payment"],
  }
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.payment.cardholder",
      "mutation_property": "accessible_name",
    }
  ]
  assert expected_evidence["bucket"] == "form_controls"
  assert expected_evidence["selector_hint"] == (
    '[data-testid="payment-cardholder"]'
  )
  assert expected_evidence["control"] == {
    "id": "payment-cardholder",
    "name": "cardholder",
  }
  assert expected_evidence["attributes"] == {
    "type": "text",
    "autocomplete": "cc-name",
    "required": True,
    "aria_label": "Card number",
    "accessible_name": "Card number",
  }
  assert expected_evidence["attribute_contains"] == {
    "label": "Cardholder name",
  }
  assert "payment-cardNumber" in expected_evidence["context"]["purpose_evidence"]


def test_registry_describes_cardholder_visible_label_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-111"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-111"]["status"] == "implemented"
  assert configurations["checkout-co-sem-111"]["seed_ids"] == ["co-sem-111"]
  assert variant["profile"] == "checkout-co-sem-111"
  assert variant["candidate_type"] == "form-label-mismatch"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S004"],
    "routes": ["/checkout/payment"],
  }
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.payment.cardholder",
      "mutation_property": "label_text",
    }
  ]
  assert expected_evidence["bucket"] == "form_controls"
  assert expected_evidence["selector_hint"] == (
    '[data-testid="payment-cardholder"]'
  )
  assert expected_evidence["control"] == {
    "id": "payment-cardholder",
    "name": "cardholder",
  }
  assert expected_evidence["attributes"] == {
    "type": "text",
    "autocomplete": "cc-name",
    "required": True,
    "aria_label": "",
    "accessible_name": "Card numberRequired",
  }
  assert expected_evidence["attribute_contains"] == {"label": "Card number"}
  assert "payment-cardNumber" in expected_evidence["context"]["purpose_evidence"]


def test_registry_describes_correct_tab_label_with_wrong_controlled_content_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-113"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-113"]["status"] == "implemented"
  assert configurations["checkout-co-sem-113"]["seed_ids"] == ["co-sem-113"]
  assert variant["profile"] == "checkout-co-sem-113"
  assert variant["candidate_type"] == "widget-label-purpose-mismatch"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S001"],
    "routes": ["/products"],
  }
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.products.categoryTabs.deskAccessories",
      "mutation_property": "controlled_content",
    }
  ]
  assert expected_evidence["bucket"] == "buttons"
  assert expected_evidence["selector_hint"] == (
    '[data-testid="product-category-tab-desk-accessories"]'
  )
  assert expected_evidence["attributes"] == {
    "tag": "button",
    "role": "tab",
    "text": "Desk accessories",
    "accessible_name": "Desk accessories",
    "aria_controls": "desk-accessories-panel",
    "aria_selected": "true",
  }
  assert expected_evidence["context"] == {
    "controlled_panel": "desk-accessories-panel",
    "controlled_panel_content": (
      "Everyday supplies for notes and planning.Notebook set"
    ),
    "controlled_panel_visible": True,
    "tablist_name": "Product categories",
    "data_testid": "product-category-tab-desk-accessories",
  }


def test_registry_describes_tablist_with_wrong_group_purpose_name():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}
  payload = _node_payload()

  variant = variants["co-sem-114"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-114"]["status"] == "implemented"
  assert configurations["checkout-co-sem-114"]["seed_ids"] == ["co-sem-114"]
  assert variant["profile"] == "checkout-co-sem-114"
  assert variant["candidate_type"] == "widget-label-purpose-mismatch"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S001"],
    "routes": ["/products"],
  }
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.products.categoryTablist",
      "mutation_property": "accessible_name",
    }
  ]
  assert payload["widgetTargets"]["productsCategoryTablist"] == (
    "checkout.products.categoryTablist"
  )
  assert expected_evidence["bucket"] == "visual_cues"
  assert expected_evidence["selector_hint"] == (
    '[data-testid="product-category-tablist"]'
  )
  assert expected_evidence["primary_evidence_key"] == "widget"
  assert expected_evidence["attributes"] == {
    "tag": "div",
    "role": "tablist",
    "text": "Desk accessories Office supplies",
    "accessible_name": "Payment methods",
    "aria_label": "Payment methods",
  }
  assert expected_evidence["context"] == {
    "data_testid": "product-category-tablist",
    "route": "/products",
    "child_tabs": [
      {
        "id": "desk-accessories-tab",
        "name": "Desk accessories",
        "aria_controls": "desk-accessories-panel",
        "aria_selected": "true",
      },
      {
        "id": "office-supplies-tab",
        "name": "Office supplies",
        "aria_controls": "office-supplies-panel",
        "aria_selected": "false",
      },
    ],
  }


def test_registry_describes_reciprocal_category_tab_label_swap():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-112"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-112"]["status"] == "implemented"
  assert configurations["checkout-co-sem-112"]["seed_ids"] == ["co-sem-112"]
  assert variant["profile"] == "checkout-co-sem-112"
  assert variant["candidate_type"] == "widget-label-purpose-mismatch"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S001"],
    "routes": ["/products"],
  }
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.products.categoryTabs.deskAccessories",
      "mutation_property": "visible_text",
    },
    {
      "subject": "checkout.products.categoryTabs.officeSupplies",
      "mutation_property": "visible_text",
    },
  ]
  assert expected_evidence["bucket"] == "buttons"
  assert expected_evidence["selector_hint"] == (
    '[data-testid="product-category-tab-desk-accessories"]'
  )
  assert expected_evidence["all_of"] == [
    {
      "bucket": "buttons",
      "selector_hint": '[data-testid="product-category-tab-desk-accessories"]',
      "primary_evidence_key": "widget",
      "attributes": {
        "tag": "button",
        "role": "tab",
        "text": "Office supplies",
        "accessible_name": "Office supplies",
        "aria_controls": "desk-accessories-panel",
        "aria_selected": "true",
      },
      "context": {
        "controlled_panel": "desk-accessories-panel",
        "controlled_panel_content": (
          "Lighting and cable tools for a tidy workspace. "
          "Desk lamp Cable organizer"
        ),
        "controlled_panel_visible": True,
        "tablist_name": "Product categories",
        "data_testid": "product-category-tab-desk-accessories",
      },
    },
    {
      "bucket": "buttons",
      "selector_hint": '[data-testid="product-category-tab-office-supplies"]',
      "primary_evidence_key": "widget",
      "attributes": {
        "tag": "button",
        "role": "tab",
        "text": "Desk accessories",
        "accessible_name": "Desk accessories",
        "aria_controls": "office-supplies-panel",
        "aria_selected": "false",
      },
      "context": {
        "controlled_panel": "office-supplies-panel",
        "controlled_panel_content": (
          "Everyday supplies for notes and planning.Notebook set"
        ),
        "controlled_panel_visible": False,
        "tablist_name": "Product categories",
        "data_testid": "product-category-tab-office-supplies",
      },
    },
  ]


def test_registry_describes_line_total_table_header_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-074"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-074"]["status"] == "implemented"
  assert configurations["checkout-co-sem-074"]["seed_ids"] == ["co-sem-074"]
  assert variant["profile"] == "checkout-co-sem-074"
  assert variant["candidate_type"] == "table-header-association-mismatch"
  assert variant["expected_state"]["benchmark_state_ids"] == ["CO-S005"]
  assert variant["expected_state"]["routes"] == ["/checkout/review"]
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.review.orderItems.deskLamp.lineTotalCell",
      "mutation_property": "table_header_association",
    }
  ]
  assert expected_evidence["bucket"] == "tables"
  assert expected_evidence["selector_hint"] == '[data-testid="review-order-table"]'
  assert "all_of" not in expected_evidence
  assert expected_evidence["primary_evidence_key"] == "table"
  assert expected_evidence["attributes"] == {
    "caption": "Product quantities and totals",
    "header_count": 4,
    "data_cell_count": 2,
  }
  assert expected_evidence["data_cell"] == {
    "text": "$32.00",
    "header_ids": [
      "review-item-header-prod-desk-lamp",
      "review-quantity-header",
    ],
    "headers_all_resolved": True,
    "row_index": 1,
    "column_index": 2,
  }
  assert variant["expected_candidate"]["selector_hint"] == (
    '[data-testid="review-order-line-total-prod-desk-lamp"]'
  )
  assert variant["expected_candidate"]["target_text"] == "$32.00"
  assert expected_evidence["context"]["seeded_header_ids"] == [
    "review-item-header-prod-desk-lamp",
    "review-quantity-header",
  ]


def test_registry_describes_quantity_table_header_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-075"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-075"]["status"] == "implemented"
  assert configurations["checkout-co-sem-075"]["seed_ids"] == ["co-sem-075"]
  assert variant["profile"] == "checkout-co-sem-075"
  assert variant["candidate_type"] == "table-header-association-mismatch"
  assert variant["expected_state"]["benchmark_state_ids"] == ["CO-S005"]
  assert variant["expected_state"]["routes"] == ["/checkout/review"]
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.review.orderItems.deskLamp.quantityCell",
      "mutation_property": "table_header_association",
    }
  ]
  assert expected_evidence["bucket"] == "tables"
  assert expected_evidence["selector_hint"] == '[data-testid="review-order-table"]'
  assert "all_of" not in expected_evidence
  assert expected_evidence["primary_evidence_key"] == "table"
  assert expected_evidence["attributes"] == {
    "caption": "Product quantities and totals",
    "header_count": 4,
    "data_cell_count": 2,
  }
  assert expected_evidence["data_cell"] == {
    "text": "1",
    "header_ids": [
      "review-item-header-prod-desk-lamp",
      "review-line-total-header",
    ],
    "headers_all_resolved": True,
    "row_index": 1,
    "column_index": 1,
  }
  assert variant["expected_candidate"]["selector_hint"] == (
    '[data-testid="review-order-quantity-prod-desk-lamp"]'
  )
  assert variant["expected_candidate"]["target_text"] == "1"
  assert expected_evidence["context"]["seeded_header_ids"] == [
    "review-item-header-prod-desk-lamp",
    "review-line-total-header",
  ]


def test_registry_describes_wrong_row_table_header_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-131"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-131"]["status"] == "implemented"
  assert configurations["checkout-co-sem-131"]["seed_ids"] == ["co-sem-131"]
  assert variant["profile"] == "checkout-co-sem-131"
  assert variant["candidate_type"] == "table-header-association-mismatch"
  assert variant["expected_state"]["benchmark_state_ids"] == ["CO-S005"]
  assert variant["expected_state"]["routes"] == ["/checkout/review"]
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.review.orderItems.deskLamp.lineTotalCell",
      "mutation_property": "table_header_association",
    }
  ]
  assert expected_evidence["bucket"] == "tables"
  assert expected_evidence["selector_hint"] == '[data-testid="review-order-table"]'
  assert expected_evidence["primary_evidence_key"] == "table"
  assert expected_evidence["attributes"] == {
    "caption": "Product quantities and totals",
    "header_count": 5,
    "data_cell_count": 4,
  }
  assert expected_evidence["data_cell"] == {
    "text": "$32.00",
    "header_ids": [
      "review-item-header-prod-notebook-set",
      "review-line-total-header",
    ],
    "headers_all_resolved": True,
    "row_index": 1,
    "column_index": 2,
  }
  assert variant["expected_candidate"]["selector_hint"] == (
    '[data-testid="review-order-line-total-prod-desk-lamp"]'
  )
  assert variant["expected_candidate"]["target_text"] == "$32.00"
  assert expected_evidence["context"]["seeded_header_ids"] == [
    "review-item-header-prod-notebook-set",
    "review-line-total-header",
  ]


def test_registry_describes_swapped_row_table_header_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-132"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-132"]["status"] == "implemented"
  assert configurations["checkout-co-sem-132"]["seed_ids"] == ["co-sem-132"]
  assert variant["profile"] == "checkout-co-sem-132"
  assert variant["candidate_type"] == "table-header-association-mismatch"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S005"],
    "routes": ["/checkout/review"],
  }
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.review.orderItems.deskLamp.lineTotalCell",
      "mutation_property": "table_header_association",
    },
    {
      "subject": "checkout.review.orderItems.notebookSet.lineTotalCell",
      "mutation_property": "table_header_association",
    },
  ]
  assert expected_evidence["bucket"] == "tables"
  assert expected_evidence["selector_hint"] == '[data-testid="review-order-table"]'
  assert expected_evidence["all_of"] == [
    {
      "bucket": "tables",
      "selector_hint": '[data-testid="review-order-table"]',
      "primary_evidence_key": "table",
      "attributes": {
        "caption": "Product quantities and totals",
        "header_count": 5,
        "data_cell_count": 4,
      },
      "data_cell": {
        "text": "$32.00",
        "header_ids": [
          "review-item-header-prod-notebook-set",
          "review-line-total-header",
        ],
        "headers_all_resolved": True,
        "row_index": 1,
        "column_index": 2,
      },
    },
    {
      "bucket": "tables",
      "selector_hint": '[data-testid="review-order-table"]',
      "primary_evidence_key": "table",
      "attributes": {
        "caption": "Product quantities and totals",
        "header_count": 5,
        "data_cell_count": 4,
      },
      "data_cell": {
        "text": "$18.00",
        "header_ids": [
          "review-item-header-prod-desk-lamp",
          "review-line-total-header",
        ],
        "headers_all_resolved": True,
        "row_index": 2,
        "column_index": 2,
      },
    },
  ]
  assert variant["expected_candidate"]["paired_targets"] == [
    {
      "selector_hint": '[data-testid="review-order-line-total-prod-desk-lamp"]',
      "target_text": "$32.00",
      "header_ids": [
        "review-item-header-prod-notebook-set",
        "review-line-total-header",
      ],
      "associated_headers": ["Notebook set", "Line total"],
    },
    {
      "selector_hint": '[data-testid="review-order-line-total-prod-notebook-set"]',
      "target_text": "$18.00",
      "header_ids": [
        "review-item-header-prod-desk-lamp",
        "review-line-total-header",
      ],
      "associated_headers": ["Desk lamp", "Line total"],
    },
  ]


def test_registry_describes_wrong_delivery_estimate_result_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-089"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-089"]["status"] == "implemented"
  assert configurations["checkout-co-sem-089"]["seed_ids"] == ["co-sem-089"]
  assert variant["profile"] == "checkout-co-sem-089"
  assert variant["candidate_type"] == "button-label-mismatch"
  assert variant["expected_state"]["benchmark_state_ids"] == ["CO-S002"]
  assert variant["expected_state"]["routes"] == ["/cart"]
  assert variant["graph_context_needed"] == "required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.cart.deliveryEstimate",
      "mutation_property": "activation_result",
    }
  ]
  assert expected_evidence["selector_hint"] == '[data-testid="delivery-estimate-trigger"]'
  assert expected_evidence["attributes"] == {
    "tag": "button",
    "type": "button",
    "text": "Delivery estimate",
    "accessible_name": "Delivery estimate",
  }
  assert "destination_state_context_v1" in expected_evidence["context"]


def test_registry_describes_continue_to_payment_wrong_result_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-103"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-103"]["status"] == "implemented"
  assert configurations["checkout-co-sem-103"]["seed_ids"] == ["co-sem-103"]
  assert variant["profile"] == "checkout-co-sem-103"
  assert variant["candidate_type"] == "button-label-mismatch"
  assert variant["expected_state"]["benchmark_state_ids"] == ["CO-S003"]
  assert variant["expected_state"]["routes"] == ["/checkout/address"]
  assert variant["graph_context_needed"] == "required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.address.continueToPayment",
      "mutation_property": "activation_destination",
    }
  ]
  assert expected_evidence["selector_hint"] == '[data-testid="continue-to-payment"]'
  assert expected_evidence["attributes"] == {
    "tag": "button",
    "type": "submit",
    "text": "Continue to payment",
    "accessible_name": "Continue to payment",
  }
  assert "destination_state_context_v1" in expected_evidence["context"]


def test_registry_describes_cart_wrong_object_result_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-104"]
  expected_candidate = variant["expected_candidate"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-104"]["status"] == "implemented"
  assert configurations["checkout-co-sem-104"]["seed_ids"] == ["co-sem-104"]
  assert variant["profile"] == "checkout-co-sem-104"
  assert variant["candidate_type"] == "button-label-mismatch"
  assert variant["expected_state"]["benchmark_state_ids"] == ["CO-S002"]
  assert variant["expected_state"]["routes"] == ["/cart"]
  assert variant["graph_context_needed"] == "required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.cart.deskLamp.increment",
      "mutation_property": "activation_target",
    }
  ]
  assert expected_evidence["selector_hint"] == (
    '[data-testid="cart-increment-prod-desk-lamp"]'
  )
  assert expected_evidence["attributes"] == {
    "tag": "button",
    "type": "button",
    "text": "+",
    "accessible_name": "Increase Desk lamp quantity",
  }
  assert expected_candidate["destination_route"] == "/cart"
  assert expected_candidate["destination_heading"] == "Cart"
  assert expected_candidate["destination_elements"] == [
    {
      "bucket": "visual_cues",
      "accessible_name": "Desk lamp quantity controls",
      "text": "- 1 +",
    },
    {
      "bucket": "visual_cues",
      "accessible_name": "Notebook set quantity controls",
      "text": "- 2 +",
    },
  ]


def test_registry_describes_active_tab_declared_unselected_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-066"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-066"]["status"] == "implemented"
  assert configurations["checkout-co-sem-066"]["seed_ids"] == ["co-sem-066"]
  assert variant["profile"] == "checkout-co-sem-066"
  assert variant["candidate_type"] == "aria-state-mismatch"
  assert variant["expected_state"]["benchmark_state_ids"] == ["CO-S001"]
  assert variant["expected_state"]["routes"] == ["/products"]
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.products.categoryTabs.deskAccessories",
      "mutation_property": "aria_selected",
    }
  ]
  assert expected_evidence["bucket"] == "buttons"
  assert expected_evidence["selector_hint"] == (
    '[data-testid="product-category-tab-desk-accessories"]'
  )
  assert expected_evidence["primary_evidence_key"] == "aria_state"
  assert expected_evidence["attributes"] == {
    "tag": "button",
    "role": "tab",
    "text": "Desk accessories",
    "accessible_name": "Desk accessories",
  }
  assert expected_evidence["state_attributes"] == {"aria_selected": "false"}
  assert expected_evidence["context"]["route"] == "/products"
  assert "Office supplies peer state unchanged" in variant["validation_approach"]


def test_registry_describes_stale_tab_selection_after_category_switch():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-067"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-067"]["status"] == "implemented"
  assert configurations["checkout-co-sem-067"]["seed_ids"] == ["co-sem-067"]
  assert variant["profile"] == "checkout-co-sem-067"
  assert variant["candidate_type"] == "aria-state-mismatch"
  assert variant["expected_state"]["benchmark_state_ids"] == ["CO-S012"]
  assert variant["expected_state"]["routes"] == ["/products"]
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.products.categoryTabs.deskAccessories",
      "mutation_property": "aria_selected",
    },
    {
      "subject": "checkout.products.categoryTabs.officeSupplies",
      "mutation_property": "aria_selected",
    },
  ]
  assert expected_evidence["bucket"] == "buttons"
  assert expected_evidence["selector_hint"] == (
    '[data-testid="product-category-tab-office-supplies"]'
  )
  assert expected_evidence["primary_evidence_key"] == "aria_state"
  assert expected_evidence["attributes"] == {
    "tag": "button",
    "role": "tab",
    "text": "Office supplies",
    "accessible_name": "Office supplies",
  }
  assert expected_evidence["state_attributes"] == {"aria_selected": "false"}
  assert expected_evidence["context"]["route"] == "/products"
  assert "stale Desk accessories peer state" in variant["validation_approach"]


def test_registry_describes_collapsed_disclosure_declared_expanded_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-069"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-069"]["status"] == "implemented"
  assert configurations["checkout-co-sem-069"]["seed_ids"] == ["co-sem-069"]
  assert variant["profile"] == "checkout-co-sem-069"
  assert variant["candidate_type"] == "aria-state-mismatch"
  assert variant["expected_state"]["benchmark_state_ids"] == ["CO-S002"]
  assert variant["expected_state"]["routes"] == ["/cart"]
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.cart.deliveryEstimate",
      "mutation_property": "aria_expanded",
    }
  ]
  assert expected_evidence["bucket"] == "buttons"
  assert expected_evidence["selector_hint"] == (
    '[data-testid="delivery-estimate-trigger"]'
  )
  assert expected_evidence["primary_evidence_key"] == "aria_state"
  assert expected_evidence["attributes"] == {
    "tag": "button",
    "text": "Delivery estimate",
    "accessible_name": "Delivery estimate",
  }
  assert expected_evidence["state_attributes"] == {"aria_expanded": "true"}
  assert expected_evidence["context"]["route"] == "/cart"
  assert "hidden controlled-panel context" in variant["validation_approach"]


def test_registry_describes_expanded_disclosure_declared_collapsed_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-068"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-068"]["status"] == "implemented"
  assert configurations["checkout-co-sem-068"]["seed_ids"] == ["co-sem-068"]
  assert variant["profile"] == "checkout-co-sem-068"
  assert variant["candidate_type"] == "aria-state-mismatch"
  assert variant["expected_state"]["benchmark_state_ids"] == ["CO-S013"]
  assert variant["expected_state"]["routes"] == ["/cart"]
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.cart.deliveryEstimate",
      "mutation_property": "aria_expanded",
    }
  ]
  assert expected_evidence["bucket"] == "buttons"
  assert expected_evidence["selector_hint"] == (
    '[data-testid="delivery-estimate-trigger"]'
  )
  assert expected_evidence["primary_evidence_key"] == "aria_state"
  assert expected_evidence["attributes"] == {
    "tag": "button",
    "text": "Delivery estimate",
    "accessible_name": "Delivery estimate",
  }
  assert expected_evidence["state_attributes"] == {"aria_expanded": "false"}
  assert expected_evidence["context"]["route"] == "/cart"
  assert "visible controlled-panel context" in variant["validation_approach"]


def test_registry_describes_disabled_switch_declared_checked_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-071"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-071"]["status"] == "implemented"
  assert configurations["checkout-co-sem-071"]["seed_ids"] == ["co-sem-071"]
  assert variant["profile"] == "checkout-co-sem-071"
  assert variant["candidate_type"] == "aria-state-mismatch"
  assert variant["expected_state"]["benchmark_state_ids"] == ["CO-S002"]
  assert variant["expected_state"]["routes"] == ["/cart"]
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.cart.giftReceipt",
      "mutation_property": "aria_checked",
    }
  ]
  assert expected_evidence["bucket"] == "buttons"
  assert expected_evidence["selector_hint"] == (
    '[data-testid="gift-receipt-switch"]'
  )
  assert expected_evidence["primary_evidence_key"] == "aria_state"
  assert expected_evidence["attributes"] == {
    "tag": "button",
    "role": "switch",
    "text": "Gift receipt",
    "accessible_name": "Gift receipt",
  }
  assert expected_evidence["state_attributes"] == {"aria_checked": "true"}
  assert expected_evidence["context"]["route"] == "/cart"
  assert "off-state styling" in variant["validation_approach"]


def test_registry_describes_saved_toggle_declared_unpressed_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-072"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-072"]["status"] == "implemented"
  assert configurations["checkout-co-sem-072"]["seed_ids"] == ["co-sem-072"]
  assert variant["profile"] == "checkout-co-sem-072"
  assert variant["candidate_type"] == "aria-state-mismatch"
  assert variant["expected_state"]["benchmark_state_ids"] == ["CO-S015"]
  assert variant["expected_state"]["routes"] == ["/cart"]
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.cart.saveCart",
      "mutation_property": "aria_pressed",
    }
  ]
  assert expected_evidence["bucket"] == "buttons"
  assert expected_evidence["selector_hint"] == '[data-testid="save-cart-toggle"]'
  assert expected_evidence["primary_evidence_key"] == "aria_state"
  assert expected_evidence["attributes"] == {
    "tag": "button",
    "text": "Save cart",
    "accessible_name": "Save cart",
  }
  assert expected_evidence["state_attributes"] == {"aria_pressed": "false"}
  assert expected_evidence["context"]["route"] == "/cart"
  assert "active is-saved styling" in variant["validation_approach"]


def test_registry_describes_unsaved_toggle_declared_pressed_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-073"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-073"]["status"] == "implemented"
  assert configurations["checkout-co-sem-073"]["seed_ids"] == ["co-sem-073"]
  assert variant["profile"] == "checkout-co-sem-073"
  assert variant["candidate_type"] == "aria-state-mismatch"
  assert variant["expected_state"]["benchmark_state_ids"] == ["CO-S002"]
  assert variant["expected_state"]["routes"] == ["/cart"]
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.cart.saveCart",
      "mutation_property": "aria_pressed",
    }
  ]
  assert expected_evidence["bucket"] == "buttons"
  assert expected_evidence["selector_hint"] == '[data-testid="save-cart-toggle"]'
  assert expected_evidence["primary_evidence_key"] == "aria_state"
  assert expected_evidence["attributes"] == {
    "tag": "button",
    "text": "Save cart",
    "accessible_name": "Save cart",
  }
  assert expected_evidence["state_attributes"] == {"aria_pressed": "true"}
  assert expected_evidence["context"]["route"] == "/cart"
  assert "inactive styling" in variant["validation_approach"]


def test_registry_describes_enabled_switch_declared_unchecked_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-070"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-070"]["status"] == "implemented"
  assert configurations["checkout-co-sem-070"]["seed_ids"] == ["co-sem-070"]
  assert variant["profile"] == "checkout-co-sem-070"
  assert variant["candidate_type"] == "aria-state-mismatch"
  assert variant["expected_state"]["benchmark_state_ids"] == ["CO-S014"]
  assert variant["expected_state"]["routes"] == ["/cart"]
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.cart.giftReceipt",
      "mutation_property": "aria_checked",
    }
  ]
  assert expected_evidence["bucket"] == "buttons"
  assert expected_evidence["selector_hint"] == (
    '[data-testid="gift-receipt-switch"]'
  )
  assert expected_evidence["primary_evidence_key"] == "aria_state"
  assert expected_evidence["attributes"] == {
    "tag": "button",
    "role": "switch",
    "text": "Gift receipt",
    "accessible_name": "Gift receipt",
  }
  assert expected_evidence["state_attributes"] == {"aria_checked": "false"}
  assert expected_evidence["context"]["route"] == "/cart"
  assert "enabled is-on styling" in variant["validation_approach"]


def test_registry_describes_stale_aria_current_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-090"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-090"]["status"] == "implemented"
  assert configurations["checkout-co-sem-090"]["seed_ids"] == ["co-sem-090"]
  assert variant["profile"] == "checkout-co-sem-090"
  assert variant["candidate_type"] == "aria-state-mismatch"
  assert variant["expected_state"]["benchmark_state_ids"] == ["CO-S002"]
  assert variant["expected_state"]["routes"] == ["/cart"]
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.navigation.products",
      "mutation_property": "aria_current",
    },
    {
      "subject": "checkout.navigation.cart",
      "mutation_property": "aria_current",
    },
  ]
  assert expected_evidence["bucket"] == "links"
  assert expected_evidence["selector_hint"] == '[data-testid="nav-products"]'
  assert expected_evidence["primary_evidence_key"] == "aria_state"
  assert expected_evidence["attributes"] == {
    "tag": "a",
    "text": "Products",
    "accessible_name": "Products",
    "href": "/products",
  }
  assert expected_evidence["context"]["route"] == "/cart"
  assert "Cart peer link not current" in variant["validation_approach"]


def test_registry_describes_wrong_checkout_progress_current_step_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-127"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-127"]["status"] == "implemented"
  assert configurations["checkout-co-sem-127"]["seed_ids"] == ["co-sem-127"]
  assert variant["profile"] == "checkout-co-sem-127"
  assert variant["candidate_type"] == "aria-state-mismatch"
  assert variant["expected_state"]["benchmark_state_ids"] == ["CO-S002"]
  assert variant["expected_state"]["routes"] == ["/cart"]
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.progress.cart",
      "mutation_property": "aria_current",
    },
    {
      "subject": "checkout.progress.address",
      "mutation_property": "aria_current",
    },
  ]
  assert expected_evidence["bucket"] == "visual_cues"
  assert expected_evidence["selector_hint"] == (
    '[data-testid="checkout-progress-address"]'
  )
  assert expected_evidence["state_attributes"] == {"aria_current": "step"}
  assert expected_evidence["peer_state"] == {
    "selector_hint": '[data-testid="checkout-progress-cart"]',
    "attributes": {"tag": "li"},
    "attribute_contains": {"text": "Cart"},
    "absent_state_attributes": ["aria_current"],
  }
  assert "conjunctively match" in variant["validation_approach"]


def test_registry_describes_stale_checkout_progress_after_address_transition_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-128"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-128"]["status"] == "implemented"
  assert configurations["checkout-co-sem-128"]["seed_ids"] == ["co-sem-128"]
  assert variant["profile"] == "checkout-co-sem-128"
  assert variant["candidate_type"] == "aria-state-mismatch"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S003"],
    "routes": ["/checkout/address"],
  }
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.progress.cart",
      "mutation_property": "aria_current",
    },
    {
      "subject": "checkout.progress.address",
      "mutation_property": "aria_current",
    },
  ]
  assert expected_evidence["bucket"] == "visual_cues"
  assert expected_evidence["selector_hint"] == (
    '[data-testid="checkout-progress-cart"]'
  )
  assert expected_evidence["state_attributes"] == {"aria_current": "step"}
  assert expected_evidence["peer_state"] == {
    "selector_hint": '[data-testid="checkout-progress-address"]',
    "attributes": {"tag": "li"},
    "attribute_contains": {"text": "Shipping address"},
    "absent_state_attributes": ["aria_current"],
  }
  assert expected_evidence["context"]["route"] == "/checkout/address"
  assert expected_evidence["context"]["document_title"] == (
    "Shipping address | Brightlane Checkout"
  )
  assert "Clean Address and co-sem-127 Cart-state controls" in (
    variant["validation_approach"]
  )


def test_registry_describes_wrong_initial_language_pressed_mapping_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-129"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-129"]["status"] == "implemented"
  assert configurations["checkout-co-sem-129"]["seed_ids"] == ["co-sem-129"]
  assert variant["profile"] == "checkout-co-sem-129"
  assert variant["candidate_type"] == "aria-state-mismatch"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S001"],
    "routes": ["/products"],
  }
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.products.language.en",
      "mutation_property": "aria_pressed",
    },
    {
      "subject": "checkout.products.language.es",
      "mutation_property": "aria_pressed",
    },
  ]
  assert expected_evidence["bucket"] == "buttons"
  assert expected_evidence["selector_hint"] == "button#products-language-es"
  assert expected_evidence["attributes"] == {
    "tag": "button",
    "role": "button",
    "text": "Spanish",
    "accessible_name": "Spanish",
  }
  assert expected_evidence["state_attributes"] == {"aria_pressed": "true"}
  assert expected_evidence["peer_state"] == {
    "selector_hint": "button#products-language-en",
    "attributes": {
      "text": "English",
      "accessible_name": "English",
    },
    "state_attributes": {"aria_pressed": "false"},
  }
  assert expected_evidence["context"]["document_language"] == "en"
  assert "CO-S001 constraint excludes" in variant["validation_approach"]


def test_registry_describes_stale_language_pressed_mapping_after_spanish_switch():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-130"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-130"]["status"] == "implemented"
  assert configurations["checkout-co-sem-130"]["seed_ids"] == ["co-sem-130"]
  assert variant["profile"] == "checkout-co-sem-130"
  assert variant["candidate_type"] == "aria-state-mismatch"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S007"],
    "routes": ["/products"],
  }
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.products.language.en",
      "mutation_property": "aria_pressed",
    },
    {
      "subject": "checkout.products.language.es",
      "mutation_property": "aria_pressed",
    },
  ]
  assert expected_evidence["bucket"] == "buttons"
  assert expected_evidence["selector_hint"] == "button#products-language-en"
  assert expected_evidence["attributes"] == {
    "tag": "button",
    "role": "button",
    "text": "Inglés",
    "accessible_name": "Inglés",
  }
  assert expected_evidence["state_attributes"] == {"aria_pressed": "true"}
  assert expected_evidence["peer_state"] == {
    "selector_hint": "button#products-language-es",
    "attributes": {
      "text": "Español",
      "accessible_name": "Español",
    },
    "state_attributes": {"aria_pressed": "false"},
  }
  assert expected_evidence["context"]["document_language"] == "es"
  assert "initial English CO-S001 state" in variant["validation_approach"]
  assert "Spanish CO-S007 result" in variant["validation_approach"]


def test_registry_describes_stale_root_language_after_switching_back_to_english():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-137"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-137"]["status"] == "implemented"
  assert configurations["checkout-co-sem-137"]["seed_ids"] == ["co-sem-137"]
  assert variant["profile"] == "checkout-co-sem-137"
  assert variant["candidate_type"] == "lang-mismatch"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S020"],
    "routes": ["/products"],
  }
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.page.root",
      "mutation_property": "lang",
    }
  ]
  assert expected_evidence["bucket"] == "page"
  assert expected_evidence["attributes"] == {
    "html_lang": "es",
    "document_lang": "es",
    "title": "Products | Brightlane Checkout",
  }
  assert expected_evidence["attribute_contains"] == {
    "body_text_sample": "Browse featured products"
  }
  assert "correct English CO-S001 and Spanish CO-S007 states" in (
    variant["validation_approach"]
  )
  assert "final English CO-S020" in variant["validation_approach"]


def test_registry_describes_premature_cart_heading_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-091"]

  assert configurations["checkout-co-sem-091"]["status"] == "implemented"
  assert configurations["checkout-co-sem-091"]["seed_ids"] == ["co-sem-091"]
  assert variant["profile"] == "checkout-co-sem-091"
  assert variant["candidate_type"] == "heading-not-descriptive"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S002"],
    "routes": ["/cart"],
  }
  assert variant["mutation_targets"] == [
    {
      "mutation_property": "visible_text",
      "subject": "checkout.cart.pageHeading",
    }
  ]
  assert variant["expected_candidate"] == {
    "candidate_type": "heading-not-descriptive",
    "selection_reason": "heading_with_section_context_evidence",
    "type": "heading-not-descriptive",
    "selector_hint": "h1:nth-of-type(1)",
    "tag": "h1",
    "level": 1,
    "text": "Shipping address",
    "accessible_name": "Shipping address",
  }
  expected_evidence = variant["expected_evidence"]
  assert expected_evidence["bucket"] == "headings"
  assert expected_evidence["selector_hint"] == "h1:nth-of-type(1)"
  assert expected_evidence["primary_evidence_key"] == "heading"
  assert expected_evidence["attributes"] == {
    "tag": "h1",
    "text": "Shipping address",
    "level": 1,
    "accessible_name": "Shipping address",
  }
  assert expected_evidence["context"]["route"] == "/cart"
  assert expected_evidence["context"]["document_title"] == (
    "Cart | Brightlane Checkout"
  )
  assert variant["graph_context_needed"] == "helpful_not_required"


def test_registry_describes_conditional_empty_cart_heading_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-092"]

  assert configurations["checkout-co-sem-092"]["status"] == "implemented"
  assert configurations["checkout-co-sem-092"]["seed_ids"] == ["co-sem-092"]
  assert variant["profile"] == "checkout-co-sem-092"
  assert variant["candidate_type"] == "heading-not-descriptive"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S017"],
    "routes": ["/cart"],
  }
  assert variant["mutation_targets"] == [
    {
      "mutation_property": "visible_text",
      "subject": "checkout.cart.emptyHeading",
    }
  ]
  assert variant["expected_candidate"] == {
    "candidate_type": "heading-not-descriptive",
    "selection_reason": "heading_with_section_context_evidence",
    "type": "heading-not-descriptive",
    "selector_hint": "h2#empty-cart-heading",
    "tag": "h2",
    "level": 2,
    "text": "Cart items",
    "accessible_name": "Cart items",
  }
  expected_evidence = variant["expected_evidence"]
  assert expected_evidence["bucket"] == "headings"
  assert expected_evidence["selector_hint"] == "h2#empty-cart-heading"
  assert expected_evidence["primary_evidence_key"] == "heading"
  assert expected_evidence["attributes"] == {
    "tag": "h2",
    "text": "Cart items",
    "level": 2,
    "accessible_name": "Cart items",
  }
  assert expected_evidence["context"]["route"] == "/cart"
  assert expected_evidence["context"]["document_title"] == (
    "Cart | Brightlane Checkout"
  )
  assert "zero cart-item elements" in expected_evidence["context"][
    "state_identity_note"
  ]
  assert variant["graph_context_needed"] == "helpful_not_required"


def test_registry_describes_narrow_payment_section_heading_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-093"]

  assert configurations["checkout-co-sem-093"]["status"] == "implemented"
  assert configurations["checkout-co-sem-093"]["seed_ids"] == ["co-sem-093"]
  assert variant["profile"] == "checkout-co-sem-093"
  assert variant["candidate_type"] == "heading-not-descriptive"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S004"],
    "routes": ["/checkout/payment"],
  }
  assert variant["mutation_targets"] == [
    {
      "mutation_property": "visible_text",
      "subject": "checkout.payment.methodHeading",
    }
  ]
  assert variant["expected_candidate"] == {
    "candidate_type": "heading-not-descriptive",
    "selection_reason": "heading_with_section_context_evidence",
    "type": "heading-not-descriptive",
    "selector_hint": "h2#payment-form-heading",
    "tag": "h2",
    "level": 2,
    "text": "Card number",
    "accessible_name": "Card number",
  }
  expected_evidence = variant["expected_evidence"]
  assert expected_evidence["bucket"] == "headings"
  assert expected_evidence["selector_hint"] == "h2#payment-form-heading"
  assert expected_evidence["primary_evidence_key"] == "heading"
  assert expected_evidence["attributes"] == {
    "tag": "h2",
    "text": "Card number",
    "level": 2,
    "accessible_name": "Card number",
  }
  assert expected_evidence["context"]["route"] == "/checkout/payment"
  assert expected_evidence["context"]["document_title"] == (
    "Payment | Brightlane Checkout"
  )
  assert "Cardholder name" in expected_evidence["context"][
    "section_content_evidence"
  ]
  assert "Security code" in expected_evidence["context"][
    "section_content_evidence"
  ]
  assert variant["graph_context_needed"] == "not_required"


def test_registry_describes_stale_products_heading_block_on_cart():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-094"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-094"]["status"] == "implemented"
  assert configurations["checkout-co-sem-094"]["seed_ids"] == ["co-sem-094"]
  assert variant["profile"] == "checkout-co-sem-094"
  assert variant["candidate_type"] == "heading-not-descriptive"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S002"],
    "routes": ["/cart"],
  }
  assert variant["mutation_targets"] == [
    {
      "mutation_property": "visible_text",
      "subject": "checkout.cart.pageHeading",
    },
    {
      "mutation_property": "visible_text",
      "subject": "checkout.cart.pageSummary",
    },
  ]
  assert variant["expected_candidate"] == {
    "candidate_type": "heading-not-descriptive",
    "selection_reason": "heading_with_section_context_evidence",
    "type": "heading-not-descriptive",
    "tag": "h1",
    "level": 1,
    "text": "Products",
    "accessible_name": "Products",
  }
  assert "selector_hint" not in variant["expected_candidate"]
  assert expected_evidence["bucket"] == "headings"
  assert "selector_hint" not in expected_evidence
  assert expected_evidence["primary_evidence_key"] == "heading"
  assert expected_evidence["attributes"] == {
    "tag": "h1",
    "text": "Products",
    "level": 1,
    "accessible_name": "Products",
  }
  assert expected_evidence["candidate_evidence"] == {
    "supporting": {
      "heading_scoped_content": {
        "schema_version": "heading_scoped_content_v1",
        "source_element_ref": {
          "bucket": "landmarks",
          "tag": "main",
        },
        "truncated": False,
      },
      "heading_scope": {
        "sampled_items": [
          {
            "kind": "paragraph",
            "text": "Browse featured products and update the cart summary.",
          }
        ]
      },
    }
  }
  assert expected_evidence["context"]["route"] == "/cart"
  assert expected_evidence["context"]["document_title"] == (
    "Cart | Brightlane Checkout"
  )
  assert variant["graph_context_needed"] == "helpful_not_required"


def test_registry_describes_navigation_copied_progress_label_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-116"]

  assert configurations["checkout-co-sem-116"]["status"] == "implemented"
  assert configurations["checkout-co-sem-116"]["seed_ids"] == ["co-sem-116"]
  assert variant["profile"] == "checkout-co-sem-116"
  assert variant["candidate_type"] == "landmark-purpose-mismatch"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S002"],
    "routes": ["/cart"],
  }
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.navigation.routes",
      "mutation_property": "accessible_name",
    }
  ]
  assert variant["expected_candidate"] == {
    "candidate_type": "landmark-purpose-mismatch",
    "selection_reason": "visible_landmark_with_role_and_context_evidence",
    "type": "landmark-purpose-mismatch",
    "selector_hint": "nav:nth-of-type(1)",
    "tag": "nav",
    "accessible_name": "Checkout progress",
    "aria_label": "Checkout progress",
  }
  expected_evidence = variant["expected_evidence"]
  assert expected_evidence["bucket"] == "landmarks"
  assert expected_evidence["selector_hint"] == "nav:nth-of-type(1)"
  assert expected_evidence["primary_evidence_key"] == "landmark"
  assert expected_evidence["attributes"] == {
    "tag": "nav",
    "text": "Products Cart",
    "accessible_name": "Checkout progress",
    "aria_label": "Checkout progress",
  }
  assert expected_evidence["context"]["route"] == "/cart"
  assert expected_evidence["context"]["document_title"] == (
    "Cart | Brightlane Checkout"
  )
  assert variant["graph_context_needed"] == "helpful_not_required"


def test_registry_describes_progress_copied_order_totals_label_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-117"]

  assert configurations["checkout-co-sem-117"]["status"] == "implemented"
  assert configurations["checkout-co-sem-117"]["seed_ids"] == ["co-sem-117"]
  assert variant["profile"] == "checkout-co-sem-117"
  assert variant["candidate_type"] == "landmark-purpose-mismatch"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S002"],
    "routes": ["/cart"],
  }
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.progress",
      "mutation_property": "accessible_name",
    }
  ]
  assert variant["expected_candidate"] == {
    "candidate_type": "landmark-purpose-mismatch",
    "selection_reason": "visible_landmark_with_role_and_context_evidence",
    "type": "landmark-purpose-mismatch",
    "selector_hint": '[data-testid="checkout-progress"]',
    "tag": "section",
    "accessible_name": "Order totals",
    "aria_label": "Order totals",
  }
  expected_evidence = variant["expected_evidence"]
  assert expected_evidence["bucket"] == "landmarks"
  assert expected_evidence["selector_hint"] == '[data-testid="checkout-progress"]'
  assert expected_evidence["primary_evidence_key"] == "landmark"
  assert expected_evidence["attributes"] == {
    "tag": "section",
    "accessible_name": "Order totals",
    "aria_label": "Order totals",
  }
  assert expected_evidence["attribute_contains"] == {"text": "Cart"}
  assert expected_evidence["context"]["route"] == "/cart"
  assert expected_evidence["context"]["document_title"] == (
    "Cart | Brightlane Checkout"
  )
  assert variant["graph_context_needed"] == "helpful_not_required"


def test_registry_describes_address_totals_copied_shipping_details_label_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-118"]

  assert configurations["checkout-co-sem-118"]["status"] == "implemented"
  assert configurations["checkout-co-sem-118"]["seed_ids"] == ["co-sem-118"]
  assert variant["profile"] == "checkout-co-sem-118"
  assert variant["candidate_type"] == "landmark-purpose-mismatch"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S003"],
    "routes": ["/checkout/address"],
  }
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.address.orderTotals",
      "mutation_property": "accessible_name",
    }
  ]
  assert variant["expected_candidate"] == {
    "candidate_type": "landmark-purpose-mismatch",
    "selection_reason": "visible_landmark_with_role_and_context_evidence",
    "type": "landmark-purpose-mismatch",
    "selector_hint": '[data-testid="address-totals-region"]',
    "tag": "aside",
    "accessible_name": "Shipping details",
    "aria_label": "Shipping details",
  }
  expected_evidence = variant["expected_evidence"]
  assert expected_evidence["bucket"] == "landmarks"
  assert expected_evidence["selector_hint"] == (
    '[data-testid="address-totals-region"]'
  )
  assert expected_evidence["primary_evidence_key"] == "landmark"
  assert expected_evidence["attributes"] == {
    "tag": "aside",
    "accessible_name": "Shipping details",
    "aria_label": "Shipping details",
  }
  assert expected_evidence["attribute_contains"] == {"text": "Cart summary"}
  assert expected_evidence["context"]["route"] == "/checkout/address"
  assert expected_evidence["context"]["document_title"] == (
    "Shipping address | Brightlane Checkout"
  )
  assert expected_evidence["context"]["implicit_role"] == "complementary"
  assert variant["graph_context_needed"] == "not_required"


def test_registry_describes_generic_desk_lamp_image_alt_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-095"]

  assert configurations["checkout-co-sem-095"]["status"] == "implemented"
  assert configurations["checkout-co-sem-095"]["seed_ids"] == ["co-sem-095"]
  assert variant["profile"] == "checkout-co-sem-095"
  assert variant["candidate_type"] == "image-alt-not-descriptive"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S001"],
    "routes": ["/products"],
  }
  assert variant["mutation_targets"] == [
    {
      "mutation_property": "alt",
      "subject": "checkout.products.deskLamp.image",
    }
  ]
  assert variant["expected_candidate"] == {
    "selector_hint": '[data-testid="product-image-prod-desk-lamp"]',
    "candidate_type": "image-alt-not-descriptive",
    "selection_reason": "visible_image_with_text_alternative_and_context",
    "type": "image-alt-not-descriptive",
    "alt": "Image",
  }
  assert variant["expected_evidence"] == {
    "selector_hint": '[data-testid="product-image-prod-desk-lamp"]',
    "attributes": {"alt": "Image"},
    "bucket": "images",
  }
  assert variant["graph_context_needed"] == "not_required"


def test_registry_describes_reciprocal_product_image_alt_swap():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-097"]

  assert configurations["checkout-co-sem-097"]["status"] == "implemented"
  assert configurations["checkout-co-sem-097"]["seed_ids"] == ["co-sem-097"]
  assert variant["profile"] == "checkout-co-sem-097"
  assert variant["mutation_targets"] == [
    {
      "mutation_property": "alt",
      "subject": "checkout.products.deskLamp.image",
    },
    {
      "mutation_property": "alt",
      "subject": "checkout.products.notebookSet.image",
    },
  ]
  assert variant["expected_candidate"] == {
    "candidate_type": "image-alt-not-descriptive",
    "selection_reason": "visible_image_with_text_alternative_and_context",
    "type": "image-alt-not-descriptive",
  }
  assert variant["expected_evidence"] == {
    "all_of": [
      {
        "bucket": "images",
        "attributes": {
          "alt": "Three notebooks with blue, teal, and coral covers",
        },
        "attribute_contains": {"src": "/desk-lamp.svg"},
      },
      {
        "bucket": "images",
        "attributes": {"alt": "Desk lamp with adjustable brass shade"},
        "attribute_contains": {"src": "/notebook-set.svg"},
      },
    ]
  }
  serialized_contract = json.dumps(
    {
      "expected_candidate": variant["expected_candidate"],
      "expected_evidence": variant["expected_evidence"],
    }
  )
  for identity_only_value in (
    "selector_hint",
    "data-testid",
    "candidate_id",
    "checkout.products.deskLamp.image",
    "checkout.products.notebookSet.image",
    "nearest_heading",
  ):
    assert identity_only_value not in serialized_contract


def test_registry_describes_wrong_purpose_products_page_title_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-058"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-058"]["status"] == "implemented"
  assert configurations["checkout-co-sem-058"]["seed_ids"] == ["co-sem-058"]
  assert variant["profile"] == "checkout-co-sem-058"
  assert variant["candidate_type"] == "page-title-not-descriptive"
  assert variant["expected_state"]["benchmark_state_ids"] == ["CO-S001"]
  assert variant["expected_state"]["routes"] == ["/products"]
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.page.products",
      "mutation_property": "document_title",
    }
  ]
  assert expected_evidence["bucket"] == "page"
  assert "selector_hint" not in expected_evidence
  assert expected_evidence["attributes"] == {
    "title": "Payment | Brightlane Checkout"
  }
  assert expected_evidence["context"] == {
    "route": "/products",
    "expected_visible_heading": "Products",
    "expected_products_context": (
      "Featured products, product cards, and current cart summary are visible."
    ),
  }


def test_registry_describes_unrelated_products_page_title_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-059"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-059"]["status"] == "implemented"
  assert configurations["checkout-co-sem-059"]["seed_ids"] == ["co-sem-059"]
  assert variant["profile"] == "checkout-co-sem-059"
  assert variant["candidate_type"] == "page-title-not-descriptive"
  assert variant["expected_state"]["benchmark_state_ids"] == ["CO-S001"]
  assert variant["expected_state"]["routes"] == ["/products"]
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.page.products",
      "mutation_property": "document_title",
    }
  ]
  assert expected_evidence["bucket"] == "page"
  assert "selector_hint" not in expected_evidence
  assert expected_evidence["attributes"] == {
    "title": "Weather Forecast | Brightlane Checkout"
  }
  assert expected_evidence["context"] == {
    "route": "/products",
    "expected_visible_heading": "Products",
    "expected_products_context": (
      "Featured products, product cards, and current cart summary are visible."
    ),
  }


def test_registry_describes_stale_payment_page_title_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-060"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-060"]["status"] == "implemented"
  assert configurations["checkout-co-sem-060"]["seed_ids"] == ["co-sem-060"]
  assert variant["profile"] == "checkout-co-sem-060"
  assert variant["candidate_type"] == "page-title-not-descriptive"
  assert variant["expected_state"]["benchmark_state_ids"] == ["CO-S004"]
  assert variant["expected_state"]["routes"] == ["/checkout/payment"]
  assert variant["graph_context_needed"] == "helpful_not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.page.payment",
      "mutation_property": "document_title",
    }
  ]
  assert expected_evidence["bucket"] == "page"
  assert "selector_hint" not in expected_evidence
  assert expected_evidence["attributes"] == {
    "title": "Shipping address | Brightlane Checkout"
  }
  assert expected_evidence["context"] == {
    "route": "/checkout/payment",
    "expected_visible_heading": "Payment",
    "expected_payment_context": "Payment method form with card fields is visible.",
    "previous_state_title": "Shipping address | Brightlane Checkout",
  }


def test_registry_describes_cart_title_stale_on_address_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-119"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-119"]["status"] == "implemented"
  assert configurations["checkout-co-sem-119"]["seed_ids"] == ["co-sem-119"]
  assert variant["profile"] == "checkout-co-sem-119"
  assert variant["candidate_type"] == "page-title-not-descriptive"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S003"],
    "routes": ["/checkout/address"],
  }
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.page.address",
      "mutation_property": "document_title",
    }
  ]
  assert variant["expected_candidate"] == {
    "candidate_type": "page-title-not-descriptive",
    "selection_reason": "page_title_with_route_and_content_context",
    "type": "page-title-not-descriptive",
    "title": "Cart | Brightlane Checkout",
    "route": "/checkout/address",
    "primary_heading": "Shipping address",
  }
  assert expected_evidence["bucket"] == "page"
  assert expected_evidence["attributes"] == {
    "title": "Cart | Brightlane Checkout"
  }
  assert expected_evidence["context"] == {
    "route": "/checkout/address",
    "expected_visible_heading": "Shipping address",
    "expected_shipping_context": (
      "Shipping details form with shipping-address fields is visible."
    ),
    "expected_progress_state": "Shipping address is the current checkout step.",
    "previous_state_title": "Cart | Brightlane Checkout",
    "next_step_action": "Continue to payment",
  }


def test_registry_describes_related_wrong_address_page_title_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-120"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-120"]["status"] == "implemented"
  assert configurations["checkout-co-sem-120"]["seed_ids"] == ["co-sem-120"]
  assert variant["profile"] == "checkout-co-sem-120"
  assert variant["candidate_type"] == "page-title-not-descriptive"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S003"],
    "routes": ["/checkout/address"],
  }
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.page.address",
      "mutation_property": "document_title",
    }
  ]
  assert variant["expected_candidate"] == {
    "candidate_type": "page-title-not-descriptive",
    "selection_reason": "page_title_with_route_and_content_context",
    "type": "page-title-not-descriptive",
    "title": "Billing address | Brightlane Checkout",
    "route": "/checkout/address",
    "primary_heading": "Shipping address",
  }
  assert expected_evidence["bucket"] == "page"
  assert expected_evidence["attributes"] == {
    "title": "Billing address | Brightlane Checkout"
  }
  assert expected_evidence["context"] == {
    "route": "/checkout/address",
    "expected_visible_heading": "Shipping address",
    "expected_shipping_context": (
      "Shipping details form with shipping-address fields is visible."
    ),
    "expected_progress_state": "Shipping address is the current checkout step.",
    "next_step_action": "Continue to payment",
  }


def test_registry_describes_premature_review_page_title_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-121"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-121"]["status"] == "implemented"
  assert configurations["checkout-co-sem-121"]["seed_ids"] == ["co-sem-121"]
  assert variant["profile"] == "checkout-co-sem-121"
  assert variant["candidate_type"] == "page-title-not-descriptive"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S004"],
    "routes": ["/checkout/payment"],
  }
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.page.payment",
      "mutation_property": "document_title",
    }
  ]
  assert variant["expected_candidate"] == {
    "candidate_type": "page-title-not-descriptive",
    "selection_reason": "page_title_with_route_and_content_context",
    "type": "page-title-not-descriptive",
    "title": "Review | Brightlane Checkout",
    "route": "/checkout/payment",
    "primary_heading": "Payment",
  }
  assert expected_evidence["bucket"] == "page"
  assert expected_evidence["attributes"] == {
    "title": "Review | Brightlane Checkout"
  }
  assert expected_evidence["context"] == {
    "route": "/checkout/payment",
    "expected_visible_heading": "Payment",
    "expected_payment_context": "Payment method form with card fields is visible.",
    "expected_progress_state": "Payment is the current checkout step.",
    "next_step_action": "Continue to review",
  }


def test_registry_describes_city_autocomplete_state_purpose_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-122"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-122"]["status"] == "implemented"
  assert configurations["checkout-co-sem-122"]["seed_ids"] == ["co-sem-122"]
  assert variant["profile"] == "checkout-co-sem-122"
  assert variant["candidate_type"] == "autocomplete-purpose-mismatch"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S003"],
    "routes": ["/checkout/address"],
  }
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.address.city",
      "mutation_property": "autocomplete",
    }
  ]
  assert variant["expected_candidate"] == {
    "candidate_type": "autocomplete-purpose-mismatch",
    "selection_reason": "control_with_autocomplete_and_purpose_context",
    "type": "autocomplete-purpose-mismatch",
    "selector_hint": '[data-testid="address-city"]',
    "label": "City",
    "autocomplete": "address-level1",
  }
  assert expected_evidence["bucket"] == "form_controls"
  assert expected_evidence["selector_hint"] == '[data-testid="address-city"]'
  assert expected_evidence["control"] == {
    "id": "address-city",
    "name": "city",
  }
  assert expected_evidence["attributes"] == {
    "type": "text",
    "autocomplete": "address-level1",
  }
  assert expected_evidence["attribute_contains"] == {"label": "City"}
  assert expected_evidence["context"]["route"] == "/checkout/address"
  assert expected_evidence["context"]["document_title"] == (
    "Shipping address | Brightlane Checkout"
  )
  assert "address-state" in expected_evidence["context"]["purpose_evidence"]


def test_registry_describes_state_autocomplete_city_purpose_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-123"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-123"]["status"] == "implemented"
  assert configurations["checkout-co-sem-123"]["seed_ids"] == ["co-sem-123"]
  assert variant["profile"] == "checkout-co-sem-123"
  assert variant["candidate_type"] == "autocomplete-purpose-mismatch"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S003"],
    "routes": ["/checkout/address"],
  }
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.address.state",
      "mutation_property": "autocomplete",
    }
  ]
  assert variant["expected_candidate"] == {
    "candidate_type": "autocomplete-purpose-mismatch",
    "selection_reason": "control_with_autocomplete_and_purpose_context",
    "type": "autocomplete-purpose-mismatch",
    "selector_hint": '[data-testid="address-state"]',
    "label": "State",
    "autocomplete": "address-level2",
  }
  assert expected_evidence["bucket"] == "form_controls"
  assert expected_evidence["selector_hint"] == '[data-testid="address-state"]'
  assert expected_evidence["control"] == {
    "id": "address-state",
    "name": "state",
  }
  assert expected_evidence["attributes"] == {
    "type": "text",
    "autocomplete": "address-level2",
  }
  assert expected_evidence["attribute_contains"] == {"label": "State"}
  assert expected_evidence["context"]["route"] == "/checkout/address"
  assert expected_evidence["context"]["document_title"] == (
    "Shipping address | Brightlane Checkout"
  )
  assert "address-city" in expected_evidence["context"]["purpose_evidence"]


def test_registry_describes_shipping_street_billing_context_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-124"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-124"]["status"] == "implemented"
  assert configurations["checkout-co-sem-124"]["seed_ids"] == ["co-sem-124"]
  assert variant["profile"] == "checkout-co-sem-124"
  assert variant["candidate_type"] == "autocomplete-purpose-mismatch"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S003"],
    "routes": ["/checkout/address"],
  }
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.address.street",
      "mutation_property": "autocomplete",
    }
  ]
  assert variant["expected_candidate"] == {
    "candidate_type": "autocomplete-purpose-mismatch",
    "selection_reason": "control_with_autocomplete_and_purpose_context",
    "type": "autocomplete-purpose-mismatch",
    "selector_hint": '[data-testid="address-street"]',
    "label": "Street address",
    "autocomplete": "billing street-address",
  }
  assert expected_evidence["bucket"] == "form_controls"
  assert expected_evidence["selector_hint"] == '[data-testid="address-street"]'
  assert expected_evidence["control"] == {
    "id": "address-streetAddress",
    "name": "streetAddress",
  }
  assert expected_evidence["attributes"] == {
    "type": "text",
    "autocomplete": "billing street-address",
  }
  assert expected_evidence["attribute_contains"] == {"label": "Street address"}
  assert expected_evidence["context"]["route"] == "/checkout/address"
  assert expected_evidence["context"]["document_title"] == (
    "Shipping address | Brightlane Checkout"
  )
  assert expected_evidence["context"]["form_context"] == "Shipping details form."


def test_registry_describes_expiry_autocomplete_security_code_purpose_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-125"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-125"]["status"] == "implemented"
  assert configurations["checkout-co-sem-125"]["seed_ids"] == ["co-sem-125"]
  assert variant["profile"] == "checkout-co-sem-125"
  assert variant["candidate_type"] == "autocomplete-purpose-mismatch"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S004"],
    "routes": ["/checkout/payment"],
  }
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.payment.expiry",
      "mutation_property": "autocomplete",
    }
  ]
  assert variant["expected_candidate"] == {
    "candidate_type": "autocomplete-purpose-mismatch",
    "selection_reason": "control_with_autocomplete_and_purpose_context",
    "type": "autocomplete-purpose-mismatch",
    "selector_hint": '[data-testid="payment-expiry"]',
    "label": "Expiry",
    "autocomplete": "cc-csc",
  }
  assert expected_evidence["bucket"] == "form_controls"
  assert expected_evidence["selector_hint"] == '[data-testid="payment-expiry"]'
  assert expected_evidence["control"] == {
    "id": "payment-expiry",
    "name": "expiry",
  }
  assert expected_evidence["attributes"] == {
    "type": "text",
    "autocomplete": "cc-csc",
  }
  assert expected_evidence["attribute_contains"] == {"label": "Expiry"}
  assert expected_evidence["context"]["route"] == "/checkout/payment"
  assert expected_evidence["context"]["document_title"] == (
    "Payment | Brightlane Checkout"
  )
  assert "payment-security-code" in expected_evidence["context"][
    "purpose_evidence"
  ]


def test_registry_describes_country_select_autocomplete_state_purpose_case():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-126"]
  expected_evidence = variant["expected_evidence"]
  autocomplete_context = expected_evidence["candidate_evidence"]["supporting"][
    "autocomplete_purpose_context_v1"
  ]

  assert configurations["checkout-co-sem-126"]["status"] == "implemented"
  assert configurations["checkout-co-sem-126"]["seed_ids"] == ["co-sem-126"]
  assert variant["profile"] == "checkout-co-sem-126"
  assert variant["candidate_type"] == "autocomplete-purpose-mismatch"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S003"],
    "routes": ["/checkout/address"],
  }
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.address.country",
      "mutation_property": "autocomplete",
    }
  ]
  assert variant["expected_candidate"] == {
    "candidate_type": "autocomplete-purpose-mismatch",
    "selection_reason": "control_with_autocomplete_and_purpose_context",
    "type": "autocomplete-purpose-mismatch",
    "tag": "select",
    "label": "Country/region",
    "autocomplete": "address-level1",
  }
  assert "selector_hint" not in variant["expected_candidate"]
  assert expected_evidence["bucket"] == "form_controls"
  assert expected_evidence["control"] == {"name": "country"}
  assert expected_evidence["attributes"] == {
    "tag": "select",
    "autocomplete": "address-level1",
    "required": True,
    "has_value": True,
  }
  assert "selector_hint" not in expected_evidence
  assert "id" not in expected_evidence["control"]
  assert autocomplete_context["control"] == {
    "tag": "select",
    "name": "country",
    "autocomplete": "address-level1",
    "required": True,
    "value_state": "filled",
  }
  assert autocomplete_context["labeling"]["label_sources"] == [
    {
      "relationship_type": "labels",
      "method": "for",
      "text_segments": ["Country/region"],
    }
  ]
  assert autocomplete_context["autocomplete_evidence"] == {
    "raw_value": "address-level1",
    "tokens": ["address-level1"],
    "section_tokens": [],
    "context_tokens": [],
    "purpose_token": "address-level1",
    "recognized_purpose": "address administrative level 1",
    "token_category": "address",
    "is_known_token": True,
    "unknown_tokens": [],
  }


def test_registry_describes_zip_required_message_during_format_failure():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-134"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-134"]["status"] == "implemented"
  assert configurations["checkout-co-sem-134"]["seed_ids"] == ["co-sem-134"]
  assert variant["profile"] == "checkout-co-sem-134"
  assert variant["candidate_type"] == "error-message-mismatch"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S022"],
    "routes": ["/checkout/address"],
  }
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.address.postalCode",
      "mutation_property": "error_message_text",
    }
  ]
  assert expected_evidence["bucket"] == "form_controls"
  assert expected_evidence["selector_hint"] == '[data-testid="address-postal-code"]'
  form_control, error_message = expected_evidence["all_of"]
  assert form_control["control"] == {
    "id": "address-postalCode",
    "name": "postalCode",
  }
  assert form_control["attributes"]["has_value"] is True
  assert form_control["attributes"]["invalid"] is True
  assert form_control["attributes"]["native_validity"] == {
    "valid": False,
    "value_missing": False,
    "type_mismatch": False,
    "pattern_mismatch": True,
    "too_long": False,
    "too_short": False,
    "range_underflow": False,
    "range_overflow": False,
    "step_mismatch": False,
    "bad_input": False,
    "custom_error": False,
  }
  assert error_message == {
    "bucket": "referenced_elements",
    "attributes": {"text": "ZIP code is required."},
    "primary_evidence_key": "error_message",
  }


def test_registry_describes_stale_email_required_message_after_format_failure():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-135"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-135"]["status"] == "implemented"
  assert configurations["checkout-co-sem-135"]["seed_ids"] == ["co-sem-135"]
  assert variant["profile"] == "checkout-co-sem-135"
  assert variant["candidate_type"] == "error-message-mismatch"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S021"],
    "routes": ["/checkout/address"],
  }
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.address.email",
      "mutation_property": "error_message_text",
    }
  ]
  assert expected_evidence["bucket"] == "form_controls"
  assert expected_evidence["selector_hint"] == '[data-testid="address-email"]'
  form_control, error_message = expected_evidence["all_of"]
  assert form_control["control"] == {"id": "address-email", "name": "email"}
  assert form_control["attributes"]["has_value"] is True
  assert form_control["attributes"]["invalid"] is True
  assert form_control["attributes"]["native_validity"] == {
    "valid": False,
    "value_missing": False,
    "type_mismatch": True,
    "pattern_mismatch": True,
    "too_long": False,
    "too_short": False,
    "range_underflow": False,
    "range_overflow": False,
    "step_mismatch": False,
    "bad_input": False,
    "custom_error": False,
  }
  assert error_message == {
    "bucket": "referenced_elements",
    "attributes": {"text": "Email is required."},
    "primary_evidence_key": "error_message",
  }


def test_registry_describes_security_code_required_message_during_format_failure():
  registry = _read_json(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {variant["variant_id"]: variant for variant in registry["variants"]}

  variant = variants["co-sem-136"]
  expected_evidence = variant["expected_evidence"]

  assert configurations["checkout-co-sem-136"]["status"] == "implemented"
  assert configurations["checkout-co-sem-136"]["seed_ids"] == ["co-sem-136"]
  assert variant["profile"] == "checkout-co-sem-136"
  assert variant["candidate_type"] == "error-message-mismatch"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["CO-S023"],
    "routes": ["/checkout/payment"],
  }
  assert variant["graph_context_needed"] == "not_required"
  assert variant["mutation_targets"] == [
    {
      "subject": "checkout.payment.securityCode",
      "mutation_property": "error_message_text",
    }
  ]
  assert expected_evidence["bucket"] == "form_controls"
  assert expected_evidence["selector_hint"] == '[data-testid="payment-security-code"]'
  form_control, error_message = expected_evidence["all_of"]
  assert form_control["control"] == {
    "id": "payment-securityCode",
    "name": "securityCode",
  }
  assert form_control["attributes"]["has_value"] is True
  assert form_control["attributes"]["invalid"] is True
  assert form_control["attributes"]["native_validity"] == {
    "valid": False,
    "value_missing": False,
    "type_mismatch": False,
    "pattern_mismatch": True,
    "too_long": False,
    "too_short": False,
    "range_underflow": False,
    "range_overflow": False,
    "step_mismatch": False,
    "bad_input": False,
    "custom_error": False,
  }
  assert error_message == {
    "bucket": "referenced_elements",
    "attributes": {"text": "Security code is required."},
    "primary_evidence_key": "error_message",
  }


def test_dataset_manifest_has_no_accepted_batches_or_cases():
  manifest = _read_json(MANIFEST)

  assert manifest["dataset_id"] == "accessgraph-controlled-local-spa-benchmark"
  assert manifest["version"] == "0.0.0"
  assert manifest["registry_path"] == "benchmarks/registry/benchmark-case-registry.json"
  assert isinstance(manifest["accepted_batches"], list)
  assert manifest["accepted_batches"] == []
  accepted_membership = json.dumps(manifest["accepted_batches"])
  assert PILOT_PROFILE_ID not in accepted_membership
  for profile_id, expected_case in IMPLEMENTED_DATASET_CASES.items():
    assert profile_id not in accepted_membership
    for seed_id in expected_case["seed_ids"]:
      assert seed_id not in accepted_membership


def test_case_tracker_has_minimal_stable_contract():
  header, rows = _read_tracker_rows()
  case_ids = [row["case_id"].strip() for row in rows if row.get("case_id", "").strip()]

  assert header == CASE_TRACKER_HEADER
  assert not (FORBIDDEN_TRACKER_ID_FIELDS & set(header))
  for row in rows:
    assert None not in row
    assert set(row) == set(CASE_TRACKER_HEADER)
    assert row["tier"].strip() in CASE_TRACKER_TIERS
    assert row["evidence_state"].strip() in CASE_TRACKER_EVIDENCE_STATES
  assert len(case_ids) == len(set(case_ids))
  assert {
    row["status"].strip()
    for row in rows
    if row.get("status", "").strip()
  } <= CASE_TRACKER_STATUSES


def test_runtime_source_does_not_depend_on_thesis_seed_machinery():
  source_text = _runtime_source_text()

  for forbidden in (
    "ex" + "p-",
    "EX" + "P-",
    "expand" + "ed-local-spas",
    "Expand" + "edLocalSpas",
    "landmark" + "-structural-violation",
    "reviewContent" + "NestedMain",
    "co-ctrl-",
    "checkout-evaluation-v1",
    "checkout-semantic-eval",
    "semanticVariants",
    "data-active-seed-count",
  ):
    assert forbidden not in source_text


def test_runner_profile_global_matches_spa_profile_contract():
  payload = _node_payload()
  runner_text = RUNNER.read_text(encoding="utf-8")
  match = re.search(r'CHECKOUT_PROFILE_GLOBAL = "([^"]+)"', runner_text)

  assert match
  assert match.group(1) == payload["profileGlobal"]
  assert "choices=" not in runner_text


def test_runner_uses_standalone_state_namespace_without_ground_truth_fields():
  runner_text = RUNNER.read_text(encoding="utf-8")

  for state_id in (
    "CO-S001",
    "CO-S002",
    "CO-S003",
    "CO-S004",
    "CO-S005",
    "CO-S007",
    "CO-S011",
    "CO-S012",
    "CO-S013",
    "CO-S014",
    "CO-S015",
    "CO-S016",
    "CO-S017",
    "CO-S021",
    "CO-S022",
    "CO-S023",
  ):
    assert state_id in runner_text

  for forbidden in (
    "EX" + "P-",
    "expected_candidate",
    "expected_evidence",
    "expected_human_judgment",
  ):
    assert forbidden not in runner_text
